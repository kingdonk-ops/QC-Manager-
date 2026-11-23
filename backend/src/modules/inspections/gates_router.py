"""Quality gates: list, create, read, edit, delete, release, waive, void and the can-proceed query. Included by the
main inspections router before the integer-id routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import eligibility, gates
from .constants import AttachmentKind, GateKind, GateStatus
from .gate_schemas import GateCreate, GateProceed, GateRelease, GateUpdate, GateWaive, QualityGateRead
from .models import QualityGate
from .permissions import InspectionPermissionName as P

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
UPDATE = [require_permissions(P.UPDATE.value)]
APPROVE = [require_permissions(P.APPROVE.value)]
DELETE = [require_permissions(P.DELETE.value)]


async def _readable(db: Any, gate_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False) -> QualityGate:
    """The gate once the caller may see its project. ``lock`` re-reads it under a row lock, so two concurrent decisions
    on one gate (release against waive, release against release) run one after the other and the second finds the
    gate no longer pending."""
    gate = await gates.get_gate(db, gate_id)
    await readable_project(db, gate.project_id, user["id"], held)
    if lock:
        await db.refresh(gate, with_for_update=True)
    return gate


@router.get(
    "/gates/",
    response_model=PaginatedListResponse[QualityGateRead],
    summary="List Quality Gates",
    description="A project's gates, newest first, with their release and waiver details. Filter by status, kind and "
    "attachment target, or by inspection to get every gate attached to or linked to that record.",
    dependencies=READ,
)
async def list_gates(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    status: GateStatus | None = None,
    kind: GateKind | None = None,
    attachment_kind: AttachmentKind | None = None,
    attachment_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    inspection_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [QualityGate.project_id == project_id]
    if inspection_id:
        where.append(gates.inspection_gate_match(inspection_id))
    if status:
        where.append(QualityGate.status == status.value)
    if kind:
        where.append(QualityGate.kind == kind.value)
    if attachment_kind:
        where.append(QualityGate.attachment_kind == attachment_kind.value)
    if attachment_id:
        where.append(QualityGate.attachment_id == attachment_id)
    total = await db.scalar(select(func.count()).select_from(QualityGate).where(*where))
    rows = (
        await db.execute(
            select(QualityGate)
            .where(*where)
            .order_by(QualityGate.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {
        "data": [QualityGateRead.model_validate(g).model_dump(mode="json") for g in rows],
        "total_count": total or 0,
    }
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/gates/",
    response_model=QualityGateRead,
    status_code=201,
    summary="Create a Quality Gate",
    description="Starts pending. The blocking flag defaults from the kind (a hold blocks, the others do not). The "
    "attachment kind and identifier come together or not at all. A linked inspection (any record of the register, ITP "
    "lines included), a criterion and the attachment target must belong to the project.",
    dependencies=UPDATE,
)
async def create_gate(values: GateCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    return await gates.create_gate(db, values.model_dump(mode="json"), user["id"])


# Fixed path before /gates/{gate_id}.
@router.get(
    "/gates/can-proceed",
    response_model=GateProceed,
    summary="May Work Proceed on this Entity?",
    description="Advisory and read-only. Blocking gates are those attached to the entity with the blocking flag on "
    "and status pending, oldest first (for an inspection, a gate that links the record counts too). For an inspection "
    "the answer also lists the earlier ITP hold points that are "
    "unreleased, and is false when either list is not empty.",
    dependencies=READ,
)
async def can_proceed(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    attachment_kind: AttachmentKind,
    attachment_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await eligibility.can_proceed(db, project_id, attachment_kind.value, attachment_id)


@router.get("/gates/{gate_id}", response_model=QualityGateRead, summary="Get a Quality Gate", dependencies=READ)
async def get_gate(gate_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _readable(db, gate_id, user, held)


@router.patch(
    "/gates/{gate_id}",
    response_model=QualityGateRead,
    summary="Edit a Pending Quality Gate",
    description="Only a pending gate changes, and its status never changes by edit; released, waived and void gates "
    "are refused.",
    dependencies=UPDATE,
)
async def update_gate(
    gate_id: Id, values: GateUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    gate = await _readable(db, gate_id, user, held, lock=True)
    await gates.update_gate(db, gate, values.model_dump(mode="json", exclude_unset=True))
    return gate


@router.delete(
    "/gates/{gate_id}",
    summary="Delete a Pending Quality Gate",
    description="Released, waived and void gates carry the decision that let work proceed and are refused.",
    dependencies=DELETE,
)
async def delete_gate(gate_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await gates.delete_gate(db, await _readable(db, gate_id, user, held, lock=True))
    return {"message": "Gate deleted"}


@router.post(
    "/gates/{gate_id}/release",
    response_model=QualityGateRead,
    summary="Release a Quality Gate",
    description="The releasing party asserts an authority level, which must be equal to or higher than the gate's "
    "requirement (otherwise forbidden). A linked inspection must have passed. Stores the user, asserted level, time, "
    "justification, network address and a digest, and announces the release after the commit.",
    dependencies=APPROVE,
)
async def release_gate(
    gate_id: Id,
    values: GateRelease,
    request: Request,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    gate = await _readable(db, gate_id, user, held, lock=True)
    return await gates.release_gate(
        db,
        gate,
        user_id=user["id"],
        level=values.authority.value,
        justification=values.justification,
        released_at=values.released_at,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/gates/{gate_id}/waive",
    response_model=QualityGateRead,
    summary="Waive a Quality Gate",
    description="Witness, surveillance and review gates only; a hold is a conflict. A reason is required. No "
    "authority level is compared and no digest is stored.",
    dependencies=APPROVE,
)
async def waive_gate(
    gate_id: Id, values: GateWaive, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    gate = await _readable(db, gate_id, user, held, lock=True)
    return await gates.waive_gate(db, gate, user_id=user["id"], reason=values.reason)


@router.post(
    "/gates/{gate_id}/void",
    response_model=QualityGateRead,
    summary="Void a Quality Gate",
    description="A pending gate that no longer applies. Decided gates are refused.",
    dependencies=APPROVE,
)
async def void_gate(gate_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    gate = await _readable(db, gate_id, user, held, lock=True)
    return await gates.void_gate(db, gate, user_id=user["id"])

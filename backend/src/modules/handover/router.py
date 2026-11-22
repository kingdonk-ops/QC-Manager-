"""Mounted at /api/v1/handover."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import ITEM_STATUSES, HandoverStatus
from .models import Handover
from .permissions import HandoverPermissionName as P
from .schemas import HandoverCreate, HandoverItemStatuses, HandoverNoteIn, HandoverRead, HandoverUpdate

router = APIRouter(tags=["Shift Handover"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _get(db: Any, handover_id: int, user: dict, held: frozenset[str]) -> Handover:
    h = await service.get(db, handover_id)
    await readable_project(db, h.project_id, user["id"], held)
    return h


async def _one(db: Any, h: Handover) -> dict[str, Any]:
    return (await service.read(db, [h], detail=True))[0]


def _items(values: Any) -> list[dict[str, Any]] | None:
    return None if values.items is None else [i.model_dump(mode="python") for i in values.items]


@router.get("/item-statuses", response_model=HandoverItemStatuses, summary="Statuses per Item Kind", dependencies=perm(P.READ))
async def item_statuses(_: CurrentUserDep) -> Any:
    return {"statuses": {k: list(v) for k, v in ITEM_STATUSES.items()}}


@router.get(
    "/handovers/",
    response_model=PaginatedListResponse[HandoverRead],
    summary="The Handover Register",
    description="`mine=to`: addressed to you; `mine=from`: yours; `unacknowledged=true`: still waiting.",
    dependencies=perm(P.READ),
)
async def list_handovers(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    status: HandoverStatus | None = None,
    area_node_id: Annotated[int | None, Query(ge=1)] = None,
    mine: Annotated[str | None, Query(pattern=r"^(to|from)$")] = None,
    unacknowledged: bool = False,
    start: date | None = None,
    end: date | None = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Handover.project_id == project_id]
    if status:
        where.append(Handover.status == status.value)
    if area_node_id:
        where.append(Handover.area_node_id == area_node_id)
    if mine == "to":
        where.append(Handover.recipient_id == user["id"])
    elif mine == "from":
        where.append(Handover.author_id == user["id"])
    if unacknowledged:
        where.append(Handover.status == HandoverStatus.SUBMITTED)
    if start:
        where.append(Handover.shift_date >= start)
    if end:
        where.append(Handover.shift_date <= end)
    total = await db.scalar(select(func.count()).select_from(Handover).where(*where))
    rows = (
        await db.execute(
            select(Handover)
            .where(*where)
            .order_by(Handover.shift_date.desc(), Handover.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/handovers/",
    response_model=HandoverRead,
    status_code=201,
    summary="Start a Handover",
    description="With `carry_forward`, items still open in the area's last handover come across. Work in progress "
    "needs a node with a work anchor on its path (422 `NoWorkAnchor`).",
    dependencies=perm(P.CREATE),
)
async def create(values: HandoverCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    data = values.model_dump(mode="python")
    data["items"] = _items(values) or []
    h = await service.create(db, data, user["id"])
    await db.commit()
    return await _one(db, h)


@router.get("/handovers/{handover_id}", response_model=HandoverRead, summary="Get a Handover", dependencies=perm(P.READ))
async def get(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _get(db, handover_id, user, held))


@router.put("/handovers/{handover_id}", response_model=HandoverRead, summary="Save a Draft", dependencies=perm(P.UPDATE))
async def save(
    handover_id: Id, values: HandoverUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    h = await _get(db, handover_id, user, held)
    data = values.model_dump(mode="python", exclude_unset=True)
    if "items" in data:
        data["items"] = _items(values)
    await service.update(db, h, data, user["id"])
    await db.commit()
    return await _one(db, h)


@router.post(
    "/handovers/{handover_id}/submit",
    response_model=HandoverRead,
    summary="Hand Over",
    description="Notifies the incoming supervisor; reminders follow until they acknowledge.",
    dependencies=perm(P.SUBMIT),
)
async def submit(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    h = await _get(db, handover_id, user, held)
    await service.submit(db, h, user["id"])
    await db.commit()
    return await _one(db, h)


@router.post(
    "/handovers/{handover_id}/recall",
    response_model=HandoverRead,
    summary="Recall Before Acknowledgement",
    dependencies=perm(P.SUBMIT),
)
async def recall(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    h = await _get(db, handover_id, user, held)
    await service.recall(db, h, user["id"])
    await db.commit()
    return await _one(db, h)


@router.post(
    "/handovers/{handover_id}/acknowledge",
    response_model=HandoverRead,
    summary="Acknowledge (Incoming Supervisor)",
    description="Only the named recipient; records the time and an optional note, and tells the author.",
    dependencies=perm(P.RESPOND),
)
async def acknowledge(
    handover_id: Id, values: HandoverNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    h = await _get(db, handover_id, user, held)
    await service.acknowledge(db, h, user["id"], values.note)
    await db.commit()
    return await _one(db, h)


@router.get("/handovers/{handover_id}/history", summary="A Handover's Status History", dependencies=perm(P.READ))
async def history(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    h = await _get(db, handover_id, user, held)
    return await history_of(db, "handover", h.id)


@router.get("/handovers/{handover_id}/pdf", summary="Handover (PDF)", dependencies=perm(P.EXPORT))
async def pdf(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    h = await _get(db, handover_id, user, held)
    body = await service.pdf(db, h)
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{h.code}.pdf"'})


@router.delete("/handovers/{handover_id}", summary="Delete a Draft", dependencies=perm(P.DELETE))
async def delete(handover_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    h = await _get(db, handover_id, user, held)
    if h.status != HandoverStatus.DRAFT:
        raise service.HandoverRuleError("Only a draft handover can be deleted; handed-over ones stay in the register.")
    if h.author_id != user["id"]:
        raise service.NotAuthor()
    await db.delete(h)
    await db.commit()
    return {"message": "Handover deleted"}

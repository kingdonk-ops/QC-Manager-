"""Mounted at /api/v1/ncr. Every route reads the NCR's project through ``projects``' visibility rule first."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import NcrStatus, Severity, Source
from .models import Ncr, NcrAction
from .permissions import NcrPermissionName as P
from .schemas import NcrActionCreate, NcrActionUpdate, NcrCreate, NcrRead, NcrStatusChange, NcrUpdate

router = APIRouter(tags=["Non-Conformance Reports"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _readable(db: Any, ncr_id: int, user: dict[str, Any], held: frozenset[str]) -> Ncr:
    ncr = await service.get_ncr(db, ncr_id)
    await readable_project(db, ncr.project_id, user["id"], held)
    return ncr


async def _one(db: Any, ncr: Ncr) -> dict[str, Any]:
    return (await service.read_ncrs(db, [ncr], with_actions=True))[0]


@router.get(
    "/",
    response_model=PaginatedListResponse[NcrRead],
    summary="List NCRs",
    description="A project's NCRs, newest first. Filter by status, severity, source, trade, `open_only`, or search text.",
    dependencies=perm(P.READ),
)
async def list_ncrs(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    status: NcrStatus | None = None,
    severity: Severity | None = None,
    source: Source | None = None,
    trade: Annotated[str | None, Query(max_length=100)] = None,
    open_only: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = service.filters(
        project_id,
        status.value if status else None,
        severity.value if severity else None,
        source.value if source else None,
        trade,
        open_only,
        search,
    )
    total = await db.scalar(select(func.count()).select_from(Ncr).where(*where))
    rows = (
        await db.execute(
            select(Ncr).where(*where).order_by(Ncr.id.desc()).offset(compute_offset(page, items_per_page)).limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_ncrs(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=NcrRead, status_code=201, summary="Raise an NCR", dependencies=perm(P.CREATE))
async def create(values: NcrCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    fields = values.model_dump(exclude={"project_id", "title"})
    ncr = await service.create_ncr(db, project_id=values.project_id, title=values.title, raised_by_id=user["id"], **fields)
    return await _one(db, ncr)


@router.get(
    "/export",
    summary="Export the NCR Register",
    description="The filtered register as Excel (`format=xlsx`, default) or CSV.",
    dependencies=perm(P.EXPORT),
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    format: Literal["xlsx", "csv"] = "xlsx",
    status: NcrStatus | None = None,
    severity: Severity | None = None,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    where = service.filters(project_id, status.value if status else None, severity.value if severity else None)
    rows = await service.export_rows(db, where)
    body, media_type, ext = write_table(service.EXPORT_COLUMNS, rows, format, title="NCR register")
    name = f"ncr-register-{project.code}.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{ncr_id}", response_model=NcrRead, summary="Get an NCR, with its Actions", dependencies=perm(P.READ))
async def get(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _readable(db, ncr_id, user, held))


@router.patch(
    "/{ncr_id}",
    response_model=NcrRead,
    summary="Update an NCR",
    description="Details, root cause, disposition and cost impact. Send only the fields that change.",
    dependencies=perm(P.UPDATE),
)
async def update(ncr_id: Id, values: NcrUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    before = ncr.responsible_user_id
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(ncr, key, value.value if hasattr(value, "value") else value)
    if ncr.responsible_user_id and ncr.responsible_user_id != before:
        await service.notify_responsible(db, ncr, user["id"])
    await db.commit()
    return await _one(db, ncr)


@router.delete("/{ncr_id}", summary="Delete an NCR", dependencies=perm(P.DELETE))
async def delete(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _readable(db, ncr_id, user, held))
    await db.commit()
    return {"message": "NCR deleted"}


@router.patch(
    "/{ncr_id}/status",
    response_model=NcrRead,
    summary="Move an NCR Through its Lifecycle",
    description=(
        "open → under_investigation → corrective_action_planned → corrective_action_taken → verified → closed. "
        "A failed verification goes back from verified to corrective_action_planned. Anything else answers 422."
    ),
    dependencies=perm(P.TRANSITION),
)
async def set_status(
    ncr_id: Id, values: NcrStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    await service.change_status(db, ncr, values.status.value, values.note, user["id"])
    return await _one(db, ncr)


@router.get("/{ncr_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    return await service.history(db, await _readable(db, ncr_id, user, held))


@router.get("/{ncr_id}/report.pdf", summary="NCR Report (PDF)", dependencies=perm(P.READ))
async def report(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    ncr = await _readable(db, ncr_id, user, held)
    pdf = await service.report_pdf(db, ncr)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{ncr.code}.pdf"'})


@router.post(
    "/{ncr_id}/actions",
    response_model=NcrRead,
    status_code=201,
    summary="Add a Corrective or Preventive Action",
    description="The responsible user is notified.",
    dependencies=perm(P.UPDATE),
)
async def add_action(
    ncr_id: Id, values: NcrActionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    action = NcrAction(ncr_id=ncr.id, **{k: (v.value if hasattr(v, "value") else v) for k, v in values.model_dump().items()})
    db.add(action)
    await db.flush()
    await service.notify_action(db, ncr, action, user["id"])
    await db.commit()
    return await _one(db, ncr)


@router.patch(
    "/{ncr_id}/actions/{action_id}",
    response_model=NcrRead,
    summary="Update an Action",
    description="Setting `status` to `verified` records the caller as verifier, with the time.",
    dependencies=perm(P.UPDATE),
)
async def update_action(
    ncr_id: Id, action_id: Id, values: NcrActionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    action = await service.get_action(db, ncr, action_id)
    await service.update_action(db, ncr, action, values.model_dump(exclude_unset=True), user["id"])
    return await _one(db, ncr)


@router.delete("/{ncr_id}/actions/{action_id}", response_model=NcrRead, summary="Remove an Action", dependencies=perm(P.UPDATE))
async def delete_action(
    ncr_id: Id, action_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    await db.delete(await service.get_action(db, ncr, action_id))
    await db.commit()
    return await _one(db, ncr)

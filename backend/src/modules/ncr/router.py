"""Mounted at /api/v1/ncr (the original NCR routes, now over the issues engine) and /api/v1/issues
(``issues_router``, in ``issues_api``). Every route reads the issue's project through ``projects``' visibility
rule first; internal issues answer 404 to external (portal) callers."""

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
from .constants import IssueType, NcrStatus, Severity, Source
from .issues_api import issues_router
from .models import Ncr, NcrAction
from .permissions import NcrPermissionName as P
from .schemas import IssueUpdate, NcrActionCreate, NcrActionUpdate, NcrCreate, NcrRead, NcrStatusChange

router = APIRouter(tags=["Non-Conformance Reports"])

__all__ = ["issues_router", "router"]

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _readable(db: Any, ncr_id: int, user: dict[str, Any], held: frozenset[str]) -> Ncr:
    return await service.readable_issue(db, ncr_id, user, held)


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
    external = service.is_external(user, held)
    where = service.filters(
        project_id,
        status.value if status else None,
        severity.value if severity else None,
        source.value if source else None,
        trade,
        open_only,
        search,
        issue_type=IssueType.NCR.value,
        external=external,
    )
    total = await db.scalar(select(func.count()).select_from(Ncr).where(*where))
    rows = list(
        (
            await db.execute(
                select(Ncr)
                .where(*where)
                .order_by(Ncr.id.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await service.read_ncrs(db, rows, external=external), "total_count": total or 0}
    if external:
        await service.mark_client_seen(db, [r.id for r in rows], "api")
        await db.commit()
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=NcrRead, status_code=201, summary="Raise an NCR", dependencies=perm(P.CREATE))
async def create(values: NcrCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    fields = values.model_dump(exclude={"project_id", "title"})
    ncr = await service.create_issue(
        db,
        project_id=values.project_id,
        title=values.title,
        raised_by_id=user["id"],
        issue_type=IssueType.NCR,
        external=service.is_external(user, held),
        **fields,
    )
    return await service.read_one(db, ncr, user, held)


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
    external = service.is_external(user, held)
    where = service.filters(
        project_id,
        status.value if status else None,
        severity.value if severity else None,
        issue_type=IssueType.NCR.value,
        external=external,
    )
    rows = await service.export_rows(db, where, external=external)
    await db.commit()
    body, media_type, ext = write_table(service.EXPORT_COLUMNS, rows, format, title="NCR register")
    name = f"ncr-register-{project.code}.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{ncr_id}", response_model=NcrRead, summary="Get an NCR, with its Actions", dependencies=perm(P.READ))
async def get(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.read_one(db, await _readable(db, ncr_id, user, held), user, held)


@router.patch(
    "/{ncr_id}",
    response_model=NcrRead,
    summary="Update an NCR",
    description="Details, template answers, root cause, disposition and cost impact. Send only the fields that change. "
    "Disposition and root cause are read-only once their step is completed.",
    dependencies=perm(P.UPDATE),
)
async def update(
    ncr_id: Id, values: IssueUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    await service.update_issue(db, ncr, values.model_dump(exclude_unset=True), user["id"])
    return await service.read_one(db, ncr, user, held)


@router.delete(
    "/{ncr_id}",
    summary="Delete an NCR",
    description="Removes the record and its number. Prefer voiding (`/issues/{id}/void`), which keeps both.",
    dependencies=perm(P.DELETE),
)
async def delete(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _readable(db, ncr_id, user, held))
    await db.commit()
    return {"message": "NCR deleted"}


@router.patch(
    "/{ncr_id}/status",
    response_model=NcrRead,
    summary="Move an NCR Through its Workflow",
    description=(
        "open (containment) → disposition → root_cause → corrective_action → effectiveness → closed. An ineffective "
        "verification goes back from effectiveness to corrective_action (with a note). Closing is the effectiveness "
        "sign-off: nobody who recorded the disposition or completed a corrective action may do it. "
        "Punch items: open → rectified → verified (→ closed). Anything else answers 422."
    ),
    dependencies=perm(P.READ),
)
async def set_status(
    ncr_id: Id, values: NcrStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    await service.change_status(db, ncr, values.status.value, values.note, user, held)
    return await service.read_one(db, ncr, user, held)


@router.get("/{ncr_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    return await service.history(db, await _readable(db, ncr_id, user, held))


@router.get("/{ncr_id}/report.pdf", summary="NCR Report (PDF)", dependencies=perm(P.READ))
async def report(ncr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    ncr = await _readable(db, ncr_id, user, held)
    pdf = await service.report_pdf(db, ncr)
    if service.is_external(user, held):
        await service.mark_client_seen(db, [ncr.id], "pdf_export")
        await db.commit()
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
    return await service.read_one(db, ncr, user, held)


@router.patch(
    "/{ncr_id}/actions/{action_id}",
    response_model=NcrRead,
    summary="Update an Action",
    description="`done` records the caller as completer, `verified` as verifier (with the time); "
    "`cancelled` needs a `cancel_reason`.",
    dependencies=perm(P.UPDATE),
)
async def update_action(
    ncr_id: Id, action_id: Id, values: NcrActionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    action = await service.get_action(db, ncr, action_id)
    await service.update_action(db, ncr, action, values.model_dump(exclude_unset=True), user["id"])
    return await service.read_one(db, ncr, user, held)


@router.delete("/{ncr_id}/actions/{action_id}", response_model=NcrRead, summary="Remove an Action", dependencies=perm(P.UPDATE))
async def delete_action(
    ncr_id: Id, action_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    ncr = await _readable(db, ncr_id, user, held)
    await db.delete(await service.get_action(db, ncr, action_id))
    await db.commit()
    return await service.read_one(db, ncr, user, held)

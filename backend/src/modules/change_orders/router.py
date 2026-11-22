"""Mounted at /api/v1/change-orders."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.exceptions import PermissionDeniedError
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.models import Project
from ..projects.service import readable_project
from . import service
from .constants import DECISIONS, Reason
from .models import ChangeOrder
from .permissions import ChangeOrderPermissionName as P
from .schemas import (
    ChangeLogSummary,
    ChangeOrderCreate,
    ChangeOrderDetail,
    ChangeOrderRead,
    ChangeOrderUpdate,
    CoHistoryEntry,
    CoLineCreate,
    CoLineRead,
    CoLineUpdate,
    CoStatusChange,
)

router = APIRouter(tags=["Change Orders"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


class ApproverOnlyError(PermissionDeniedError):
    public_detail = "Only approvers can review, approve or reject a change order."


class SubmitterOnlyError(PermissionDeniedError):
    public_detail = "You need permission to submit change orders."


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _download(body: bytes, media_type: str, name: str) -> Response:
    return Response(body, media_type=media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


async def _order(db: AsyncSession, co_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[ChangeOrder, Project]:
    co = await service.get_order(db, co_id)
    project = await readable_project(db, co.project_id, user["id"], held)
    return co, project


@router.get(
    "/",
    response_model=PaginatedListResponse[ChangeOrderRead],
    summary="List Change Orders",
    description="`status=pending` lists submitted and under-review change orders together.",
    dependencies=perm(P.READ),
)
async def list_change_orders(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: Annotated[
        str | None, Query(pattern=r"^(pending|draft|submitted|under_review|approved|rejected|withdrawn)$")
    ] = None,
    reason: Reason | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    where = service.filters(project_id, status, reason.value if reason else None, search)
    total = await db.scalar(select(func.count()).select_from(ChangeOrder).where(*where))
    rows = (
        await db.execute(
            select(ChangeOrder)
            .where(*where)
            .order_by(ChangeOrder.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_orders(db, list(rows), project.currency), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/", response_model=ChangeOrderDetail, status_code=201, summary="Raise a Change Order", dependencies=perm(P.CREATE)
)
async def create_change_order(
    values: ChangeOrderCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    co = await service.create(db, values.model_dump(), user["id"])
    return await service.detail(db, co, project.currency)


@router.get(
    "/summary",
    response_model=ChangeLogSummary,
    summary="The Project's Change Log Totals",
    description="Approved, pending (submitted or under review), rejected, draft and withdrawn totals.",
    dependencies=perm(P.READ),
)
async def summary(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.summary(db, project)


@router.get("/export", summary="Export the Change Log", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    rows = (
        await db.execute(select(ChangeOrder).where(ChangeOrder.project_id == project_id).order_by(ChangeOrder.id))
    ).scalars()
    data = await service.read_orders(db, list(rows), project.currency, mode="python")
    body, media_type, ext = write_table(service.EXPORT_COLUMNS, data, format, title="Change log")
    return _download(body, media_type, f"{project.code}-change-log.{ext}")


@router.get("/{co_id}", response_model=ChangeOrderDetail, summary="Get a Change Order", dependencies=perm(P.READ))
async def get_change_order(co_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    co, project = await _order(db, co_id, user, held)
    return await service.detail(db, co, project.currency)


@router.patch(
    "/{co_id}",
    response_model=ChangeOrderDetail,
    summary="Update a Change Order",
    description="Only while it's a draft.",
    dependencies=perm(P.UPDATE),
)
async def update_change_order(
    co_id: Id, values: ChangeOrderUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    co, project = await _order(db, co_id, user, held)
    await service.update(db, co, values.model_dump(exclude_unset=True))
    return await service.detail(db, co, project.currency)


@router.delete(
    "/{co_id}",
    summary="Delete a Change Order",
    description="Not once it's submitted, under review or approved.",
    dependencies=perm(P.DELETE),
)
async def delete_change_order(
    co_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    co, _ = await _order(db, co_id, user, held)
    await service.delete(db, co)
    return {"message": "Change order deleted"}


@router.patch(
    "/{co_id}/status",
    response_model=ChangeOrderDetail,
    summary="Move a Change Order Through Approval",
    description="Submitting and withdrawing need `change_orders.submit`; review, approval and rejection need "
    "`change_orders.approve`. Approval applies the line deltas to linked CVR cost heads when `cvr_apply` says so.",
    dependencies=perm(P.READ),
)
async def change_status(
    co_id: Id, values: CoStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    co, project = await _order(db, co_id, user, held)
    if values.status in DECISIONS:
        if P.APPROVE.value not in held:
            raise ApproverOnlyError(values.status.value)
    elif P.SUBMIT.value not in held:
        raise SubmitterOnlyError(values.status.value)
    await service.transition(db, co, values.status.value, user["id"], values.comment)
    return await service.detail(db, co, project.currency)


@router.get(
    "/{co_id}/history",
    response_model=list[CoHistoryEntry],
    summary="A Change Order's Status History",
    dependencies=perm(P.READ),
)
async def history(co_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    co, _ = await _order(db, co_id, user, held)
    return await history_of(db, service.ENTITY, co.id)


@router.get("/{co_id}/pdf", summary="The Change Order as a PDF", dependencies=perm(P.READ))
async def change_order_pdf(co_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    co, project = await _order(db, co_id, user, held)
    body = await service.pdf(db, co, project)
    return Response(
        body,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(f'{project.code}-{co.code}.pdf')}"},
    )


# --- lines ----------------------------------------------------------------------------------------------


@router.get("/{co_id}/lines", response_model=list[CoLineRead], summary="A Change Order's Lines", dependencies=perm(P.READ))
async def list_lines(co_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    co, _ = await _order(db, co_id, user, held)
    return await service.lines_of(db, co.id)


@router.post("/{co_id}/lines", response_model=CoLineRead, status_code=201, summary="Add a Line", dependencies=perm(P.UPDATE))
async def add_line(
    co_id: Id, values: CoLineCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    co, _ = await _order(db, co_id, user, held)
    return await service.add_line(db, co, values.model_dump())


@router.patch("/{co_id}/lines/{line_id}", response_model=CoLineRead, summary="Change a Line", dependencies=perm(P.UPDATE))
async def update_line(
    co_id: Id, line_id: Id, values: CoLineUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    co, _ = await _order(db, co_id, user, held)
    line = await service.get_line(db, co, line_id)
    await service.update_line(db, co, line, values.model_dump(exclude_unset=True))
    return line


@router.delete("/{co_id}/lines/{line_id}", summary="Delete a Line", dependencies=perm(P.UPDATE))
async def delete_line(
    co_id: Id, line_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    co, _ = await _order(db, co_id, user, held)
    await service.delete_line(db, co, await service.get_line(db, co, line_id))
    return {"message": "Line deleted"}

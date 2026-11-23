"""Mounted at /api/v1/temporary-works/trash: the recycle bin and the hidden Deleted folder (two separate views, each
listing deleted items and deleted permits), restore of either kind, and the bin's retention setting. Every route needs the
restore permission, which is what makes the two views visible at all; project access is checked as well."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import deletion, deletion_rules, permits, service
from .deletion_schemas import (
    TwDeletedItemRead,
    TwDeletedPermitRead,
    TwRetentionRead,
    TwRetentionUpdate,
    TwTrashView,
)
from .models import TemporaryWorksItem, TemporaryWorksPermit
from .permissions import TemporaryWorksPermissionName as P
from .permit_schemas import TwPermitRead, TwPermitWriteRead
from .schemas import TwItemRead, TwItemWriteRead

router = APIRouter(tags=["Temporary Works Deleted Records"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
RESTORE = [require_permissions(P.RESTORE.value)]


async def _locked(db: Any, model: Any, row_id: int) -> Any:
    """The row re-read under a row lock, or ``None`` when it no longer exists (a refresh would raise instead)."""
    query = select(model).where(model.id == row_id).with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def _listed(db: Any, model: Any, read: Any, project_id: int, view: TwTrashView, page: int, per_page: int) -> Any:
    """One page of a view for a project the caller can already see."""
    total, rows = await deletion.list_trash(db, model, project_id, view.value, compute_offset(page, per_page), per_page)
    retention = await deletion.retention_of(db, project_id)
    data: list[dict[str, Any]] = []
    for row in rows:
        purge_on = deletion_rules.purge_on(row.deleted_at, retention) if deletion_rules.in_bin(row.deleted_kind) else None
        data.append(read.model_validate(row).model_copy(update={"purge_on": purge_on}).model_dump(mode="json"))
    return paginated_response(crud_data={"data": data, "total_count": total}, page=page, items_per_page=per_page)


@router.get(
    "/settings",
    response_model=TwRetentionRead,
    summary="Recycle Bin Retention",
    description="Days a deleted draft with no history beyond its creation stays in the recycle bin before the scheduled "
    "purge removes it. Default 30, one to 60.",
    dependencies=RESTORE,
)
async def get_retention(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return TwRetentionRead(project_id=project_id, bin_retention_days=await deletion.retention_of(db, project_id))


@router.put(
    "/settings",
    response_model=TwRetentionRead,
    summary="Set Recycle Bin Retention",
    description="Whole days, one to 60. Audit-logged. Applies to records already in the bin, which are judged against the "
    "setting as it stands when the purge runs.",
    dependencies=RESTORE,
)
async def put_retention(
    values: TwRetentionUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    days = await deletion.set_retention(db, values.project_id, values.bin_retention_days, user["id"])
    return TwRetentionRead(project_id=values.project_id, bin_retention_days=days)


@router.get(
    "/{view}/items",
    response_model=PaginatedListResponse[TwDeletedItemRead],
    summary="List Deleted Items",
    description="The recycle bin (view bin) or the hidden Deleted folder (view deleted): a project's deleted items, most "
    "recently deleted first. The bin shows when the purge may remove each one.",
    dependencies=RESTORE,
)
async def list_deleted_items(
    view: TwTrashView,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await _listed(db, TemporaryWorksItem, TwDeletedItemRead, project_id, view, page, items_per_page)


@router.get(
    "/{view}/permits",
    response_model=PaginatedListResponse[TwDeletedPermitRead],
    summary="List Deleted Permits",
    description="As for items: the recycle bin (view bin) or the hidden Deleted folder (view deleted).",
    dependencies=RESTORE,
)
async def list_deleted_permits(
    view: TwTrashView,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await _listed(db, TemporaryWorksPermit, TwDeletedPermitRead, project_id, view, page, items_per_page)


@router.post(
    "/items/{item_id}/restore",
    response_model=TwItemWriteRead,
    summary="Restore a Deleted Item",
    description="From the recycle bin or the Deleted folder, back to draft. Its permits are left as they were: a permit "
    "deleted earlier stays deleted until it is restored itself.",
    dependencies=RESTORE,
)
async def restore_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    item = await db.get(TemporaryWorksItem, item_id)
    if item is None:
        raise service.ItemNotFoundError("No such temporary works item")
    await readable_project(db, item.project_id, user["id"], held)
    item = await _locked(db, TemporaryWorksItem, item_id)  # a restore and a purge of one record run in turn
    if item is None:  # the purge removed it while this request waited
        raise service.ItemNotFoundError("No such temporary works item")
    try:
        await deletion.restore(db, item, user["id"])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return service.write_body(TwItemRead.model_validate(item), [])


@router.post(
    "/permits/{permit_id}/restore",
    response_model=TwPermitWriteRead,
    summary="Restore a Deleted Permit",
    description="From the recycle bin or the Deleted folder, back to draft. Its item must not be deleted (conflict "
    "otherwise): restore the item first.",
    dependencies=RESTORE,
)
async def restore_permit(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    permit = await db.get(TemporaryWorksPermit, permit_id)
    if permit is None:
        raise permits.PermitNotFoundError("No such temporary works permit")
    await readable_project(db, permit.project_id, user["id"], held)
    permit = await _locked(db, TemporaryWorksPermit, permit_id)
    if permit is None:  # the purge removed it while this request waited
        raise permits.PermitNotFoundError("No such temporary works permit")
    try:
        await deletion.restore(db, permit, user["id"])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return service.write_body(TwPermitRead.model_validate(permit), [])

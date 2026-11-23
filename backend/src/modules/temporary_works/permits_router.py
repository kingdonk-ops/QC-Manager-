"""Mounted at /api/v1/temporary-works/permits: list, create, read, edit while draft, delete a draft, issue, activate,
close, return to draft and history. The item and project of a permit come from the request context, never the body."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import permits, service
from .constants import PERMIT_ENTITY, PermitStatus
from .models import TemporaryWorksPermit
from .permissions import TemporaryWorksPermissionName as P
from .permit_schemas import TwPermitCreate, TwPermitRead, TwPermitUpdate, TwPermitWriteRead
from .schemas import TwHistoryRead, TwReasonBody

router = APIRouter(tags=["Temporary Works Permits"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
ItemQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID, description="The item the permit is for")]
READ = [require_permissions(P.READ.value)]
CREATE = [require_permissions(P.CREATE.value)]
UPDATE = [require_permissions(P.UPDATE.value)]
DELETE = [require_permissions(P.DELETE.value)]
ISSUE = [require_permissions(P.ISSUE.value)]
RETURN = [require_permissions(P.RETURN_TO_DRAFT.value)]


async def _readable(
    db: Any, permit_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False
) -> TemporaryWorksPermit:
    """The permit once the caller may see its project (a missing or foreign one answers the same not-found). ``lock``
    re-reads it under a row lock so two simultaneous actions run one after the other."""
    permit = await permits.get_permit(db, permit_id)
    await readable_project(db, permit.project_id, user["id"], held)
    return await permits.lock_permit(db, permit) if lock else permit


def _written(permit: TemporaryWorksPermit, warnings: Any) -> dict[str, Any]:
    return service.write_body(TwPermitRead.model_validate(permit), warnings)


@router.get(
    "/",
    response_model=PaginatedListResponse[TwPermitRead],
    summary="List Permits",
    description="A project's permits in creation order, filtered by item and status.",
    dependencies=READ,
)
async def list_permits(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    item_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    status: PermitStatus | None = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    if item_id is not None and (await service.get_item(db, item_id)).project_id != project_id:
        raise service.ItemNotFoundError("No such temporary works item")
    total, rows = await permits.list_permits(
        db,
        project_id,
        item_id=item_id,
        status=status.value if status else None,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
    )
    data = {"data": [TwPermitRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=TwPermitWriteRead,
    status_code=201,
    summary="Create a Permit",
    description="Always a draft, for the item named in the query. An item of another project, or a missing one, answers "
    "not-found. Issue it with the issue action.",
    dependencies=CREATE,
)
async def create_permit(
    values: TwPermitCreate, item_id: ItemQuery, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    item = await service.lock_item(db, item)  # a concurrent delete or move of the item runs before or after, not between
    permit, warnings = await permits.create_permit(db, item, values.model_dump(), user["id"])
    return _written(permit, warnings)


@router.get("/{permit_id}", response_model=TwPermitRead, summary="Get a Permit", dependencies=READ)
async def get_permit(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _readable(db, permit_id, user, held)


@router.patch(
    "/{permit_id}",
    response_model=TwPermitWriteRead,
    summary="Edit a Draft Permit",
    description="Only while the permit is a draft (conflict otherwise). The status is not part of an edit.",
    dependencies=UPDATE,
)
async def update_permit(
    permit_id: Id, values: TwPermitUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    permit = await _readable(db, permit_id, user, held, lock=True)
    permit, warnings = await permits.update_permit(db, permit, values.model_dump(exclude_unset=True))
    return _written(permit, warnings)


@router.delete(
    "/{permit_id}",
    summary="Delete a Draft Permit",
    description="Only a permit in draft. A soft delete, audit-logged: a permit with no history beyond its creation goes to "
    "the recycle bin (removed by the scheduled purge after the project's retention), any other to the hidden Deleted "
    "folder (kept). The response names which. Both are restorable with the restore permission.",
    dependencies=DELETE,
)
async def delete_permit(
    permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    kind = await permits.delete_permit(db, await _readable(db, permit_id, user, held, lock=True), user["id"])
    return {"message": "Permit deleted", "destination": kind}


@router.post(
    "/{permit_id}/issue",
    response_model=TwPermitWriteRead,
    summary="Issue a Permit",
    description="Draft to issued. A permit to load must record both the design check and the inspection: one error per "
    "missing flag, and it stays a draft.",
    dependencies=ISSUE,
)
async def issue_permit(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    permit = await _readable(db, permit_id, user, held, lock=True)
    permit, warnings = await permits.issue_permit(db, permit, user["id"])
    return _written(permit, warnings)


@router.post("/{permit_id}/activate", response_model=TwPermitWriteRead, summary="Activate a Permit", dependencies=ISSUE)
async def activate_permit(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    permit = await _readable(db, permit_id, user, held, lock=True)
    permit, warnings = await permits.activate_permit(db, permit, user["id"])
    return _written(permit, warnings)


@router.post(
    "/{permit_id}/close",
    response_model=TwPermitWriteRead,
    summary="Close a Permit",
    description="Issued or active to closed, recording the closing user and day.",
    dependencies=ISSUE,
)
async def close_permit(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    permit = await _readable(db, permit_id, user, held, lock=True)
    permit, warnings = await permits.close_permit(db, permit, user["id"])
    return _written(permit, warnings)


@router.post(
    "/{permit_id}/return-to-draft",
    response_model=TwPermitWriteRead,
    summary="Return a Permit to Draft",
    description="Needs its own permission, separate from edit, and a reason that is audit-logged. Clears the issued and "
    "closed days.",
    dependencies=RETURN,
)
async def return_permit_to_draft(
    permit_id: Id, values: TwReasonBody, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    permit = await _readable(db, permit_id, user, held, lock=True)
    return _written(await permits.return_to_draft(db, permit, values.reason, user["id"]), [])


@router.get("/{permit_id}/history", response_model=list[TwHistoryRead], summary="Permit Status History", dependencies=READ)
async def permit_history(permit_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    permit = await _readable(db, permit_id, user, held)
    return await service.history_for(db, PERMIT_ENTITY, permit.id)

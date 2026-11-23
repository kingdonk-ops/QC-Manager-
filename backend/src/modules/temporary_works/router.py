"""Mounted at /api/v1/temporary-works: the register of temporary works items (list, create, read, edit, delete a draft,
transition, return to draft, history), with the permits under /permits, the recycle bin and Deleted folder under /trash and
the register views under /register and /load-status. The fixed-segment routers are included before the routes with an
integer item path parameter."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import item_actions, service
from .constants import ITEM_ENTITY, Family, ItemStatus
from .deletion_router import router as deletion_router
from .models import TemporaryWorksItem
from .permissions import TemporaryWorksPermissionName as P
from .permits_router import router as permits_router
from .register_router import router as register_router
from .schemas import (
    TwHistoryRead,
    TwItemCreate,
    TwItemRead,
    TwItemTransition,
    TwItemUpdate,
    TwItemWriteRead,
    TwReasonBody,
)

router = APIRouter(tags=["Temporary Works"])
router.include_router(register_router)
router.include_router(permits_router, prefix="/permits")
router.include_router(deletion_router, prefix="/trash")

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
CREATE = [require_permissions(P.CREATE.value)]
UPDATE = [require_permissions(P.UPDATE.value)]
DELETE = [require_permissions(P.DELETE.value)]
TRANSITION = [require_permissions(P.TRANSITION.value)]
RETURN = [require_permissions(P.RETURN_TO_DRAFT.value)]


async def _readable(
    db: Any, item_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False
) -> TemporaryWorksItem:
    """The item once the caller may see its project: a missing, deleted or foreign item answers the same not-found.
    ``lock`` re-reads it under a row lock, so two concurrent changes to one item run in turn."""
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    return await service.lock_item(db, item) if lock else item


def _written(item: TemporaryWorksItem, warnings: Any) -> dict[str, Any]:
    return service.write_body(TwItemRead.model_validate(item), warnings)


@router.get(
    "/",
    response_model=PaginatedListResponse[TwItemRead],
    summary="List Temporary Works Items",
    description="A project's items, ascending sort order then creation time, filtered by family, status, design check "
    "category and linked scaffold. Deleted items are not listed.",
    dependencies=READ,
)
async def list_items(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    family: Family | None = None,
    status: ItemStatus | None = None,
    category: Annotated[int | None, Query(ge=0, le=3, description="Design check category")] = None,
    scaffold_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    total, rows = await service.list_items(
        db,
        project_id,
        family=family.value if family else None,
        status=status.value if status else None,
        category=category,
        scaffold_id=scaffold_id,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
    )
    data = {"data": [TwItemRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=TwItemWriteRead,
    status_code=201,
    summary="Create a Temporary Works Item",
    description="Starts in identified. A duplicate reference in the project is a conflict, checked before the rules. "
    "Non-blocking warnings come back in the response.",
    dependencies=CREATE,
)
async def create_item(values: TwItemCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    item, warnings = await service.create_item(db, values.model_dump(), user["id"])
    return _written(item, warnings)


@router.get("/{item_id}", response_model=TwItemRead, summary="Get a Temporary Works Item", dependencies=READ)
async def get_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _readable(db, item_id, user, held)


@router.patch(
    "/{item_id}",
    response_model=TwItemWriteRead,
    summary="Edit a Temporary Works Item",
    description="Any subset of fields; an explicit null clears an optional one. The rules run only when a rule-relevant "
    "field is supplied. The status is not editable: use the transition action.",
    dependencies=UPDATE,
)
async def update_item(
    item_id: Id, values: TwItemUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await _readable(db, item_id, user, held, lock=True)
    item, warnings = await service.update_item(db, item, values.model_dump(exclude_unset=True))
    return _written(item, warnings)


@router.delete(
    "/{item_id}",
    summary="Delete a Draft Temporary Works Item",
    description="Only an item in draft whose permits have each been deleted first (conflict otherwise). A soft delete, "
    "audit-logged: an item with no history beyond its creation goes to the recycle bin (removed by the scheduled purge after "
    "the project's retention), any other to the hidden Deleted folder (kept). The response names which. Both are restorable "
    "with the restore permission.",
    dependencies=DELETE,
)
async def delete_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    kind = await item_actions.delete_item(db, await _readable(db, item_id, user, held, lock=True), user["id"])
    return {"message": "Temporary works item deleted", "destination": kind}


@router.post(
    "/{item_id}/transition",
    response_model=TwItemWriteRead,
    summary="Move an Item Along Its Guarded Flow",
    description="One step forward, one step back with a note, on hold from any live status, and from on hold only back to "
    "the status held from. Entering approved to load needs a category and a coordinator; loaded needs the load gate open "
    "(and, for a linked scaffold, a green or yellow tag with the inspection not overdue); in use only from loaded with no "
    "breach; struck needs the strike gate open.",
    dependencies=TRANSITION,
)
async def transition_item(
    item_id: Id, values: TwItemTransition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await _readable(db, item_id, user, held, lock=True)
    item, warnings = await item_actions.transition_item(db, item, values.status, values.note, user["id"])
    return _written(item, warnings)


@router.post(
    "/{item_id}/return-to-draft",
    response_model=TwItemWriteRead,
    summary="Return an Item to Draft",
    description="Needs its own permission, separate from edit, and a reason that is audit-logged.",
    dependencies=RETURN,
)
async def return_item_to_draft(
    item_id: Id, values: TwReasonBody, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await _readable(db, item_id, user, held, lock=True)
    return _written(await item_actions.return_to_draft(db, item, values.reason, user["id"]), [])


@router.get("/{item_id}/history", response_model=list[TwHistoryRead], summary="Item Status History", dependencies=READ)
async def item_history(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    item = await _readable(db, item_id, user, held)
    return await service.history_for(db, ITEM_ENTITY, item.id)

"""Mounted at /api/v1/saved-views."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .models import SavedView
from .permissions import SavedViewPermissionName as P
from .schemas import RegisterKey, SavedViewIn, SavedViewRead, SavedViewUpdate

router = APIRouter(tags=["Saved views"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


@router.get(
    "/",
    response_model=PaginatedListResponse[SavedViewRead],
    summary="Views of a Register",
    description="The caller's own views and those shared with the project or with one of the caller's teams.",
    dependencies=[require_permissions(P.READ.value)],
)
async def list_views(
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    register_key: Annotated[RegisterKey, Query()],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    v = await service.viewer(db, user["id"], held)
    where = [SavedView.project_id == project_id, SavedView.register_key == register_key, service.visible_filter(v)]
    total = await db.scalar(select(func.count()).select_from(SavedView).where(*where))
    rows = (
        await db.execute(
            select(SavedView)
            .where(*where)
            .order_by(SavedView.name, SavedView.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [SavedViewRead.model_validate(r).model_dump(mode="json") for r in await service.present(db, v, list(rows))]
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


@router.get(
    "/default",
    response_model=SavedViewRead | None,
    summary="The View to Open a Register With",
    description="The caller's own default, else the project default, else null.",
    dependencies=[require_permissions(P.READ.value)],
)
async def default(
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    register_key: Annotated[RegisterKey, Query()],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    v = await service.viewer(db, user["id"], held)
    view = await service.default_view(db, v, project_id, register_key)
    return (await service.present(db, v, [view]))[0] if view else None


@router.post(
    "/",
    response_model=SavedViewRead,
    status_code=201,
    summary="Save a View",
    dependencies=[require_permissions(P.READ.value, P.CREATE.value)],
)
async def create(values: SavedViewIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    v = await service.viewer(db, user["id"], held)
    data = values.model_dump(mode="json")
    data["config"] = values.config.model_dump(mode="json", exclude_none=True)
    view = await service.create(db, v, data)
    await db.commit()
    return (await service.present(db, v, [view]))[0]


@router.get("/{view_id}", response_model=SavedViewRead, summary="Get a View", dependencies=[require_permissions(P.READ.value)])
async def get_view(view_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    v = await service.viewer(db, user["id"], held)
    view = await service.get_visible(db, v, view_id)
    await readable_project(db, view.project_id, user["id"], held)
    return (await service.present(db, v, [view]))[0]


@router.patch(
    "/{view_id}",
    response_model=SavedViewRead,
    summary="Change a View",
    description="Rename, re-share, make default, or save the grid's current state into it.",
    dependencies=[require_permissions(P.READ.value)],
)
async def change(
    view_id: Id, values: SavedViewUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    v = await service.viewer(db, user["id"], held)
    view = await service.get_visible(db, v, view_id)
    await readable_project(db, view.project_id, user["id"], held)
    data = {k: v for k, v in values.model_dump(mode="json", exclude_unset=True).items() if v is not None}
    if values.config is not None:
        data["config"] = values.config.model_dump(mode="json", exclude_none=True)
    await service.change(db, v, view, data)
    await db.commit()
    return (await service.present(db, v, [view]))[0]


@router.delete("/{view_id}", summary="Delete a View", dependencies=[require_permissions(P.READ.value)])
async def delete_view(view_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    v = await service.viewer(db, user["id"], held)
    view = await service.get_visible(db, v, view_id)
    await readable_project(db, view.project_id, user["id"], held)
    await service.remove(db, v, view)
    await db.commit()
    return {"message": "View deleted"}

"""Mounted at /api/v1/projects."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from .permissions import ProjectPermissionName
from .schemas import ProjectCreate, ProjectRead, ProjectUpdate
from .service import ProjectService

router = APIRouter(tags=["Projects"])

Projects = Annotated[ProjectService, Depends(ProjectService)]
ProjectId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


@router.get("/", response_model=PaginatedListResponse[ProjectRead], summary="List the Projects the Caller May See")
async def list_projects(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    projects: Projects,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    data = await projects.page(db, user["id"], held, compute_offset(page, items_per_page), items_per_page)

    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/{project_id}", response_model=ProjectRead, summary="Get a Project")
async def get_project(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, projects: Projects
) -> Any:
    return await projects.get(db, project_id, user["id"], held)


@router.post(
    "/",
    response_model=ProjectRead,
    status_code=201,
    summary="Create a Project",
    dependencies=[require_permissions(ProjectPermissionName.CREATE.value)],
)
async def create_project(values: ProjectCreate, db: AsyncSessionDep, _: CurrentUserDep, projects: Projects) -> Any:
    return await projects.create(db, values.model_dump())


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Change a Project",
    dependencies=[require_permissions(ProjectPermissionName.UPDATE.value)],
)
async def update_project(
    project_id: ProjectId, values: ProjectUpdate, db: AsyncSessionDep, _: CurrentUserDep, projects: Projects
) -> Any:
    return await projects.update(db, project_id, values.model_dump(exclude_unset=True))


@router.delete(
    "/{project_id}", summary="Delete a Project", dependencies=[require_permissions(ProjectPermissionName.DELETE.value)]
)
async def delete_project(project_id: ProjectId, db: AsyncSessionDep, _: CurrentUserDep, projects: Projects) -> dict[str, str]:
    await projects.delete(db, project_id)

    return {"message": "Project deleted"}

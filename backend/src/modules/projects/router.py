"""Mounted at /api/v1/projects."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.modules.loader import installed_modules
from ...infrastructure.modules.state import register_project_override
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from .constants import REGIONS
from .permissions import ProjectPermissionName
from .schemas import ModuleOverrideSet, ProjectCreate, ProjectRead, ProjectUpdate, RegionRead
from .service import ProjectService, module_override, overrides_of, readable_project, set_overrides

register_project_override(module_override)

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


@router.get("/regions", response_model=list[RegionRead], summary="Regions and What They Imply")
async def regions(_: CurrentUserDep) -> list[RegionRead]:
    return [RegionRead(code=code, **values) for code, values in REGIONS.items()]


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


@router.get("/{project_id}/modules", summary="The Project's Module Overrides")
async def project_modules(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, bool]:
    await readable_project(db, project_id, user["id"], held)
    return await overrides_of(db, project_id)


@router.put(
    "/{project_id}/modules",
    summary="Override Modules for One Project",
    description="`{module: true|false}` overrides the system-wide switch for this project; `null` removes the override.",
    dependencies=[require_permissions(ProjectPermissionName.UPDATE.value)],
)
async def set_project_modules(
    project_id: ProjectId, values: ModuleOverrideSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, bool]:
    await readable_project(db, project_id, user["id"], held)
    switchable = {m.manifest.name for m in installed_modules() if m.enabled and not m.manifest.core}
    unknown = set(values.overrides) - switchable
    if unknown:
        raise UnprocessableEntityException(f"Not a module a project can switch: {', '.join(sorted(unknown))}")
    before = await overrides_of(db, project_id)
    changed = sorted(m for m, v in values.overrides.items() if before.get(m) != v)
    if changed:
        await record_audit(
            db,
            "projects.modules.overridden",
            "project",
            project_id,
            actor_id=user["id"],
            project_id=project_id,
            summary=f"Module overrides changed: {', '.join(changed)}",
            before={m: before.get(m) for m in changed},
            after={m: values.overrides[m] for m in changed},
        )
    return await set_overrides(db, project_id, values.overrides)

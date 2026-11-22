"""Mounted at /api/v1/coatings."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.records import history_of
from ..asset_tree import service as tree
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .calc import dft_stats, environment_check
from .models import CoatingJob, CoatingSystem
from .permissions import CoatingPermissionName as P
from .schemas import (
    DftCreate,
    DftPreview,
    DftRead,
    DftStatsRead,
    EnvironmentCheckRead,
    EnvironmentCreate,
    EnvironmentPreview,
    EnvironmentRead,
    JobCreate,
    JobDetail,
    JobRead,
    JobUpdate,
    StageRead,
    StageRelease,
    StageUpdate,
    SystemCreate,
    SystemRead,
    SystemUpdate,
)

router = APIRouter(tags=["Coatings"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# --- calculators (no project data) --------------------------------------------------------------


@router.post(
    "/check/dft",
    response_model=DftStatsRead,
    summary="DFT Statistics for a Set of Readings",
    description="Mean, min, max, % within range and the verdict under 80/20, 90/10 or min/max. Stores nothing.",
    dependencies=perm(P.READ),
)
async def check_dft(values: DftPreview, _: CurrentUserDep) -> Any:
    stats = dft_stats(values.readings, values.dft_min_um, values.dft_max_um, values.rule.value)
    return DftStatsRead(**{**stats.__dict__, "failures": list(stats.failures)})


@router.post(
    "/check/environment",
    response_model=EnvironmentCheckRead,
    summary="Dew Point and the Surface-Temperature Margin",
    description="Dew point from air temperature and RH (Magnus), and whether the surface is at least "
    "`required_margin_c` (3 °C) above it. Stores nothing.",
    dependencies=perm(P.READ),
)
async def check_environment(values: EnvironmentPreview, _: CurrentUserDep) -> Any:
    if values.dew_point_c is None and (values.air_temp_c is None or values.rh_pct is None):
        raise UnprocessableEntityException("Give the dew point, or the air temperature and relative humidity.")
    check = environment_check(
        values.surface_temp_c,
        air_temp_c=values.air_temp_c,
        rh_pct=values.rh_pct,
        dew_point_c=values.dew_point_c,
        required_margin_c=values.required_margin_c,
    )
    return EnvironmentCheckRead(**check.__dict__)


# --- systems ------------------------------------------------------------------------------------


@router.get(
    "/systems/",
    response_model=PaginatedListResponse[SystemRead],
    summary="Coating Systems",
    dependencies=perm(P.READ),
)
async def list_systems(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = CoatingSystem.project_id == project_id
    total = await db.scalar(select(func.count()).select_from(CoatingSystem).where(where))
    rows = (
        await db.execute(
            select(CoatingSystem)
            .where(where)
            .order_by(CoatingSystem.code)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [service.read_system(s) for s in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/systems/", response_model=SystemRead, status_code=201, summary="Add a Coating System", dependencies=perm(P.CREATE)
)
async def create_system(values: SystemCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    await service.code_free(db, values.project_id, values.code)
    body = values.model_dump(mode="json")
    system = CoatingSystem(**body)
    db.add(system)
    await db.commit()
    return service.read_system(system)


async def _system(db: Any, system_id: int, user: dict[str, Any], held: frozenset[str]) -> CoatingSystem:
    system = await service.get_system(db, system_id)
    await readable_project(db, system.project_id, user["id"], held)
    return system


@router.get("/systems/{system_id}", response_model=SystemRead, summary="Get a Coating System", dependencies=perm(P.READ))
async def get_system(system_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return service.read_system(await _system(db, system_id, user, held))


@router.patch(
    "/systems/{system_id}",
    response_model=SystemRead,
    summary="Change a Coating System",
    description="Jobs already created keep the coats and DFT limits they were created with.",
    dependencies=perm(P.UPDATE),
)
async def update_system(
    system_id: Id, values: SystemUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    system = await _system(db, system_id, user, held)
    for key, value in values.model_dump(mode="json", exclude_unset=True).items():
        if value is None and key in {"name", "coats", "dft_rule", "dew_point_margin_c"}:
            continue
        setattr(system, key, value)
    await db.commit()
    return service.read_system(system)


@router.delete("/systems/{system_id}", summary="Delete an Unused Coating System", dependencies=perm(P.DELETE))
async def delete_system(
    system_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    system = await _system(db, system_id, user, held)
    if await db.scalar(select(CoatingJob.id).where(CoatingJob.system_id == system.id).limit(1)):
        raise UnprocessableEntityException("Jobs use this system.")
    await db.delete(system)
    await db.commit()
    return {"message": "Coating system deleted"}


# --- jobs ---------------------------------------------------------------------------------------


async def _job(db: Any, job_id: int, user: dict[str, Any], held: frozenset[str]) -> CoatingJob:
    job = await service.get_job(db, job_id)
    await readable_project(db, job.project_id, user["id"], held)
    return job


@router.get(
    "/jobs/",
    response_model=PaginatedListResponse[JobRead],
    summary="Coating Jobs",
    description="Filter by status, or by `node_id` (with its subtree).",
    dependencies=perm(P.READ),
)
async def list_jobs(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: Annotated[str | None, Query(pattern=r"^(open|in_progress|passed|failed)$")] = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [CoatingJob.project_id == project_id]
    if status:
        where.append(CoatingJob.status == status)
    if node_id is not None:
        await tree.get_node(db, node_id, project_id)
        where.append(CoatingJob.node_id.in_(await tree.subtree_ids(db, node_id, with_lineage=False)))
    total = await db.scalar(select(func.count()).select_from(CoatingJob).where(*where))
    rows = (
        await db.execute(
            select(CoatingJob)
            .where(*where)
            .order_by(CoatingJob.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_jobs(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/jobs/",
    response_model=JobDetail,
    status_code=201,
    summary="Start a Coating Job",
    description="Creates the hold points from the system: surface preparation, then one per coat.",
    dependencies=perm(P.CREATE),
)
async def create_job(values: JobCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    job = await service.create_job(db, values.model_dump(), user["id"])
    return await service.job_detail(db, job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetail,
    summary="A Coating Job with Hold Points and Readings",
    dependencies=perm(P.READ),
)
async def get_job(job_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.job_detail(db, await _job(db, job_id, user, held))


@router.patch("/jobs/{job_id}", response_model=JobDetail, summary="Change a Coating Job", dependencies=perm(P.UPDATE))
async def update_job(
    job_id: Id, values: JobUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    job = await _job(db, job_id, user, held)
    for key, value in values.model_dump(mode="json", exclude_unset=True).items():
        if value is None and key in {"title", "dft_rule"}:
            continue
        setattr(job, key, value)
    await db.commit()
    return await service.job_detail(db, job)


@router.delete("/jobs/{job_id}", summary="Delete a Coating Job", dependencies=perm(P.DELETE))
async def delete_job(job_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    job = await _job(db, job_id, user, held)
    await db.delete(job)
    await db.commit()
    return {"message": "Coating job deleted"}


@router.get("/jobs/{job_id}/history", summary="Status History", dependencies=perm(P.READ))
async def job_history(
    job_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    job = await _job(db, job_id, user, held)
    return await history_of(db, service.ENTITY, job.id)


@router.post(
    "/jobs/{job_id}/environment",
    response_model=EnvironmentRead,
    status_code=201,
    summary="Record an Environmental Reading",
    description="Dew point is calculated from air temperature and RH unless measured. Fails when the surface is less "
    "than the system's margin (3 °C) above the dew point, or RH is above the system's limit.",
    dependencies=perm(P.UPDATE),
)
async def add_environment(
    job_id: Id, values: EnvironmentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    job = await _job(db, job_id, user, held)
    return await service.add_environment(db, job, values.model_dump(), user["id"])


@router.post(
    "/jobs/{job_id}/dft",
    response_model=DftRead,
    status_code=201,
    summary="Record a Set of DFT Readings for a Coat",
    dependencies=perm(P.UPDATE),
)
async def add_dft(job_id: Id, values: DftCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    job = await _job(db, job_id, user, held)
    return await service.add_dft(db, job, values.model_dump(), user["id"])


@router.patch(
    "/jobs/{job_id}/stages/{stage_id}",
    response_model=StageRead,
    summary="Record Batch Numbers, Profile and Notes on a Hold Point",
    dependencies=perm(P.UPDATE),
)
async def update_stage(
    job_id: Id, stage_id: Id, values: StageUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    job = await _job(db, job_id, user, held)
    stage = await service.get_stage(db, job, stage_id)
    for key, value in values.model_dump(mode="json", exclude_unset=True).items():
        setattr(stage, key, [] if key == "batch_numbers" and value is None else value)
    await db.commit()
    return stage


@router.post(
    "/jobs/{job_id}/stages/{stage_id}/release",
    response_model=JobDetail,
    summary="Pass or Fail a Hold Point",
    description="Passing needs the previous hold point passed, passing environmental readings on this one, and for a "
    "coat a passing latest DFT set and batch numbers (for surface prep, the profile within range). 422 lists what's missing.",
    dependencies=perm(P.REVIEW),
)
async def release(
    job_id: Id, stage_id: Id, values: StageRelease, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    job = await _job(db, job_id, user, held)
    stage = await service.get_stage(db, job, stage_id)
    if stage.status != "pending":
        raise UnprocessableEntityException("This hold point has already been decided.")
    if values.result == "passed":
        problems = await service.release_problems(db, job, stage)
        if problems:
            raise UnprocessableEntityException("Can't pass yet: " + "; ".join(problems) + ".")
    await service.release(db, job, stage, values.result, values.note, user["id"])
    return await service.job_detail(db, job)

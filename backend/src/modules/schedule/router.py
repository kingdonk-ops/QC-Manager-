"""Mounted at /api/v1/schedule. Every route reads the project through ``projects``' visibility rule first.

A change that would make the links loop answers 422 with ``detail = {message, cycle: [ids], codes}``.
"""

import re
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastapi.exceptions import HTTPException
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .cpm import CycleError
from .interchange import ImportFormatError, parse
from .models import Activity
from .permissions import SchedulePermissionName as P
from .schemas import (
    ScheduleActivityCreate,
    ScheduleActivityRead,
    ScheduleActivityStatus,
    ScheduleActivityUpdate,
    ScheduleBaselineCreate,
    ScheduleBaselineRead,
    ScheduleCalendarRead,
    ScheduleCalendarUpdate,
    ScheduleDependencyCreate,
    ScheduleDependencyRead,
    ScheduleDependencyUpdate,
    ScheduleGantt,
    ScheduleGenerateRequest,
    ScheduleImportReport,
    ScheduleMonteCarloRequest,
    ScheduleMonteCarloResult,
    ScheduleSummary,
)

router = APIRouter(tags=["4D Schedule"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
MAX_IMPORT_BYTES = 20 * 1024 * 1024


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _cycle(db: AsyncSession, err: CycleError) -> HTTPException:
    return HTTPException(status_code=422, detail=await service.cycle_detail(db, err))


# --- activities ----------------------------------------------------------------------------------


@router.get(
    "/activities/",
    response_model=PaginatedListResponse[ScheduleActivityRead],
    summary="List Activities",
    description="A project's activities in WBS order. Filter by status, critical, parent or text.",
    dependencies=perm(P.READ),
)
async def list_activities(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: ScheduleActivityStatus | None = None,
    critical: bool | None = None,
    parent_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Activity.project_id == project_id]
    if status:
        where.append(Activity.status == status.value)
    if critical is not None:
        where.append(Activity.is_critical.is_(critical))
    if parent_id:
        where.append(Activity.parent_id == parent_id)
    if search:
        needle = f"%{search.lower()}%"
        where.append(or_(func.lower(Activity.name).like(needle), func.lower(Activity.code).like(needle)))
    total = await db.scalar(select(func.count()).select_from(Activity).where(*where))
    rows = list((await db.execute(select(Activity).where(*where))).scalars())
    rows.sort(key=lambda a: (service.wbs_key(a.wbs_code), a.sort_order, a.id))
    offset = compute_offset(page, items_per_page)
    rows = rows[offset : offset + items_per_page]
    data = {"data": await service.read_activities(db, project_id, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/activities/", response_model=ScheduleActivityRead, status_code=201, summary="Add an Activity", dependencies=perm(P.CREATE)
)
async def create_activity(
    values: ScheduleActivityCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    activity = await service.create_activity(db, project, values.model_dump(exclude_unset=True), user)
    return (await service.read_activities(db, project.id, [activity]))[0]


@router.get(
    "/activities/{activity_id}", response_model=ScheduleActivityRead, summary="Get an Activity", dependencies=perm(P.READ)
)
async def get_activity(activity_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    activity = await service.get_activity(db, activity_id)
    await readable_project(db, activity.project_id, user["id"], held)
    return (await service.read_activities(db, activity.project_id, [activity]))[0]


@router.patch(
    "/activities/{activity_id}",
    response_model=ScheduleActivityRead,
    summary="Change an Activity",
    description="Send only what changed. `planned_start` moves the bar (a start-no-earlier-than constraint); "
    "`planned_finish` or `duration` stretches it; status, percent and actual dates keep each other consistent.",
    dependencies=perm(P.UPDATE),
)
async def update_activity(
    activity_id: Id, values: ScheduleActivityUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    activity = await service.get_activity(db, activity_id)
    project = await readable_project(db, activity.project_id, user["id"], held)
    await service.update_activity(db, project, activity, values.model_dump(exclude_unset=True), user)
    return (await service.read_activities(db, project.id, [activity]))[0]


@router.delete("/activities/{activity_id}", summary="Delete an Activity", dependencies=perm(P.DELETE))
async def delete_activity(
    activity_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    activity = await service.get_activity(db, activity_id)
    project = await readable_project(db, activity.project_id, user["id"], held)
    await service.delete_activity(db, project, activity)
    return {"message": "Activity deleted"}


@router.get("/activities/{activity_id}/history", summary="An Activity's Status History", dependencies=perm(P.READ))
async def activity_history(
    activity_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    activity = await service.get_activity(db, activity_id)
    await readable_project(db, activity.project_id, user["id"], held)
    return await history_of(db, service.ENTITY, activity.id)


# --- dependencies --------------------------------------------------------------------------------


@router.post(
    "/dependencies/",
    response_model=ScheduleDependencyRead,
    status_code=201,
    summary="Link Two Activities",
    description="FS, SS, FF or SF with a lag in working days (negative for a lead). 422 with the loop if it would close one.",
    dependencies=perm(P.UPDATE),
)
async def create_dependency(
    values: ScheduleDependencyCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project, dep = await service.add_dependency(db, values.model_dump())
    await readable_project(db, project.id, user["id"], held)
    try:
        await service.save_dependency(db, project, dep)
    except CycleError as err:
        raise await _cycle(db, err) from err
    return ScheduleDependencyRead.model_validate(dep)


@router.patch(
    "/dependencies/{dependency_id}", response_model=ScheduleDependencyRead, summary="Change a Link", dependencies=perm(P.UPDATE)
)
async def update_dependency(
    dependency_id: Id, values: ScheduleDependencyUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    dep = await service.get_dependency(db, dependency_id)
    project = await readable_project(db, dep.project_id, user["id"], held)
    if values.type is not None:
        dep.type = values.type.value
    if values.lag is not None:
        dep.lag = values.lag
    await service.save_dependency(db, project, dep)
    return ScheduleDependencyRead.model_validate(dep)


@router.delete("/dependencies/{dependency_id}", summary="Remove a Link", dependencies=perm(P.UPDATE))
async def delete_dependency(
    dependency_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    dep = await service.get_dependency(db, dependency_id)
    project = await readable_project(db, dep.project_id, user["id"], held)
    await db.delete(dep)
    await db.flush()
    await service.recalculate(db, project)
    await db.commit()
    return {"message": "Dependency deleted"}


# --- the project's schedule ----------------------------------------------------------------------


@router.get(
    "/gantt/{project_id}",
    response_model=ScheduleGantt,
    summary="The Project's Gantt",
    description="Every activity with its CPM fields and baseline dates, the links, the calendar and the baselines.",
    dependencies=perm(P.READ),
)
async def gantt(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> ScheduleGantt:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.gantt(db, project)


@router.post(
    "/{project_id}/calculate",
    response_model=ScheduleSummary,
    summary="Recalculate the Critical Path",
    dependencies=perm(P.UPDATE),
)
async def calculate(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> ScheduleSummary:
    project = await readable_project(db, project_id, user["id"], held)
    try:
        await service.recalculate(db, project)
    except CycleError as err:
        await db.rollback()
        raise await _cycle(db, err) from err
    await db.commit()
    settings = await service.get_settings(db, project)
    acts, _ = await service.load(db, project.id)
    return await service.summary(db, project, acts, settings)


@router.get(
    "/{project_id}/calendar", response_model=ScheduleCalendarRead, summary="The Working Calendar", dependencies=perm(P.READ)
)
async def get_calendar(
    project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> ScheduleCalendarRead:
    project = await readable_project(db, project_id, user["id"], held)
    settings = await service.get_settings(db, project)
    await db.commit()
    return service.read_calendar(settings)


@router.put(
    "/{project_id}/calendar",
    response_model=ScheduleCalendarRead,
    summary="Set the Calendar and Data Date",
    description="Working weekdays (Monday 0 .. Sunday 6), holidays, project start and the status (data) date.",
    dependencies=perm(P.UPDATE),
)
async def put_calendar(
    project_id: Id, values: ScheduleCalendarUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> ScheduleCalendarRead:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.update_calendar(db, project, values.model_dump(exclude_unset=True))


@router.get(
    "/{project_id}/baselines", response_model=list[ScheduleBaselineRead], summary="Baselines", dependencies=perm(P.READ)
)
async def baselines(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.list_baselines(db, await service.get_settings(db, project))


@router.post(
    "/{project_id}/baselines",
    response_model=list[ScheduleBaselineRead],
    status_code=201,
    summary="Save a Baseline",
    description="Snapshots every activity's planned dates under a name; by default it becomes the current baseline.",
    dependencies=perm(P.UPDATE),
)
async def create_baseline(
    project_id: Id, values: ScheduleBaselineCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.create_baseline(db, project, values.name, values.make_current, user)


@router.post(
    "/{project_id}/baselines/{baseline_id}/current",
    response_model=list[ScheduleBaselineRead],
    summary="Make a Baseline Current",
    dependencies=perm(P.UPDATE),
)
async def set_current_baseline(
    project_id: Id, baseline_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    baseline = await service.get_baseline(db, project.id, baseline_id)
    settings = await service.get_settings(db, project)
    settings.current_baseline_id = baseline.id
    await db.commit()
    return await service.list_baselines(db, settings)


@router.delete("/{project_id}/baselines/{baseline_id}", summary="Delete a Baseline", dependencies=perm(P.DELETE))
async def delete_baseline(
    project_id: Id, baseline_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    project = await readable_project(db, project_id, user["id"], held)
    baseline = await service.get_baseline(db, project.id, baseline_id)
    settings = await service.get_settings(db, project)
    if settings.current_baseline_id == baseline.id:
        settings.current_baseline_id = None
    await db.delete(baseline)
    await db.commit()
    return {"message": "Baseline deleted"}


@router.post(
    "/{project_id}/generate",
    response_model=list[ScheduleActivityRead],
    status_code=201,
    summary="Generate Activities from Sections",
    description="One activity per section, durations proportional to `value`, linked finish-to-start. "
    "`source: cvr` takes the sections from the project's CVR cost heads (budget as weight).",
    dependencies=perm(P.CREATE),
)
async def generate(
    project_id: Id, values: ScheduleGenerateRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    sections = (
        await service.cvr_sections(db, project.id) if values.source == "cvr" else [s.model_dump() for s in values.sections]
    )
    await service.generate(db, project, sections, values.total_duration, values.start_date, values.replace, user)
    acts, _ = await service.load(db, project.id)
    return await service.read_activities(db, project.id, acts)


@router.post(
    "/{project_id}/monte-carlo",
    response_model=ScheduleMonteCarloResult,
    summary="Monte Carlo Schedule Risk",
    description="Samples three-point durations (default -10% / planned / +25%) and reports the finish-date "
    "distribution, P50/P80/P90, the chance of meeting the target and each activity's criticality index.",
    dependencies=perm(P.READ),
)
async def monte_carlo(
    project_id: Id, values: ScheduleMonteCarloRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    try:
        return await service.monte_carlo(db, project, values.iterations, values.distribution, values.seed, values.target_date)
    except CycleError as err:
        raise await _cycle(db, err) from err


@router.post(
    "/{project_id}/import",
    response_model=ScheduleImportReport,
    summary="Import a P6 or MS Project Schedule",
    description="Primavera P6 XER or XML, or Microsoft Project XML, detected from the content. "
    "`dry_run` reports the counts without writing; `replace` deletes the current activities first.",
    dependencies=perm(P.IMPORT),
)
async def import_schedule(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    dry_run: Annotated[bool, Form()] = False,
    replace: Annotated[bool, Form()] = False,
) -> ScheduleImportReport:
    project = await readable_project(db, project_id, user["id"], held)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=422, detail="Schedule files are limited to 20 MB.")
    try:
        parsed = parse(data)
    except ImportFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if dry_run:
        return service.import_report(parsed, dry_run=True)
    return await service.import_schedule(db, project, parsed, replace, user)


@router.get(
    "/{project_id}/export",
    summary="Export the Schedule",
    description="`msp_xml` (Microsoft Project XML, which P6 also imports), `xlsx` or `csv`.",
    dependencies=perm(P.EXPORT),
)
async def export_schedule(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    format: Literal["msp_xml", "xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    body, media_type, ext = await service.export(db, project, format)
    await db.commit()
    stamp = date.today().isoformat()
    code = re.sub(r"[^A-Za-z0-9_.-]", "_", project.code)
    return Response(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="schedule-{code}-{stamp}.{ext}"'},
    )

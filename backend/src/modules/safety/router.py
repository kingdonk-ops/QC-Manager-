"""Mounted at /api/v1/safety. Every route reads the project through ``projects``' visibility rule first."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import ProjectService, readable_project
from . import service
from .constants import OPEN_ACTIONS, IncidentStatus, IncidentType, ObservationCategory, ObservationKind, ParentType, RateBase
from .models import HoursWorked, Incident, Observation, SafetyAction
from .permissions import SafetyPermissionName as P
from .schemas import (
    IncidentCreate,
    IncidentRead,
    IncidentStatusChange,
    IncidentUpdate,
    ObservationCreate,
    ObservationRead,
    ObservationUpdate,
    SafetyActionCreate,
    SafetyActionRead,
    SafetyActionUpdate,
    SafetyDashboard,
    SafetyHoursRead,
    SafetyHoursSet,
)

router = APIRouter(tags=["Safety"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
Month = Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")]
Base = Annotated[
    RateBase | None,
    Query(description="Hours base for both rates. Leave out for the conventions: TRIR per 200,000 h, LTIFR per 1,000,000 h."),
]

RATES = (
    "TRIR = recordable incidents × 200,000 / hours worked. "
    "LTIFR (LTIR) = lost-time injuries × 1,000,000 / hours worked. "
    "`base` applies 200,000 or 1,000,000 to both. Near-miss ratio = near misses / recordable incidents. "
    "Risk score = severity × likelihood (1-25): 1-4 low, 5-9 medium, 10-14 high, 15-25 extreme."
)


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _page(data: list[dict[str, Any]], total: int | None, page: int, items_per_page: int) -> Any:
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


# --- incidents ---------------------------------------------------------------------------------------


async def _incident(db: Any, incident_id: int, user: dict[str, Any], held: frozenset[str]) -> Incident:
    i = await service.get_incident(db, incident_id)
    await readable_project(db, i.project_id, user["id"], held)
    return i


@router.get(
    "/incidents/",
    response_model=PaginatedListResponse[IncidentRead],
    summary="List Incidents",
    description="Newest first. Filter by type, status, recordable, lost time or search text.",
    dependencies=perm(P.READ),
)
async def list_incidents(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    type: IncidentType | None = None,
    status: IncidentStatus | None = None,
    recordable: bool | None = None,
    lost_time: bool | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Incident.project_id == project_id]
    if type:
        where.append(Incident.type == type.value)
    if status:
        where.append(Incident.status == status.value)
    if recordable is not None:
        where.append(Incident.recordable.is_(recordable))
    if lost_time is not None:
        where.append(Incident.lost_time.is_(lost_time))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Incident.title + " " + Incident.code).like(like),
                func.lower(func.coalesce(Incident.location, "")).like(like),
            )
        )
    total = await db.scalar(select(func.count()).select_from(Incident).where(*where))
    rows = (
        await db.execute(
            select(Incident)
            .where(*where)
            .order_by(Incident.occurred_at.desc(), Incident.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page(await service.read_incidents(db, list(rows)), total, page, items_per_page)


@router.post(
    "/incidents/",
    response_model=IncidentRead,
    status_code=201,
    summary="Report an Incident",
    description="Risk score = severity × likelihood, banded low (1-4), medium (5-9), high (10-14), extreme (15-25).",
    dependencies=perm(P.CREATE),
)
async def create_incident(
    values: IncidentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    incident = await service.create_incident(db, values.model_dump(), user["id"])
    return (await service.read_incidents(db, [incident]))[0]


@router.get("/incidents/{incident_id}", response_model=IncidentRead, summary="Get an Incident", dependencies=perm(P.READ))
async def get_incident(incident_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_incidents(db, [await _incident(db, incident_id, user, held)]))[0]


@router.patch(
    "/incidents/{incident_id}", response_model=IncidentRead, summary="Update an Incident", dependencies=perm(P.UPDATE)
)
async def update_incident(
    incident_id: Id, values: IncidentUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    incident = await _incident(db, incident_id, user, held)
    service.apply_incident(incident, values.model_dump(exclude_unset=True))
    await db.commit()
    return (await service.read_incidents(db, [incident]))[0]


@router.patch(
    "/incidents/{incident_id}/status",
    response_model=IncidentRead,
    summary="Change an Incident's Status",
    description="reported → investigating → actions_open → closed (reported and investigating may close directly; "
    "closed reopens to investigating). Closing is refused while corrective actions are open.",
    dependencies=perm(P.TRANSITION),
)
async def incident_status(
    incident_id: Id, values: IncidentStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    incident = await _incident(db, incident_id, user, held)
    await service.change_incident_status(db, incident, values.status.value, values.note, user["id"])
    return (await service.read_incidents(db, [incident]))[0]


@router.get("/incidents/{incident_id}/history", summary="Incident Status History", dependencies=perm(P.READ))
async def incident_history(
    incident_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    return await service.incident_history(db, await _incident(db, incident_id, user, held))


@router.delete("/incidents/{incident_id}", summary="Delete an Incident", dependencies=perm(P.DELETE))
async def delete_incident(
    incident_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    incident = await _incident(db, incident_id, user, held)
    await _delete_actions(db, ParentType.INCIDENT, incident.id)
    await db.delete(incident)
    await db.commit()
    return {"message": "Incident deleted"}


async def _delete_actions(db: Any, parent_type: str, parent_id: int) -> None:
    for a in (
        await db.execute(
            select(SafetyAction).where(SafetyAction.parent_type == parent_type, SafetyAction.parent_id == parent_id)
        )
    ).scalars():
        await db.delete(a)


# --- observations ------------------------------------------------------------------------------------


async def _observation(db: Any, observation_id: int, user: dict[str, Any], held: frozenset[str]) -> Observation:
    o = await service.get_observation(db, observation_id)
    await readable_project(db, o.project_id, user["id"], held)
    return o


@router.get(
    "/observations/",
    response_model=PaginatedListResponse[ObservationRead],
    summary="List Observations",
    dependencies=perm(P.READ),
)
async def list_observations(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    kind: ObservationKind | None = None,
    category: ObservationCategory | None = None,
    status: Annotated[str | None, Query(pattern=r"^(open|closed)$")] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Observation.project_id == project_id]
    if kind:
        where.append(Observation.kind == kind.value)
    if category:
        where.append(Observation.category == category.value)
    if status:
        where.append(Observation.status == status)
    total = await db.scalar(select(func.count()).select_from(Observation).where(*where))
    rows = (
        await db.execute(
            select(Observation)
            .where(*where)
            .order_by(Observation.observed_at.desc(), Observation.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page(await service.read_observations(db, list(rows)), total, page, items_per_page)


@router.post(
    "/observations/",
    response_model=ObservationRead,
    status_code=201,
    summary="Log an Observation",
    description="Positive observations are logged closed; negative ones stay open until closed or actioned.",
    dependencies=perm(P.CREATE),
)
async def create_observation(
    values: ObservationCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    observation = await service.create_observation(db, values.model_dump(), user["id"])
    return (await service.read_observations(db, [observation]))[0]


@router.get(
    "/observations/{observation_id}", response_model=ObservationRead, summary="Get an Observation", dependencies=perm(P.READ)
)
async def get_observation(observation_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_observations(db, [await _observation(db, observation_id, user, held)]))[0]


@router.patch(
    "/observations/{observation_id}",
    response_model=ObservationRead,
    summary="Update an Observation",
    dependencies=perm(P.UPDATE),
)
async def update_observation(
    observation_id: Id, values: ObservationUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    observation = await _observation(db, observation_id, user, held)
    service.apply_observation(observation, values.model_dump(exclude_unset=True))
    await db.commit()
    return (await service.read_observations(db, [observation]))[0]


@router.delete("/observations/{observation_id}", summary="Delete an Observation", dependencies=perm(P.DELETE))
async def delete_observation(
    observation_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    observation = await _observation(db, observation_id, user, held)
    await _delete_actions(db, ParentType.OBSERVATION, observation.id)
    await db.delete(observation)
    await db.commit()
    return {"message": "Observation deleted"}


# --- corrective actions ------------------------------------------------------------------------------


@router.get(
    "/actions/",
    response_model=PaginatedListResponse[SafetyActionRead],
    summary="List Corrective Actions",
    description="A project's actions, by due date. Filter by the incident or observation, assignee (`me`), or `open_only`.",
    dependencies=perm(P.READ),
)
async def list_actions(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    parent_type: ParentType | None = None,
    parent_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    assignee: Annotated[str | None, Query(pattern=r"^(me|\d+)$")] = None,
    open_only: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [SafetyAction.project_id == project_id]
    if parent_type:
        where.append(SafetyAction.parent_type == parent_type.value)
    if parent_id:
        where.append(SafetyAction.parent_id == parent_id)
    if assignee:
        where.append(SafetyAction.assignee_id == (user["id"] if assignee == "me" else int(assignee)))
    if open_only:
        where.append(SafetyAction.status.in_(OPEN_ACTIONS))
    total = await db.scalar(select(func.count()).select_from(SafetyAction).where(*where))
    rows = (
        await db.execute(
            select(SafetyAction)
            .where(*where)
            .order_by(SafetyAction.due_date.is_(None), SafetyAction.due_date, SafetyAction.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page(await service.read_actions(db, list(rows)), total, page, items_per_page)


@router.post(
    "/actions/",
    response_model=SafetyActionRead,
    status_code=201,
    summary="Add a Corrective Action",
    description="On an incident or observation. The assignee is notified; an incident under report or investigation "
    "moves to actions_open.",
    dependencies=perm(P.UPDATE),
)
async def create_action(
    values: SafetyActionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    parent = await service.parent_of(db, values.parent_type.value, values.parent_id)
    await readable_project(db, parent.project_id, user["id"], held)
    action = await service.create_action(db, parent, values.model_dump(), user["id"])
    return (await service.read_actions(db, [action]))[0]


@router.patch(
    "/actions/{action_id}",
    response_model=SafetyActionRead,
    summary="Update a Corrective Action",
    description="Setting `status` to `verified` records the caller as verifier, with the time.",
    dependencies=perm(P.UPDATE),
)
async def update_action(
    action_id: Id, values: SafetyActionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    action = await service.get_action(db, action_id)
    await readable_project(db, action.project_id, user["id"], held)
    await service.update_action(db, action, values.model_dump(exclude_unset=True), user["id"])
    return (await service.read_actions(db, [action]))[0]


@router.delete("/actions/{action_id}", summary="Delete a Corrective Action", dependencies=perm(P.UPDATE))
async def delete_action(
    action_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    action = await service.get_action(db, action_id)
    await readable_project(db, action.project_id, user["id"], held)
    await db.delete(action)
    await db.commit()
    return {"message": "Action deleted"}


# --- hours worked ------------------------------------------------------------------------------------


@router.get(
    "/hours/",
    response_model=PaginatedListResponse[SafetyHoursRead],
    summary="Hours Worked by Month",
    dependencies=perm(P.READ),
)
async def list_hours(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = [HoursWorked.project_id == project_id]
    total = await db.scalar(select(func.count()).select_from(HoursWorked).where(*where))
    rows = (
        await db.execute(
            select(HoursWorked)
            .where(*where)
            .order_by(HoursWorked.month.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page([SafetyHoursRead.model_validate(r).model_dump(mode="json") for r in rows], total, page, items_per_page)


@router.put("/hours", response_model=SafetyHoursRead, summary="Set a Month's Hours Worked", dependencies=perm(P.UPDATE))
async def set_hours(values: SafetyHoursSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    month = service.month_start(values.month)
    row = await db.scalar(select(HoursWorked).where(HoursWorked.project_id == values.project_id, HoursWorked.month == month))
    if row is None:
        row = HoursWorked(project_id=values.project_id, month=month)
        db.add(row)
    row.hours, row.headcount, row.notes = values.hours, values.headcount, values.notes
    await db.commit()
    return SafetyHoursRead.model_validate(row)


@router.delete("/hours/{hours_id}", summary="Delete a Month's Hours", dependencies=perm(P.UPDATE))
async def delete_hours(hours_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    row = await db.get(HoursWorked, hours_id)
    if row is None:
        raise service.ActionNotFoundError("No such month")
    await readable_project(db, row.project_id, user["id"], held)
    await db.delete(row)
    await db.commit()
    return {"message": "Hours deleted"}


# --- dashboard & report ------------------------------------------------------------------------------


@router.get(
    "/dashboard",
    response_model=SafetyDashboard,
    summary="Safety SafetyDashboard, All Projects",
    description="Across every project the caller can see. " + RATES,
    dependencies=perm(P.READ),
)
async def dashboard_all(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    date_from: date | None = None,
    date_to: date | None = None,
    base: Base = None,
) -> SafetyDashboard:
    projects = await ProjectService().page(db, user["id"], held, 0, 10_000)
    ids = [p["id"] for p in projects["data"]]
    return await service.dashboard(db, ids, date_from, date_to, int(base) if base else None)


@router.get(
    "/dashboard/{project_id}",
    response_model=SafetyDashboard,
    summary="Safety SafetyDashboard",
    description="SafetyLagging (incidents, rates) and leading (observations) indicators, monthly figures and the 5×5 risk "
    "matrix (incident and observation counts per severity × likelihood cell). " + RATES,
    dependencies=perm(P.READ),
)
async def dashboard(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    date_from: date | None = None,
    date_to: date | None = None,
    base: Base = None,
) -> SafetyDashboard:
    await readable_project(db, project_id, user["id"], held)
    return await service.dashboard(db, [project_id], date_from, date_to, int(base) if base else None)


@router.get(
    "/summary.pdf",
    summary="Monthly Safety Summary (PDF)",
    description="The month's and year-to-date figures, rates and incident list. " + RATES,
    dependencies=perm(P.READ),
)
async def summary_pdf(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery, month: Month | None = None
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    month = month or datetime.now().strftime("%Y-%m")
    pdf = await service.summary_pdf(db, project, month)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="safety-summary-{project.code}-{month}.pdf"'},
    )

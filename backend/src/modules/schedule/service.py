"""The schedule's business logic: activities, links, calendars, baselines and every calculation.

Every edit recalculates the project (``recalculate``) before it commits, so the stored early/late dates,
floats and critical flags always match the network. A link that would close a loop raises
``cpm.CycleError`` before anything is written; the router answers 422 with the loop.

Other modules (earned value, reports) read activities by id: planned and baseline dates, percent
complete, budget hours and cost are all on ``ScheduleActivityRead``; ``activity_snapshot`` gives them in bulk.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ...infrastructure.tabular import write_table
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..cvr.models import CostHead
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from . import cpm
from .calendar import MON_FRI, Calendar
from .interchange import ExportActivity, Imported, write_msp_xml
from .models import Activity, Baseline, Dependency, ScheduleSettings
from .montecarlo import Estimate, simulate
from .schemas import (
    ScheduleActivityRead,
    ScheduleActivityStatus,
    ScheduleActivityType,
    ScheduleBaselineRead,
    ScheduleCalendarRead,
    ScheduleDependencyRead,
    ScheduleGantt,
    ScheduleImportReport,
    ScheduleSummary,
)

ENTITY = "schedule_activity"
FLOW: dict[str, set[str]] = {
    ScheduleActivityStatus.PENDING: {ScheduleActivityStatus.IN_PROGRESS, ScheduleActivityStatus.COMPLETED},
    ScheduleActivityStatus.IN_PROGRESS: {ScheduleActivityStatus.PENDING, ScheduleActivityStatus.COMPLETED},
    ScheduleActivityStatus.COMPLETED: {ScheduleActivityStatus.IN_PROGRESS, ScheduleActivityStatus.PENDING},
}


class ActivityNotFoundError(ResourceNotFoundError):
    public_detail = "Activity not found."


class DependencyNotFoundError(ResourceNotFoundError):
    public_detail = "Dependency not found."


class BaselineNotFoundError(ResourceNotFoundError):
    public_detail = "Baseline not found."


class ScheduleError(ValidationError):
    """A request the schedule can't carry out; the message says why and is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.public_detail = message  # type: ignore[misc]


def link_of(activity: Activity) -> str:
    return f"/schedule?project={activity.project_id}&activity={activity.id}"


def wbs_key(code: str) -> tuple:
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in code.split("."))


# --- settings and calendar -----------------------------------------------------------------------


async def get_settings(db: AsyncSession, project: Project) -> ScheduleSettings:
    settings = await db.get(ScheduleSettings, project.id)
    if settings is None:
        settings = ScheduleSettings(
            project_id=project.id, working_days=list(MON_FRI), start_date=project.start_date or date.today()
        )
        db.add(settings)
        await db.flush()
    elif settings.start_date is None:
        settings.start_date = project.start_date or date.today()
    return settings


def calendar_of(settings: ScheduleSettings) -> Calendar:
    return Calendar(
        settings.start_date or date.today(),
        settings.working_days or MON_FRI,
        [date.fromisoformat(h) for h in settings.holidays or []],
    )


def read_calendar(settings: ScheduleSettings) -> ScheduleCalendarRead:
    return ScheduleCalendarRead(
        project_id=settings.project_id,
        working_days=sorted(settings.working_days or MON_FRI),
        holidays=sorted(date.fromisoformat(h) for h in settings.holidays or []),
        start_date=settings.start_date,
        data_date=settings.data_date,
        finish_date=settings.finish_date,
        current_baseline_id=settings.current_baseline_id,
    )


async def update_calendar(db: AsyncSession, project: Project, changes: dict[str, Any]) -> ScheduleCalendarRead:
    settings = await get_settings(db, project)
    if "working_days" in changes and changes["working_days"] is not None:
        settings.working_days = sorted(set(changes["working_days"]))
    if "holidays" in changes and changes["holidays"] is not None:
        settings.holidays = sorted({d.isoformat() for d in changes["holidays"]})
    if "start_date" in changes and changes["start_date"] is not None:
        settings.start_date = changes["start_date"]
    if "data_date" in changes:
        settings.data_date = changes["data_date"]
    await recalculate(db, project)
    await db.commit()
    return read_calendar(settings)


# --- loading and reading -------------------------------------------------------------------------


async def load(db: AsyncSession, project_id: int) -> tuple[list[Activity], list[Dependency]]:
    acts = list((await db.execute(select(Activity).where(Activity.project_id == project_id))).scalars())
    deps = list((await db.execute(select(Dependency).where(Dependency.project_id == project_id))).scalars())
    acts.sort(key=lambda a: (wbs_key(a.wbs_code), a.sort_order, a.id))
    return acts, deps


async def get_activity(db: AsyncSession, activity_id: int) -> Activity:
    activity = await db.get(Activity, activity_id)
    if activity is None:
        raise ActivityNotFoundError(f"Activity {activity_id} not found")
    return activity


async def current_baseline(db: AsyncSession, settings: ScheduleSettings) -> Baseline | None:
    return await db.get(Baseline, settings.current_baseline_id) if settings.current_baseline_id else None


def _variance(cal: Calendar, actual: date | None, planned: date | None, finish: bool) -> int | None:
    if actual is None or planned is None:
        return None
    if finish:
        return cal.finish_index(actual) - cal.finish_index(planned)
    return cal.index_of(actual) - cal.index_of(planned)


async def read_activities(
    db: AsyncSession, project_id: int, rows: Sequence[Activity], settings: ScheduleSettings | None = None
) -> list[dict[str, Any]]:
    if settings is None:
        settings = await db.get(ScheduleSettings, project_id)
    cal = calendar_of(settings) if settings else Calendar(date.today())
    baseline = await current_baseline(db, settings) if settings else None
    snapshot = baseline.snapshot if baseline else {}
    out = []
    for a in rows:
        base = snapshot.get(str(a.id))
        b_start = date.fromisoformat(base[0]) if base and base[0] else None
        b_finish = date.fromisoformat(base[1]) if base and base[1] else None
        forecast_start = a.actual_start or a.early_start
        forecast_finish = a.actual_finish or a.early_finish
        out.append(
            ScheduleActivityRead.model_validate(a)
            .model_copy(
                update={
                    "baseline_start": b_start,
                    "baseline_finish": b_finish,
                    "start_variance": _variance(cal, forecast_start, a.planned_start, False),
                    "finish_variance": _variance(cal, forecast_finish, a.planned_finish, True),
                    "baseline_variance": _variance(cal, forecast_finish, b_finish, True),
                    "p6_critical": (
                        a.p6_critical_by(settings.p6_critical_definition, settings.p6_critical_float_hours)
                        if settings
                        else None
                    ),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def activity_snapshot(db: AsyncSession, activity_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
    """For other modules: planned/baseline dates, progress and budgets of these activities, by id."""
    rows = list((await db.execute(select(Activity).where(Activity.id.in_(activity_ids)))).scalars())
    out: dict[int, dict[str, Any]] = {}
    for project_id in {r.project_id for r in rows}:
        mine = [r for r in rows if r.project_id == project_id]
        for read in await read_activities(db, project_id, mine):
            out[read["id"]] = read
    return out


# --- calculation ---------------------------------------------------------------------------------


def _engine_input(acts: Sequence[Activity], deps: Sequence[Dependency]) -> tuple[list[cpm.Activity], list[cpm.Link]]:
    parents = {a.parent_id for a in acts if a.parent_id is not None}
    return (
        [
            cpm.Activity(
                id=a.id,
                duration=0 if a.type == ScheduleActivityType.MILESTONE else a.duration,
                parent_id=a.parent_id,
                summary=a.type == ScheduleActivityType.SUMMARY or a.id in parents,
                constraint=a.constraint_type,
                constraint_date=a.constraint_date,
                actual_start=a.actual_start,
                actual_finish=a.actual_finish,
                percent_complete=a.percent_complete,
                weight=float(a.budget_hours or 0),
            )
            for a in acts
        ],
        [cpm.Link(d.predecessor_id, d.successor_id, d.type, d.lag) for d in deps],
    )


async def recalculate(db: AsyncSession, project: Project) -> cpm.Schedule:
    """Run the CPM over the project and write the results onto its activities (not committed)."""
    settings = await get_settings(db, project)
    acts, deps = await load(db, project.id)
    cal = calendar_of(settings)
    activities, links = _engine_input(acts, deps)
    schedule = cpm.calculate(activities, links, cal, settings.data_date)
    by_id = {a.id: a for a in acts}
    parents = {a.parent_id for a in acts if a.parent_id is not None}

    for aid, r in schedule.activities.items():
        a = by_id[aid]
        a.early_start, a.early_finish = r.early_start, r.early_finish
        a.late_start, a.late_finish = r.late_start, r.late_finish
        a.total_float, a.free_float = r.total_float, r.free_float
        a.is_critical = r.critical
        a.driving_predecessor_ids = r.driving
        if a.actual_start is None or a.planned_start is None:
            a.planned_start, a.planned_finish = r.early_start, r.early_finish

    # Summaries: span, progress and status from their children, deepest first.
    for a in sorted((x for x in acts if x.id in parents), key=lambda x: -len(x.wbs_code.split("."))):
        a.type = ScheduleActivityType.SUMMARY
        kids = [k for k in acts if k.parent_id == a.id]
        rolled = schedule.activities.get(a.id)
        if rolled is not None:
            a.duration = rolled.duration
            a.percent_complete = rolled.percent_complete
        if kids:
            a.budget_hours = sum((Decimal(k.budget_hours or 0) for k in kids), Decimal(0))
            a.budget_cost = sum((Decimal(k.budget_cost or 0) for k in kids), Decimal(0))
        starts = [k.planned_start for k in kids if k.planned_start]
        finishes = [k.planned_finish for k in kids if k.planned_finish]
        a.planned_start = min(starts) if starts else a.planned_start
        a.planned_finish = max(finishes) if finishes else a.planned_finish
        actual_starts = [k.actual_start for k in kids if k.actual_start]
        a.actual_start = min(actual_starts) if actual_starts else None
        done = bool(kids) and all(k.status == ScheduleActivityStatus.COMPLETED for k in kids)
        a.actual_finish = max(k.actual_finish for k in kids if k.actual_finish) if done else None
        a.status = (
            ScheduleActivityStatus.COMPLETED
            if done
            else ScheduleActivityStatus.IN_PROGRESS
            if a.actual_start or a.percent_complete > 0
            else ScheduleActivityStatus.PENDING
        )

    settings.finish_date = schedule.finish if acts else None
    settings.calculated_at = datetime.now(UTC)
    await db.flush()
    return schedule


# --- activities ----------------------------------------------------------------------------------


async def _next_wbs(db: AsyncSession, project_id: int, parent: Activity | None) -> str:
    rows = (
        await db.execute(
            select(Activity.wbs_code).where(
                Activity.project_id == project_id,
                Activity.parent_id == parent.id if parent else Activity.parent_id.is_(None),
            )
        )
    ).scalars()
    last = max((int(c.rsplit(".", 1)[-1]) for c in rows if c.rsplit(".", 1)[-1].isdigit()), default=0)
    return f"{parent.wbs_code}.{last + 1}" if parent else str(last + 1)


async def _parent_by_wbs(db: AsyncSession, project_id: int, wbs: str) -> Activity | None:
    if "." not in wbs:
        return None
    parent: Activity | None = await db.scalar(
        select(Activity).where(Activity.project_id == project_id, Activity.wbs_code == wbs.rsplit(".", 1)[0]).limit(1)
    )
    return parent


async def _check_parent(db: AsyncSession, project_id: int, parent_id: int, child_id: int | None = None) -> Activity:
    parent = await db.get(Activity, parent_id)
    if parent is None or parent.project_id != project_id:
        raise ScheduleError("The parent activity isn't in this project.")
    seen = set()
    walk: Activity | None = parent
    while walk is not None and walk.id not in seen:
        if child_id is not None and walk.id == child_id:
            raise ScheduleError("An activity can't sit under itself.")
        seen.add(walk.id)
        walk = await db.get(Activity, walk.parent_id) if walk.parent_id else None
    return parent


async def _notify_responsible(db: AsyncSession, a: Activity, actor: dict[str, Any]) -> None:
    if a.responsible_id and a.responsible_id != actor["id"]:
        await notify(
            db,
            [a.responsible_id],
            Category.ASSIGNMENT,
            f"{a.code}: {a.name}",
            body=f"Schedule activity assigned to you by {actor.get('name') or 'a colleague'}.",
            link=link_of(a),
            entity=(ENTITY, a.id),
            actor_id=actor["id"],
        )


async def create_activity(db: AsyncSession, project: Project, values: dict[str, Any], actor: dict[str, Any]) -> Activity:
    values = {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}
    values.pop("project_id", None)
    predecessor_id = values.pop("predecessor_id", None)
    planned_start = values.pop("planned_start", None)
    parent = await _check_parent(db, project.id, values["parent_id"]) if values.get("parent_id") else None
    if parent is None and values.get("wbs_code"):
        parent = await _parent_by_wbs(db, project.id, values["wbs_code"])
    if not values.get("wbs_code"):
        values["wbs_code"] = await _next_wbs(db, project.id, parent)
    values["parent_id"] = parent.id if parent else None
    if not values.get("code"):
        values["code"] = await next_reference(db, "A", project.id, width=4)
    if values.get("type") == ScheduleActivityType.MILESTONE:
        values["duration"] = 0
    if planned_start is not None and values.get("constraint_type", "asap") == "asap":
        values["constraint_type"], values["constraint_date"] = "snet", planned_start
    activity = Activity(project_id=project.id, **values)
    db.add(activity)
    await db.flush()
    if parent is not None and parent.type != ScheduleActivityType.SUMMARY:
        parent.type = ScheduleActivityType.SUMMARY
    if predecessor_id:
        pred = await get_activity(db, predecessor_id)
        if pred.project_id != project.id:
            raise ScheduleError("The predecessor isn't in this project.")
        db.add(Dependency(project_id=project.id, predecessor_id=pred.id, successor_id=activity.id))
        await db.flush()
    await record_transition(db, ENTITY, activity.id, None, activity.status, actor["id"], note="Created")
    await recalculate(db, project)
    await _notify_responsible(db, activity, actor)
    await db.commit()
    await publish("schedule.activity.created", {"project_id": project.id, "activity_id": activity.id})
    return activity


def _derive_progress(a: Activity, changes: dict[str, Any], today: date) -> None:
    """Keep status, percent and actual dates consistent with whichever of them was changed."""
    target = changes.get("status")
    if target == ScheduleActivityStatus.PENDING:
        a.actual_start = a.actual_finish = None
        a.percent_complete = 0.0
    elif target == ScheduleActivityStatus.IN_PROGRESS:
        a.actual_finish = None
        a.actual_start = a.actual_start or min(today, a.planned_start or today)
        if a.percent_complete >= 100:
            a.percent_complete = 0.0 if "percent_complete" not in changes else min(a.percent_complete, 99.0)
    elif target == ScheduleActivityStatus.COMPLETED:
        a.actual_finish = a.actual_finish or today
        a.actual_start = a.actual_start or min(a.planned_start or a.actual_finish, a.actual_finish)
        a.percent_complete = 100.0
    if target is None:
        if a.actual_finish is not None or a.percent_complete >= 100:
            a.actual_finish = a.actual_finish or today
            a.actual_start = a.actual_start or min(a.planned_start or a.actual_finish, a.actual_finish)
            a.percent_complete = 100.0
            a.status = ScheduleActivityStatus.COMPLETED
        elif a.actual_start is not None or a.percent_complete > 0:
            a.actual_start = a.actual_start or min(today, a.planned_start or today)
            a.status = ScheduleActivityStatus.IN_PROGRESS
        elif a.status != ScheduleActivityStatus.PENDING and ("percent_complete" in changes or "actual_start" in changes):
            a.status = ScheduleActivityStatus.PENDING
    else:
        a.status = target
    if a.actual_start and a.actual_finish and a.actual_finish < a.actual_start:
        raise ScheduleError("The actual finish is before the actual start.")


async def update_activity(
    db: AsyncSession, project: Project, a: Activity, changes: dict[str, Any], actor: dict[str, Any]
) -> Activity:
    changes = {k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()}
    settings = await get_settings(db, project)
    cal = calendar_of(settings)
    before_status, before_responsible = a.status, a.responsible_id
    if "status" in changes and changes["status"] is not None and changes["status"] != a.status:
        assert_transition(FLOW, a.status, changes["status"])
    elif "status" in changes:
        changes.pop("status")

    if "parent_id" in changes:
        parent_id = changes.pop("parent_id")
        parent = await _check_parent(db, project.id, parent_id, a.id) if parent_id else None
        a.parent_id = parent.id if parent else None
        if parent is not None:
            parent.type = ScheduleActivityType.SUMMARY
            if "wbs_code" not in changes:
                a.wbs_code = await _next_wbs(db, project.id, parent)

    start = changes.pop("planned_start", None)
    finish = changes.pop("planned_finish", None)
    for key, value in changes.items():
        if key in ("name", "wbs_code", "code", "type") and value is None:
            continue
        if key in ("percent_complete", "budget_hours", "budget_cost", "sort_order", "duration") and value is None:
            continue
        setattr(a, key, value)
    if changes.get("constraint_type") == "asap":
        a.constraint_date = None
    if start is not None:
        if a.actual_start is not None:
            a.actual_start = start
        else:
            a.constraint_type, a.constraint_date = "snet", start
    if finish is not None:
        first = start or a.actual_start or a.planned_start or finish
        a.duration = max(0 if a.type == ScheduleActivityType.MILESTONE else 1, cal.working_days_between(first, finish))
    if a.type == ScheduleActivityType.MILESTONE:
        a.duration = 0

    _derive_progress(a, changes, settings.data_date or date.today())
    if a.status != before_status:
        await record_transition(db, ENTITY, a.id, before_status, a.status, actor["id"])
    await recalculate(db, project)
    if a.responsible_id != before_responsible:
        await _notify_responsible(db, a, actor)
    await db.commit()
    await publish("schedule.activity.updated", {"project_id": project.id, "activity_id": a.id, "fields": sorted(changes)})
    return a


async def delete_activity(db: AsyncSession, project: Project, a: Activity) -> None:
    await db.delete(a)
    await db.flush()
    await recalculate(db, project)
    await db.commit()
    await publish("schedule.activity.deleted", {"project_id": project.id, "activity_id": a.id})


# --- dependencies --------------------------------------------------------------------------------


async def add_dependency(db: AsyncSession, values: dict[str, Any]) -> tuple[Project, Dependency]:
    pred = await get_activity(db, values["predecessor_id"])
    succ = await get_activity(db, values["successor_id"])
    if pred.project_id != succ.project_id:
        raise ScheduleError("Both activities must be in the same project.")
    if pred.id == succ.id:
        raise ScheduleError("An activity can't depend on itself.")
    existing = await db.scalar(
        select(Dependency).where(Dependency.predecessor_id == pred.id, Dependency.successor_id == succ.id)
    )
    if existing is not None:
        raise ScheduleError("Those activities are already linked.")
    project = await db.get(Project, pred.project_id)
    assert project is not None
    dep = Dependency(
        project_id=pred.project_id,
        predecessor_id=pred.id,
        successor_id=succ.id,
        type=str(getattr(values.get("type"), "value", values.get("type") or "FS")),
        lag=int(values.get("lag") or 0),
    )
    return project, dep


async def save_dependency(db: AsyncSession, project: Project, dep: Dependency) -> Dependency:
    """Write a new or changed link and recalculate; ``cpm.CycleError`` (nothing written) if it closes a loop."""
    db.add(dep)
    await db.flush()
    try:
        await recalculate(db, project)
    except cpm.CycleError:
        await db.rollback()
        raise
    await db.commit()
    await publish("schedule.dependency.saved", {"project_id": project.id, "dependency_id": dep.id})
    return dep


async def cycle_detail(db: AsyncSession, err: cpm.CycleError) -> dict[str, Any]:
    names = dict((await db.execute(select(Activity.id, Activity.code).where(Activity.id.in_(err.cycle)))).tuples().all())
    codes = [names.get(i, str(i)) for i in err.cycle]
    return {"message": "Dependency cycle: " + " → ".join(codes), "cycle": err.cycle, "codes": codes}


async def get_dependency(db: AsyncSession, dependency_id: int) -> Dependency:
    dep = await db.get(Dependency, dependency_id)
    if dep is None:
        raise DependencyNotFoundError(f"Dependency {dependency_id} not found")
    return dep


# --- baselines -----------------------------------------------------------------------------------


async def list_baselines(db: AsyncSession, settings: ScheduleSettings) -> list[ScheduleBaselineRead]:
    rows = (
        await db.execute(select(Baseline).where(Baseline.project_id == settings.project_id).order_by(Baseline.id))
    ).scalars()
    return [
        ScheduleBaselineRead(
            id=b.id,
            project_id=b.project_id,
            name=b.name,
            is_current=b.id == settings.current_baseline_id,
            finish_date=b.finish_date,
            activity_count=len(b.snapshot or {}),
            created_at=b.created_at.isoformat() if b.created_at else None,
        )
        for b in rows
    ]


async def create_baseline(
    db: AsyncSession, project: Project, name: str, make_current: bool, actor: dict[str, Any]
) -> list[ScheduleBaselineRead]:
    settings = await get_settings(db, project)
    acts, _ = await load(db, project.id)
    snapshot = {
        str(a.id): [
            a.planned_start.isoformat() if a.planned_start else None,
            a.planned_finish.isoformat() if a.planned_finish else None,
            a.duration,
        ]
        for a in acts
    }
    finishes = [a.planned_finish for a in acts if a.planned_finish]
    baseline = Baseline(
        project_id=project.id,
        name=name,
        snapshot=snapshot,
        finish_date=max(finishes) if finishes else None,
        created_by_id=actor["id"],
    )
    db.add(baseline)
    await db.flush()
    if make_current or settings.current_baseline_id is None:
        settings.current_baseline_id = baseline.id
    await db.commit()
    await publish("schedule.baseline.created", {"project_id": project.id, "baseline_id": baseline.id})
    return await list_baselines(db, settings)


async def get_baseline(db: AsyncSession, project_id: int, baseline_id: int) -> Baseline:
    baseline = await db.get(Baseline, baseline_id)
    if baseline is None or baseline.project_id != project_id:
        raise BaselineNotFoundError(f"Baseline {baseline_id} not found")
    return baseline


# --- summary and Gantt ---------------------------------------------------------------------------------


async def summary(db: AsyncSession, project: Project, acts: Sequence[Activity], settings: ScheduleSettings) -> ScheduleSummary:
    baseline = await current_baseline(db, settings)
    top = [a for a in acts if a.parent_id is None]
    by_hours = bool(top) and all(float(a.budget_hours or 0) > 0 for a in top)
    weights = [(float(a.budget_hours) if by_hours else max(a.duration, 1), a.percent_complete) for a in top]
    total = sum(w for w, _ in weights)
    starts = [a.early_start for a in acts if a.early_start]
    finish = settings.finish_date
    cal = calendar_of(settings)
    return ScheduleSummary(
        project_id=project.id,
        start=min(starts) if starts else settings.start_date,
        finish=finish,
        baseline_finish=baseline.finish_date if baseline else None,
        finish_variance=_variance(cal, finish, baseline.finish_date if baseline else None, True),
        data_date=settings.data_date,
        activity_count=len(acts),
        critical_count=sum(1 for a in acts if a.type != ScheduleActivityType.SUMMARY and _critical(a, settings)),
        percent_complete=round(sum(w * p for w, p in weights) / total, 2) if total else 0.0,
    )


def _critical(a: Activity, settings: ScheduleSettings) -> bool:
    """P6's own critical flag for a mirrored activity (project definition); otherwise the CPM's."""
    p6 = a.p6_critical_by(settings.p6_critical_definition, settings.p6_critical_float_hours)
    return a.is_critical if p6 is None else p6


async def gantt(db: AsyncSession, project: Project) -> ScheduleGantt:
    settings = await get_settings(db, project)
    acts, deps = await load(db, project.id)
    if acts and settings.calculated_at is None:
        await recalculate(db, project)
        await db.commit()
    return ScheduleGantt(
        project_id=project.id,
        summary=await summary(db, project, acts, settings),
        calendar=read_calendar(settings),
        activities=[ScheduleActivityRead(**r) for r in await read_activities(db, project.id, acts, settings)],
        dependencies=[ScheduleDependencyRead.model_validate(d) for d in deps],
        baselines=await list_baselines(db, settings),
    )


# --- generation ----------------------------------------------------------------------------------


def split_duration(values: Sequence[Decimal | float], total: int) -> list[int]:
    """Whole working days proportional to ``values`` that add up to ``total`` (each at least 1 when possible)."""
    n = len(values)
    if n == 0:
        return []
    weights = [max(float(v), 0.0) for v in values]
    whole = sum(weights)
    if whole <= 0:
        weights, whole = [1.0] * n, float(n)
    shares = [total * w / whole for w in weights]
    days = [int(s) for s in shares]
    leftover = total - sum(days)
    for i in sorted(range(n), key=lambda i: -(shares[i] - int(shares[i])))[:leftover]:
        days[i] += 1
    if total >= n:
        # No section may vanish: borrow a day from the longest for each empty one.
        for i in range(n):
            if days[i] == 0:
                days[days.index(max(days))] -= 1
                days[i] = 1
    return days


async def generate(
    db: AsyncSession,
    project: Project,
    sections: list[dict[str, Any]],
    total_duration: int,
    start_date: date | None,
    replace: bool,
    actor: dict[str, Any],
) -> int:
    if not sections:
        raise ScheduleError("There are no sections to schedule.")
    settings = await get_settings(db, project)
    if replace:
        await db.execute(delete(Activity).where(Activity.project_id == project.id))
        await db.flush()
    if start_date is not None:
        settings.start_date = start_date
    durations = split_duration([s["value"] for s in sections], total_duration)
    top = await _next_wbs(db, project.id, None)
    first = int(top)
    previous: Activity | None = None
    for n, (section, days) in enumerate(zip(sections, durations, strict=True)):
        a = Activity(
            project_id=project.id,
            code=str(section["code"])[:40],
            wbs_code=str(first + n),
            name=str(section["name"])[:300],
            duration=days,
            budget_cost=Decimal(str(section["value"])),
            sort_order=n,
            notes="Generated from section " + str(section["code"])[:40],
        )
        db.add(a)
        await db.flush()
        if previous is not None:
            db.add(Dependency(project_id=project.id, predecessor_id=previous.id, successor_id=a.id))
        previous = a
    await db.flush()
    await recalculate(db, project)
    await db.commit()
    await publish("schedule.generated", {"project_id": project.id, "activities": len(sections), "by": actor["id"]})
    return len(sections)


async def cvr_sections(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    """The project's CVR cost heads as weighted sections, when the cvr module is switched on."""
    if not await is_enabled(db, "cvr", project_id):
        raise ScheduleError("The cost-value reconciliation module is switched off for this project.")
    rows = (
        await db.execute(select(CostHead).where(CostHead.project_id == project_id).order_by(CostHead.sort_order, CostHead.code))
    ).scalars()
    return [{"code": h.code, "name": h.description, "value": h.budget} for h in rows]


# --- Monte Carlo ---------------------------------------------------------------------------------


async def monte_carlo(
    db: AsyncSession,
    project: Project,
    iterations: int,
    distribution: str,
    seed: int | None,
    target: date | None,
) -> dict[str, Any]:
    settings = await get_settings(db, project)
    acts, deps = await load(db, project.id)
    activities, links = _engine_input(acts, deps)
    parents = {a.parent_id for a in activities if a.parent_id is not None}
    tasks = [a for a in activities if not a.summary and a.id not in parents]
    if not tasks:
        raise ScheduleError("Add activities before running a simulation.")
    estimates = {
        a.id: Estimate(a.optimistic_duration, a.most_likely_duration, a.pessimistic_duration)
        for a in acts
        if a.optimistic_duration is not None or a.most_likely_duration is not None or a.pessimistic_duration is not None
    }
    result = simulate(
        tasks,
        links,
        calendar_of(settings),
        estimates,
        iterations=iterations,
        seed=seed,
        distribution=distribution,
        data_date=settings.data_date,
        target=target,
    )
    by_id = {a.id: a for a in acts}
    for c in result["criticality"]:
        a = by_id.get(c["activity_id"])
        c["name"], c["wbs_code"] = (a.name, a.wbs_code) if a else (None, None)
    return result


# --- import / export -----------------------------------------------------------------------------


def import_report(parsed: Imported, dry_run: bool) -> ScheduleImportReport:
    return ScheduleImportReport(
        format=parsed.format,
        dry_run=dry_run,
        project_name=parsed.project_name,
        activities=sum(1 for a in parsed.activities if a.type != "summary"),
        summaries=sum(1 for a in parsed.activities if a.type == "summary"),
        milestones=sum(1 for a in parsed.activities if a.type == "milestone"),
        dependencies=len(parsed.links),
        working_days=parsed.working_days,
        holidays=len(parsed.holidays),
    )


async def import_schedule(
    db: AsyncSession, project: Project, parsed: Imported, replace: bool, actor: dict[str, Any]
) -> ScheduleImportReport:
    report = import_report(parsed, dry_run=False)
    settings = await get_settings(db, project)
    if replace:
        report.replaced = (
            await db.scalar(select(func.count()).select_from(Activity).where(Activity.project_id == project.id)) or 0
        )
        await db.execute(delete(Activity).where(Activity.project_id == project.id))
        await db.flush()
    settings.working_days = parsed.working_days
    settings.holidays = sorted({h.isoformat() for h in parsed.holidays})
    starts = [a.planned_start for a in parsed.activities if a.planned_start and a.type != "summary"]
    if starts and (replace or settings.start_date is None or min(starts) < settings.start_date):
        settings.start_date = min(starts)
    if parsed.data_date:
        settings.data_date = parsed.data_date
    offset = 0
    if not replace:
        offset = int(await _next_wbs(db, project.id, None)) - 1

    has_preds = {lk.successor for lk in parsed.links}
    created: dict[str, Activity] = {}
    for n, src in enumerate(parsed.activities):
        wbs = src.wbs_code or str(n + 1)
        if offset:
            head, _, rest = wbs.partition(".")
            wbs = f"{int(head) + offset}{'.' + rest if rest else ''}" if head.isdigit() else wbs
        constraint, constraint_date = src.constraint_type, src.constraint_date
        if (
            constraint == "asap"
            and src.type != "summary"
            and src.key not in has_preds
            and src.actual_start is None
            and src.planned_start is not None
            and settings.start_date is not None
            and src.planned_start > settings.start_date
        ):
            constraint, constraint_date = "snet", src.planned_start
        a = Activity(
            project_id=project.id,
            code=(src.code or f"A{n + 1}")[:40],
            wbs_code=wbs[:60],
            name=src.name[:300],
            type=src.type,
            duration=max(0, src.duration),
            planned_start=src.planned_start,
            planned_finish=src.planned_finish,
            actual_start=src.actual_start,
            actual_finish=src.actual_finish,
            percent_complete=min(max(src.percent_complete, 0.0), 100.0),
            status=(
                ScheduleActivityStatus.COMPLETED
                if src.actual_finish or src.percent_complete >= 100
                else ScheduleActivityStatus.IN_PROGRESS
                if src.actual_start or src.percent_complete > 0
                else ScheduleActivityStatus.PENDING
            ),
            constraint_type=constraint,
            constraint_date=constraint_date if constraint != "asap" else None,
            budget_hours=Decimal(str(round(src.budget_hours or 0, 2))),
            notes=src.notes,
            sort_order=n,
            external_id=src.key[:60],
        )
        if a.status == ScheduleActivityStatus.COMPLETED and a.actual_finish is None:
            a.actual_finish = src.planned_finish
            a.actual_start = a.actual_start or src.planned_start
        db.add(a)
        created[src.key] = a
    await db.flush()
    for src in parsed.activities:
        if src.parent_key and src.parent_key in created:
            created[src.key].parent_id = created[src.parent_key].id
    seen: set[tuple[int, int]] = set()
    for lk in parsed.links:
        p, s = created[lk.predecessor].id, created[lk.successor].id
        if p == s or (p, s) in seen:
            continue
        seen.add((p, s))
        db.add(Dependency(project_id=project.id, predecessor_id=p, successor_id=s, type=lk.type, lag=lk.lag))
    await db.flush()
    try:
        await recalculate(db, project)
    except cpm.CycleError as err:
        codes = {a.id: a.code for a in created.values()}
        await db.rollback()
        raise ScheduleError("The file's links loop: " + " → ".join(codes.get(i, str(i)) for i in err.cycle)) from err
    await db.commit()
    report.created = len(created)
    await publish("schedule.imported", {"project_id": project.id, "format": parsed.format, "by": actor["id"]})
    return report


EXPORT_COLUMNS = [
    ("wbs_code", "WBS"),
    ("code", "Activity ID"),
    ("name", "Name"),
    ("type", "Type"),
    ("duration", "Duration (days)"),
    ("planned_start", "Planned start"),
    ("planned_finish", "Planned finish"),
    ("early_start", "Early start"),
    ("early_finish", "Early finish"),
    ("late_start", "Late start"),
    ("late_finish", "Late finish"),
    ("total_float", "Total float"),
    ("free_float", "Free float"),
    ("is_critical", "Critical"),
    ("actual_start", "Actual start"),
    ("actual_finish", "Actual finish"),
    ("percent_complete", "% complete"),
    ("status", "Status"),
    ("baseline_start", "Baseline start"),
    ("baseline_finish", "Baseline finish"),
    ("baseline_variance", "Baseline variance (days)"),
    ("predecessors", "Predecessors"),
    ("resource", "Resource"),
    ("budget_hours", "Budget hours"),
    ("budget_cost", "Budget cost"),
]


async def export(db: AsyncSession, project: Project, fmt: str) -> tuple[bytes, str, str]:
    settings = await get_settings(db, project)
    acts, deps = await load(db, project.id)
    codes = {a.id: a.code for a in acts}
    if fmt == "msp_xml":
        uid = {a.id: n for n, a in enumerate(acts, start=1)}
        preds: dict[int, list[tuple[int, str, int]]] = {}
        for d in deps:
            preds.setdefault(d.successor_id, []).append((uid[d.predecessor_id], d.type, d.lag))
        rows = [
            ExportActivity(
                uid=uid[a.id],
                wbs_code=a.wbs_code,
                name=a.name,
                outline_level=a.wbs_code.count(".") + 1,
                summary=a.type == ScheduleActivityType.SUMMARY,
                milestone=a.type == ScheduleActivityType.MILESTONE,
                duration=a.duration,
                start=a.early_start or a.planned_start or settings.start_date or date.today(),
                finish=a.early_finish or a.planned_finish or settings.start_date or date.today(),
                percent_complete=a.percent_complete,
                constraint_type=a.constraint_type,
                constraint_date=a.constraint_date,
                actual_start=a.actual_start,
                actual_finish=a.actual_finish,
                notes=a.notes,
                predecessors=preds.get(a.id, []),
            )
            for a in acts
        ]
        body = write_msp_xml(
            project.name,
            settings.start_date or date.today(),
            rows,
            list(settings.working_days or MON_FRI),
            [date.fromisoformat(h) for h in settings.holidays or []],
        )
        return body, "application/xml", "xml"

    pred_text: dict[int, list[str]] = {}
    for d in deps:
        lag = f"{'+' if d.lag > 0 else ''}{d.lag}d" if d.lag else ""
        pred_text.setdefault(d.successor_id, []).append(f"{codes.get(d.predecessor_id, d.predecessor_id)}{d.type}{lag}")
    rows_out = await read_activities(db, project.id, acts, settings)
    for r in rows_out:
        r["predecessors"] = ", ".join(pred_text.get(r["id"], []))
        r["is_critical"] = "Yes" if r["is_critical"] else ""
    return write_table(EXPORT_COLUMNS, rows_out, fmt, title="Schedule")

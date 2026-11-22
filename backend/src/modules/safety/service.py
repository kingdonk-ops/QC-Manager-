import calendar
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, history_of, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError
from ..common.exceptions import ValidationError as DomainValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..user.models import User
from .constants import (
    FLOW,
    LTIFR_BASE,
    OPEN_ACTIONS,
    TRIR_BASE,
    ActionStatus,
    IncidentStatus,
    IncidentType,
    ObservationKind,
    ParentType,
    RiskBand,
    risk_band,
)
from .models import HoursWorked, Incident, Observation, SafetyAction
from .schemas import (
    IncidentRead,
    ObservationRead,
    SafetyActionRead,
    SafetyDashboard,
    SafetyLagging,
    SafetyLeading,
    SafetyMatrixCell,
    SafetyMonthStats,
)

INCIDENT = "safety_incident"
OBSERVATION = "safety_observation"


class IncidentNotFoundError(ResourceNotFoundError):
    public_detail = "Incident not found."


class ObservationNotFoundError(ResourceNotFoundError):
    public_detail = "Observation not found."


class ActionNotFoundError(ResourceNotFoundError):
    public_detail = "Action not found."


class OpenActionsRemain(DomainValidationError):
    public_detail = "Close or cancel the incident's open actions first."


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


def rate(count: int, hours: float, base: int) -> float | None:
    """``count × base / hours``, to two decimals; None without hours."""
    return round(count * base / hours, 2) if hours > 0 else None


def score(severity: int | None, likelihood: int | None) -> tuple[int | None, str | None]:
    if severity is None or likelihood is None:
        return None, None
    value = severity * likelihood
    return value, risk_band(value)


def month_start(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def month_end(start: date) -> date:
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def link(kind: str, project_id: int, record_id: int) -> str:
    return f"/safety/{kind}?project={project_id}&id={record_id}"


# --- reads -------------------------------------------------------------------------------------------


async def _open_actions(db: AsyncSession, parent_type: str, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(SafetyAction.parent_id).where(
            SafetyAction.parent_type == parent_type, SafetyAction.parent_id.in_(ids), SafetyAction.status.in_(OPEN_ACTIONS)
        )
    )
    return Counter(rows.scalars())


async def read_incidents(db: AsyncSession, rows: list[Incident]) -> list[dict[str, Any]]:
    names = await user_names(db, {r.reported_by_id for r in rows})
    actions = await _open_actions(db, ParentType.INCIDENT, [r.id for r in rows])
    return [
        IncidentRead.model_validate(r)
        .model_copy(
            update={
                "reported_by_name": names.get(r.reported_by_id) if r.reported_by_id else None,
                "open_actions": actions.get(r.id, 0),
            }
        )
        .model_dump(mode="json")
        for r in rows
    ]


async def read_observations(db: AsyncSession, rows: list[Observation]) -> list[dict[str, Any]]:
    names = await user_names(db, {r.observer_id for r in rows})
    actions = await _open_actions(db, ParentType.OBSERVATION, [r.id for r in rows])
    return [
        ObservationRead.model_validate(r)
        .model_copy(
            update={
                "observer_name": names.get(r.observer_id) if r.observer_id else None,
                "open_actions": actions.get(r.id, 0),
            }
        )
        .model_dump(mode="json")
        for r in rows
    ]


async def read_actions(db: AsyncSession, rows: list[SafetyAction]) -> list[dict[str, Any]]:
    names = await user_names(db, {r.assignee_id for r in rows} | {r.verified_by_id for r in rows})
    incident_ids = {r.parent_id for r in rows if r.parent_type == ParentType.INCIDENT}
    observation_ids = {r.parent_id for r in rows if r.parent_type == ParentType.OBSERVATION}
    codes: dict[tuple[str, int], str] = {}
    if incident_ids:
        for i, c in (await db.execute(select(Incident.id, Incident.code).where(Incident.id.in_(incident_ids)))).tuples():
            codes[(ParentType.INCIDENT.value, i)] = c
    if observation_ids:
        for i, c in (
            await db.execute(select(Observation.id, Observation.code).where(Observation.id.in_(observation_ids)))
        ).tuples():
            codes[(ParentType.OBSERVATION.value, i)] = c
    today = date.today()
    return [
        SafetyActionRead.model_validate(r)
        .model_copy(
            update={
                "parent_code": codes.get((r.parent_type, r.parent_id)),
                "assignee_name": names.get(r.assignee_id) if r.assignee_id else None,
                "verified_by_name": names.get(r.verified_by_id) if r.verified_by_id else None,
                "overdue": bool(r.due_date and r.due_date < today and r.status in OPEN_ACTIONS),
            }
        )
        .model_dump(mode="json")
        for r in rows
    ]


# --- incidents ---------------------------------------------------------------------------------------


async def get_incident(db: AsyncSession, incident_id: int) -> Incident:
    i = await db.get(Incident, incident_id)
    if i is None:
        raise IncidentNotFoundError("No such incident")
    return i


async def create_incident(db: AsyncSession, values: dict[str, Any], user_id: int) -> Incident:
    project_id = values.pop("project_id")
    value, band = score(values["severity"], values["likelihood"])
    incident = Incident(
        project_id=project_id,
        code=await next_reference(db, "INC", project_id),
        reported_by_id=user_id,
        risk_score=value or 1,
        risk_band=band or RiskBand.LOW.value,
        status=IncidentStatus.REPORTED.value,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(incident)
    await db.flush()
    await record_transition(db, INCIDENT, incident.id, None, incident.status, user_id, "Reported")
    await db.commit()
    return incident


def apply_incident(incident: Incident, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        setattr(incident, key, value.value if hasattr(value, "value") else value)
    if not incident.lost_time:
        incident.days_lost = 0
    value, band = score(incident.severity, incident.likelihood)
    incident.risk_score, incident.risk_band = value or 1, band or RiskBand.LOW.value


async def change_incident_status(db: AsyncSession, incident: Incident, target: str, note: str | None, user_id: int) -> None:
    assert_transition(FLOW, incident.status, target)
    if target == IncidentStatus.CLOSED and (await _open_actions(db, ParentType.INCIDENT, [incident.id])).get(incident.id):
        raise OpenActionsRemain(f"incident {incident.id}")
    await record_transition(db, INCIDENT, incident.id, incident.status, target, user_id, note)
    incident.status = target
    incident.closed_at = datetime.now(UTC) if target == IncidentStatus.CLOSED else None
    await db.commit()


async def incident_history(db: AsyncSession, incident: Incident) -> list[dict[str, Any]]:
    rows = await history_of(db, INCIDENT, incident.id)
    names = await user_names(db, {r["changed_by_id"] for r in rows})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"]) if r["changed_by_id"] else None} for r in rows]


# --- observations ------------------------------------------------------------------------------------


async def get_observation(db: AsyncSession, observation_id: int) -> Observation:
    o = await db.get(Observation, observation_id)
    if o is None:
        raise ObservationNotFoundError("No such observation")
    return o


async def create_observation(db: AsyncSession, values: dict[str, Any], user_id: int) -> Observation:
    project_id = values.pop("project_id")
    value, band = score(values.get("severity"), values.get("likelihood"))
    observed_at = values.pop("observed_at", None) or datetime.now(UTC)
    observation = Observation(
        project_id=project_id,
        code=await next_reference(db, "OBS", project_id),
        observed_at=observed_at,
        observer_id=user_id,
        risk_score=value,
        risk_band=band,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items() if v is not None},
    )
    if observation.kind == ObservationKind.POSITIVE:
        observation.status = "closed"
    db.add(observation)
    await db.commit()
    return observation


def apply_observation(observation: Observation, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        setattr(observation, key, value.value if hasattr(value, "value") else value)
    observation.risk_score, observation.risk_band = score(observation.severity, observation.likelihood)


# --- actions -----------------------------------------------------------------------------------------


async def parent_of(db: AsyncSession, parent_type: str, parent_id: int) -> Incident | Observation:
    if parent_type == ParentType.INCIDENT:
        return await get_incident(db, parent_id)
    return await get_observation(db, parent_id)


async def get_action(db: AsyncSession, action_id: int) -> SafetyAction:
    a = await db.get(SafetyAction, action_id)
    if a is None:
        raise ActionNotFoundError("No such action")
    return a


async def notify_assignee(db: AsyncSession, action: SafetyAction, parent_code: str, actor_id: int) -> None:
    if action.assignee_id:
        kind = "incidents" if action.parent_type == ParentType.INCIDENT else "observations"
        await notify(
            db,
            [action.assignee_id],
            Category.ASSIGNMENT,
            f"{parent_code}: safety action",
            body=action.description[:300] + (f" (due {action.due_date.isoformat()})" if action.due_date else ""),
            link=link(kind, action.project_id, action.parent_id),
            entity=(INCIDENT if action.parent_type == ParentType.INCIDENT else OBSERVATION, action.parent_id),
            actor_id=actor_id,
        )


async def create_action(db: AsyncSession, parent: Incident | Observation, values: dict[str, Any], user_id: int) -> SafetyAction:
    action = SafetyAction(
        project_id=parent.project_id,
        created_by_id=user_id,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(action)
    await db.flush()
    if isinstance(parent, Incident) and parent.status in (IncidentStatus.REPORTED, IncidentStatus.INVESTIGATING):
        await record_transition(db, INCIDENT, parent.id, parent.status, IncidentStatus.ACTIONS_OPEN, user_id, "Action added")
        parent.status = IncidentStatus.ACTIONS_OPEN.value
    await notify_assignee(db, action, parent.code, user_id)
    await db.commit()
    return action


async def update_action(db: AsyncSession, action: SafetyAction, changes: dict[str, Any], user_id: int) -> None:
    before_status, before_assignee = action.status, action.assignee_id
    for key, value in changes.items():
        setattr(action, key, value.value if hasattr(value, "value") else value)
    if action.status != before_status:
        now = datetime.now(UTC)
        if action.status in (ActionStatus.DONE, ActionStatus.VERIFIED) and action.completed_at is None:
            action.completed_at = now
        if action.status in OPEN_ACTIONS:
            action.completed_at = None
        if action.status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = user_id, now
        elif before_status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = None, None
    if action.assignee_id and action.assignee_id != before_assignee:
        parent = await parent_of(db, action.parent_type, action.parent_id)
        await notify_assignee(db, action, parent.code, user_id)
    await db.commit()


# --- dashboard ---------------------------------------------------------------------------------------


def _bounds(date_from: date | None, date_to: date | None) -> list[Any]:
    out: list[Any] = []
    if date_from:
        out.append(datetime.combine(date_from, time.min, tzinfo=UTC))
    else:
        out.append(None)
    if date_to:
        out.append(datetime.combine(date_to, time.max, tzinfo=UTC))
    else:
        out.append(None)
    return out


async def dashboard(
    db: AsyncSession,
    project_ids: list[int],
    date_from: date | None = None,
    date_to: date | None = None,
    base: int | None = None,
) -> SafetyDashboard:
    trir_base, ltifr_base = (base, base) if base else (TRIR_BASE, LTIFR_BASE)
    start, end = _bounds(date_from, date_to)

    incident_q = select(Incident).where(Incident.project_id.in_(project_ids))
    observation_q = select(Observation).where(Observation.project_id.in_(project_ids))
    hours_q = select(HoursWorked).where(HoursWorked.project_id.in_(project_ids))
    if start is not None:
        incident_q = incident_q.where(Incident.occurred_at >= start)
        observation_q = observation_q.where(Observation.observed_at >= start)
        hours_q = hours_q.where(HoursWorked.month >= date(start.year, start.month, 1))
    if end is not None:
        incident_q = incident_q.where(Incident.occurred_at <= end)
        observation_q = observation_q.where(Observation.observed_at <= end)
        hours_q = hours_q.where(HoursWorked.month <= end.date())
    incidents = list((await db.execute(incident_q)).scalars())
    observations = list((await db.execute(observation_q)).scalars())
    hours_rows = list((await db.execute(hours_q)).scalars())
    actions = list((await db.execute(select(SafetyAction).where(SafetyAction.project_id.in_(project_ids)))).scalars())

    hours = sum(h.hours for h in hours_rows)
    recordables = sum(1 for i in incidents if i.recordable)
    ltis = sum(1 for i in incidents if i.lost_time)
    near_misses = sum(1 for i in incidents if i.type == IncidentType.NEAR_MISS)
    positive = sum(1 for o in observations if o.kind == ObservationKind.POSITIVE)

    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for h in hours_rows:
        monthly[h.month.strftime("%Y-%m")]["hours"] += h.hours
    for i in incidents:
        m = monthly[i.occurred_at.strftime("%Y-%m")]
        m["incidents"] += 1
        m["recordables"] += i.recordable
        m["lost_time_injuries"] += i.lost_time
        m["near_misses"] += i.type == IncidentType.NEAR_MISS
    for o in observations:
        m = monthly[o.observed_at.strftime("%Y-%m")]
        m["observations"] += 1
        m["positive_observations"] += o.kind == ObservationKind.POSITIVE

    cells: dict[tuple[int, int], list[int]] = {(s, lk): [0, 0] for s in range(1, 6) for lk in range(1, 6)}
    for i in incidents:
        cells[(i.severity, i.likelihood)][0] += 1
    for o in observations:
        if o.severity and o.likelihood:
            cells[(o.severity, o.likelihood)][1] += 1

    today = date.today()
    open_actions = [a for a in actions if a.status in OPEN_ACTIONS]
    closed_with_due = [a for a in actions if a.status in (ActionStatus.DONE, ActionStatus.VERIFIED) and a.due_date]
    on_time = sum(1 for a in closed_with_due if a.completed_at and a.due_date and a.completed_at.date() <= a.due_date)

    trir, ltifr = rate(recordables, hours, trir_base), rate(ltis, hours, ltifr_base)
    return SafetyDashboard(
        project_ids=project_ids,
        date_from=date_from,
        date_to=date_to,
        hours_worked=hours,
        trir_base=trir_base,
        ltifr_base=ltifr_base,
        trir=trir,
        ltifr=ltifr,
        near_miss_ratio=round(near_misses / recordables, 2) if recordables else None,
        by_type={t.value: sum(1 for i in incidents if i.type == t) for t in IncidentType},
        by_band={b.value: sum(1 for i in incidents if i.risk_band == b) for b in RiskBand},
        open_actions=len(open_actions),
        overdue_actions=sum(1 for a in open_actions if a.due_date and a.due_date < today),
        leading=SafetyLeading(
            observations=len(observations),
            positive_observations=positive,
            negative_observations=len(observations) - positive,
            positive_ratio=round(positive / len(observations), 3) if observations else None,
            actions_closed_on_time_pct=round(on_time * 100 / len(closed_with_due), 1) if closed_with_due else None,
        ),
        lagging=SafetyLagging(
            incidents=len(incidents),
            recordables=recordables,
            lost_time_injuries=ltis,
            days_lost=sum(i.days_lost for i in incidents),
            near_misses=near_misses,
            trir=trir,
            ltifr=ltifr,
        ),
        monthly=[
            SafetyMonthStats(
                month=month,
                hours=m["hours"],
                incidents=int(m["incidents"]),
                recordables=int(m["recordables"]),
                lost_time_injuries=int(m["lost_time_injuries"]),
                near_misses=int(m["near_misses"]),
                observations=int(m["observations"]),
                positive_observations=int(m["positive_observations"]),
                trir=rate(int(m["recordables"]), m["hours"], trir_base),
                ltifr=rate(int(m["lost_time_injuries"]), m["hours"], ltifr_base),
            )
            for month, m in sorted(monthly.items())
        ],
        risk_matrix=[
            SafetyMatrixCell(
                severity=s,
                likelihood=lk,
                score=s * lk,
                band=risk_band(s * lk) or RiskBand.LOW.value,
                incidents=n[0],
                observations=n[1],
            )
            for (s, lk), n in sorted(cells.items())
        ],
    )


# --- monthly summary PDF -----------------------------------------------------------------------------


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


async def summary_pdf(db: AsyncSession, project: Project, month: str) -> bytes:
    start = month_start(month)
    end = month_end(start)
    this = await dashboard(db, [project.id], start, end)
    ytd = await dashboard(db, [project.id], date(start.year, 1, 1), end)
    doc = Document(
        title=f"Safety summary {start.strftime('%B %Y')}",
        subtitle=f"{project.code} {project.name}",
        footer=f"Safety summary {project.code} {month}",
    )
    doc.heading("Key figures")
    doc.table(
        ["Measure", start.strftime("%b %Y"), "Year to date"],
        [
            ["Hours worked", _fmt(this.hours_worked), _fmt(ytd.hours_worked)],
            ["Incidents", this.lagging.incidents, ytd.lagging.incidents],
            ["Recordable incidents", this.lagging.recordables, ytd.lagging.recordables],
            ["Lost-time injuries", this.lagging.lost_time_injuries, ytd.lagging.lost_time_injuries],
            ["Days lost", this.lagging.days_lost, ytd.lagging.days_lost],
            ["Near misses", this.lagging.near_misses, ytd.lagging.near_misses],
            [f"TRIR (per {this.trir_base:,} h)", _fmt(this.trir), _fmt(ytd.trir)],
            [f"LTIFR (per {this.ltifr_base:,} h)", _fmt(this.ltifr), _fmt(ytd.ltifr)],
            ["Observations", this.leading.observations, ytd.leading.observations],
            [
                "Positive observations",
                f"{this.leading.positive_observations} ({_pct(this.leading.positive_ratio)})",
                f"{ytd.leading.positive_observations} ({_pct(ytd.leading.positive_ratio)})",
            ],
            ["Open corrective actions", this.open_actions, ""],
            ["Overdue corrective actions", this.overdue_actions, ""],
        ],
        widths=[0.5, 0.25, 0.25],
        numeric={1, 2},
    )
    doc.paragraph(
        "TRIR = recordable incidents × 200,000 / hours worked. LTIFR = lost-time injuries × 1,000,000 / hours worked."
    )
    lo, hi = _bounds(start, end)
    incidents = list(
        (
            await db.execute(
                select(Incident)
                .where(Incident.project_id == project.id, Incident.occurred_at >= lo, Incident.occurred_at <= hi)
                .order_by(Incident.occurred_at)
            )
        ).scalars()
    )
    doc.heading("Incidents this month")
    if incidents:
        doc.table(
            ["Ref", "Date", "Type", "Title", "Risk", "Rec.", "LTI", "Status"],
            [
                [
                    i.code,
                    i.occurred_at.strftime("%d %b"),
                    i.type.replace("_", " "),
                    i.title,
                    f"{i.risk_score} {i.risk_band}",
                    "Y" if i.recordable else "",
                    f"{i.days_lost}d" if i.lost_time else "",
                    i.status.replace("_", " "),
                ]
                for i in incidents
            ],
            widths=[0.09, 0.08, 0.14, 0.33, 0.1, 0.05, 0.06, 0.15],
        )
    else:
        doc.paragraph("No incidents reported.")
    doc.heading("Incidents by type (month)")
    doc.table(["Type", "Count"], [[k.replace("_", " "), v] for k, v in this.by_type.items()], widths=[0.6, 0.2], numeric={1})
    return render_pdf(doc)


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"

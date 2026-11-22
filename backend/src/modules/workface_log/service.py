"""The daily workface log. No FastAPI imports.

Signing a log publishes ``workface_log.day.signed``::

    {"project_id": 1, "log_id": 7, "code": "DWL-007", "crew_id": 2, "work_date": "2026-11-24", "shift": "day",
     "hours_by_anchor": {"41": 36.0, "42": 8.0},          # productive hours per work-anchor node id
     "qty_by_node": {"41": 14.0},                          # installed quantity per progress-unit node id
     "delay_hours_by_code": {"weather": 6.0}, "overhead_hours_by_code": {"toolbox": 4.0},
     "total_hours": 54.0, "signed_by_id": 3}

How ``evm`` should consume it (not wired here, so ``evm`` stays independent of this module): subscribe in
``evm/events.py`` and enqueue a Taskiq task (handlers have no database session). The task maps each work anchor
to a work package — ``asset_nodes.wbs_code == evm_work_packages.wbs``, or the anchor's ``schedule_link`` activity
equal to ``evm_work_packages.schedule_activity_id`` — and adds the hours to that package's ``evm_progress`` row
for ``data_date = work_date`` (progress is cumulative: start from the latest earlier row, and carry the added
hours into later rows). Delay and overhead hours stay out of earned-value actuals unless the project books them
to an overhead package. Re-signing never happens (signed is final), so the event is delivered once per log.

The planner reads actuals through ``planner.readiness.register_actuals`` (registered below), not the event.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.constants import Role
from ..asset_tree.models import AssetNode
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..planner import service as planner
from ..planner.models import Crew
from ..planner.readiness import Actual, register_actuals
from .constants import LOG_FLOW, LogStatus
from .models import DailyLog, LogDelay, LogEquipment, LogHours, LogQuantity
from .schemas import LogDelayRead, LogEquipmentRead, LogHoursRead, LogQuantityRead, LogRead, WorkfaceAnchorTotal, WorkfaceTotals

ZERO = Decimal(0)


class LogNotFound(ResourceNotFoundError):
    public_detail = "Daily log not found."


class LogExists(ResourceExistsError):
    public_detail = "That crew already has a log for that day and shift."


class LogRuleError(ValidationError):
    public_detail = "That change breaks the log's rules."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class NoAllocation(tree.NoWorkAnchor):
    """Hours with neither a work anchor nor a delay/overhead code."""

    def __init__(self, person: str) -> None:
        super().__init__()
        self.public_detail = (  # type: ignore[misc]
            f"{person}: hours need a work anchor (e.g. RSW), or a delay or overhead code."
        )


def link_of(log: DailyLog) -> str:
    return f"/workface-log?project={log.project_id}&id={log.id}"


async def get_log(db: AsyncSession, log_id: int) -> DailyLog:
    log = await db.get(DailyLog, log_id)
    if log is None:
        raise LogNotFound(str(log_id))
    return log


def _require_draft(log: DailyLog) -> None:
    if log.status != LogStatus.DRAFT:
        raise LogRuleError(f"{log.code} is {log.status}; only a draft can change.")


# --- writing -------------------------------------------------------------------------------------------


async def create_log(db: AsyncSession, values: dict[str, Any], user_id: int) -> DailyLog:
    project_id = values["project_id"]
    crew = await planner.get_crew(db, values["crew_id"], project_id)
    prefill = values.pop("prefill", True)
    if await db.scalar(
        select(DailyLog.id).where(
            DailyLog.crew_id == crew.id, DailyLog.work_date == values["work_date"], DailyLog.shift == values["shift"]
        )
    ):
        raise LogExists(f"{crew.code} {values['work_date']} {values['shift']}")
    if values.get("area_node_id"):
        await tree.get_node(db, values["area_node_id"], project_id)
    log = DailyLog(
        code=await next_reference(db, "DWL", project_id),
        supervisor_id=crew.supervisor_id or user_id,
        **values,
    )
    db.add(log)
    await db.flush()
    if prefill:
        await _prefill(db, log, crew)
    await record_transition(db, "workface_log", log.id, None, log.status, user_id)
    return log


async def _prefill(db: AsyncSession, log: DailyLog, crew: Crew) -> None:
    """Crew members (0 h) on the first planned anchor, and a 0-quantity line per anchor the planner put them on."""
    planned = await planner.daily_plan(db, log.project_id, log.work_date, crew.id)
    anchors = list(dict.fromkeys(a.anchor_id for a in planned))
    nodes = await planner.nodes_by_id(db, set(anchors))
    for seq, member in enumerate(crew.members or [], start=1):
        db.add(
            LogHours(
                log_id=log.id,
                person=str(member.get("name", ""))[:120] or f"Member {seq}",
                hours=ZERO,
                user_id=member.get("user_id"),
                trade=member.get("trade"),
                anchor_id=anchors[0] if anchors else None,
                seq=seq,
            )
        )
    for seq, anchor_id in enumerate(anchors, start=1):
        node = nodes.get(anchor_id)
        db.add(
            LogQuantity(
                log_id=log.id, node_id=anchor_id, anchor_id=anchor_id, qty=ZERO, uom=node.uom if node else None, seq=seq
            )
        )
    await db.flush()


async def _anchor(db: AsyncSession, project_id: int, node_id: int | None) -> int | None:
    if not node_id:
        return None
    return (await planner.resolve_anchor(db, project_id, node_id)).id


async def _hours_rows(db: AsyncSession, log: DailyLog, rows: list[dict[str, Any]]) -> list[LogHours]:
    out = []
    for seq, r in enumerate(rows, start=1):
        node_id = r.pop("node_id", None)
        if r.get("delay_code") and r.get("overhead_code"):
            raise LogRuleError(f"{r['person']}: give a delay code or an overhead code, not both.")
        anchor_id = await _anchor(db, log.project_id, node_id)
        if anchor_id is None and not r.get("delay_code") and not r.get("overhead_code") and r["hours"] > 0:
            raise NoAllocation(r["person"])
        out.append(LogHours(log_id=log.id, anchor_id=anchor_id, seq=seq, **r))
    return out


async def _quantity_rows(db: AsyncSession, log: DailyLog, rows: list[dict[str, Any]]) -> list[LogQuantity]:
    out = []
    for seq, r in enumerate(rows, start=1):
        node = await tree.get_node(db, r.pop("node_id"), log.project_id)
        anchor = await tree.work_anchor_for(db, node.id)
        target = node if await tree.has_role(db, node, Role.PROGRESS_UNIT) else anchor
        out.append(
            LogQuantity(
                log_id=log.id, node_id=target.id, anchor_id=anchor.id, seq=seq, **{**r, "uom": r.get("uom") or target.uom}
            )
        )
    return out


async def update_log(db: AsyncSession, log: DailyLog, values: dict[str, Any]) -> None:
    _require_draft(log)
    hours, quantities = values.pop("hours", None), values.pop("quantities", None)
    delays, equipment = values.pop("delays", None), values.pop("equipment", None)
    if values.get("area_node_id"):
        await tree.get_node(db, values["area_node_id"], log.project_id)
    for key, value in values.items():
        setattr(log, key, value)
    if hours is not None:
        new_hours = await _hours_rows(db, log, hours)
        await db.execute(delete(LogHours).where(LogHours.log_id == log.id))
        db.add_all(new_hours)
    if quantities is not None:
        new_qty = await _quantity_rows(db, log, quantities)
        await db.execute(delete(LogQuantity).where(LogQuantity.log_id == log.id))
        db.add_all(new_qty)
    if delays is not None:
        rows = [
            LogDelay(log_id=log.id, seq=seq, anchor_id=await _anchor(db, log.project_id, d.pop("node_id", None)), **d)
            for seq, d in enumerate(delays, start=1)
        ]
        await db.execute(delete(LogDelay).where(LogDelay.log_id == log.id))
        db.add_all(rows)
    if equipment is not None:
        kit = [
            LogEquipment(log_id=log.id, seq=seq, anchor_id=await _anchor(db, log.project_id, e.pop("node_id", None)), **e)
            for seq, e in enumerate(equipment, start=1)
        ]
        await db.execute(delete(LogEquipment).where(LogEquipment.log_id == log.id))
        db.add_all(kit)
    await db.flush()


async def copy_previous(db: AsyncSession, log: DailyLog) -> DailyLog:
    """Copy yesterday: the crew's people, hours and equipment from its last earlier log."""
    _require_draft(log)
    previous = await db.scalar(
        select(DailyLog)
        .where(DailyLog.crew_id == log.crew_id, DailyLog.work_date < log.work_date)
        .order_by(DailyLog.work_date.desc(), DailyLog.id.desc())
        .limit(1)
    )
    if previous is None:
        raise LogRuleError("This crew has no earlier log to copy.")
    hours = (await db.execute(select(LogHours).where(LogHours.log_id == previous.id).order_by(LogHours.seq))).scalars().all()
    kit = (
        await db.execute(select(LogEquipment).where(LogEquipment.log_id == previous.id).order_by(LogEquipment.seq))
    ).scalars()
    await db.execute(delete(LogHours).where(LogHours.log_id == log.id))
    await db.execute(delete(LogEquipment).where(LogEquipment.log_id == log.id))
    db.add_all(
        [
            LogHours(
                log_id=log.id,
                person=h.person,
                hours=h.hours,
                user_id=h.user_id,
                trade=h.trade,
                anchor_id=h.anchor_id,
                delay_code=h.delay_code,
                overhead_code=h.overhead_code,
                seq=h.seq,
            )
            for h in hours
        ]
        + [
            LogEquipment(log_id=log.id, equipment=e.equipment, hours=e.hours, status=e.status, anchor_id=e.anchor_id, seq=e.seq)
            for e in kit
        ]
    )
    await db.flush()
    return previous


# --- reading -------------------------------------------------------------------------------------------


def category_of(h: LogHours) -> str:
    if h.delay_code:
        return "delay"
    if h.overhead_code:
        return "overhead"
    return "productive"


def totals_of(
    hours: Sequence[LogHours], quantities: Sequence[LogQuantity], equipment: Sequence[LogEquipment], nodes: dict[int, AssetNode]
) -> WorkfaceTotals:
    by_anchor: dict[int, list[Any]] = defaultdict(lambda: [ZERO, ZERO, None])
    delay: dict[str, Decimal] = defaultdict(Decimal)
    overhead: dict[str, Decimal] = defaultdict(Decimal)
    productive = ZERO
    for h in hours:
        cat = category_of(h)
        if cat == "delay":
            delay[h.delay_code or "other"] += h.hours
        elif cat == "overhead":
            overhead[h.overhead_code or "other"] += h.hours
        else:
            productive += h.hours
            if h.anchor_id:
                by_anchor[h.anchor_id][0] += h.hours
    for q in quantities:
        by_anchor[q.anchor_id][1] += q.qty
        by_anchor[q.anchor_id][2] = by_anchor[q.anchor_id][2] or q.uom
    rows = []
    for anchor_id, (h_, q_, uom) in by_anchor.items():
        node = nodes.get(anchor_id)
        rows.append(
            WorkfaceAnchorTotal(
                anchor_id=anchor_id,
                anchor_code=(node.display_code or node.code) if node else str(anchor_id),
                anchor_path=node.display_path if node else "",
                hours=h_,
                qty=q_,
                uom=uom,
            )
        )
    rows.sort(key=lambda r: r.anchor_path)
    delay_total = sum(delay.values(), ZERO)
    overhead_total = sum(overhead.values(), ZERO)
    return WorkfaceTotals(
        productive_hours=productive,
        delay_hours=delay_total,
        overhead_hours=overhead_total,
        total_hours=productive + delay_total + overhead_total,
        headcount=len({h.person.strip().lower() for h in hours if h.hours > 0}),
        equipment_hours=sum((e.hours for e in equipment), ZERO),
        by_anchor=rows,
        by_delay_code=dict(delay),
        by_overhead_code=dict(overhead),
    )


async def _children(db: AsyncSession, log_ids: list[int]) -> tuple[dict, dict, dict, dict]:
    def grouped(rows: Any) -> dict[int, list[Any]]:
        out: dict[int, list[Any]] = defaultdict(list)
        for r in rows:
            out[r.log_id].append(r)
        return out

    if not log_ids:
        return {}, {}, {}, {}
    return (
        grouped((await db.execute(select(LogHours).where(LogHours.log_id.in_(log_ids)).order_by(LogHours.seq))).scalars()),
        grouped(
            (await db.execute(select(LogQuantity).where(LogQuantity.log_id.in_(log_ids)).order_by(LogQuantity.seq))).scalars()
        ),
        grouped((await db.execute(select(LogDelay).where(LogDelay.log_id.in_(log_ids)).order_by(LogDelay.seq))).scalars()),
        grouped(
            (
                await db.execute(select(LogEquipment).where(LogEquipment.log_id.in_(log_ids)).order_by(LogEquipment.seq))
            ).scalars()
        ),
    )


async def quantity_warnings(db: AsyncSession, log: DailyLog, quantities: Sequence[LogQuantity]) -> list[str]:
    """Amber flags: today's quantity takes a node past its budget (not yet counted while the log is unsigned)."""
    nodes = await planner.nodes_by_id(db, {q.node_id for q in quantities})
    today: dict[int, Decimal] = defaultdict(Decimal)
    for q in quantities:
        today[q.node_id] += q.qty
    out = []
    for node_id, qty in today.items():
        node = nodes.get(node_id)
        if node is None or node.budget_qty is None:
            continue
        earned = (node.earned_qty or ZERO) + (ZERO if log.progress_applied else qty)
        if earned > node.budget_qty:
            out.append(
                f"{node.code}: {earned:g} {node.uom or ''} installed exceeds the budget of {node.budget_qty:g}.".replace(
                    "  ", " "
                )
            )
    return out


async def read_logs(db: AsyncSession, logs: list[DailyLog], *, detail: bool = False) -> list[dict[str, Any]]:
    ids = [log.id for log in logs]
    crews = (
        {c.id: c for c in (await db.execute(select(Crew).where(Crew.id.in_({log.crew_id for log in logs})))).scalars()}
        if logs
        else {}
    )
    names = await planner.user_names(db, {log.supervisor_id for log in logs} | {log.signed_by_id for log in logs})
    hours, quantities, delays, kit = await _children(db, ids)
    anchor_ids = {h.anchor_id for hs in hours.values() for h in hs if h.anchor_id}
    anchor_ids |= {q.anchor_id for qs in quantities.values() for q in qs} | {
        q.node_id for qs in quantities.values() for q in qs
    }
    anchor_ids |= {d.anchor_id for ds in delays.values() for d in ds if d.anchor_id}
    anchor_ids |= {e.anchor_id for es in kit.values() for e in es if e.anchor_id}
    nodes = await planner.nodes_by_id(db, anchor_ids) if detail else {}

    def code(node_id: int | None) -> str | None:
        node = nodes.get(node_id or 0)
        return (node.display_code or node.code) if node else None

    out = []
    for log in logs:
        crew = crews.get(log.crew_id)
        hs, qs, ds, es = hours.get(log.id, []), quantities.get(log.id, []), delays.get(log.id, []), kit.get(log.id, [])
        update: dict[str, Any] = {
            "crew_code": crew.code if crew else None,
            "crew_name": crew.name if crew else None,
            "supervisor_name": names.get(log.supervisor_id or 0),
            "signed_by_name": names.get(log.signed_by_id or 0),
            "total_hours": sum((h.hours for h in hs), ZERO),
        }
        if detail:
            update |= {
                "hours": [
                    LogHoursRead.model_validate(h).model_copy(
                        update={"anchor_code": code(h.anchor_id), "category": category_of(h)}
                    )
                    for h in hs
                ],
                "quantities": [
                    LogQuantityRead.model_validate(q).model_copy(
                        update={"anchor_code": code(q.anchor_id), "node_code": code(q.node_id)}
                    )
                    for q in qs
                ],
                "delays": [LogDelayRead.model_validate(d).model_copy(update={"anchor_code": code(d.anchor_id)}) for d in ds],
                "equipment": [
                    LogEquipmentRead.model_validate(e).model_copy(update={"anchor_code": code(e.anchor_id)}) for e in es
                ],
                "totals": totals_of(hs, qs, es, nodes),
                "warnings": await quantity_warnings(db, log, qs),
            }
        out.append(LogRead.model_validate(log).model_copy(update=update).model_dump(mode="json"))
    return out


# --- flow ----------------------------------------------------------------------------------------------


async def submit(db: AsyncSession, log: DailyLog, user_id: int, note: str | None) -> None:
    assert_transition(LOG_FLOW, log.status, LogStatus.SUBMITTED)
    hours = (await db.execute(select(LogHours).where(LogHours.log_id == log.id))).scalars().all()
    if not any(h.hours > 0 for h in hours):
        raise LogRuleError("Record the crew's hours before submitting.")
    for h in hours:
        if h.hours > 0 and not (h.anchor_id or h.delay_code or h.overhead_code):
            raise NoAllocation(h.person)
    await record_transition(db, "workface_log", log.id, log.status, LogStatus.SUBMITTED, user_id, note)
    log.status = LogStatus.SUBMITTED
    log.submitted_at, log.submitted_by_id = datetime.now(UTC), user_id
    await notify(
        db,
        [log.supervisor_id or 0],
        Category.APPROVAL,
        f"Daily log {log.code} is ready for sign-off",
        body=f"{log.work_date:%a %d %b} {log.shift} shift",
        link=link_of(log),
        entity=("workface_log", log.id),
        actor_id=user_id,
    )
    await db.flush()


async def return_log(db: AsyncSession, log: DailyLog, user_id: int, note: str | None) -> None:
    assert_transition(LOG_FLOW, log.status, LogStatus.DRAFT)
    await record_transition(db, "workface_log", log.id, log.status, LogStatus.DRAFT, user_id, note)
    log.status = LogStatus.DRAFT
    await notify(
        db,
        [log.submitted_by_id or 0],
        Category.STATUS,
        f"Daily log {log.code} returned for changes",
        body=note,
        link=link_of(log),
        entity=("workface_log", log.id),
        actor_id=user_id,
    )
    await db.flush()


async def sign(db: AsyncSession, log: DailyLog, user_id: int, note: str | None) -> dict[str, Any]:
    """Supervisor sign-off: lock the log, add its quantities to ``earned_qty``, publish the day's hours."""
    assert_transition(LOG_FLOW, log.status, LogStatus.SIGNED)
    hours = (await db.execute(select(LogHours).where(LogHours.log_id == log.id))).scalars().all()
    quantities = (await db.execute(select(LogQuantity).where(LogQuantity.log_id == log.id))).scalars().all()
    if not log.progress_applied:
        per_node: dict[int, Decimal] = defaultdict(Decimal)
        for q in quantities:
            per_node[q.node_id] += q.qty
        nodes = await planner.nodes_by_id(db, set(per_node))
        for node_id, qty in per_node.items():
            node = nodes[node_id]
            node.earned_qty = (node.earned_qty or ZERO) + qty
        log.progress_applied = True
    await record_transition(db, "workface_log", log.id, log.status, LogStatus.SIGNED, user_id, note)
    log.status = LogStatus.SIGNED
    log.signed_at, log.signed_by_id, log.sign_note = datetime.now(UTC), user_id, note
    await notify(
        db,
        [log.submitted_by_id or 0],
        Category.STATUS,
        f"Daily log {log.code} signed off",
        link=link_of(log),
        entity=("workface_log", log.id),
        actor_id=user_id,
    )
    await db.flush()
    by_anchor: dict[int, Decimal] = defaultdict(Decimal)
    delay: dict[str, Decimal] = defaultdict(Decimal)
    overhead: dict[str, Decimal] = defaultdict(Decimal)
    for h in hours:
        cat = category_of(h)
        if cat == "delay":
            delay[h.delay_code or "other"] += h.hours
        elif cat == "overhead":
            overhead[h.overhead_code or "other"] += h.hours
        elif h.anchor_id:
            by_anchor[h.anchor_id] += h.hours
    qty_by_node: dict[int, Decimal] = defaultdict(Decimal)
    for q in quantities:
        qty_by_node[q.node_id] += q.qty
    return {
        "project_id": log.project_id,
        "log_id": log.id,
        "code": log.code,
        "crew_id": log.crew_id,
        "work_date": log.work_date.isoformat(),
        "shift": log.shift,
        "hours_by_anchor": {str(k): float(v) for k, v in by_anchor.items()},
        "qty_by_node": {str(k): float(v) for k, v in qty_by_node.items()},
        "delay_hours_by_code": {k: float(v) for k, v in delay.items()},
        "overhead_hours_by_code": {k: float(v) for k, v in overhead.items()},
        "total_hours": float(sum((h.hours for h in hours), ZERO)),
        "signed_by_id": user_id,
    }


async def publish_signed(payload: dict[str, Any]) -> None:
    await publish("workface_log.day.signed", payload)


# --- roll-ups ------------------------------------------------------------------------------------------


async def rollup(
    db: AsyncSession,
    project_id: int,
    start: date | None = None,
    end: date | None = None,
    anchor_ids: Sequence[int] | None = None,
    *,
    signed_only: bool = True,
) -> dict[int, Actual]:
    """Productive hours and installed quantity per work anchor."""
    where: list[Any] = [DailyLog.project_id == project_id]
    if signed_only:
        where.append(DailyLog.status == LogStatus.SIGNED)
    if start:
        where.append(DailyLog.work_date >= start)
    if end:
        where.append(DailyLog.work_date <= end)
    hours_q = (
        select(LogHours.anchor_id, func.sum(LogHours.hours))
        .join(DailyLog, DailyLog.id == LogHours.log_id)
        .where(*where, LogHours.anchor_id.is_not(None), LogHours.delay_code.is_(None), LogHours.overhead_code.is_(None))
        .group_by(LogHours.anchor_id)
    )
    qty_q = (
        select(LogQuantity.anchor_id, func.sum(LogQuantity.qty))
        .join(DailyLog, DailyLog.id == LogQuantity.log_id)
        .where(*where)
        .group_by(LogQuantity.anchor_id)
    )
    if anchor_ids is not None:
        hours_q = hours_q.where(LogHours.anchor_id.in_(anchor_ids))
        qty_q = qty_q.where(LogQuantity.anchor_id.in_(anchor_ids))
    out: dict[int, Actual] = defaultdict(Actual)
    for anchor_id, total in (await db.execute(hours_q)).tuples():
        if anchor_id is not None:
            out[anchor_id].hours = total or ZERO
    for anchor_id, total in (await db.execute(qty_q)).tuples():
        out[anchor_id].qty = total or ZERO
    return dict(out)


async def _actuals(
    db: AsyncSession, project_id: int, anchor_ids: Sequence[int], start: date | None, end: date | None
) -> dict[int, Actual]:
    return await rollup(db, project_id, start, end, anchor_ids)


register_actuals("workface_log", _actuals)


async def day_summary(db: AsyncSession, project_id: int, day: date) -> dict[str, Any]:
    crews = list(
        (
            await db.execute(select(Crew).where(Crew.project_id == project_id, Crew.active.is_(True)).order_by(Crew.code))
        ).scalars()
    )
    logs = list(
        (await db.execute(select(DailyLog).where(DailyLog.project_id == project_id, DailyLog.work_date == day))).scalars()
    )
    hours, quantities, _delays, kit = await _children(db, [log.id for log in logs])
    planned = await planner.daily_plan(db, project_id, day, None)
    planned_per_crew: dict[int, set[int]] = defaultdict(set)
    for a in planned:
        planned_per_crew[a.crew_id].add(a.anchor_id)
    all_h = [h for hs in hours.values() for h in hs]
    all_q = [q for qs in quantities.values() for q in qs]
    all_e = [e for es in kit.values() for e in es]
    nodes = await planner.nodes_by_id(db, {h.anchor_id for h in all_h if h.anchor_id} | {q.anchor_id for q in all_q})
    by_crew: dict[int, list[DailyLog]] = defaultdict(list)
    for log in logs:
        by_crew[log.crew_id].append(log)
    rows = []
    for crew in crews:
        crew_logs = by_crew.get(crew.id, [])
        if not crew_logs and crew.id not in planned_per_crew:
            continue
        hs = [h for log in crew_logs for h in hours.get(log.id, [])]
        t = totals_of(hs, [], [], {})
        first = crew_logs[0] if crew_logs else None
        rows.append(
            {
                "crew_id": crew.id,
                "crew_code": crew.code,
                "crew_name": crew.name,
                "log_id": first.id if first else None,
                "log_code": first.code if first else None,
                "status": first.status if first else None,
                "total_hours": t.total_hours,
                "productive_hours": t.productive_hours,
                "delay_hours": t.delay_hours,
                "planned_anchors": len(planned_per_crew.get(crew.id, set())),
            }
        )
    return {"project_id": project_id, "work_date": day, "crews": rows, "totals": totals_of(all_h, all_q, all_e, nodes)}

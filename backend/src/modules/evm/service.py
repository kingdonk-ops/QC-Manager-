"""Work packages, progress, metrics, S-curves and snapshots. No FastAPI imports.

Progress records are cumulative: a package's state at any date is its latest record on or before
that date, so a data date needs no record for every package.
"""

import bisect
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ..projects.models import Project
from . import calc
from .constants import Basis, Curve, EacMethod, GroupBy, Interval
from .exceptions import SnapshotNotFoundError, WorkPackageCodeTakenError, WorkPackageNotFoundError
from .models import BudgetSnapshot, EvmSettings, ProgressRecord, WorkPackage
from .schemas import EvmProgressEntry, EvmSnapshotRead, EvmWorkPackageRead

NO_GROUP = "(unassigned)"


# --- plain views of packages and progress -------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """What the calculations need of a package: from the live table or a snapshot."""

    id: int | None
    code: str
    name: str
    control_account: str | None
    discipline: str | None
    start: date | None
    finish: date | None
    hours: float
    cost: float | None
    curve: str

    def budget(self, basis: Basis) -> float:
        return self.hours if basis == Basis.HOURS else (self.cost or 0.0)

    def planned(self, basis: Basis, on: date) -> float:
        return calc.planned_to_date(self.budget(basis), self.start, self.finish, self.curve, on)

    def frozen(self) -> dict[str, Any]:
        return {
            "work_package_id": self.id,
            "code": self.code,
            "name": self.name,
            "control_account": self.control_account,
            "discipline": self.discipline,
            "planned_start": self.start.isoformat() if self.start else None,
            "planned_finish": self.finish.isoformat() if self.finish else None,
            "budget_hours": self.hours,
            "budget_cost": self.cost,
            "curve": self.curve,
        }

    @classmethod
    def of(cls, wp: WorkPackage) -> "Plan":
        return cls(
            id=wp.id,
            code=wp.code,
            name=wp.name,
            control_account=wp.control_account,
            discipline=wp.discipline,
            start=wp.planned_start,
            finish=wp.planned_finish,
            hours=float(wp.budget_hours),
            cost=None if wp.budget_cost is None else float(wp.budget_cost),
            curve=wp.curve,
        )

    @classmethod
    def thawed(cls, row: dict[str, Any]) -> "Plan":
        return cls(
            id=row.get("work_package_id"),
            code=row["code"],
            name=row.get("name", ""),
            control_account=row.get("control_account"),
            discipline=row.get("discipline"),
            start=date.fromisoformat(row["planned_start"]) if row.get("planned_start") else None,
            finish=date.fromisoformat(row["planned_finish"]) if row.get("planned_finish") else None,
            hours=float(row.get("budget_hours") or 0),
            cost=None if row.get("budget_cost") is None else float(row["budget_cost"]),
            curve=row.get("curve") or Curve.LINEAR.value,
        )


@dataclass(frozen=True)
class Progress:
    on: date
    percent: float
    actual_hours: float
    actual_cost: float | None
    comment: str | None


@dataclass
class History:
    """Each package's progress records in date order, for 'as at' lookups."""

    by_package: dict[int, list[Progress]] = field(default_factory=dict)

    def as_of(self, package_id: int | None, on: date) -> Progress | None:
        records = self.by_package.get(package_id or 0)
        if not records:
            return None
        i = bisect.bisect_right([r.on for r in records], on)
        return records[i - 1] if i else None

    def first_date(self) -> date | None:
        dates = [r[0].on for r in self.by_package.values() if r]
        return min(dates) if dates else None

    def last_date(self) -> date | None:
        dates = [r[-1].on for r in self.by_package.values() if r]
        return max(dates) if dates else None


def earned(plan: Plan, progress: Progress | None, basis: Basis) -> float:
    return plan.budget(basis) * (progress.percent if progress else 0.0) / 100


def actual(progress: Progress | None, basis: Basis) -> float:
    if progress is None:
        return 0.0
    return progress.actual_hours if basis == Basis.HOURS else (progress.actual_cost or 0.0)


@dataclass
class Sums:
    bac: float = 0.0
    pv: float = 0.0
    ev: float = 0.0
    ac: float = 0.0
    earned_hours: float = 0.0
    actual_hours: float = 0.0
    count: int = 0

    def add(self, plan: Plan, progress: Progress | None, basis: Basis, on: date) -> None:
        self.bac += plan.budget(basis)
        self.pv += plan.planned(basis, on)
        self.ev += earned(plan, progress, basis)
        self.ac += actual(progress, basis)
        self.earned_hours += earned(plan, progress, Basis.HOURS)
        self.actual_hours += actual(progress, Basis.HOURS)
        self.count += 1

    def metrics(self, method: EacMethod) -> calc.Metrics:
        return calc.compute(
            self.bac, self.pv, self.ev, self.ac, method, earned_hours=self.earned_hours, actual_hours=self.actual_hours
        )


def rounded(metrics: calc.Metrics) -> dict[str, Any]:
    indices = {"spi", "cpi", "tcpi", "tcpi_eac", "productivity"}
    return {k: (None if v is None else round(v, 4 if k in indices else 2)) for k, v in metrics.as_dict().items()}


# --- loading ------------------------------------------------------------------------------------------


async def packages(db: AsyncSession, project_id: int) -> list[WorkPackage]:
    rows = await db.execute(
        select(WorkPackage).where(WorkPackage.project_id == project_id).order_by(WorkPackage.sort_order, WorkPackage.code)
    )
    return list(rows.scalars())


async def history(db: AsyncSession, project_id: int) -> History:
    rows = await db.execute(
        select(ProgressRecord).where(ProgressRecord.project_id == project_id).order_by(ProgressRecord.data_date)
    )
    out = History()
    for r in rows.scalars():
        out.by_package.setdefault(r.work_package_id, []).append(
            Progress(
                on=r.data_date,
                percent=float(r.percent_complete),
                actual_hours=float(r.actual_hours),
                actual_cost=None if r.actual_cost is None else float(r.actual_cost),
                comment=r.comment,
            )
        )
    return out


async def settings(db: AsyncSession, project_id: int) -> EvmSettings:
    found = await db.get(EvmSettings, project_id)
    return found or EvmSettings(project_id=project_id)


async def data_date(db: AsyncSession, project_id: int, requested: date | None = None) -> date:
    """The date asked for, else the project's data date, else the latest progress, else today."""
    if requested:
        return requested
    current = await settings(db, project_id)
    if current.data_date:
        return current.data_date
    latest = await db.scalar(select(func.max(ProgressRecord.data_date)).where(ProgressRecord.project_id == project_id))
    return latest or date.today()


def cost_available(plans: Iterable[Plan]) -> bool:
    return any(p.cost for p in plans)


# --- work packages ------------------------------------------------------------------------------------


def read_package(wp: WorkPackage) -> dict[str, Any]:
    return EvmWorkPackageRead.model_validate(wp).model_dump(mode="json")


async def get_package(db: AsyncSession, package_id: int) -> WorkPackage:
    wp = await db.get(WorkPackage, package_id)
    if wp is None:
        raise WorkPackageNotFoundError(f"Work package {package_id} not found")
    return wp


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise WorkPackageCodeTakenError("Code taken") from exc


def _check_dates(start: date | None, finish: date | None) -> None:
    if start and finish and finish < start:
        raise UnprocessableEntityException("planned_finish is before planned_start")


async def create_package(db: AsyncSession, values: dict[str, Any]) -> WorkPackage:
    values["curve"] = Curve(values.get("curve") or Curve.LINEAR).value
    wp = WorkPackage(**values)
    db.add(wp)
    await _commit(db)
    await publish("evm.work_package.created", {"project_id": wp.project_id, "work_package_id": wp.id})
    return wp


async def update_package(db: AsyncSession, wp: WorkPackage, values: dict[str, Any]) -> WorkPackage:
    required = {"code", "name", "budget_hours", "curve", "sort_order"}
    _check_dates(values.get("planned_start", wp.planned_start), values.get("planned_finish", wp.planned_finish))
    for key, value in values.items():
        if value is None and key in required:
            continue
        setattr(wp, key, value.value if isinstance(value, Curve) else value)
    await _commit(db)
    await publish("evm.work_package.updated", {"project_id": wp.project_id, "work_package_id": wp.id, "fields": sorted(values)})
    return wp


# --- progress -----------------------------------------------------------------------------------------


async def progress_sheet(db: AsyncSession, project_id: int, on: date) -> list[dict[str, Any]]:
    hist = await history(db, project_id)
    rows = []
    for wp in await packages(db, project_id):
        p = hist.as_of(wp.id, on)
        percent = Decimal(str(p.percent)) if p else Decimal(0)
        rows.append(
            {
                "work_package_id": wp.id,
                "code": wp.code,
                "name": wp.name,
                "control_account": wp.control_account,
                "discipline": wp.discipline,
                "budget_hours": wp.budget_hours,
                "budget_cost": wp.budget_cost,
                "recorded_on": p.on if p else None,
                "percent_complete": percent,
                "earned_hours": (wp.budget_hours * percent / 100).quantize(Decimal("0.01")),
                "actual_hours": Decimal(str(p.actual_hours)) if p else Decimal(0),
                "actual_cost": None if p is None or p.actual_cost is None else Decimal(str(p.actual_cost)),
                "comment": p.comment if p and p.on == on else None,
            }
        )
    return rows


async def save_progress(
    db: AsyncSession,
    project_id: int,
    on: date,
    entries: list[EvmProgressEntry],
    user_id: int | None,
    set_data_date: bool = True,
) -> int:
    """Upsert one record per entry at ``on``. Omitted values carry forward from the previous record."""
    by_id = {wp.id: wp for wp in await packages(db, project_id)}
    unknown = sorted({e.work_package_id for e in entries} - set(by_id))
    if unknown:
        raise UnprocessableEntityException(f"Work packages not in this project: {', '.join(map(str, unknown))}")
    hist = await history(db, project_id)
    existing = {
        r.work_package_id: r
        for r in (
            await db.execute(
                select(ProgressRecord).where(ProgressRecord.project_id == project_id, ProgressRecord.data_date == on)
            )
        ).scalars()
    }
    saved = 0
    for entry in entries:
        wp = by_id[entry.work_package_id]
        percent = entry.percent_complete
        if entry.earned_hours is not None:
            if not wp.budget_hours:
                raise UnprocessableEntityException(f"{wp.code} has no budget hours to earn against; enter a percentage.")
            percent = min(Decimal(100), entry.earned_hours / wp.budget_hours * 100).quantize(Decimal("0.001"))
        record = existing.get(wp.id)
        if record is None:
            before = hist.as_of(wp.id, on - timedelta(days=1))
            record = ProgressRecord(
                project_id=project_id,
                work_package_id=wp.id,
                data_date=on,
                percent_complete=Decimal(str(before.percent)) if before else Decimal(0),
                actual_hours=Decimal(str(before.actual_hours)) if before else Decimal(0),
                actual_cost=Decimal(str(before.actual_cost)) if before and before.actual_cost is not None else None,
            )
            db.add(record)
        if percent is not None:
            record.percent_complete = percent
        if entry.actual_hours is not None:
            record.actual_hours = entry.actual_hours
        if entry.actual_cost is not None:
            record.actual_cost = entry.actual_cost
        if entry.comment is not None:
            record.comment = entry.comment or None
        record.recorded_by_id = user_id
        saved += 1
    if set_data_date:
        current = await db.get(EvmSettings, project_id)
        if current is None:
            db.add(EvmSettings(project_id=project_id, data_date=on))
        else:
            current.data_date = on
    await db.commit()
    await publish("evm.progress.recorded", {"project_id": project_id, "data_date": on.isoformat(), "entries": saved})
    return saved


# --- metrics ------------------------------------------------------------------------------------------


def _group_key(plan: Plan, group_by: GroupBy) -> tuple[str, str]:
    match group_by:
        case GroupBy.PACKAGE:
            return plan.code, f"{plan.code} {plan.name}".strip()
        case GroupBy.ACCOUNT:
            return plan.control_account or NO_GROUP, plan.control_account or NO_GROUP
        case GroupBy.DISCIPLINE:
            return plan.discipline or NO_GROUP, plan.discipline or NO_GROUP
        case GroupBy.PROJECT:
            return "project", "Project"


def metrics(
    plans: list[Plan], hist: History, on: date, basis: Basis, group_by: GroupBy, method: EacMethod
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Totals, and one row per group, as at the end of ``on``."""
    total = Sums()
    groups: dict[str, tuple[str, Sums, Plan]] = {}
    for plan in plans:
        if basis == Basis.COST and plan.cost is None:
            continue
        progress = hist.as_of(plan.id, on)
        total.add(plan, progress, basis, on)
        key, label = _group_key(plan, group_by)
        if key not in groups:
            groups[key] = (label, Sums(), plan)
        groups[key][1].add(plan, progress, basis, on)
    rows = []
    for key, (label, sums, first) in groups.items():
        row = {"key": key, "label": label, "packages": sums.count, **rounded(sums.metrics(method))}
        if group_by == GroupBy.PACKAGE:
            row |= {"work_package_id": first.id, "control_account": first.control_account, "discipline": first.discipline}
        rows.append(row)
    if group_by != GroupBy.PACKAGE:
        rows.sort(key=lambda r: (r["key"] == NO_GROUP, r["key"]))
    return rounded(total.metrics(method)), rows


async def metrics_report(
    db: AsyncSession,
    project: Project,
    on: date | None,
    basis: Basis,
    group_by: GroupBy,
    method: EacMethod | None,
) -> dict[str, Any]:
    on = await data_date(db, project.id, on)
    method = method or EacMethod((await settings(db, project.id)).eac_method)
    plans = [Plan.of(wp) for wp in await packages(db, project.id)]
    total, rows = metrics(plans, await history(db, project.id), on, basis, group_by, method)
    return {
        "project_id": project.id,
        "data_date": on,
        "basis": basis,
        "group_by": group_by,
        "eac_method": method,
        "cost_available": cost_available(plans),
        "currency": project.currency,
        "total": total,
        "rows": rows,
    }


# --- time series --------------------------------------------------------------------------------------


def _span(plans: list[Plan], project: Project, hist: History, on: date) -> tuple[date, date] | None:
    starts = [p.start for p in plans if p.start] + [d for d in (project.start_date, hist.first_date()) if d]
    finishes = [p.finish for p in plans if p.finish] + [d for d in (project.end_date, hist.last_date()) if d]
    if not starts:
        return None
    return min(starts), max([*finishes, min(starts)])


def s_curve(
    plans: list[Plan],
    hist: History,
    project: Project,
    on: date,
    interval: Interval,
    basis: Basis,
    method: EacMethod,
    baseline: list[Plan] | None = None,
) -> dict[str, Any]:
    if basis == Basis.COST:
        plans = [p for p in plans if p.cost is not None]
        baseline = None if baseline is None else [p for p in baseline if p.cost is not None]
    totals = Sums()
    for plan in plans:
        totals.add(plan, hist.as_of(plan.id, on), basis, on)
    m = totals.metrics(method)
    span = _span(plans, project, hist, on)
    out: dict[str, Any] = {
        "project_id": project.id,
        "basis": basis,
        "interval": interval,
        "data_date": on,
        "bac": round(totals.bac, 2),
        "eac": None if m.eac is None else round(m.eac, 2),
        "forecast_finish": None,
        "points": [],
    }
    if span is None:
        return out
    first, planned_last = span
    finish = calc.forecast_finish(first, planned_last, on, m.spi) if m.eac is not None else planned_last
    out["forecast_finish"] = finish if m.eac is not None else None
    last = max(planned_last, finish, on)

    def cum(date_: date) -> tuple[float, float]:
        ev = sum(earned(p, hist.as_of(p.id, date_), basis) for p in plans)
        ac = sum(actual(hist.as_of(p.id, date_), basis) for p in plans)
        return ev, ac

    forecast_days = max((finish - on).days, 0)
    prev = {"pv": 0.0, "ev": 0.0, "ac": 0.0}
    for start, end in calc.periods(first, last, interval):
        pv = sum(p.planned(basis, end) for p in plans)
        point: dict[str, Any] = {
            "period_start": start,
            "period_end": end,
            "label": start.strftime("%d %b %y") if interval == Interval.WEEK else start.strftime("%b %Y"),
            "pv": round(pv, 2),
            "period_pv": round(pv - prev["pv"], 2),
            "ev": None,
            "ac": None,
            "period_ev": None,
            "period_ac": None,
            "forecast": None,
            "baseline_pv": None if baseline is None else round(sum(p.planned(basis, end) for p in baseline), 2),
        }
        prev["pv"] = pv
        if start <= on:
            ev, ac = cum(min(end, on))
            point |= {
                "ev": round(ev, 2),
                "ac": round(ac, 2),
                "period_ev": round(ev - prev["ev"], 2),
                "period_ac": round(ac - prev["ac"], 2),
            }
            prev["ev"], prev["ac"] = ev, ac
        if m.eac is not None and end >= on:
            reached = min((min(end, finish) - on).days, forecast_days)
            share = 1.0 if forecast_days == 0 else reached / forecast_days
            if start <= on <= end:
                share = 0.0 if forecast_days else 1.0
            point["forecast"] = round(totals.ac + (m.eac - totals.ac) * share, 2)
        out["points"].append(point)
    return out


async def s_curve_report(
    db: AsyncSession, project: Project, on: date | None, interval: Interval, basis: Basis, snapshot_id: int | None
) -> dict[str, Any]:
    on = await data_date(db, project.id, on)
    method = EacMethod((await settings(db, project.id)).eac_method)
    snap = await (get_snapshot(db, project.id, snapshot_id) if snapshot_id else active_baseline(db, project.id))
    baseline = [Plan.thawed(r) for r in snap.packages] if snap else None
    plans = [Plan.of(wp) for wp in await packages(db, project.id)]
    out = s_curve(plans, await history(db, project.id), project, on, interval, basis, method, baseline)
    out["baseline_id"] = snap.id if snap else None
    return out


async def cashflow(db: AsyncSession, project: Project) -> dict[str, Any]:
    """Monthly planned against actual cost from the packages' cost budgets, beside ``cvr``'s cashflow when it's on."""
    plans = [Plan.of(wp) for wp in await packages(db, project.id)]
    on = await data_date(db, project.id)
    curve = s_curve(plans, await history(db, project.id), project, on, Interval.MONTH, Basis.COST, EacMethod.CPI)
    months: dict[date, dict[str, Any]] = {}
    for p in curve["points"]:
        months[p["period_start"]] = {
            "month": p["period_start"],
            "planned_cost": p["period_pv"],
            "actual_cost": p["period_ac"],
            "cumulative_planned": p["pv"],
            "cumulative_actual": p["ac"],
        }
    cvr_rows = await _cvr_cashflow(db, project.id)
    for row in cvr_rows:
        month = months.setdefault(
            row["month"],
            {
                "month": row["month"],
                "planned_cost": 0.0,
                "actual_cost": None,
                "cumulative_planned": 0.0,
                "cumulative_actual": None,
            },
        )
        month["cvr_planned_cost"] = row["planned"]
        month["cvr_actual_cost"] = row["actual"]
    return {
        "project_id": project.id,
        "currency": project.currency,
        "cost_available": cost_available(plans),
        "cvr_included": bool(cvr_rows),
        "months": [months[k] for k in sorted(months)],
    }


async def _cvr_cashflow(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    """``cvr``'s monthly cashflow, read-only; empty when the module is off or absent."""
    if not await is_enabled(db, "cvr", project_id):
        return []
    try:
        from ..cvr.models import CashflowPeriod  # noqa: PLC0415 - optional module
    except ImportError:  # pragma: no cover - cvr removed from the deployment
        return []
    rows = await db.execute(
        select(CashflowPeriod).where(CashflowPeriod.project_id == project_id).order_by(CashflowPeriod.period)
    )
    return [
        {
            "month": r.period,
            "planned": float(r.planned_cost),
            "actual": None if r.actual_cost is None else float(r.actual_cost),
        }
        for r in rows.scalars()
    ]


# --- snapshots ----------------------------------------------------------------------------------------


def read_snapshot(snap: BudgetSnapshot) -> dict[str, Any]:
    plans = [Plan.thawed(r) for r in snap.packages]
    costs = [p.cost for p in plans if p.cost is not None]
    return EvmSnapshotRead(
        id=snap.id,
        project_id=snap.project_id,
        name=snap.name,
        note=snap.note,
        is_baseline=snap.is_baseline,
        created_at=snap.created_at,
        created_by_id=snap.created_by_id,
        package_count=len(plans),
        budget_hours=round(sum(p.hours for p in plans), 2),
        budget_cost=round(sum(costs), 2) if costs else None,
    ).model_dump(mode="json")


async def get_snapshot(db: AsyncSession, project_id: int, snapshot_id: int) -> BudgetSnapshot:
    snap = await db.get(BudgetSnapshot, snapshot_id)
    if snap is None or snap.project_id != project_id:
        raise SnapshotNotFoundError(f"Snapshot {snapshot_id} not found")
    return snap


async def active_baseline(db: AsyncSession, project_id: int) -> BudgetSnapshot | None:
    found: BudgetSnapshot | None = await db.scalar(
        select(BudgetSnapshot)
        .where(BudgetSnapshot.project_id == project_id, BudgetSnapshot.is_baseline.is_(True))
        .order_by(BudgetSnapshot.id.desc())
        .limit(1)
    )
    return found


async def _clear_baseline(db: AsyncSession, project_id: int, keep: int | None = None) -> None:
    rows = await db.execute(
        select(BudgetSnapshot).where(BudgetSnapshot.project_id == project_id, BudgetSnapshot.is_baseline.is_(True))
    )
    for snap in rows.scalars():
        if snap.id != keep:
            snap.is_baseline = False


async def create_snapshot(
    db: AsyncSession, project_id: int, name: str, note: str | None, baseline: bool, user_id: int | None
) -> BudgetSnapshot:
    """Freeze every package's budget, dates and curve. ``baseline`` makes it the active baseline (re-baselining)."""
    frozen = [Plan.of(wp).frozen() for wp in await packages(db, project_id)]
    if baseline:
        await _clear_baseline(db, project_id)
    snap = BudgetSnapshot(
        project_id=project_id, name=name, packages=frozen, is_baseline=baseline, note=note, created_by_id=user_id
    )
    db.add(snap)
    await db.commit()
    await publish("evm.snapshot.created", {"project_id": project_id, "snapshot_id": snap.id, "baseline": baseline})
    return snap


async def update_snapshot(db: AsyncSession, snap: BudgetSnapshot, values: dict[str, Any]) -> BudgetSnapshot:
    if values.get("name"):
        snap.name = values["name"]
    if "note" in values:
        snap.note = values["note"]
    if values.get("is_baseline") is not None:
        if values["is_baseline"]:
            await _clear_baseline(db, snap.project_id, keep=snap.id)
        snap.is_baseline = values["is_baseline"]
    await db.commit()
    return snap


def compare(snapshot: list[Plan], current: list[Plan], on: date) -> dict[str, Any]:
    """Budget, dates and planned value to date, package by package, matched on code."""
    before = {p.code: p for p in snapshot}
    now = {p.code: p for p in current}
    rows = []
    for code in [*now, *(c for c in before if c not in now)]:
        b, c = before.get(code), now.get(code)
        same = (
            b is not None
            and c is not None
            and (b.hours, b.cost, b.start, b.finish, b.curve) == (c.hours, c.cost, c.start, c.finish, c.curve)
        )
        rows.append(
            {
                "code": code,
                "name": (c or b).name,  # type: ignore[union-attr]
                "status": "added" if b is None else "removed" if c is None else "same" if same else "changed",
                "snapshot_hours": b.hours if b else None,
                "current_hours": c.hours if c else None,
                "delta_hours": round((c.hours if c else 0) - (b.hours if b else 0), 2),
                "snapshot_cost": b.cost if b else None,
                "current_cost": c.cost if c else None,
                "delta_cost": None
                if (b is None or b.cost is None) and (c is None or c.cost is None)
                else round(((c.cost or 0) if c else 0) - ((b.cost or 0) if b else 0), 2),
                "snapshot_start": b.start if b else None,
                "current_start": c.start if c else None,
                "snapshot_finish": b.finish if b else None,
                "current_finish": c.finish if c else None,
                "snapshot_pv": round(b.planned(Basis.HOURS, on), 2) if b else None,
                "current_pv": round(c.planned(Basis.HOURS, on), 2) if c else None,
            }
        )
    return {
        "data_date": on,
        "snapshot_hours": round(sum(p.hours for p in snapshot), 2),
        "current_hours": round(sum(p.hours for p in current), 2),
        "snapshot_pv": round(sum(p.planned(Basis.HOURS, on) for p in snapshot), 2),
        "current_pv": round(sum(p.planned(Basis.HOURS, on) for p in current), 2),
        "rows": rows,
    }

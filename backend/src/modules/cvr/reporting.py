"""CVR for reporting: cost heads and cashflow as datasets, margin KPIs, and the budget importer.

The budget importer upserts cost heads by code from a spreadsheet: a code already on the project is
updated with the row's non-empty figures, a new code is added (it then needs a description). Rows
with an error are reported and left out; nothing is written on a dry run.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.reporting import (
    Column,
    Dataset,
    Importer,
    ImportField,
    ImportJob,
    ImportReport,
    Kpi,
    register_dataset,
    register_importer,
    register_kpi,
)
from ...infrastructure.reporting.tables import number
from .models import CashflowPeriod, CostHead

MONEY_FIELDS = ("budget", "cost_to_date", "value_to_date", "forecast_cost", "forecast_value")
LIMIT = Decimal("99999999999999")


def _f(value: Decimal | None) -> float:
    return float(value or 0)


async def cost_head_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    heads = (
        await db.execute(select(CostHead).where(CostHead.project_id == project_id).order_by(CostHead.sort_order, CostHead.code))
    ).scalars()
    rows = []
    for h in heads:
        budget, cost, value, f_cost, f_value = (_f(getattr(h, k)) for k in MONEY_FIELDS)
        rows.append(
            {
                "project_id": h.project_id,
                "code": h.code,
                "description": h.description,
                "budget": budget,
                "cost_to_date": cost,
                "value_to_date": value,
                "margin_to_date": value - cost,
                "forecast_cost": f_cost,
                "forecast_value": f_value,
                "forecast_margin": f_value - f_cost,
                "variance": budget - f_cost,
                "variance_pct": round((budget - f_cost) / budget * 100, 2) if budget else None,
            }
        )
    return rows


async def cashflow_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    periods = (
        await db.execute(select(CashflowPeriod).where(CashflowPeriod.project_id == project_id).order_by(CashflowPeriod.period))
    ).scalars()
    return [
        {
            "project_id": p.project_id,
            "period": p.period,
            "planned_cost": _f(p.planned_cost),
            "actual_cost": None if p.actual_cost is None else _f(p.actual_cost),
            "planned_value": _f(p.planned_value),
            "actual_value": None if p.actual_value is None else _f(p.actual_value),
        }
        for p in periods
    ]


register_dataset(
    Dataset(
        name="cvr_cost_heads",
        module="cvr",
        title="CVR cost heads",
        description="Budget, cost, value, forecast and margin per cost head.",
        permission="cvr.read",
        columns=[
            Column("code", "Code"),
            Column("description", "Cost head"),
            Column("budget", "Budget", "money"),
            Column("cost_to_date", "Cost to date", "money"),
            Column("value_to_date", "Value to date", "money"),
            Column("margin_to_date", "Margin to date", "money"),
            Column("forecast_cost", "Forecast cost", "money"),
            Column("forecast_value", "Forecast value", "money"),
            Column("forecast_margin", "Forecast margin", "money"),
            Column("variance", "Budget variance", "money"),
            Column("variance_pct", "Variance %", "number", aggregatable=False),
        ],
        rows=cost_head_rows,
    )
)

register_dataset(
    Dataset(
        name="cvr_cashflow",
        module="cvr",
        title="CVR cashflow",
        description="Planned and actual cost and value per month.",
        permission="cvr.read",
        columns=[
            Column("period", "Month", "date"),
            Column("planned_cost", "Planned cost", "money"),
            Column("actual_cost", "Actual cost", "money"),
            Column("planned_value", "Planned value", "money"),
            Column("actual_value", "Actual value", "money"),
        ],
        rows=cashflow_rows,
    )
)


async def totals(db: AsyncSession, project_id: int) -> tuple[float, float, float, float, float]:
    row = (
        await db.execute(
            select(*(func.coalesce(func.sum(getattr(CostHead, k)), 0) for k in MONEY_FIELDS)).where(
                CostHead.project_id == project_id
            )
        )
    ).one()
    budget, cost, value, f_cost, f_value = (float(x) for x in row)
    return budget, cost, value, f_cost, f_value


def _pct(part: float, whole: float) -> float | None:
    return round(part / whole * 100, 2) if whole else None


async def _budget(db: AsyncSession, project_id: int) -> float:
    return (await totals(db, project_id))[0]


async def _cost(db: AsyncSession, project_id: int) -> float:
    return (await totals(db, project_id))[1]


async def _value(db: AsyncSession, project_id: int) -> float:
    return (await totals(db, project_id))[2]


async def _margin_pct(db: AsyncSession, project_id: int) -> float | None:
    _, cost, value, _, _ = await totals(db, project_id)
    return _pct(value - cost, value)


async def _forecast_margin_pct(db: AsyncSession, project_id: int) -> float | None:
    _, _, _, f_cost, f_value = await totals(db, project_id)
    return _pct(f_value - f_cost, f_value)


async def _cost_value_ratio(db: AsyncSession, project_id: int) -> float | None:
    _, cost, value, _, _ = await totals(db, project_id)
    return _pct(cost, value)


async def _variance_pct(db: AsyncSession, project_id: int) -> float | None:
    budget, _, _, f_cost, _ = await totals(db, project_id)
    return _pct(budget - f_cost, budget)


for kpi in (
    Kpi("cvr.budget", "cvr", "Budget", _budget, unit="money", permission="cvr.read"),
    Kpi("cvr.cost_to_date", "cvr", "Cost to date", _cost, unit="money", permission="cvr.read"),
    Kpi("cvr.value_to_date", "cvr", "Value to date", _value, unit="money", permission="cvr.read"),
    Kpi("cvr.margin_pct", "cvr", "Margin to date", _margin_pct, unit="%", thresholds=(10, 0), permission="cvr.read"),
    Kpi(
        "cvr.forecast_margin_pct",
        "cvr",
        "Forecast margin",
        _forecast_margin_pct,
        unit="%",
        thresholds=(10, 0),
        permission="cvr.read",
    ),
    Kpi(
        "cvr.cost_value_ratio",
        "cvr",
        "Cost / value to date",
        _cost_value_ratio,
        unit="%",
        good="down",
        thresholds=(90, 100),
        permission="cvr.read",
        description="Cost to date as a share of the value earned; above 100% the work is losing money.",
    ),
    Kpi(
        "cvr.budget_variance_pct",
        "cvr",
        "Budget variance",
        _variance_pct,
        unit="%",
        thresholds=(0, -5),
        permission="cvr.read",
        description="Budget less forecast cost, as a share of the budget; negative is over budget.",
    ),
):
    register_kpi(kpi)


# --- budget import ------------------------------------------------------------------------------------


def _money(value: Any) -> Decimal | None | str:
    """The amount, None for a blank cell, or an error message."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    n = number(value)
    if n is None:
        return f"'{value}' isn't an amount"
    amount = Decimal(str(round(n, 2)))
    if abs(amount) > LIMIT:
        return f"{value} is too large"
    return amount


async def import_budget(db: AsyncSession, job: ImportJob) -> ImportReport:
    report = ImportReport(dry_run=job.dry_run, rows=len(job.rows))
    if job.project_id is None:
        report.errors.append("Choose a project.")
        return report
    existing = {h.code: h for h in (await db.execute(select(CostHead).where(CostHead.project_id == job.project_id))).scalars()}
    next_order = max((h.sort_order for h in existing.values()), default=0)
    seen: set[str] = set()
    changed = False
    for line, row in enumerate(job.rows, start=2):
        code = str(row.get("code") or "").strip()
        if not code:
            if any(v not in (None, "") for v in row.values()):
                report.errors.append(f"Row {line}: no code")
                report.skipped += 1
            else:
                report.rows -= 1
            continue
        if len(code) > 30:
            report.errors.append(f"Row {line}: code '{code[:30]}…' is longer than 30 characters")
            report.skipped += 1
            continue
        if code in seen:
            report.errors.append(f"Row {line}: code {code} appears twice in the file")
            report.skipped += 1
            continue
        seen.add(code)
        values: dict[str, Any] = {}
        problems = []
        for key in MONEY_FIELDS:
            parsed = _money(row.get(key))
            if isinstance(parsed, str):
                problems.append(f"{key.replace('_', ' ')}: {parsed}")
            elif parsed is not None:
                values[key] = parsed
        description = str(row.get("description") or "").strip()
        if len(description) > 300:
            problems.append("description is longer than 300 characters")
        elif description:
            values["description"] = description
        order = number(row.get("sort_order"))
        if order is not None:
            values["sort_order"] = int(order)
        if problems:
            report.errors.append(f"Row {line} ({code}): " + "; ".join(problems))
            report.skipped += 1
            continue

        head = existing.get(code)
        if head is None:
            if not description:
                report.errors.append(f"Row {line} ({code}): a new cost head needs a description")
                report.skipped += 1
                continue
            report.created += 1
            if not job.dry_run:
                next_order += 10
                values.setdefault("sort_order", next_order)
                db.add(CostHead(project_id=job.project_id, code=code, **values))
                changed = True
            continue
        diff = {k: v for k, v in values.items() if getattr(head, k) != v}
        if not diff:
            report.unchanged += 1
            continue
        report.updated += 1
        if not job.dry_run:
            for key, value in diff.items():
                setattr(head, key, value)
            changed = True
    if changed:
        await db.commit()
        await publish("cvr.budget.imported", {"project_id": job.project_id, "created": report.created})
    return report


register_importer(
    Importer(
        name="budget",
        module="cvr",
        title="Budget (CVR cost heads)",
        description="Cost heads from Excel or CSV, matched by code: new codes are added, existing ones updated.",
        permission="cvr.edit",
        fields=[
            ImportField("code", "Code", required=True, aliases=("cost code", "item", "ref", "wbs", "account")),
            ImportField("description", "Description", aliases=("cost head", "name", "item description", "title")),
            ImportField("budget", "Budget", aliases=("budget amount", "original budget", "approved budget")),
            ImportField("cost_to_date", "Cost to date", aliases=("actual cost", "actuals", "cost", "spent")),
            ImportField("value_to_date", "Value to date", aliases=("earned value", "value", "valuation")),
            ImportField("forecast_cost", "Forecast cost", aliases=("forecast", "eac", "forecast final cost", "ffc")),
            ImportField("forecast_value", "Forecast value", aliases=("forecast revenue", "forecast final value")),
            ImportField("sort_order", "Sort order", aliases=("sort", "order", "seq", "sequence")),
        ],
        apply=import_budget,
    )
)

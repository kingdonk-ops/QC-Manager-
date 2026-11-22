"""KPIs, the portfolio, and reading datasets on a caller's behalf."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ...infrastructure.reporting import Dataset, Kpi, available_kpis, find_dataset, load_rows
from ...infrastructure.reporting.tables import FilterError
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..cvr.models import CostHead
from ..projects.models import Project
from ..projects.service import readable_project, visible_project_ids
from .schemas import CurrencyTotals, KpiValue, PortfolioRow, PortfolioSummary


class DatasetNotFoundError(ResourceNotFoundError):
    public_detail = "No such dataset, or you can't read it."


class ReportInputError(ValidationError):
    public_detail = "The report can't be built from that."


class BadFilterError(ValidationError):
    public_detail = "Those filters don't fit the dataset."


@dataclass(frozen=True)
class Viewer:
    """Whose eyes a report is built for: what they hold and which projects they can read."""

    user_id: int
    held: frozenset[str]
    visible: frozenset[int]

    @classmethod
    async def of(cls, db: AsyncSession, user_id: int, held: frozenset[str]) -> "Viewer":
        return cls(user_id, held, frozenset(await visible_project_ids(db, user_id, held)))


async def dataset_for(db: AsyncSession, viewer: Viewer, name: str, project_id: int | None) -> Dataset:
    if project_id is not None and project_id not in viewer.visible:
        await readable_project(db, project_id, viewer.user_id, viewer.held)
    found = await find_dataset(db, name, viewer.held, project_id)
    if found is None:
        raise DatasetNotFoundError(name)
    if found.project_scoped and project_id is None:
        raise ReportInputError(f"{found.title} belongs to a project: choose one.")
    return found


async def rows_for(
    db: AsyncSession, viewer: Viewer, dataset: Dataset, project_id: int | None, filters: dict[str, Any] | None
) -> list[dict[str, Any]]:
    try:
        return await load_rows(db, dataset, project_id, filters, set(viewer.visible))
    except FilterError as exc:
        raise BadFilterError(str(exc)) from exc


# --- KPIs ----------------------------------------------------------------------------------------------


async def kpi_value(db: AsyncSession, kpi: Kpi, project_id: int) -> float | None:
    value = await kpi.fn(db, project_id)
    return None if value is None else float(value)


async def kpi_values(db: AsyncSession, project_id: int, held: frozenset[str], keys: list[str] | None = None) -> list[KpiValue]:
    out = []
    for kpi in await available_kpis(db, held, project_id):
        if keys and kpi.key not in keys:
            continue
        value = await kpi_value(db, kpi, project_id)
        out.append(
            KpiValue(
                key=kpi.key,
                module=kpi.module,
                label=kpi.label,
                unit=kpi.unit,
                good=kpi.good,
                value=value,
                status=kpi.status(value),
                description=kpi.description,
            )
        )
    if keys:
        order = {k: i for i, k in enumerate(keys)}
        out.sort(key=lambda v: order.get(v.key, len(order)))
    return out


# --- portfolio -----------------------------------------------------------------------------------------


def _pct(part: float, whole: float) -> float | None:
    return round(part / whole * 100, 2) if whole else None


async def _cvr_totals(db: AsyncSession, held: frozenset[str], ids: list[int]) -> dict[int, tuple[float, ...]]:
    if not ids or "cvr.read" not in held or not await is_enabled(db, "cvr"):
        return {}
    rows = await db.execute(
        select(
            CostHead.project_id,
            func.coalesce(func.sum(CostHead.budget), 0),
            func.coalesce(func.sum(CostHead.cost_to_date), 0),
            func.coalesce(func.sum(CostHead.value_to_date), 0),
            func.coalesce(func.sum(CostHead.forecast_cost), 0),
            func.coalesce(func.sum(CostHead.forecast_value), 0),
        )
        .where(CostHead.project_id.in_(ids))
        .group_by(CostHead.project_id)
    )
    return {pid: tuple(float(x) for x in rest) for pid, *rest in rows.all()}


def _row(project: Project, figures: tuple[float, ...] | None) -> PortfolioRow:
    base: dict[str, Any] = {
        "project_id": project.id,
        "code": project.code,
        "name": project.name,
        "client_name": project.client_name,
        "region": project.region,
        "status": project.status,
        "currency": project.currency,
    }
    if figures is None:
        return PortfolioRow(
            **base,
            budget=None,
            value_to_date=None,
            cost_to_date=None,
            forecast_cost=None,
            forecast_value=None,
            variance=None,
            variance_pct=None,
            forecast_margin=None,
            forecast_margin_pct=None,
            budget_status="none",
        )
    budget, cost, value, f_cost, f_value = figures
    outturn = f_cost or cost
    """Forecast cost, or cost to date while no forecast is entered."""
    variance = budget - outturn
    status = "none" if not budget and not outturn else "over" if outturn > budget else "on"
    return PortfolioRow(
        **base,
        budget=budget,
        value_to_date=value,
        cost_to_date=cost,
        forecast_cost=f_cost,
        forecast_value=f_value,
        variance=round(variance, 2),
        variance_pct=_pct(variance, budget),
        forecast_margin=round(f_value - f_cost, 2),
        forecast_margin_pct=_pct(f_value - f_cost, f_value),
        budget_status=status,
    )


async def portfolio(
    db: AsyncSession,
    user_id: int,
    held: frozenset[str],
    *,
    region: str | None = None,
    status: str | None = None,
    budget: str | None = None,
    search: str | None = None,
) -> list[PortfolioRow]:
    """Every visible project with its CVR figures, filtered; KPIs are added per page by ``with_kpis``."""
    visible = await visible_project_ids(db, user_id, held)
    query = select(Project).where(Project.id.in_(visible)).order_by(Project.code)
    if region:
        query = query.where(func.upper(Project.region) == region.upper())
    if status:
        query = query.where(Project.status == status)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Project.code).like(like),
                func.lower(Project.name).like(like),
                func.lower(func.coalesce(Project.client_name, "")).like(like),
            )
        )
    projects = list((await db.execute(query)).scalars())
    figures = await _cvr_totals(db, held, [p.id for p in projects])
    cvr_on = bool(figures) or ("cvr.read" in held and await is_enabled(db, "cvr"))
    rows = [_row(p, figures.get(p.id, (0.0,) * 5) if cvr_on else None) for p in projects]
    if budget:
        rows = [r for r in rows if r.budget_status == budget]
    return rows


async def portfolio_kpis(db: AsyncSession, held: frozenset[str]) -> list[Kpi]:
    return [k for k in await available_kpis(db, held) if k.portfolio]


async def with_kpis(db: AsyncSession, held: frozenset[str], rows: list[PortfolioRow]) -> list[PortfolioRow]:
    kpis = await portfolio_kpis(db, held)
    for row in rows:
        for kpi in kpis:
            if not await is_enabled(db, kpi.module, row.project_id):
                continue
            value = await kpi_value(db, kpi, row.project_id)
            row.kpis[kpi.key] = value
            row.kpi_status[kpi.key] = kpi.status(value)
    return rows


async def regions_of(db: AsyncSession, user_id: int, held: frozenset[str]) -> list[str]:
    visible = await visible_project_ids(db, user_id, held)
    return sorted({r for r in (await db.execute(select(Project.region).where(Project.id.in_(visible)))).scalars() if r})


async def portfolio_summary(
    db: AsyncSession, held: frozenset[str], rows: list[PortfolioRow], regions: list[str]
) -> PortfolioSummary:
    by_currency: dict[str, list[PortfolioRow]] = defaultdict(list)
    for row in rows:
        by_currency[row.currency].append(row)
    variances = [r.variance_pct for r in rows if r.variance_pct is not None]
    return PortfolioSummary(
        projects=len(rows),
        over_budget=sum(1 for r in rows if r.budget_status == "over"),
        on_budget=sum(1 for r in rows if r.budget_status == "on"),
        no_budget=sum(1 for r in rows if r.budget_status == "none"),
        average_variance_pct=round(sum(variances) / len(variances), 2) if variances else None,
        totals=[
            CurrencyTotals(
                currency=currency,
                projects=len(group),
                budget=sum(r.budget or 0 for r in group),
                value_to_date=sum(r.value_to_date or 0 for r in group),
                cost_to_date=sum(r.cost_to_date or 0 for r in group),
                forecast_cost=sum(r.forecast_cost or 0 for r in group),
                forecast_value=sum(r.forecast_value or 0 for r in group),
            )
            for currency, group in sorted(by_currency.items(), key=lambda kv: -len(kv[1]))
        ],
        regions=regions,
        kpis=[{"key": k.key, "label": k.label, "unit": k.unit} for k in await portfolio_kpis(db, held)],
    )

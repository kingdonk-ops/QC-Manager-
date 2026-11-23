"""The temporary works register as a dataset, and four counts as KPIs.

Both read the register through ``register.load_summary`` for today at the site, so the counts agree with the rollup for
the same day. The platform hides them when the module is switched off."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .register import load_summary


async def register_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    if project_id is None:
        return []
    summary = await load_summary(db, project_id)
    breached = {b.item_id for b in summary.breaches}
    late_load = {i.id for i in summary.overdue_load}
    late_strike = {i.id for i in summary.overdue_strike}
    return [
        {
            "project_id": project_id,
            "reference": g.item.reference,
            "title": g.item.title,
            "family": g.item.family,
            "status": g.item.status,
            "category": g.item.design_check_category,
            "required_load_on": g.item.required_load_on,
            "required_strike_on": g.item.required_strike_on,
            "load_gate_open": g.load_open,
            "strike_gate_open": g.strike_open,
            "breach": g.item.id in breached,
            "overdue_to_load": g.item.id in late_load,
            "overdue_to_strike": g.item.id in late_strike,
            "items": 1,
        }
        for g in summary.gates
    ]


register_dataset(
    Dataset(
        name="temporary_works_register",
        module="temporary_works",
        title="Temporary works register",
        permission="temporary_works.read",
        columns=[
            Column("reference", "Reference"),
            Column("title", "Title"),
            Column("family", "Family"),
            Column("status", "Status"),
            Column("category", "Check category", "number", aggregatable=False),
            Column("required_load_on", "Required load", "date"),
            Column("required_strike_on", "Required strike", "date"),
            Column("load_gate_open", "Cleared to load", "bool"),
            Column("strike_gate_open", "Cleared to strike", "bool"),
            Column("breach", "Breach", "bool"),
            Column("overdue_to_load", "Overdue to load", "bool"),
            Column("overdue_to_strike", "Overdue to strike", "bool"),
            Column("items", "Count", "number"),
        ],
        rows=register_rows,
    )
)


async def items(db: AsyncSession, project_id: int) -> int:
    return (await load_summary(db, project_id)).total


async def breaches(db: AsyncSession, project_id: int) -> int:
    return len((await load_summary(db, project_id)).breaches)


async def overdue_to_load(db: AsyncSession, project_id: int) -> int:
    return len((await load_summary(db, project_id)).overdue_load)


async def overdue_to_strike(db: AsyncSession, project_id: int) -> int:
    return len((await load_summary(db, project_id)).overdue_strike)


register_kpi(
    Kpi(
        "temporary_works.items",
        "temporary_works",
        "Temporary works items",
        items,
        unit="count",
        permission="temporary_works.read",
    )
)
register_kpi(
    Kpi(
        "temporary_works.breaches",
        "temporary_works",
        "Temporary works breaches",
        breaches,
        unit="count",
        good="down",
        thresholds=(0, 0),
        permission="temporary_works.read",
    )
)
register_kpi(
    Kpi(
        "temporary_works.overdue_to_load",
        "temporary_works",
        "Temporary works overdue to load",
        overdue_to_load,
        unit="count",
        good="down",
        thresholds=(0, 2),
        permission="temporary_works.read",
    )
)
register_kpi(
    Kpi(
        "temporary_works.overdue_to_strike",
        "temporary_works",
        "Temporary works overdue to strike",
        overdue_to_strike,
        unit="count",
        good="down",
        thresholds=(0, 2),
        permission="temporary_works.read",
    )
)

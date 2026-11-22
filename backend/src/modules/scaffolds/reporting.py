"""The scaffold register as a dataset, and standing / overdue counts as KPIs."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .constants import STANDING
from .models import Scaffold
from .service import inspection_overdue, read_scaffolds


async def scaffold_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(Scaffold).where(Scaffold.project_id == project_id).order_by(Scaffold.code))).scalars())
    return [
        {
            "project_id": r["project_id"],
            "code": r["code"],
            "tag_no": r["tag_no"],
            "status": r["status"],
            "tag": r["effective_tag"],
            "location": r["node_path"],
            "scaffold_type": r["scaffold_type"],
            "erected_on": r["erected_on"],
            "days_erected": r["days_erected"],
            "hire_cost": r["hire_cost"],
            "scaffolds": 1,
        }
        for r in await read_scaffolds(db, rows)
    ]


register_dataset(
    Dataset(
        name="scaffolds",
        module="scaffolds",
        title="Scaffold register",
        permission="scaffolds.read",
        columns=[
            Column("code", "Scaffold"),
            Column("tag_no", "Tag no."),
            Column("status", "Status"),
            Column("tag", "Tag"),
            Column("location", "Location"),
            Column("scaffold_type", "Type"),
            Column("erected_on", "Erected", "date"),
            Column("days_erected", "Days erected", "number"),
            Column("hire_cost", "Hire cost", "money"),
            Column("scaffolds", "Count", "number"),
        ],
        rows=scaffold_rows,
    )
)


async def _standing(db: AsyncSession, project_id: int) -> list[Scaffold]:
    rows = await db.execute(
        select(Scaffold).where(Scaffold.project_id == project_id, Scaffold.status.in_([s.value for s in STANDING]))
    )
    return list(rows.scalars())


async def standing(db: AsyncSession, project_id: int) -> int:
    return len(await _standing(db, project_id))


async def overdue(db: AsyncSession, project_id: int) -> int:
    return sum(1 for s in await _standing(db, project_id) if inspection_overdue(s))


register_kpi(Kpi("scaffolds.standing", "scaffolds", "Scaffolds standing", standing, unit="count", permission="scaffolds.read"))
register_kpi(
    Kpi(
        "scaffolds.overdue",
        "scaffolds",
        "Scaffold inspections overdue",
        overdue,
        unit="count",
        good="down",
        thresholds=(0, 2),
        permission="scaffolds.read",
    )
)

"""Welding for reporting: the weld register as a dataset and the repair-rate KPI."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .models import Weld
from .service import read_welds, repair_rates


async def weld_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    welds = list(
        (
            await db.execute(select(Weld).where(Weld.project_id == project_id).order_by(Weld.drawing_ref, Weld.weld_number))
        ).scalars()
    )
    return [
        {
            **r,
            "welders": ", ".join(r["welders"]),
            "welded_on": date.fromisoformat(r["welded_on"]) if r["welded_on"] else None,
            "welds": 1,
        }
        for r in await read_welds(db, welds)
    ]


register_dataset(
    Dataset(
        name="welds",
        module="welding",
        title="Weld register",
        permission="welding.read",
        columns=[
            Column("weld_number", "Weld"),
            Column("drawing_ref", "Drawing"),
            Column("line_ref", "Line"),
            Column("joint_type", "Joint"),
            Column("weld_category", "Category"),
            Column("wps_code", "WPS"),
            Column("welders", "Welders"),
            Column("welded_on", "Welded", "date"),
            Column("status", "Status"),
            Column("repair_count", "Repairs", "number"),
            Column("welds", "Count", "number"),
        ],
        rows=weld_rows,
    )
)


async def repair_rate(db: AsyncSession, project_id: int) -> float | None:
    rate = (await repair_rates(db, project_id))["overall"]["rate"]
    return float(rate) if rate is not None else None


register_kpi(
    Kpi(
        "welding.repair_rate",
        "welding",
        "Weld repair rate",
        repair_rate,
        unit="%",
        good="down",
        thresholds=(2, 5),
        permission="welding.read",
    )
)

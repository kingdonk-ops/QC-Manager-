"""Calibration for reporting: the equipment register as a dataset and an overdue KPI."""

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .constants import EquipmentStatus
from .models import Equipment
from .service import read_equipment


async def equipment_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(
        (await db.execute(select(Equipment).where(Equipment.project_id == project_id).order_by(Equipment.code))).scalars()
    )
    return [
        {**r, "due_on": date.fromisoformat(r["due_on"]) if r["due_on"] else None, "items": 1}
        for r in await read_equipment(db, rows)
    ]


register_dataset(
    Dataset(
        name="calibration_equipment",
        module="calibration",
        title="Calibration register",
        permission="calibration.read",
        columns=[
            Column("code", "No."),
            Column("name", "Equipment"),
            Column("equipment_type", "Type"),
            Column("serial_number", "Serial"),
            Column("custodian_name", "Custodian"),
            Column("due_on", "Due", "date"),
            Column("status", "Status"),
            Column("items", "Count", "number"),
        ],
        rows=equipment_rows,
    )
)


async def overdue(db: AsyncSession, project_id: int) -> int:
    return (
        await db.scalar(
            select(func.count()).where(
                Equipment.project_id == project_id,
                Equipment.status == EquipmentStatus.IN_SERVICE.value,
                Equipment.requires_calibration.is_(True),
                or_(Equipment.due_on.is_(None), Equipment.due_on < date.today()),
            )
        )
        or 0
    )


register_kpi(
    Kpi(
        "calibration.overdue",
        "calibration",
        "Equipment overdue for calibration",
        overdue,
        unit="count",
        good="down",
        thresholds=(0, 2),
        permission="calibration.read",
    )
)

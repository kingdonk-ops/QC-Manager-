"""Daily log hours for the export hub, report builder and pivot explorer."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, register_dataset
from ..asset_tree.models import AssetNode
from ..planner.models import Crew
from .models import DailyLog, LogHours
from .service import category_of


async def hours_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(LogHours, DailyLog, Crew.code, AssetNode.code)
            .join(DailyLog, DailyLog.id == LogHours.log_id)
            .join(Crew, Crew.id == DailyLog.crew_id)
            .outerjoin(AssetNode, AssetNode.id == LogHours.anchor_id)
            .where(DailyLog.project_id == project_id)
            .order_by(DailyLog.work_date, Crew.code, LogHours.seq)
        )
    ).tuples()
    return [
        {
            "project_id": log.project_id,
            "log": log.code,
            "work_date": log.work_date,
            "shift": log.shift,
            "crew": crew,
            "status": log.status,
            "person": h.person,
            "trade": h.trade or "",
            "work_anchor": anchor or "",
            "category": category_of(h),
            "code": h.delay_code or h.overhead_code or "",
            "hours": h.hours,
        }
        for h, log, crew, anchor in rows
    ]


register_dataset(
    Dataset(
        name="workface_hours",
        module="workface_log",
        title="Daily log hours",
        permission="workface_log.read",
        description="Every person's hours from the daily workface log, by work anchor or delay/overhead code.",
        columns=[
            Column("log", "Log"),
            Column("work_date", "Date", "date"),
            Column("shift", "Shift"),
            Column("crew", "Crew"),
            Column("status", "Status"),
            Column("person", "Person"),
            Column("trade", "Trade"),
            Column("work_anchor", "Work anchor"),
            Column("category", "Category"),
            Column("code", "Delay / overhead code"),
            Column("hours", "Hours", "number"),
        ],
        rows=hours_rows,
    )
)

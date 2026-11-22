"""Progress from the field: hours from signed workface logs, percent complete from verified progress.

A work package reaches the asset breakdown two ways: nodes whose ``wbs_code`` equals the package's ``wbs``,
and the nodes linked (confirmed) to its schedule activity by the P6 import. Everything under those nodes counts.

* actual hours = hours booked on those work anchors in workface logs signed on or before the data date;
* percent complete = verified earned budget / budget of the progress units under those nodes (never the
  self-reported quantity), from ``schedule.progress.earned_value``.

A package with no matching node, or a source module that is off for the project, is left as it was.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.loader import enabled_modules
from ...infrastructure.modules.state import is_enabled
from ..asset_tree.models import AssetNode
from ..asset_tree.service import subtree_ids
from ..schedule.p6_models import P6Link
from ..schedule.progress import earned_value
from ..workface_log.models import DailyLog, LogHours
from .models import WorkPackage
from .schemas import EvmProgressEntry


async def _on(db: AsyncSession, module: str, project_id: int) -> bool:
    return module in {m.manifest.name for m in enabled_modules()} and await is_enabled(db, module, project_id)


async def _scope(db: AsyncSession, project_id: int, wp: WorkPackage, use_schedule: bool) -> set[int]:
    roots: set[int] = set()
    if wp.wbs:
        roots |= set(
            (
                await db.execute(
                    select(AssetNode.id).where(
                        AssetNode.project_id == project_id,
                        func.lower(AssetNode.wbs_code) == wp.wbs.lower(),
                        AssetNode.status == "active",
                    )
                )
            ).scalars()
        )
    if use_schedule and wp.schedule_activity_id:
        roots |= set(
            (
                await db.execute(
                    select(P6Link.node_id).where(P6Link.activity_id == wp.schedule_activity_id, P6Link.status == "confirmed")
                )
            ).scalars()
        )
    scope: set[int] = set()
    for root in roots:
        scope |= set(await subtree_ids(db, root))
    return scope


async def field_progress(db: AsyncSession, project_id: int, on: date) -> tuple[list[EvmProgressEntry], list[dict[str, Any]]]:
    """Entries to save at ``on`` and a row per package saying what was found."""
    if not await _on(db, "asset_tree", project_id):
        return [], []
    hours_on = await _on(db, "workface_log", project_id)
    schedule_on = await _on(db, "schedule", project_id)
    earned: list[dict[str, Any]] = []
    if schedule_on:
        earned = await earned_value(db, project_id)

    packages = (
        await db.execute(select(WorkPackage).where(WorkPackage.project_id == project_id).order_by(WorkPackage.sort_order))
    ).scalars()
    entries: list[EvmProgressEntry] = []
    rows: list[dict[str, Any]] = []
    for wp in packages:
        scope = await _scope(db, project_id, wp, schedule_on)
        row: dict[str, Any] = {
            "work_package_id": wp.id,
            "code": wp.code,
            "nodes": len(scope),
            "actual_hours": None,
            "percent_complete": None,
        }
        if scope:
            if hours_on:
                total = await db.scalar(
                    select(func.coalesce(func.sum(LogHours.hours), 0))
                    .join(DailyLog, DailyLog.id == LogHours.log_id)
                    .where(
                        DailyLog.project_id == project_id,
                        DailyLog.status == "signed",
                        DailyLog.work_date <= on,
                        LogHours.anchor_id.in_(scope),
                    )
                )
                row["actual_hours"] = Decimal(total or 0)
            units = [u for u in earned if u["node_id"] in scope]
            budget = sum(Decimal(str(u["budget"] or 0)) for u in units)
            if budget:
                done = sum(Decimal(str(u["earned"] or 0)) for u in units)
                row["percent_complete"] = min(Decimal(100), (done / budget * 100).quantize(Decimal("0.01")))
        if row["actual_hours"] is not None or row["percent_complete"] is not None:
            entries.append(
                EvmProgressEntry(
                    work_package_id=wp.id,
                    actual_hours=row["actual_hours"],
                    percent_complete=row["percent_complete"],
                    comment="From the field: signed workface logs and verified progress",
                )
            )
        rows.append(row)
    return entries, rows

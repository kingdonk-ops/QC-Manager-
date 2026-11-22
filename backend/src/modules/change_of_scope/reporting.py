"""Change cards for the export hub and reports: the register as a dataset, and waiting/expiring KPIs."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .constants import REMIND_BEFORE_DAYS, WAITING
from .models import ChangeCard
from .service import read


async def card_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    cards = list(
        (await db.execute(select(ChangeCard).where(ChangeCard.project_id == project_id).order_by(ChangeCard.id))).scalars()
    )
    return [
        {
            "project_id": r["project_id"],
            "code": r["code"],
            "title": r["title"],
            "status": r["status"],
            "change_type": r["change_type"],
            "source": r["source"],
            "location": r["node_path"],
            "client_reference": r["client_reference"],
            "estimated_hours": r["estimated_hours"],
            "estimated_amount": r["estimated_amount"],
            "approved_amount": r["approved_amount"],
            "raised": r["created_at"].date(),
            "expires": r["expires_at"].date() if r["expires_at"] else None,
            "change_order": r["change_order_code"],
            "cards": 1,
        }
        for r in await read(db, cards)
    ]


register_dataset(
    Dataset(
        name="change_cards",
        module="change_of_scope",
        title="Change of scope",
        permission="change_of_scope.read",
        columns=[
            Column("code", "No."),
            Column("title", "Title"),
            Column("status", "Status"),
            Column("change_type", "Change type"),
            Column("source", "Source"),
            Column("location", "Location"),
            Column("client_reference", "Client reference"),
            Column("estimated_hours", "Est. hours", "number"),
            Column("estimated_amount", "Est. amount", "money"),
            Column("approved_amount", "Approved amount", "money"),
            Column("raised", "Raised", "date"),
            Column("expires", "Expires", "date"),
            Column("change_order", "Change order"),
            Column("cards", "Count", "number"),
        ],
        rows=card_rows,
    )
)


async def waiting(db: AsyncSession, project_id: int) -> int:
    return (
        await db.scalar(
            select(func.count()).where(ChangeCard.project_id == project_id, ChangeCard.status.in_([s.value for s in WAITING]))
        )
        or 0
    )


async def expiring(db: AsyncSession, project_id: int) -> int:
    soon = datetime.now(UTC) + timedelta(days=REMIND_BEFORE_DAYS)
    return (
        await db.scalar(
            select(func.count()).where(
                ChangeCard.project_id == project_id,
                ChangeCard.status.in_([s.value for s in WAITING]),
                ChangeCard.expires_at <= soon,
            )
        )
        or 0
    )


register_kpi(
    Kpi(
        "change_of_scope.waiting",
        "change_of_scope",
        "Change cards waiting for the client",
        waiting,
        unit="count",
        good="down",
        thresholds=(5, 20),
        permission="change_of_scope.read",
    )
)
register_kpi(
    Kpi(
        "change_of_scope.expiring",
        "change_of_scope",
        "Change cards expiring within 3 days",
        expiring,
        unit="count",
        good="down",
        thresholds=(0, 3),
        permission="change_of_scope.read",
    )
)

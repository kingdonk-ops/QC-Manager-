"""Daily review reminders to risk owners."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from ..notifications.constants import Category
from ..notifications.service import notify
from .constants import RiskStatus
from .models import Risk
from .service import ENTITY, link_of


async def send_review_reminders(db: AsyncSession, today: date | None = None) -> int:
    """Notify the owner of every open risk whose review date has come. Returns how many were sent."""
    today = today or date.today()
    rows = (
        await db.execute(
            select(Risk).where(
                Risk.status != RiskStatus.CLOSED.value,
                Risk.owner_id.is_not(None),
                Risk.review_date.is_not(None),
                Risk.review_date <= today,
            )
        )
    ).scalars()
    count = 0
    for risk in rows:
        assert risk.review_date is not None and risk.owner_id is not None
        when = "is due for review today" if risk.review_date == today else "is overdue for review"
        await notify(
            db,
            [risk.owner_id],
            Category.DUE,
            f"{risk.code} {when}",
            body=risk.title,
            link=link_of(risk),
            entity=(ENTITY, risk.id),
        )
        count += 1
    await db.commit()
    return count


@default_broker.task(task_name="risk:review_reminders", schedule=[{"cron": "13 21 * * *"}])
async def review_reminders(db: DBSession) -> int:
    return await send_review_reminders(db)

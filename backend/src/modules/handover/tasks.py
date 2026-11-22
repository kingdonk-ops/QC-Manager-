"""Reminders for handovers the incoming supervisor hasn't acknowledged."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .service import remind_unacknowledged


@default_broker.task(task_name="handover:remind_unacknowledged", schedule=[{"cron": "*/30 * * * *"}])
async def remind(db: DBSession) -> int:
    """Every 30 minutes: remind recipients (first after 1 h, then every 2 h); tell the author after 3 reminders."""
    return await remind_unacknowledged(db)

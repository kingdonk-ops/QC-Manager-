"""Hourly: an overdue scaffold inspection turns the tag red and tells the custodian."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .service import mark_overdue


@default_broker.task(task_name="scaffolds:overdue", schedule=[{"cron": "13 * * * *"}])
async def overdue_tags(db: DBSession) -> int:
    return await mark_overdue(db)

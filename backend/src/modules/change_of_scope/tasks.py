"""Daily expiry of change cards that waited 14 days for the client, with a reminder three days before."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .service import expire_due


@default_broker.task(task_name="change_of_scope:expiry", schedule=[{"cron": "13 21 * * *"}])
async def expiry(db: DBSession) -> dict[str, int]:
    """21:13 UTC: early morning in Australia, before the day's client meetings."""
    return await expire_due(db)

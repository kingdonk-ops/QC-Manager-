"""Scheduled reports, checked every 15 minutes."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .schedules import run_due


@default_broker.task(task_name="reporting:run_due", schedule=[{"cron": "*/15 * * * *"}])
async def run_due_reports(db: DBSession) -> int:
    """Generate and email every scheduled report that has come due."""
    return await run_due(db)

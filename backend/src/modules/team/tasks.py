"""The scheduled Entra group sync."""

from ...infrastructure.logging import get_logger
from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .graph import graph_configured
from .sync_job import sync_all_linked_teams

logger = get_logger()

SYNC_TASK_NAME = "team:sync_entra_groups"

SYNC_CRON = "23 * * * *"
"""Hourly, at 23 minutes past."""


@default_broker.task(task_name=SYNC_TASK_NAME, schedule=[{"cron": SYNC_CRON}])
async def sync_entra_groups(db: DBSession) -> dict:
    """Refresh every Entra-linked team's members from Microsoft Graph."""
    if not graph_configured():
        logger.info("Entra is not configured, so the group sync has nothing to do")

        return {}

    return (await sync_all_linked_teams(db)).model_dump()

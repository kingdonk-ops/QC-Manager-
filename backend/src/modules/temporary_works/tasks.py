"""Hourly: expire lapsed permits, send expiring-soon notices and announce breaches (see ``sweep``). Daily: empty the
recycle bin once the retention has passed (see ``deletion``)."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .deletion import purge_expired
from .sweep import run_sweep


@default_broker.task(task_name="temporary_works:sweep", schedule=[{"cron": "41 * * * *"}])
async def hourly_sweep(db: DBSession) -> int:
    return (await run_sweep(db)).total


@default_broker.task(task_name="temporary_works:purge_bin", schedule=[{"cron": "23 3 * * *"}])
async def daily_purge(db: DBSession) -> int:
    """Daily: physically remove recycle-bin records whose project retention has passed (the Deleted folder is never
    touched). Returns how many were removed."""
    return (await purge_expired(db)).total

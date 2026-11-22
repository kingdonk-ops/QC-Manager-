"""Daily calibration due reminders."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .service import due_reminders


@default_broker.task(task_name="calibration:due_reminders", schedule=[{"cron": "13 21 * * *"}])
async def calibration_due_reminders(db: DBSession) -> int:
    """Remind custodians of equipment due or overdue for calibration (21:13 UTC, early morning in Australia)."""
    return await due_reminders(db)

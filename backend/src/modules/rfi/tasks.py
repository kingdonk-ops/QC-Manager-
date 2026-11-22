"""Daily overdue reminders to whoever holds the ball."""

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .service import overdue_reminders as remind


@default_broker.task(task_name="rfi:overdue_reminders", schedule=[{"cron": "13 21 * * *"}])
async def overdue_reminders(db: DBSession) -> int:
    """Notify the ball-in-court user of each open RFI past its due date (21:13 UTC)."""
    return await remind(db)

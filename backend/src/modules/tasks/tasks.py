"""Daily due-date reminders."""

from datetime import date, timedelta

from sqlalchemy import select

from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from ..notifications.constants import Category
from ..notifications.service import notify
from .constants import TaskStatus
from .models import Task
from .service import link_of


@default_broker.task(task_name="tasks:due_reminders", schedule=[{"cron": "7 21 * * *"}])
async def due_reminders(db: DBSession) -> int:
    """Remind assignees of tasks due tomorrow or overdue (21:07 UTC, early morning in Australia)."""
    tomorrow = date.today() + timedelta(days=1)
    rows = (
        await db.execute(
            select(Task).where(Task.status != TaskStatus.DONE.value, Task.assignee_id.is_not(None), Task.due_date <= tomorrow)
        )
    ).scalars()
    count = 0
    for task in rows:
        assert task.due_date is not None and task.assignee_id is not None
        when = (
            "is overdue" if task.due_date < date.today() else "is due " + ("tomorrow" if task.due_date == tomorrow else "today")
        )
        await notify(
            db,
            [task.assignee_id],
            Category.DUE,
            f"{task.code} {when}",
            body=task.title,
            link=link_of(task),
            entity=("task", task.id),
        )
        count += 1
    await db.commit()
    return count

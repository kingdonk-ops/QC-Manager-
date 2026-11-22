"""Tasks for reporting: the task list as a dataset, open/overdue/completion KPIs, and a task importer."""

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import (
    Column,
    Dataset,
    Importer,
    ImportField,
    ImportJob,
    ImportReport,
    Kpi,
    register_dataset,
    register_importer,
    register_kpi,
)
from ..user.models import User
from .constants import Priority, TaskStatus, TaskType
from .models import Task
from .service import create_task

STATUS_WORDS = {
    "to do": "todo",
    "open": "todo",
    "not started": "todo",
    "new": "todo",
    "in progress": "in_progress",
    "started": "in_progress",
    "doing": "in_progress",
    "in review": "review",
    "complete": "done",
    "completed": "done",
    "closed": "done",
    "finished": "done",
}


async def task_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Task, User.name)
            .outerjoin(User, User.id == Task.assignee_id)
            .where(Task.project_id == project_id)
            .order_by(Task.code)
        )
    ).all()
    today = date.today()
    return [
        {
            "project_id": t.project_id,
            "code": t.code,
            "title": t.title,
            "type": t.type,
            "status": t.status,
            "priority": t.priority,
            "assignee": name,
            "start_date": t.start_date,
            "due_date": t.due_date,
            "overdue": bool(t.due_date and t.due_date < today and t.status != TaskStatus.DONE),
            "done": t.status == TaskStatus.DONE,
            "created_at": t.created_at.date() if t.created_at else None,
            "completed_at": t.completed_at.date() if t.completed_at else None,
            "tasks": 1,
        }
        for t, name in rows
    ]


register_dataset(
    Dataset(
        name="tasks",
        module="tasks",
        title="Tasks",
        description="Every task on the project with its status, priority, assignee and dates.",
        permission="tasks.read",
        columns=[
            Column("code", "Code"),
            Column("title", "Title"),
            Column("type", "Type"),
            Column("status", "Status"),
            Column("priority", "Priority"),
            Column("assignee", "Assignee"),
            Column("start_date", "Start", "date"),
            Column("due_date", "Due", "date"),
            Column("overdue", "Overdue", "bool"),
            Column("done", "Done", "bool"),
            Column("created_at", "Created", "date"),
            Column("completed_at", "Completed", "date"),
            Column("tasks", "Count", "number"),
        ],
        rows=task_rows,
    )
)


async def _count(db: AsyncSession, project_id: int, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id, *where)) or 0)


async def open_tasks(db: AsyncSession, project_id: int) -> int:
    return await _count(db, project_id, Task.status != TaskStatus.DONE.value)


async def overdue_tasks(db: AsyncSession, project_id: int) -> int:
    return await _count(db, project_id, Task.status != TaskStatus.DONE.value, Task.due_date < date.today())


async def completion_rate(db: AsyncSession, project_id: int) -> float | None:
    total = await _count(db, project_id)
    if not total:
        return None
    return round(await _count(db, project_id, Task.status == TaskStatus.DONE.value) / total * 100, 1)


register_kpi(Kpi("tasks.open", "tasks", "Open tasks", open_tasks, unit="count", good="down", permission="tasks.read"))
register_kpi(
    Kpi(
        "tasks.overdue",
        "tasks",
        "Overdue tasks",
        overdue_tasks,
        unit="count",
        good="down",
        thresholds=(0, 5),
        permission="tasks.read",
        portfolio=True,
    )
)
register_kpi(
    Kpi(
        "tasks.completion_rate",
        "tasks",
        "Task completion",
        completion_rate,
        unit="%",
        thresholds=(80, 50),
        permission="tasks.read",
        portfolio=True,
    )
)


# --- import -------------------------------------------------------------------------------------------


def _word(value: Any) -> str:
    return re.sub(r"[\s\-]+", " ", str(value or "").strip().lower())


def _choice(value: Any, choices: set[str], synonyms: dict[str, str] | None = None) -> str | None:
    text = _word(value)
    if not text:
        return None
    if synonyms and text in synonyms:
        return synonyms[text]
    snake = text.replace(" ", "_")
    return snake if snake in choices else None


def parse_date(value: Any) -> date | None | str:
    """A date from an Excel cell or text (ISO, or day-first like 31/01/2026); an error message if unreadable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return f"'{text}' isn't a date"


async def import_tasks(db: AsyncSession, job: ImportJob) -> ImportReport:
    report = ImportReport(dry_run=job.dry_run, rows=len(job.rows))
    if job.project_id is None:
        report.errors.append("Choose a project.")
        return report
    on_duplicate = job.options.get("on_duplicate", "skip")
    open_titles = {
        t.lower()
        for t in (
            await db.execute(select(Task.title).where(Task.project_id == job.project_id, Task.status != TaskStatus.DONE.value))
        ).scalars()
    }
    emails = {str(r.get("assignee_email") or "").strip().lower() for r in job.rows} - {""}
    users = (
        dict(
            (await db.execute(select(func.lower(User.email), User.id).where(func.lower(User.email).in_(emails)))).tuples().all()
        )
        if emails
        else {}
    )
    for line, row in enumerate(job.rows, start=2):
        title = str(row.get("title") or "").strip()
        if not title:
            if any(v not in (None, "") for v in row.values()):
                report.errors.append(f"Row {line}: no title")
                report.skipped += 1
            else:
                report.rows -= 1
            continue
        problems: list[str] = []
        fields: dict[str, Any] = {}
        for key, enum, synonyms in (
            ("type", TaskType, None),
            ("status", TaskStatus, STATUS_WORDS),
            ("priority", Priority, None),
        ):
            raw = row.get(key)
            if raw in (None, ""):
                continue
            picked = _choice(raw, {e.value for e in enum}, synonyms)
            if picked is None:
                problems.append(f"{key} '{raw}' isn't one of {', '.join(e.value for e in enum)}")
            else:
                fields[key] = picked
        for key in ("start_date", "due_date"):
            parsed = parse_date(row.get(key))
            if isinstance(parsed, str):
                problems.append(f"{key.replace('_', ' ')}: {parsed}")
            elif parsed is not None:
                fields[key] = parsed
        if len(title) > 300:
            problems.append("title is longer than 300 characters")
        if problems:
            report.errors.append(f"Row {line}: " + "; ".join(problems))
            report.skipped += 1
            continue
        email = str(row.get("assignee_email") or "").strip().lower()
        if email:
            if email in users:
                fields["assignee_id"] = users[email]
            else:
                report.warnings.append(f"Row {line}: no user with email {email}; left unassigned")
        if row.get("description"):
            fields["description"] = str(row["description"])
        if title.lower() in open_titles and on_duplicate == "skip":
            report.warnings.append(f"Row {line}: an open task '{title}' already exists; skipped")
            report.skipped += 1
            continue
        open_titles.add(title.lower())
        report.created += 1
        if not job.dry_run:
            await create_task(db, project_id=job.project_id, title=title, created_by_id=job.user_id, commit=False, **fields)
    if not job.dry_run and report.created:
        await db.commit()
    return report


register_importer(
    Importer(
        name="tasks",
        module="tasks",
        title="Tasks",
        description="Tasks with type, status, priority, dates and assignee (by email). Open duplicates are skipped.",
        permission="tasks.create",
        options={"on_duplicate": ["skip", "create"]},
        fields=[
            ImportField("title", "Title", required=True, aliases=("task", "name", "summary", "activity")),
            ImportField("description", "Description", aliases=("details", "notes")),
            ImportField("type", "Type", aliases=("task type", "category")),
            ImportField("status", "Status", aliases=("state",)),
            ImportField("priority", "Priority"),
            ImportField("start_date", "Start date", aliases=("start", "starts")),
            ImportField("due_date", "Due date", aliases=("due", "deadline", "finish", "end date")),
            ImportField("assignee_email", "Assignee email", aliases=("assignee", "assigned to", "owner", "email")),
        ],
        apply=import_tasks,
    )
)

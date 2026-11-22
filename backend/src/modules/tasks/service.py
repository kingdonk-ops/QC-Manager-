from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import next_reference
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .constants import TaskStatus
from .models import Task, TaskBoard
from .schemas import TaskRead


class TaskNotFoundError(ResourceNotFoundError):
    public_detail = "Task not found."


class WipLimitReached(ValidationError):
    public_detail = "That column is at its WIP limit. Finish something first, or move it anyway."


def link_of(task: Task) -> str:
    return f"/tasks?project={task.project_id}&task={task.id}"


async def read_tasks(db: AsyncSession, tasks: list[Task]) -> list[dict[str, Any]]:
    ids = {t.assignee_id for t in tasks if t.assignee_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    today = date.today()
    return [
        TaskRead.model_validate(t)
        .model_copy(
            update={
                "assignee_name": names.get(t.assignee_id) if t.assignee_id else None,
                "overdue": bool(t.due_date and t.due_date < today and t.status != TaskStatus.DONE),
            }
        )
        .model_dump(mode="json")
        for t in tasks
    ]


async def _bottom(db: AsyncSession, project_id: int, status: str) -> float:
    top = await db.scalar(select(func.max(Task.position)).where(Task.project_id == project_id, Task.status == status))
    return (top or 0.0) + 1024.0


async def create_task(
    db: AsyncSession,
    *,
    project_id: int,
    title: str,
    created_by_id: int | None,
    entity: tuple[str, int] | None = None,
    commit: bool = True,
    **fields: Any,
) -> Task:
    """Create a task, notify its assignee, and (by default) commit. For other modules too."""
    status = str(fields.pop("status", TaskStatus.TODO))
    task = Task(
        project_id=project_id,
        code=await next_reference(db, "TASK", project_id),
        title=title,
        status=status,
        position=await _bottom(db, project_id, status),
        created_by_id=created_by_id,
        entity_type=entity[0] if entity else fields.pop("entity_type", None),
        entity_id=entity[1] if entity else fields.pop("entity_id", None),
        **{k: (v.value if hasattr(v, "value") else v) for k, v in fields.items() if v is not None},
    )
    if status == TaskStatus.DONE:
        task.completed_at = datetime.now(UTC)
    db.add(task)
    await db.flush()
    if task.assignee_id:
        await notify(
            db,
            [task.assignee_id],
            Category.ASSIGNMENT,
            f"{task.code}: {task.title}",
            body="Assigned to you.",
            link=link_of(task),
            entity=("task", task.id),
            actor_id=created_by_id,
        )
    if commit:
        await db.commit()
    return task


async def get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError("No such task")
    return task


async def wip_limits(db: AsyncSession, project_id: int) -> dict[str, int]:
    board = await db.get(TaskBoard, project_id)
    return {s.value: int((board.wip_limits if board else {}).get(s.value, 0)) for s in TaskStatus}


async def apply_update(db: AsyncSession, task: Task, changes: dict[str, Any], actor: dict[str, Any]) -> None:
    before_status, before_assignee = task.status, task.assignee_id
    for key, value in changes.items():
        setattr(task, key, value.value if hasattr(value, "value") else value)
    if task.status != before_status:
        if task.status == TaskStatus.DONE:
            task.completed_at = datetime.now(UTC)
        elif before_status == TaskStatus.DONE:
            task.completed_at = None
        if "position" not in changes:
            task.position = await _bottom(db, task.project_id, task.status)
        watchers = {task.assignee_id, task.created_by_id} - {None}
        await notify(
            db,
            [w for w in watchers if w],
            Category.STATUS,
            f"{task.code} is now {task.status.replace('_', ' ')}",
            body=task.title,
            link=link_of(task),
            entity=("task", task.id),
            actor_id=actor["id"],
        )
    if task.assignee_id and task.assignee_id != before_assignee:
        await notify(
            db,
            [task.assignee_id],
            Category.ASSIGNMENT,
            f"{task.code}: {task.title}",
            body=f"Assigned to you by {actor['name']}.",
            link=link_of(task),
            entity=("task", task.id),
            actor_id=actor["id"],
        )
    await db.commit()


async def move(
    db: AsyncSession, task: Task, status: str, before_id: int | None, override_wip: bool, actor: dict[str, Any]
) -> None:
    if status != task.status and not override_wip:
        limit = (await wip_limits(db, task.project_id)).get(status, 0)
        if limit:
            count = await db.scalar(
                select(func.count()).select_from(Task).where(Task.project_id == task.project_id, Task.status == status)
            )
            if (count or 0) >= limit:
                raise WipLimitReached(status)
    position: float
    if before_id is not None:
        before = await get_task(db, before_id)
        above = await db.scalar(
            select(func.max(Task.position)).where(
                Task.project_id == task.project_id, Task.status == status, Task.position < before.position, Task.id != task.id
            )
        )
        position = ((above if above is not None else before.position - 1024.0) + before.position) / 2
    else:
        position = await _bottom(db, task.project_id, status)
    await apply_update(db, task, {"status": status, "position": position}, actor)

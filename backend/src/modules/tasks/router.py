"""Mounted at /api/v1/tasks."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from ..user.models import User
from . import service
from .constants import TYPE_FIELDS, Priority, TaskStatus, TaskType
from .models import Task, TaskBoard
from .permissions import TaskPermissionName as P
from .schemas import Assignee, Board, BoardColumn, TaskCreate, TaskMove, TaskRead, TaskUpdate, WipLimits

router = APIRouter(tags=["Tasks"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


@router.get(
    "/",
    response_model=PaginatedListResponse[TaskRead],
    summary="List Tasks",
    description="Filter by project, assignee (`me` for yourself), status, type, priority, overdue, or the record they link to.",
    dependencies=perm(P.READ),
)
async def list_tasks(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    assignee: Annotated[str | None, Query(pattern=r"^(me|\d+)$")] = None,
    status: TaskStatus | None = None,
    type: TaskType | None = None,
    priority: Priority | None = None,
    overdue: bool = False,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[int | None, Query(ge=1)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Task.project_id == project_id]
    if assignee:
        where.append(Task.assignee_id == (user["id"] if assignee == "me" else int(assignee)))
    if status:
        where.append(Task.status == status.value)
    if type:
        where.append(Task.type == type.value)
    if priority:
        where.append(Task.priority == priority.value)
    if overdue:
        where += [Task.due_date < date.today(), Task.status != TaskStatus.DONE.value]
    if entity_type:
        where.append(Task.entity_type == entity_type)
    if entity_id:
        where.append(Task.entity_id == entity_id)
    if search:
        where.append(func.lower(Task.title + " " + Task.code).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(Task).where(*where))
    rows = (
        await db.execute(
            select(Task)
            .where(*where)
            .order_by(Task.due_date.is_(None), Task.due_date, Task.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_tasks(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=TaskRead, status_code=201, summary="Create a Task", dependencies=perm(P.CREATE))
async def create(values: TaskCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    fields = values.model_dump(exclude={"project_id", "title"})
    task = await service.create_task(db, project_id=values.project_id, title=values.title, created_by_id=user["id"], **fields)
    return (await service.read_tasks(db, [task]))[0]


@router.get("/board/{project_id}", response_model=Board, summary="The Project's Kanban Board", dependencies=perm(P.READ))
async def board(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Board:
    await readable_project(db, project_id, user["id"], held)
    rows = list(
        (await db.execute(select(Task).where(Task.project_id == project_id).order_by(Task.position, Task.id))).scalars()
    )
    read = await service.read_tasks(db, rows)
    limits = await service.wip_limits(db, project_id)
    return Board(
        project_id=project_id,
        columns=[
            BoardColumn(status=s, wip_limit=limits[s.value], tasks=[TaskRead(**t) for t in read if t["status"] == s.value])
            for s in TaskStatus
        ],
        type_fields={k.value if hasattr(k, "value") else k: v for k, v in TYPE_FIELDS.items()},
    )


@router.put("/board/{project_id}/limits", response_model=Board, summary="Set WIP Limits", dependencies=perm(P.UPDATE))
async def set_limits(
    project_id: Id, values: WipLimits, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Board:
    await readable_project(db, project_id, user["id"], held)
    b = await db.get(TaskBoard, project_id)
    limits = {k.value: v for k, v in values.wip_limits.items()}
    if b is None:
        db.add(TaskBoard(project_id=project_id, wip_limits=limits))
    else:
        b.wip_limits = {**b.wip_limits, **limits}
    await db.commit()
    return await board(project_id, db, user, held)


@router.get(
    "/assignees",
    response_model=list[Assignee],
    summary="People Tasks Can Be Assigned To",
    description="Active accounts by name, for assignee pickers here and in other modules.",
    dependencies=perm(P.READ),
)
async def assignees(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> Any:
    where: list[Any] = [User.is_deleted.is_(False)]
    if search:
        where.append(func.lower(User.name).like(f"%{search.lower()}%"))
    rows = await db.execute(select(User.id, User.name, User.email).where(*where).order_by(User.name).limit(limit))
    return [{"id": i, "name": n, "email": e} for i, n, e in rows.tuples().all()]


@router.get("/{task_id}", response_model=TaskRead, summary="Get a Task", dependencies=perm(P.READ))
async def get(task_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    task = await service.get_task(db, task_id)
    await readable_project(db, task.project_id, user["id"], held)
    return (await service.read_tasks(db, [task]))[0]


@router.patch("/{task_id}", response_model=TaskRead, summary="Update a Task", dependencies=perm(P.UPDATE))
async def update(
    task_id: Id, values: TaskUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    task = await service.get_task(db, task_id)
    await readable_project(db, task.project_id, user["id"], held)
    await service.apply_update(db, task, values.model_dump(exclude_unset=True), user)
    return (await service.read_tasks(db, [task]))[0]


@router.post(
    "/{task_id}/move",
    response_model=TaskRead,
    summary="Move a Card on the Board",
    description="Refused with 422 when the target column is at its WIP limit, unless `override_wip`.",
    dependencies=perm(P.UPDATE),
)
async def move(task_id: Id, values: TaskMove, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    task = await service.get_task(db, task_id)
    await readable_project(db, task.project_id, user["id"], held)
    await service.move(db, task, values.status.value, values.before_id, values.override_wip, user)
    return (await service.read_tasks(db, [task]))[0]


@router.delete("/{task_id}", summary="Delete a Task", dependencies=perm(P.DELETE))
async def delete(task_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    task = await service.get_task(db, task_id)
    await readable_project(db, task.project_id, user["id"], held)
    await db.delete(task)
    await db.commit()
    return {"message": "Task deleted"}

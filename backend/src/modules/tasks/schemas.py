from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import Priority, TaskStatus, TaskType

Title = Annotated[str, Field(min_length=1, max_length=300)]
EntityType = Annotated[str | None, Field(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]


class TaskCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Title
    description: str | None = None
    type: TaskType = TaskType.GENERAL
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    assignee_id: int | None = None
    start_date: date | None = None
    due_date: date | None = None
    type_fields: dict[str, Any] = Field(default_factory=dict)
    entity_type: EntityType = None
    entity_id: int | None = None


class TaskUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: str | None = None
    type: TaskType | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    assignee_id: int | None = None
    start_date: date | None = None
    due_date: date | None = None
    type_fields: dict[str, Any] | None = None
    position: float | None = None


class TaskMove(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus
    before_id: int | None = Field(None, description="Place above this card; omit for the bottom of the column")
    override_wip: bool = False


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    type: str
    status: str
    priority: str
    assignee_id: int | None
    assignee_name: str | None = None
    start_date: date | None
    due_date: date | None
    overdue: bool = False
    position: float
    type_fields: dict[str, Any]
    entity_type: str | None
    entity_id: int | None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class BoardColumn(BaseModel):
    status: TaskStatus
    wip_limit: int
    tasks: list[TaskRead]


class Board(BaseModel):
    project_id: int
    columns: list[BoardColumn]
    type_fields: dict[str, list[str]]


class WipLimits(EncodableText):
    model_config = ConfigDict(extra="forbid")

    wip_limits: dict[TaskStatus, Annotated[int, Field(ge=0, le=500)]]


class Assignee(BaseModel):
    id: int
    name: str
    email: str

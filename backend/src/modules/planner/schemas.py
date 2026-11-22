from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .constants import (
    ConstraintCategory,
    ConstraintStatus,
    PlanKind,
    PrerequisiteKind,
    PrerequisiteStatus,
)

Name = Annotated[str, Field(min_length=1, max_length=200)]
Short = Annotated[str | None, Field(max_length=120)]
Hours = Annotated[Decimal, Field(ge=0, le=100000, max_digits=10, decimal_places=2)]
Qty = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]


# --- crews ---------------------------------------------------------------------------------------------


class CrewMember(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    trade: Short = None
    user_id: int | None = Field(None, ge=1)


class CrewIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    code: Annotated[str, Field(min_length=1, max_length=40)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    trade: Annotated[str | None, Field(max_length=60)] = None
    supervisor_id: int | None = Field(None, ge=1)
    members: list[CrewMember] = Field(default_factory=list, max_length=200)
    shift_hours: Hours = Decimal("10")
    active: bool = True


class CrewUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str | None, Field(min_length=1, max_length=40)] = None
    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    trade: Annotated[str | None, Field(max_length=60)] = None
    supervisor_id: int | None = Field(None, ge=1)
    members: list[CrewMember] | None = Field(None, max_length=200)
    shift_hours: Hours | None = None
    active: bool | None = None


class CrewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    name: str
    trade: str | None
    supervisor_id: int | None
    supervisor_name: str | None = None
    members: list[dict[str, Any]]
    shift_hours: Decimal
    active: bool
    headcount: int = 0


# --- plans ---------------------------------------------------------------------------------------------


class PlanMilestone(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    day: date


class PlanIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Name
    window_start: date
    window_end: date
    kind: PlanKind = PlanKind.LOOK_AHEAD
    owner_id: int | None = Field(None, ge=1)
    client_ref: Annotated[str | None, Field(max_length=60)] = None
    schedule_activity_ids: list[int] = Field(default_factory=list, max_length=500)
    milestones: list[PlanMilestone] = Field(default_factory=list, max_length=50)
    notes: str | None = None

    @model_validator(mode="after")
    def _window(self) -> "PlanIn":
        if self.window_end < self.window_start:
            raise ValueError("The window ends before it starts.")
        return self


class PlanUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Name | None = None
    window_start: date | None = None
    window_end: date | None = None
    kind: PlanKind | None = None
    owner_id: int | None = Field(None, ge=1)
    client_ref: Annotated[str | None, Field(max_length=60)] = None
    schedule_activity_ids: list[int] | None = Field(None, max_length=500)
    milestones: list[PlanMilestone] | None = Field(None, max_length=50)
    notes: str | None = None


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    kind: str
    status: str
    window_start: date
    window_end: date
    collection_id: int | None
    owner_id: int | None
    client_ref: str | None
    schedule_activity_ids: list[int]
    milestones: list[dict[str, Any]]
    notes: str | None
    issued_at: datetime | None
    pack_count: int = 0
    anchor_count: int = 0
    planned_hours: Decimal = Decimal(0)


class PlannerTransition(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=20)
    note: Annotated[str | None, Field(max_length=1000)] = None
    force: bool = Field(False, description="Move a pack to ready despite blocking findings.")


# --- packs ---------------------------------------------------------------------------------------------


class PackLineIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_id: int | None = Field(None, ge=1, description="Any node; resolved to the work anchor on its path.")
    item_id: int | None = Field(None, ge=1, description="Or an item; its node's work anchor is used.")
    activity_code: Annotated[str | None, Field(max_length=40)] = None
    description: Annotated[str | None, Field(max_length=300)] = None
    planned_qty: Qty | None = None
    uom: Annotated[str | None, Field(max_length=20)] = None
    planned_hours: Hours | None = None


class PackLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    anchor_id: int
    anchor_code: str | None = None
    anchor_path: str | None = None
    item_id: int | None
    seq: int
    activity_code: str | None
    description: str | None
    planned_qty: Decimal | None
    uom: str | None
    planned_hours: Decimal | None


class PackIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    plan_id: int = Field(ge=1)
    title: Name
    crew_id: int | None = Field(None, ge=1)
    supervisor_id: int | None = Field(None, ge=1)
    planned_start: date | None = None
    planned_end: date | None = None
    schedule_activity_id: int | None = Field(None, ge=1)
    access: Annotated[str | None, Field(max_length=20)] = None
    notes: str | None = None
    lines: list[PackLineIn] = Field(default_factory=list, max_length=500)


class PackUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Name | None = None
    crew_id: int | None = Field(None, ge=1)
    supervisor_id: int | None = Field(None, ge=1)
    planned_start: date | None = None
    planned_end: date | None = None
    schedule_activity_id: int | None = Field(None, ge=1)
    access: Annotated[str | None, Field(max_length=20)] = None
    notes: str | None = None


class PackLinesIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    lines: list[PackLineIn] = Field(max_length=500)


class ReadinessFindingRead(BaseModel):
    source: str
    kind: str
    severity: str
    message: str
    anchor_id: int | None = None


class PrerequisiteIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    kind: PrerequisiteKind
    description: Annotated[str, Field(min_length=1, max_length=300)]
    status: PrerequisiteStatus = PrerequisiteStatus.PENDING
    required_by: date | None = None
    reference: Short = None


class PrerequisiteUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    status: PrerequisiteStatus | None = None
    required_by: date | None = None
    reference: Short = None


class PrerequisiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pack_id: int
    kind: str
    description: str
    status: str
    required_by: date | None
    reference: str | None
    cleared_at: datetime | None


class PackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    plan_id: int
    code: str
    title: str
    status: str
    crew_id: int | None
    crew_name: str | None = None
    supervisor_id: int | None
    supervisor_name: str | None = None
    planned_start: date | None
    planned_end: date | None
    schedule_activity_id: int | None
    access: str | None
    notes: str | None
    issued_at: datetime | None
    planned_hours: Decimal = Decimal(0)
    lines: list[PackLineRead] = Field(default_factory=list)
    prerequisites: list[PrerequisiteRead] = Field(default_factory=list)
    findings: list[ReadinessFindingRead] = Field(default_factory=list)
    readiness: str = "ready"
    """``ready`` (no findings), ``warning`` or ``blocked``."""


# --- constraints ---------------------------------------------------------------------------------------


class ConstraintIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    category: ConstraintCategory
    description: Annotated[str, Field(min_length=1, max_length=4000)]
    plan_id: int | None = Field(None, ge=1)
    pack_id: int | None = Field(None, ge=1)
    node_id: int | None = Field(None, ge=1, description="Resolved to its work anchor.")
    owner_id: int | None = Field(None, ge=1)
    due_date: date | None = None


class ConstraintUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    category: ConstraintCategory | None = None
    description: Annotated[str | None, Field(min_length=1, max_length=4000)] = None
    owner_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    status: ConstraintStatus | None = None
    resolution: Annotated[str | None, Field(max_length=4000)] = None


class ConstraintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    category: str
    description: str
    plan_id: int | None
    pack_id: int | None
    anchor_id: int | None
    owner_id: int | None
    owner_name: str | None = None
    due_date: date | None
    status: str
    overdue: bool = False
    resolved_at: datetime | None
    resolution: str | None
    created_at: datetime | None = None


# --- board and daily plans -----------------------------------------------------------------------------


class AssignmentIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    plan_id: int = Field(ge=1)
    crew_id: int = Field(ge=1)
    anchor_id: int = Field(ge=1)
    work_date: date
    pack_id: int | None = Field(None, ge=1)
    planned_hours: Hours | None = None
    note: Annotated[str | None, Field(max_length=300)] = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    crew_id: int
    crew_code: str | None = None
    crew_name: str | None = None
    anchor_id: int
    anchor_code: str | None = None
    anchor_path: str | None = None
    work_date: date
    pack_id: int | None
    pack_code: str | None = None
    planned_hours: Decimal | None
    note: str | None
    warnings: list[str] = Field(default_factory=list)


class PlanBoardRow(BaseModel):
    anchor_id: int
    anchor_code: str
    anchor_path: str
    pack_ids: list[int]
    pack_codes: list[str]
    planned_qty: Decimal | None
    uom: str | None
    planned_hours: Decimal
    readiness: str


class PlanBoard(BaseModel):
    plan: PlanRead
    days: list[date]
    rows: list[PlanBoardRow]
    crews: list[CrewRead]
    assignments: list[AssignmentRead]


class PlanVsActualRow(BaseModel):
    anchor_id: int
    anchor_code: str
    anchor_path: str
    uom: str | None
    budget_qty: Decimal | None
    planned_qty: Decimal
    actual_qty: Decimal
    earned_qty: Decimal | None
    planned_hours: Decimal
    actual_hours: Decimal
    assigned_days: int
    hours_variance: Decimal
    percent_qty: float | None


class PlanVsActual(BaseModel):
    plan_id: int
    rows: list[PlanVsActualRow]
    planned_hours: Decimal
    actual_hours: Decimal
    planned_qty: Decimal
    actual_qty: Decimal

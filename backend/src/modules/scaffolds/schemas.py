from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import DutyClass, InspectionKind, ModificationStatus, ScaffoldStatus, ScaffoldType, Tag

Text300 = Annotated[str | None, Field(max_length=300)]
LongText = Annotated[str | None, Field(max_length=10_000)]


class Dimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_m: Annotated[float | None, Field(ge=0, le=10_000)] = None
    width_m: Annotated[float | None, Field(ge=0, le=10_000)] = None
    height_m: Annotated[float | None, Field(ge=0, le=1_000)] = None
    lifts: Annotated[int | None, Field(ge=0, le=500)] = None
    bays: Annotated[int | None, Field(ge=0, le=5_000)] = None


class ScaffoldCreate(EncodableText):
    """A build request."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    node_id: int = Field(ge=1, description="Where it stands: a work anchor, area or asset node")
    item_id: int | None = Field(None, ge=1)
    location_text: Text300 = None
    purpose: LongText = None
    scaffold_type: ScaffoldType = ScaffoldType.INDEPENDENT
    duty_class: DutyClass = DutyClass.MEDIUM
    max_load_kpa: Annotated[Decimal | None, Field(ge=0, le=100_000)] = None
    dimensions: Dimensions = Field(default_factory=Dimensions)
    required_by: date | None = None
    custodian_id: int | None = Field(None, ge=1)
    linked_node_ids: list[Annotated[int, Field(ge=1)]] = Field(default_factory=list, max_length=200)
    notes: LongText = None


class ScaffoldUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_id: int | None = Field(None, ge=1)
    item_id: int | None = Field(None, ge=1)
    location_text: Text300 = None
    purpose: LongText = None
    scaffold_type: ScaffoldType | None = None
    duty_class: DutyClass | None = None
    max_load_kpa: Annotated[Decimal | None, Field(ge=0, le=100_000)] = None
    dimensions: Dimensions | None = None
    required_by: date | None = None
    custodian_id: int | None = Field(None, ge=1)
    inspection_interval_days: Annotated[int | None, Field(ge=1, le=90)] = None
    hire_rate: Annotated[Decimal | None, Field(ge=0, le=10_000_000)] = None
    linked_node_ids: list[Annotated[int, Field(ge=1)]] | None = Field(None, max_length=200)
    notes: LongText = None
    erected_on: date | None = None
    dismantled_on: date | None = None


class ScaffoldTransition(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: ScaffoldStatus
    on: date | None = Field(None, description="The day it happened (erected, dismantled); today by default")
    note: Annotated[str | None, Field(max_length=2000)] = None


class ChecklistRow(EncodableText):
    model_config = ConfigDict(extra="forbid")

    item: Annotated[str, Field(min_length=1, max_length=300)]
    ok: bool
    note: Annotated[str | None, Field(max_length=1000)] = None


class ScaffoldInspectionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    kind: InspectionKind
    tag: Tag = Field(description="green: safe, yellow: restricted, red: do not use")
    tag_no: Annotated[str | None, Field(max_length=40)] = None
    restrictions: Annotated[str | None, Field(max_length=2000)] = None
    checklist: list[ChecklistRow] = Field(default_factory=list, max_length=100)
    notes: LongText = None
    inspected_at: datetime | None = Field(None, description="Now by default")


class ScaffoldInspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scaffold_id: int
    kind: str
    inspected_at: datetime
    inspector_id: int | None
    inspector_name: str | None = None
    tag: str
    tag_no: str | None
    restrictions: str | None
    checklist: list[dict[str, Any]]
    notes: str | None
    next_due_at: datetime | None


class InspectionRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: InspectionKind = InspectionKind.AD_HOC
    note: Annotated[str | None, Field(max_length=2000)] = None


class WeatherEvent(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    node_id: int | None = Field(None, ge=1, description="Limit to scaffolds under this node; the whole project by default")
    description: Annotated[str, Field(min_length=1, max_length=500)]


class ModificationCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=5000)]
    required_by: date | None = None


class ModificationDecision(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: ModificationStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class ModificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scaffold_id: int
    description: str
    required_by: date | None
    status: str
    requested_by_id: int | None
    decided_by_id: int | None
    decided_at: datetime | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime | None = None


class ScaffoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    node_id: int
    node_path: str | None = None
    item_id: int | None
    location_text: str | None
    purpose: str | None
    scaffold_type: str
    duty_class: str
    max_load_kpa: Decimal | None
    dimensions: dict[str, Any]
    status: str
    required_by: date | None
    requested_by_id: int | None
    requested_by_name: str | None = None
    custodian_id: int | None
    custodian_name: str | None = None
    approved_by_id: int | None
    approved_at: datetime | None
    erected_on: date | None
    dismantle_requested_on: date | None
    dismantled_on: date | None
    inspection_interval_days: int
    tag_status: str
    effective_tag: str = "none"
    inspection_overdue: bool = False
    tag_no: str | None
    tag_restrictions: str | None
    last_inspected_at: datetime | None
    next_inspection_due: datetime | None
    days_erected: int = 0
    hire_rate: Decimal | None
    hire_cost: Decimal | None = None
    linked_node_ids: list[int] = Field(default_factory=list)
    notes: str | None
    created_at: datetime | None = None


class HireLine(BaseModel):
    scaffold_id: int
    code: str
    tag_no: str | None
    status: str
    node_path: str | None
    erected_on: date | None
    dismantled_on: date | None
    days: int
    rate: Decimal | None
    cost: Decimal | None


class HireSummary(BaseModel):
    project_id: int
    currency: str
    period_start: date | None
    period_end: date
    lines: list[HireLine]
    total_days: int
    total_cost: Decimal


class ReadinessBlocker(BaseModel):
    scaffold_id: int
    code: str
    status: str
    effective_tag: str
    reason: str


class Readiness(BaseModel):
    node_id: int
    on_date: date
    ready: bool
    scaffolds: int
    blockers: list[ReadinessBlocker]


class TagBoard(BaseModel):
    green: list[ScaffoldRead]
    yellow: list[ScaffoldRead]
    red: list[ScaffoldRead]
    none: list[ScaffoldRead]


class StatusChangeRead(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

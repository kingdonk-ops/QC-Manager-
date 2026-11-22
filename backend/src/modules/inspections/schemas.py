from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText, PartialUpdate
from .constants import FollowUp, InspectionStatus, ResponseType, Result

Short = Annotated[str | None, Field(max_length=200)]
Reading = Annotated[float, Field(ge=-1e9, le=1e9)]


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=500)]
    response_type: ResponseType = ResponseType.PASS_FAIL
    unit: Annotated[str | None, Field(max_length=30)] = None
    min_value: Reading | None = Field(None, description="Lowest acceptable reading (numeric items)")
    max_value: Reading | None = Field(None, description="Highest acceptable reading (numeric items)")
    requires_photo_on_fail: bool = False
    guidance: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _limits(self) -> "ChecklistItem":
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value is above max_value")
        return self


class ChecklistSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    items: Annotated[list[ChecklistItem], Field(max_length=200)] = []


class ChecklistTemplateIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    trade: Annotated[str | None, Field(max_length=100)] = None
    activity: Short = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    sections: Annotated[list[ChecklistSection], Field(max_length=50)] = []
    active: bool = True


class ChecklistTemplateUpdate(EncodableText, PartialUpdate):
    """Changing the sections bumps the version; inspections already started keep their copy."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("name", "sections", "active")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    activity: Short = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    sections: Annotated[list[ChecklistSection] | None, Field(max_length=50)] = None
    active: bool | None = None


class ChecklistTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    trade: str | None
    activity: str | None
    description: str | None
    version: int
    sections: list[ChecklistSection]
    active: bool
    item_count: int = 0
    updated_at: datetime | None = None


class ChecklistStarterSeed(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)


class InspectionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    template_id: int = Field(ge=1)
    title: Annotated[str | None, Field(max_length=300)] = Field(None, description="Defaults to the template's name")
    location: Short = None
    area: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = Field(None, description="Defaults to the template's trade")
    inspector_id: int | None = Field(None, ge=1)
    scheduled_date: date | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class InspectionUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title",)

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    location: Short = None
    area: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    inspector_id: int | None = Field(None, ge=1)
    scheduled_date: date | None = None
    inspected_date: date | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class InspectionItemAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    result: Result | None = Field(None, description="pass, fail or na; send null to clear")
    reading: Reading | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class InspectionItemsFill(EncodableText):
    """Answers for some or all items. Fields left out of an answer keep their value."""

    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[InspectionItemAnswer], Field(min_length=1, max_length=500)]


class InspectionStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: InspectionStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class InspectionFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(ge=1)
    action: FollowUp = FollowUp.TASK
    assignee_id: int | None = Field(None, ge=1, description="Task assignee, or the NCR's responsible user")
    due_date: date | None = None
    severity: Annotated[str, Field(pattern=r"^(minor|major|critical)$")] = "minor"


class InspectionCompletion(EncodableText):
    """Completes the inspection. Each failed item gets a task unless ``follow_ups`` says ``ncr`` (or ``none``)."""

    model_config = ConfigDict(extra="forbid")

    follow_ups: Annotated[list[InspectionFollowUp], Field(max_length=500)] = []
    default_assignee_id: int | None = Field(None, ge=1)
    default_due_date: date | None = None
    allow_unanswered: bool = Field(False, description="Complete even with unanswered items")
    note: Annotated[str | None, Field(max_length=2000)] = None


class InspectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    section: str
    text: str
    response_type: str
    unit: str | None
    min_value: float | None
    max_value: float | None
    requires_photo_on_fail: bool
    guidance: str | None
    result: str | None
    reading: float | None
    outcome: str | None
    notes: str | None
    follow_up: str | None
    task_id: int | None
    ncr_id: int | None
    photo_count: int = 0


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    template_id: int | None
    template_name: str | None
    template_version: int | None
    location: str | None
    area: str | None
    trade: str | None
    inspector_id: int | None
    inspector_name: str | None = None
    scheduled_date: date | None
    inspected_date: date | None
    status: str
    notes: str | None
    passed: int
    failed: int
    not_applicable: int
    unanswered: int
    total: int = 0
    pass_rate: float | None
    completed_at: datetime | None
    created_at: datetime | None = None
    items: list[InspectionItemRead] = []


class InspectionTrendPoint(BaseModel):
    inspection_id: int
    code: str
    date: date | None
    pass_rate: float | None
    passed: int
    failed: int


class InspectionTrendMonth(BaseModel):
    month: str
    inspections: int
    passed: int
    failed: int
    pass_rate: float | None


class InspectionTrendGroup(BaseModel):
    key: str
    inspections: int
    passed: int
    failed: int
    pass_rate: float | None
    points: list[InspectionTrendPoint]
    monthly: list[InspectionTrendMonth]


class InspectionTrends(BaseModel):
    project_id: int
    group_by: str
    groups: list[InspectionTrendGroup]

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import Party, Priority, RfiStatus

Subject = Annotated[str, Field(min_length=1, max_length=300)]
EntityType = Annotated[str | None, Field(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]
Short = Annotated[str | None, Field(max_length=60)]
Place = Annotated[str | None, Field(max_length=200)]
Amount = Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999999999"), decimal_places=2)]
Days = Annotated[int | None, Field(ge=0, le=10000)]


class RfiCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    subject: Subject
    question: str = Field(min_length=1, max_length=20000)
    discipline: Short = None
    location: Place = None
    priority: Priority = Priority.MEDIUM
    status: RfiStatus = Field(RfiStatus.DRAFT, description="`draft` or `open` (issue it straight away)")
    raised_by_party: Party = Party.CONTRACTOR
    addressed_to_contact_id: int | None = Field(None, ge=1)
    addressed_to_user_id: int | None = Field(None, ge=1)
    due_date: date | None = Field(None, description="Defaults to today plus the project's RFI due days")
    ball_in_court: Party | None = Field(None, description="Defaults to the designer once issued")
    bic_user_id: int | None = Field(None, ge=1)
    bic_contact_id: int | None = Field(None, ge=1)
    cost_impact: bool = False
    schedule_impact: bool = False
    scope_impact: bool = False
    cost_impact_amount: Amount = None
    schedule_impact_days: Days = None
    entity_type: EntityType = None
    entity_id: int | None = Field(None, ge=1)


class RfiUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    subject: Subject | None = None
    question: str | None = Field(None, min_length=1, max_length=20000)
    discipline: Short = None
    location: Place = None
    priority: Priority | None = None
    raised_by_party: Party | None = None
    addressed_to_contact_id: int | None = Field(None, ge=1)
    addressed_to_user_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    cost_impact: bool | None = None
    schedule_impact: bool | None = None
    scope_impact: bool | None = None
    cost_impact_amount: Amount = None
    schedule_impact_days: Days = None
    entity_type: EntityType = None
    entity_id: int | None = Field(None, ge=1)


class RfiStatusChange(EncodableText):
    """Change the status, who holds the ball, or both."""

    model_config = ConfigDict(extra="forbid")

    status: RfiStatus | None = None
    ball_in_court: Party | None = None
    bic_user_id: int | None = Field(None, ge=1)
    bic_contact_id: int | None = Field(None, ge=1)
    note: str | None = Field(None, max_length=2000)


class RfiRespond(EncodableText):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20000)
    is_answer: bool = Field(True, description="An answer moves an open RFI to answered and hands the ball to the raiser")
    attachment_ids: list[Annotated[int, Field(ge=1)]] = Field(
        default_factory=list, max_length=20, description="Files already uploaded to the project, to attach"
    )


class RfiTaskCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=300)
    assignee_id: int | None = Field(None, ge=1)
    due_date: date | None = None


class RfiSettingsSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    default_due_days: int = Field(ge=1, le=365)


class RfiSettingsRead(BaseModel):
    project_id: int
    default_due_days: int


class Attachment(BaseModel):
    id: int
    name: str
    size: int
    revision: int


class ResponseRead(BaseModel):
    id: int
    rfi_id: int
    body: str
    is_answer: bool
    author_id: int | None
    author_name: str | None = None
    created_at: datetime | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class RfiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    subject: str
    question: str
    discipline: str | None
    location: str | None
    priority: str
    status: str
    raised_by_id: int | None
    raised_by_name: str | None = None
    raised_by_party: str
    addressed_to_contact_id: int | None
    addressed_to_contact_name: str | None = None
    addressed_to_user_id: int | None
    addressed_to_user_name: str | None = None
    due_date: date | None
    ball_in_court: str | None
    bic_user_id: int | None
    bic_user_name: str | None = None
    bic_contact_id: int | None
    bic_contact_name: str | None = None
    cost_impact: bool
    schedule_impact: bool
    scope_impact: bool
    cost_impact_amount: Decimal | None
    schedule_impact_days: int | None
    entity_type: str | None
    entity_id: int | None
    opened_on: date | None
    answered_at: datetime | None
    closed_at: datetime | None
    created_at: datetime | None = None
    overdue: bool = False
    days_open: int | None = None
    response_count: int = 0


class RfiDetail(RfiRead):
    responses: list[ResponseRead] = Field(default_factory=list)


class UserOption(BaseModel):
    id: int
    name: str


class CreatedTask(BaseModel):
    id: int
    code: str
    title: str

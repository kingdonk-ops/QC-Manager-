from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText, PartialUpdate
from .constants import ActionKind, ActionStatus, Disposition, NcrStatus, RootCause, Severity, Source

Cost = Annotated[Decimal, Field(max_digits=14, decimal_places=2, ge=0)]
Short = Annotated[str | None, Field(max_length=200)]
Text = Annotated[str | None, Field(max_length=20000)]


class NcrCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Text = None
    raised_on: date | None = Field(None, description="Defaults to today")
    location: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    responsible_user_id: int | None = Field(None, ge=1)
    responsible_contact_id: int | None = Field(None, ge=1, description="A contact from the directory")
    responsible_company_id: int | None = Field(None, ge=1, description="A company from the directory")
    source: Source = Source.OTHER
    source_reference: Short = None
    inspection_id: int | None = Field(None, ge=1)
    inspection_item_id: int | None = Field(None, ge=1)
    spec_reference: Short = Field(None, description="Specification clause or drawing reference")
    severity: Severity = Severity.MINOR


class NcrUpdate(EncodableText, PartialUpdate):
    """Only the fields sent change. The status changes through ``/status``."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title", "severity", "source", "rework_cost", "delay_cost", "other_cost", "days_delay")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    description: Text = None
    raised_on: date | None = None
    location: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    responsible_user_id: int | None = Field(None, ge=1)
    responsible_contact_id: int | None = Field(None, ge=1)
    responsible_company_id: int | None = Field(None, ge=1)
    source: Source | None = None
    source_reference: Short = None
    spec_reference: Short = None
    severity: Severity | None = None
    root_cause_category: RootCause | None = None
    root_cause_description: Text = None
    disposition: Disposition | None = None
    disposition_notes: Text = None
    concession_reference: Annotated[str | None, Field(max_length=100)] = Field(
        None, description="The client's concession reference, for a use-as-is disposition"
    )
    rework_cost: Cost | None = None
    delay_cost: Cost | None = None
    other_cost: Cost | None = None
    days_delay: Annotated[int | None, Field(ge=0, le=10000)] = None


class NcrStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: NcrStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class NcrActionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=5000)]
    kind: ActionKind = ActionKind.CORRECTIVE
    responsible_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    verification_criteria: Annotated[str | None, Field(max_length=5000)] = None


class NcrActionUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("description", "kind", "status")

    description: Annotated[str | None, Field(min_length=1, max_length=5000)] = None
    kind: ActionKind | None = None
    responsible_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    verification_criteria: Annotated[str | None, Field(max_length=5000)] = None
    status: ActionStatus | None = Field(None, description="`verified` records you as the verifier")
    verification_notes: Annotated[str | None, Field(max_length=5000)] = None


class NcrActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ncr_id: int
    description: str
    kind: str
    responsible_id: int | None
    responsible_name: str | None = None
    due_date: date | None
    overdue: bool = False
    verification_criteria: str | None
    status: str
    completed_at: datetime | None
    verified_by_id: int | None
    verified_by_name: str | None = None
    verified_at: datetime | None
    verification_notes: str | None


class NcrRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    raised_by_id: int | None
    raised_by_name: str | None = None
    raised_on: date | None
    location: str | None
    trade: str | None
    responsible_user_id: int | None
    responsible_user_name: str | None = None
    responsible_contact_id: int | None
    responsible_contact_name: str | None = None
    responsible_company_id: int | None
    responsible_company_name: str | None = None
    source: str
    source_reference: str | None
    inspection_id: int | None
    inspection_item_id: int | None
    spec_reference: str | None
    severity: str
    status: str
    root_cause_category: str | None
    root_cause_description: str | None
    disposition: str | None
    disposition_notes: str | None
    concession_reference: str | None
    rework_cost: Decimal
    delay_cost: Decimal
    other_cost: Decimal
    total_cost: Decimal = Decimal(0)
    days_delay: int
    open_actions: int = 0
    actions: list[NcrActionRead] = []
    created_at: datetime | None = None
    closed_at: datetime | None = None

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import CardStatus, ChangeType, Source

Title = Annotated[str, Field(min_length=1, max_length=300)]
LongText = Annotated[str | None, Field(max_length=20_000)]
Qty = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999"), decimal_places=3)]
Rate = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999"), decimal_places=2)]


class CardLine(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=500)]
    quantity: Qty = Decimal(0)
    unit: Annotated[str | None, Field(max_length=20)] = None
    rate: Rate = Decimal(0)
    hours: Qty = Decimal(0)


class CardLineRead(BaseModel):
    description: str
    quantity: Decimal
    unit: str | None
    rate: Decimal
    hours: Decimal
    amount: Decimal


class CardCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Title
    description: LongText = None
    source: Source = Source.SITE_INSTRUCTION
    change_type: ChangeType = ChangeType.SCOPE_INCREASE
    node_id: int | None = Field(None, ge=1, description="Usually the work anchor (RSW); any breakdown node")
    item_id: int | None = Field(None, ge=1)
    client_reference: Annotated[str | None, Field(max_length=120)] = None
    instructed_by: Annotated[str | None, Field(max_length=200)] = None
    instruction_date: date | None = None
    lines: Annotated[list[CardLine], Field(max_length=200)] = Field(default_factory=list)


class CardUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: LongText = None
    source: Source | None = None
    change_type: ChangeType | None = None
    node_id: int | None = Field(None, ge=1)
    item_id: int | None = Field(None, ge=1)
    client_reference: Annotated[str | None, Field(max_length=120)] = None
    instructed_by: Annotated[str | None, Field(max_length=200)] = None
    instruction_date: date | None = None
    lines: Annotated[list[CardLine] | None, Field(max_length=200)] = None


class CardStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: CardStatus
    note: Annotated[str | None, Field(max_length=5000)] = None
    approved_amount: Rate | None = Field(None, description="On approval: the agreed amount; defaults to the estimate")


class CardRead(BaseModel):
    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    source: str
    change_type: str
    node_id: int | None
    node_path: str | None
    work_anchor_id: int | None
    work_anchor_path: str | None
    item_id: int | None
    item_tag: str | None
    client_reference: str | None
    instructed_by: str | None
    instruction_date: date | None
    lines: list[CardLineRead]
    estimated_hours: Decimal
    estimated_amount: Decimal
    approved_amount: Decimal | None
    status: str
    submitted_at: datetime | None
    expires_at: datetime | None
    expires_in_days: int | None
    acknowledged_at: datetime | None
    decided_at: datetime | None
    decided_by_id: int | None
    decision_note: str | None
    change_order_id: int | None
    change_order_code: str | None
    created_by_id: int | None
    created_by_name: str | None
    created_at: datetime


class StatusCount(BaseModel):
    count: int
    amount: Decimal


class CardSummary(BaseModel):
    by_status: dict[str, StatusCount]
    expiring_soon: int
    """Waiting for the client and expiring within the reminder window."""
    approved_amount: Decimal
    pending_amount: Decimal

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999999"), decimal_places=2)]
Qty = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999999"), decimal_places=4)]


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CERTIFIED = "certified"
    PAID = "paid"


class RateItemCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    code: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str, Field(min_length=1, max_length=300)]
    unit: Annotated[str | None, Field(max_length=20)] = None
    contract_qty: Qty = Decimal(0)
    rate: Money = Decimal(0)
    node_id: int | None = Field(None, ge=1)
    sort_order: int = Field(0, ge=0, le=1_000_000)


class RateItemUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str | None, Field(min_length=1, max_length=60)] = None
    description: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    unit: Annotated[str | None, Field(max_length=20)] = None
    contract_qty: Qty | None = None
    rate: Money | None = None
    node_id: int | None = Field(None, ge=1)
    sort_order: int | None = Field(None, ge=0, le=1_000_000)


class RateItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    description: str
    unit: str | None
    contract_qty: Decimal
    rate: Decimal
    node_id: int | None
    node_path: str | None = None
    contract_value: Decimal = Decimal(0)
    sort_order: int


class SeedResult(BaseModel):
    created: int


class ClaimCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    period_start: date
    period_end: date
    retention_pct: Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)] = Decimal(5)
    retention_cap: Money | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class ClaimUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    period_start: date | None = None
    period_end: date | None = None
    retention_pct: Annotated[Decimal | None, Field(ge=0, le=100, decimal_places=2)] = None
    retention_cap: Money | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class LineUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    to_date_qty: Qty


class ClaimStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: ClaimStatus
    certified_amount: Money | None = Field(None, description="Required to certify: what the client certified")
    paid_amount: Money | None = Field(None, description="Defaults to the certified amount")
    on: date | None = Field(None, description="Certification or payment date; defaults to today")
    client_reference: Annotated[str | None, Field(max_length=120)] = None
    note: Annotated[str | None, Field(max_length=5000)] = None


class LineRead(BaseModel):
    id: int
    kind: str
    code: str
    description: str
    unit: str | None
    contract_qty: Decimal
    rate: Decimal
    contract_value: Decimal
    verified_qty: Decimal
    previous_qty: Decimal
    to_date_qty: Decimal
    this_qty: Decimal
    previous_value: Decimal
    to_date_value: Decimal
    this_value: Decimal
    percent_complete: float
    overridden: bool
    rate_item_id: int | None
    node_id: int | None
    source_type: str | None
    source_id: int | None


class Totals(BaseModel):
    contract_sum: Decimal
    variations_sum: Decimal
    works_to_date: Decimal
    variations_to_date: Decimal
    gross_to_date: Decimal
    previous_gross: Decimal
    gross_this_period: Decimal
    retention_to_date: Decimal
    net_to_date: Decimal
    previous_payments: Decimal
    this_claim: Decimal


class ClaimRead(BaseModel):
    id: int
    project_id: int
    code: str
    period_start: date
    period_end: date
    status: str
    retention_pct: Decimal
    retention_cap: Decimal | None
    notes: str | None
    submitted_at: datetime | None
    certified_amount: Decimal | None
    certified_on: date | None
    client_reference: str | None
    paid_amount: Decimal | None
    paid_on: date | None
    currency: str
    totals: Totals
    created_at: datetime


class ClaimDetail(ClaimRead):
    lines: list[LineRead]

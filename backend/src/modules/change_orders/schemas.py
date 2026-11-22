from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import CoStatus, CvrApply, Reason

Rate = Annotated[Decimal, Field(max_digits=16, decimal_places=2, ge=Decimal("-999999999999"), le=Decimal("999999999999"))]
Qty = Annotated[Decimal, Field(max_digits=16, decimal_places=3, ge=Decimal("-999999999"), le=Decimal("999999999"))]
Title = Annotated[str, Field(min_length=1, max_length=300)]
LongText = Annotated[str | None, Field(max_length=20_000)]
Days = Annotated[int, Field(ge=-36_500, le=36_500)]


class ChangeOrderCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Title
    reason: Reason = Reason.CLIENT_REQUEST
    description: LongText = None
    requested_by_id: int | None = Field(None, ge=1, description="Defaults to you")
    request_date: date | None = Field(None, description="Defaults to today")
    time_impact_days: Days = 0
    cvr_apply: CvrApply = CvrApply.NONE


class ChangeOrderUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    reason: Reason | None = None
    description: LongText = None
    requested_by_id: int | None = Field(None, ge=1)
    request_date: date | None = None
    time_impact_days: Days | None = None
    cvr_apply: CvrApply | None = None


class CoLineCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=500)]
    sort_order: int = Field(0, ge=0, le=1_000_000)
    cost_head_id: int | None = Field(None, ge=1, description="A CVR cost head of the same project")
    cost_code: Annotated[str | None, Field(max_length=30)] = None
    unit: Annotated[str | None, Field(max_length=20)] = None
    original_quantity: Qty = Decimal(0)
    original_rate: Rate = Decimal(0)
    new_quantity: Qty = Decimal(0)
    new_rate: Rate = Decimal(0)


class CoLineUpdate(EncodableText):
    """Only the fields sent change: a grid edit sends the one cell."""

    model_config = ConfigDict(extra="forbid")

    description: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    sort_order: int | None = Field(None, ge=0, le=1_000_000)
    cost_head_id: int | None = Field(None, ge=1)
    cost_code: Annotated[str | None, Field(max_length=30)] = None
    unit: Annotated[str | None, Field(max_length=20)] = None
    original_quantity: Qty | None = None
    original_rate: Rate | None = None
    new_quantity: Qty | None = None
    new_rate: Rate | None = None


class CoLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    change_order_id: int
    description: str
    sort_order: int
    cost_head_id: int | None
    cost_code: str | None
    unit: str | None
    original_quantity: Decimal
    original_rate: Decimal
    new_quantity: Decimal
    new_rate: Decimal
    original_amount: Decimal
    new_amount: Decimal
    delta: Decimal


class CoStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: CoStatus
    comment: Annotated[str | None, Field(max_length=5000)] = None


class ChangeOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    reason: str
    description: str | None
    requested_by_id: int | None
    requested_by_name: str | None = None
    request_date: date | None
    time_impact_days: int
    status: str
    cvr_apply: str
    approver_id: int | None
    approver_name: str | None = None
    decided_on: date | None
    decision_comment: str | None
    submitted_at: datetime | None
    applied_to_cvr_at: datetime | None
    currency: str = ""
    original_total: Decimal = Decimal(0)
    new_total: Decimal = Decimal(0)
    total_delta: Decimal = Decimal(0)
    line_count: int = 0
    created_at: datetime | None = None


class ChangeOrderDetail(ChangeOrderRead):
    lines: list[CoLineRead] = []


class CoStatusTotal(BaseModel):
    count: int
    delta: Decimal
    time_impact_days: int


class ChangeLogSummary(BaseModel):
    project_id: int
    currency: str
    approved: CoStatusTotal
    pending: CoStatusTotal
    rejected: CoStatusTotal
    draft: CoStatusTotal
    withdrawn: CoStatusTotal
    by_reason: dict[str, CoStatusTotal]
    """Approved change orders by reason."""


class CoHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

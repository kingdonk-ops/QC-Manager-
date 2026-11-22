from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import EncodableText
from .constants import PoStatus

Price = Annotated[Decimal, Field(max_digits=16, decimal_places=2, ge=Decimal(0), le=Decimal("999999999999"))]
Qty = Annotated[Decimal, Field(max_digits=16, decimal_places=3, ge=Decimal(0), le=Decimal("999999999"))]
TaxRate = Annotated[Decimal, Field(max_digits=5, decimal_places=2, ge=Decimal(0), le=Decimal(100))]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
LongText = Annotated[str | None, Field(max_length=20_000)]


class PurchaseOrderCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str | None, Field(max_length=300)] = None
    supplier_company_id: int | None = Field(None, ge=1)
    supplier_contact_id: int | None = Field(None, ge=1, description="Its company becomes the supplier when none is given")
    order_date: date | None = Field(None, description="Defaults to today")
    required_by: date | None = None
    delivery_address: LongText = None
    currency: Currency | None = Field(None, description="Defaults to the project's currency")
    terms: LongText = None
    notes: LongText = None
    approval_threshold: Price | None = None


class PurchaseOrderUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, Field(max_length=300)] = None
    supplier_company_id: int | None = Field(None, ge=1)
    supplier_contact_id: int | None = Field(None, ge=1)
    order_date: date | None = None
    required_by: date | None = None
    delivery_address: LongText = None
    currency: Currency | None = None
    terms: LongText = None
    notes: LongText = None
    approval_threshold: Price | None = None


class PoLineCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=500)]
    sort_order: int = Field(0, ge=0, le=1_000_000)
    unit: Annotated[str | None, Field(max_length=20)] = None
    quantity: Qty = Decimal(0)
    unit_price: Price = Decimal(0)
    tax_rate: TaxRate = Decimal(0)
    cost_code: Annotated[str | None, Field(max_length=30)] = None
    cost_head_id: int | None = Field(None, ge=1)


class PoLineUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    sort_order: int | None = Field(None, ge=0, le=1_000_000)
    unit: Annotated[str | None, Field(max_length=20)] = None
    quantity: Qty | None = None
    unit_price: Price | None = None
    tax_rate: TaxRate | None = None
    cost_code: Annotated[str | None, Field(max_length=30)] = None
    cost_head_id: int | None = Field(None, ge=1)


class PoLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_id: int
    description: str
    sort_order: int
    unit: str | None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    amount: Decimal
    tax: Decimal
    cost_code: str | None
    cost_head_id: int | None
    received_quantity: Decimal
    outstanding_quantity: Decimal = Decimal(0)


class SendRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    to: Annotated[list[EmailStr], Field(max_length=10)] = Field(
        default_factory=list, description="Leave empty for the supplier contact's (or company's) email"
    )
    message: Annotated[str | None, Field(max_length=5000)] = None


class PoStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: PoStatus = Field(description="Only `closed` or `cancelled`: sending and receipts set the others")
    note: Annotated[str | None, Field(max_length=2000)] = None


class ReceiptLineIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    line_id: int = Field(ge=1)
    quantity: Annotated[Decimal, Field(max_digits=16, decimal_places=3, gt=Decimal(0), le=Decimal("999999999"))]


class ReceiptCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    received_date: date | None = Field(None, description="Defaults to today")
    received_by_id: int | None = Field(None, ge=1, description="Defaults to you")
    quality_notes: LongText = None
    lines: Annotated[list[ReceiptLineIn], Field(min_length=1, max_length=500)]


class ReceiptLineRead(BaseModel):
    line_id: int
    description: str
    unit: str | None
    quantity: Decimal


class ReceiptPhoto(BaseModel):
    id: int
    name: str
    content_type: str


class ReceiptRead(BaseModel):
    id: int
    purchase_order_id: int
    code: str
    received_date: date
    received_by_id: int | None
    received_by_name: str | None
    quality_notes: str | None
    lines: list[ReceiptLineRead]
    photos: list[ReceiptPhoto]
    created_at: datetime | None = None


class PoSupplier(BaseModel):
    company_id: int | None = None
    company_name: str | None = None
    address: str | None = None
    email: str | None = None
    phone: str | None = None
    tax_id: str | None = None
    banking: dict[str, Any] = {}
    contact_id: int | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str | None
    supplier_company_id: int | None
    supplier_contact_id: int | None
    supplier_name: str | None = None
    order_date: date | None
    required_by: date | None
    delivery_address: str | None
    currency: str
    terms: str | None
    notes: str | None
    status: str
    approval_threshold: Decimal | None
    approved_by_id: int | None
    sent_at: datetime | None
    sent_to: str | None
    net_total: Decimal = Decimal(0)
    tax_total: Decimal = Decimal(0)
    gross_total: Decimal = Decimal(0)
    received_net: Decimal = Decimal(0)
    outstanding_net: Decimal = Decimal(0)
    received_pct: float = 0.0
    needs_approval: bool = False
    overdue: bool = False
    line_count: int = 0
    created_at: datetime | None = None


class PurchaseOrderDetail(PurchaseOrderRead):
    supplier: PoSupplier = PoSupplier()
    lines: list[PoLineRead] = []
    receipts: list[ReceiptRead] = []


class ReceiptResult(BaseModel):
    receipt: ReceiptRead
    status: str
    warnings: list[str]
    """Over-receipts, line by line: recorded, but worth a look."""


class OutstandingDelivery(BaseModel):
    purchase_order_id: int
    code: str
    title: str | None
    supplier_name: str | None
    status: str
    required_by: date | None
    overdue: bool
    days_overdue: int
    outstanding_net: Decimal
    lines_outstanding: int


class ProcurementSummary(BaseModel):
    project_id: int
    currency: str
    committed_net: Decimal
    committed_gross: Decimal
    received_net: Decimal
    outstanding_net: Decimal
    draft_net: Decimal
    by_status: dict[str, int]
    overdue_count: int
    outstanding: list[OutstandingDelivery]


class PoHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

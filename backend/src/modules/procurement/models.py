from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)
Quantity = Numeric(16, 3)


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "procurement_purchase_orders"
    __table_args__ = (Index("ix_procurement_purchase_orders_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    title: Mapped[str | None] = mapped_column(String(300), default=None)
    supplier_company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contact_companies.id", ondelete="SET NULL"), index=True, default=None
    )
    supplier_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None
    )
    order_date: Mapped[date | None] = mapped_column(Date, default=None)
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    delivery_address: Mapped[str | None] = mapped_column(Text, default=None)
    terms: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    approval_threshold: Mapped[Decimal | None] = mapped_column(Money, default=None)
    """Sending a PO whose gross total is above this needs ``procurement.approve``."""
    approved_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    sent_to: Mapped[str | None] = mapped_column(String(1000), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class PurchaseOrderLine(Base, TimestampMixin):
    __tablename__ = "procurement_po_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    purchase_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("procurement_purchase_orders.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(0))
    unit_price: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    """Percent, e.g. 10.00."""
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    tax: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    cost_code: Mapped[str | None] = mapped_column(String(30), default=None)
    cost_head_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A ``cvr`` cost head; a plain id so procurement works without ``cvr``."""
    received_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(0))


class GoodsReceipt(Base, TimestampMixin):
    __tablename__ = "procurement_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    purchase_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("procurement_purchase_orders.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(20))
    received_date: Mapped[date] = mapped_column(Date)
    received_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    quality_notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class GoodsReceiptLine(Base, TimestampMixin):
    __tablename__ = "procurement_receipt_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    receipt_id: Mapped[int] = mapped_column(Integer, ForeignKey("procurement_receipts.id", ondelete="CASCADE"), index=True)
    line_id: Mapped[int] = mapped_column(Integer, ForeignKey("procurement_po_lines.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity)

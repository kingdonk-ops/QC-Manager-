from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)
Quantity = Numeric(16, 3)


class ChangeOrder(Base, TimestampMixin):
    __tablename__ = "change_orders"
    __table_args__ = (Index("ix_change_orders_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(30), default="client_request")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    requested_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    request_date: Mapped[date | None] = mapped_column(Date, default=None)
    time_impact_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    cvr_apply: Mapped[str] = mapped_column(String(10), default="none")
    """Which forecast of the linked CVR cost heads approval moves: none, value, cost or both."""
    approver_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    decided_on: Mapped[date | None] = mapped_column(Date, default=None)
    decision_comment: Mapped[str | None] = mapped_column(Text, default=None)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    applied_to_cvr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class ChangeOrderLine(Base, TimestampMixin):
    __tablename__ = "change_orders_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    change_order_id: Mapped[int] = mapped_column(Integer, ForeignKey("change_orders.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    cost_head_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A ``cvr`` cost head of the same project; a plain id, so this module works with ``cvr`` off."""
    cost_code: Mapped[str | None] = mapped_column(String(30), default=None)
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    original_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(0))
    original_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    new_quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(0))
    new_rate: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    original_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    new_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    delta: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class ChangeCard(Base, TimestampMixin):
    """A field-raised change of scope.

    ``lines`` is ``[{description, quantity, unit, rate, hours, amount}]``: the estimate; ``estimated_*`` are its
    totals. Money is a commercial mirror for the client conversation, never posted anywhere.
    """

    __tablename__ = "change_of_scope_cards"
    __table_args__ = (Index("ix_change_of_scope_cards_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(30), default="site_instruction")
    change_type: Mapped[str] = mapped_column(String(30), default="scope_increase")
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), index=True, default=None
    )
    work_anchor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), index=True, default=None
    )
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    client_reference: Mapped[str | None] = mapped_column(String(120), default=None)
    instructed_by: Mapped[str | None] = mapped_column(String(200), default=None)
    instruction_date: Mapped[date | None] = mapped_column(Date, default=None)
    lines: Mapped[list] = mapped_column(JSON, default_factory=list)
    estimated_hours: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal(0))
    estimated_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal(0))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)
    change_order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("change_orders.id", ondelete="SET NULL"), index=True, default=None
    )
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

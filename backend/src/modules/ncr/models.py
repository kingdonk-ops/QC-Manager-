from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Ncr(Base, TimestampMixin):
    __tablename__ = "ncr_reports"
    __table_args__ = (
        Index("ix_ncr_reports_project_status", "project_id", "status"),
        Index("ix_ncr_reports_inspection", "inspection_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    raised_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    raised_on: Mapped[date | None] = mapped_column(Date, default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    responsible_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    responsible_contact_id: Mapped[int | None] = mapped_column(Integer, default=None)
    responsible_company_id: Mapped[int | None] = mapped_column(Integer, default=None)
    source: Mapped[str] = mapped_column(String(20), default="other")
    source_reference: Mapped[str | None] = mapped_column(String(200), default=None)
    inspection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    inspection_item_id: Mapped[int | None] = mapped_column(Integer, default=None)
    spec_reference: Mapped[str | None] = mapped_column(String(200), default=None)
    severity: Mapped[str] = mapped_column(String(10), default="minor")
    status: Mapped[str] = mapped_column(String(30), default="open")
    root_cause_category: Mapped[str | None] = mapped_column(String(20), default=None)
    root_cause_description: Mapped[str | None] = mapped_column(Text, default=None)
    disposition: Mapped[str | None] = mapped_column(String(30), default=None)
    disposition_notes: Mapped[str | None] = mapped_column(Text, default=None)
    concession_reference: Mapped[str | None] = mapped_column(String(100), default=None)
    rework_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    delay_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    days_delay: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class NcrAction(Base, TimestampMixin):
    """A corrective or preventive action (CAPA) on an NCR."""

    __tablename__ = "ncr_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    ncr_id: Mapped[int] = mapped_column(Integer, ForeignKey("ncr_reports.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="corrective")
    responsible_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    verification_criteria: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verification_notes: Mapped[str | None] = mapped_column(Text, default=None)

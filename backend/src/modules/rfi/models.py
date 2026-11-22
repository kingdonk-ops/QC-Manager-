from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Rfi(Base, TimestampMixin):
    __tablename__ = "rfis"
    __table_args__ = (
        Index("ix_rfis_project_status", "project_id", "status"),
        Index("ix_rfis_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(300))
    question: Mapped[str] = mapped_column(Text)
    discipline: Mapped[str | None] = mapped_column(String(60), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    raised_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    raised_by_party: Mapped[str] = mapped_column(String(20), default="contractor")
    addressed_to_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None
    )
    addressed_to_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    ball_in_court: Mapped[str | None] = mapped_column(String(20), default=None)
    """The party who must act next; ``bic_user_id`` / ``bic_contact_id`` name the person."""
    bic_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    bic_contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None)
    cost_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_impact_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), default=None)
    schedule_impact_days: Mapped[int | None] = mapped_column(Integer, default=None)
    entity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    entity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    opened_on: Mapped[date | None] = mapped_column(Date, default=None)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class RfiResponse(Base, TimestampMixin):
    """One message in an RFI's thread. ``is_answer`` marks a reply that answers the question."""

    __tablename__ = "rfi_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    rfi_id: Mapped[int] = mapped_column(Integer, ForeignKey("rfis.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=True)


class RfiSettings(Base, TimestampMixin):
    """A project's RFI settings."""

    __tablename__ = "rfi_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    default_due_days: Mapped[int] = mapped_column(Integer, default=7)

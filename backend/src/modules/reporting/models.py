from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class ReportTemplate(Base, TimestampMixin):
    """A report layout: an ordered list of sections (KPI cards, tables, charts, pivots, text) and its branding."""

    __tablename__ = "reporting_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sections: Mapped[list] = mapped_column(JSON, default_factory=list)
    branding: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """``company_name`` and ``logo_file_id``."""
    landscape: Mapped[bool] = mapped_column(Boolean, default=False)
    builtin_key: Mapped[str | None] = mapped_column(String(40), unique=True, default=None)
    """Set on the shipped templates, which are seeded once and can't be deleted."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class ReportSchedule(Base, TimestampMixin):
    """Generate a template for some projects on a cadence and email it."""

    __tablename__ = "reporting_schedules"
    __table_args__ = (Index("ix_reporting_schedules_due", "enabled", "next_run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("reporting_templates.id", ondelete="CASCADE"), index=True)
    project_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    cadence: Mapped[str] = mapped_column(String(10), default="weekly")
    """``daily``, ``weekly`` or ``monthly``."""
    weekday: Mapped[int | None] = mapped_column(Integer, default=0)
    """0 = Monday, for weekly schedules."""
    day_of_month: Mapped[int | None] = mapped_column(Integer, default=1)
    """1-31 for monthly schedules; a day past the month's end means its last day."""
    time_of_day: Mapped[str] = mapped_column(String(5), default="07:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Australia/Perth")
    format: Mapped[str] = mapped_column(String(5), default="pdf")
    recipient_user_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    recipient_emails: Mapped[list] = mapped_column(JSON, default_factory=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    """Reports run with this person's access, so a schedule never shows more than its owner could see."""


class ReportRun(Base, TimestampMixin):
    """One generated report: from a schedule (on time or "send now")."""

    __tablename__ = "reporting_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    schedule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("reporting_schedules.id", ondelete="CASCADE"), index=True, default=None
    )
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("reporting_templates.id", ondelete="SET NULL"), default=None
    )
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(10), default="success")
    """``success`` or ``failed``."""
    trigger: Mapped[str] = mapped_column(String(10), default="schedule")
    """``schedule`` or ``manual``."""
    format: Mapped[str] = mapped_column(String(5), default="pdf")
    recipients: Mapped[list] = mapped_column(JSON, default_factory=list)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    size: Mapped[int] = mapped_column(Integer, default=0)
    triggered_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)

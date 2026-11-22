from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class ChecklistTemplate(Base, TimestampMixin):
    """A reusable checklist. ``sections`` is ``[{title, items: [{text, response_type, unit, min_value, max_value,
    requires_photo_on_fail, guidance}]}]``; inspections copy it, so editing a template never changes past results."""

    __tablename__ = "inspections_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    activity: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[list] = mapped_column(JSON, default_factory=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class InspectionSettings(Base):
    """Per-project flags: whether the starter templates were seeded already (so deleting them sticks)."""

    __tablename__ = "inspections_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    starters_seeded: Mapped[bool] = mapped_column(Boolean, default=False)


class Inspection(Base, TimestampMixin):
    __tablename__ = "inspections"
    __table_args__ = (Index("ix_inspections_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_templates.id", ondelete="SET NULL"), default=None
    )
    template_name: Mapped[str | None] = mapped_column(String(200), default=None)
    template_version: Mapped[int | None] = mapped_column(Integer, default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    area: Mapped[str | None] = mapped_column(String(200), default=None)
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    inspector_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    scheduled_date: Mapped[date | None] = mapped_column(Date, default=None)
    inspected_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    not_applicable: Mapped[int] = mapped_column(Integer, default=0)
    unanswered: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float | None] = mapped_column(Float, default=None)
    """passed / (passed + failed) as a percentage, N/A excluded; None until something is scored."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class InspectionItem(Base):
    """One checklist line of an inspection: the template's wording, copied, and the answer."""

    __tablename__ = "inspections_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(String(500))
    response_type: Mapped[str] = mapped_column(String(20), default="pass_fail")
    unit: Mapped[str | None] = mapped_column(String(30), default=None)
    min_value: Mapped[float | None] = mapped_column(Float, default=None)
    max_value: Mapped[float | None] = mapped_column(Float, default=None)
    requires_photo_on_fail: Mapped[bool] = mapped_column(Boolean, default=False)
    guidance: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str | None] = mapped_column(String(10), default=None)
    """What the inspector chose: pass, fail or na."""
    reading: Mapped[float | None] = mapped_column(Float, default=None)
    outcome: Mapped[str | None] = mapped_column(String(10), default=None)
    """The scored result: a numeric reading outside its limits is a fail whatever was chosen."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    follow_up: Mapped[str | None] = mapped_column(String(10), default=None)
    task_id: Mapped[int | None] = mapped_column(Integer, default=None)
    ncr_id: Mapped[int | None] = mapped_column(Integer, default=None)

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Incident(Base, TimestampMixin):
    __tablename__ = "safety_incidents"
    __table_args__ = (Index("ix_safety_incidents_project_occurred", "project_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    severity: Mapped[int] = mapped_column(Integer, default=1)
    likelihood: Mapped[int] = mapped_column(Integer, default=1)
    risk_score: Mapped[int] = mapped_column(Integer, default=1)
    risk_band: Mapped[str] = mapped_column(String(10), default="low")
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    people_involved: Mapped[list] = mapped_column(JSON, default_factory=list)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    immediate_actions: Mapped[str | None] = mapped_column(Text, default=None)
    root_cause: Mapped[str | None] = mapped_column(Text, default=None)
    recordable: Mapped[bool] = mapped_column(Boolean, default=False)
    lost_time: Mapped[bool] = mapped_column(Boolean, default=False)
    days_lost: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="reported")
    reported_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Observation(Base, TimestampMixin):
    __tablename__ = "safety_observations"
    __table_args__ = (Index("ix_safety_observations_project_observed", "project_id", "observed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    observer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    severity: Mapped[int | None] = mapped_column(Integer, default=None)
    likelihood: Mapped[int | None] = mapped_column(Integer, default=None)
    risk_score: Mapped[int | None] = mapped_column(Integer, default=None)
    risk_band: Mapped[str | None] = mapped_column(String(10), default=None)
    status: Mapped[str] = mapped_column(String(10), default="open")


class SafetyAction(Base, TimestampMixin):
    """A corrective action on an incident or an observation."""

    __tablename__ = "safety_actions"
    __table_args__ = (Index("ix_safety_actions_parent", "parent_type", "parent_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_type: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verified_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verification_notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class HoursWorked(Base, TimestampMixin):
    """Hours worked on a project in one month (``month`` is the first day), the denominator of every rate."""

    __tablename__ = "safety_hours"
    __table_args__ = (UniqueConstraint("project_id", "month", name="uq_safety_hours_project_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    headcount: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

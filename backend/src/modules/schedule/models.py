from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class ScheduleSettings(Base, TimestampMixin):
    """A project's working calendar, data date and current baseline."""

    __tablename__ = "schedule_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    working_days: Mapped[list] = mapped_column(JSON, default_factory=lambda: [0, 1, 2, 3, 4])
    """Python weekday numbers worked: Monday 0 .. Sunday 6."""
    holidays: Mapped[list] = mapped_column(JSON, default_factory=list)
    """ISO dates that aren't worked."""
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    data_date: Mapped[date | None] = mapped_column(Date, default=None)
    current_baseline_id: Mapped[int | None] = mapped_column(Integer, default=None)
    finish_date: Mapped[date | None] = mapped_column(Date, default=None)
    """The calculated finish, kept from the last calculation."""
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    p6_critical_definition: Mapped[str] = mapped_column(String(20), default="total_float_le")
    """How a mirrored P6 activity counts as critical: ``total_float_le`` (float at or below the threshold) or
    ``longest_path`` (the schedule's own longest-path flag)."""
    p6_critical_float_hours: Mapped[float] = mapped_column(Float, default=0.0)
    p6_rules_seeded: Mapped[bool] = mapped_column(Boolean, default=False)


class Activity(Base, TimestampMixin):
    """One line of the programme: a task, a milestone, or a summary of the activities under it.

    ``planned_*`` is the programme's own dates (the early dates while the activity hasn't started; frozen
    once it has), ``early_*``/``late_*`` and the floats are written by every calculation.
    """

    __tablename__ = "schedule_activities"
    __table_args__ = (
        Index("ix_schedule_activities_project_wbs", "project_id", "wbs_code"),
        Index("uq_schedule_activities_p6", "project_id", "p6_activity_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    wbs_code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(300))
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("schedule_activities.id", ondelete="CASCADE"), index=True, default=None
    )
    type: Mapped[str] = mapped_column(String(20), default="task")
    duration: Mapped[int] = mapped_column(Integer, default=1)
    planned_start: Mapped[date | None] = mapped_column(Date, default=None)
    planned_finish: Mapped[date | None] = mapped_column(Date, default=None)
    actual_start: Mapped[date | None] = mapped_column(Date, default=None)
    actual_finish: Mapped[date | None] = mapped_column(Date, default=None)
    percent_complete: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    constraint_type: Mapped[str] = mapped_column(String(10), default="asap")
    constraint_date: Mapped[date | None] = mapped_column(Date, default=None)
    resource: Mapped[str | None] = mapped_column(String(200), default=None)
    responsible_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    budget_hours: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal(0))
    budget_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal(0))
    optimistic_duration: Mapped[float | None] = mapped_column(Float, default=None)
    most_likely_duration: Mapped[float | None] = mapped_column(Float, default=None)
    pessimistic_duration: Mapped[float | None] = mapped_column(Float, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    external_id: Mapped[str | None] = mapped_column(String(60), default=None)
    early_start: Mapped[date | None] = mapped_column(Date, default=None)
    early_finish: Mapped[date | None] = mapped_column(Date, default=None)
    late_start: Mapped[date | None] = mapped_column(Date, default=None)
    late_finish: Mapped[date | None] = mapped_column(Date, default=None)
    total_float: Mapped[int | None] = mapped_column(Integer, default=None)
    free_float: Mapped[int | None] = mapped_column(Integer, default=None)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    driving_predecessor_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    p6_activity_id: Mapped[str | None] = mapped_column(String(60), default=None)
    """The P6 Activity ID (``task_code``) this activity mirrors; its identity across re-imports."""
    p6_guid: Mapped[str | None] = mapped_column(String(60), default=None)
    schedule_state: Mapped[str] = mapped_column(String(30), default="active")
    """``active`` or ``removed_from_schedule`` (missing from the latest P6 import; never deleted)."""
    p6_facts: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """P6-owned facts of the last committed import: ``src`` (the source row), float, longest path, codes,
    UDFs, eligibility and the name-grammar match."""


class Dependency(Base, TimestampMixin):
    __tablename__ = "schedule_dependencies"
    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id", name="uq_schedule_dependencies_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    predecessor_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_activities.id", ondelete="CASCADE"), index=True)
    successor_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_activities.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(2), default="FS")
    lag: Mapped[int] = mapped_column(Integer, default=0)
    """Working days; negative is a lead."""


class Baseline(Base):
    """A named snapshot of every activity's planned dates: ``{activity_id: [start, finish, duration]}``."""

    __tablename__ = "schedule_baselines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    snapshot: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    finish_date: Mapped[date | None] = mapped_column(Date, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)


from .p6_models import P6Change, P6Export, P6Import, P6Link, P6LinkMemory, P6Rule, ProgressVerification  # noqa: E402

__all__ = [
    "Activity",
    "Baseline",
    "Dependency",
    "P6Change",
    "P6Export",
    "P6Import",
    "P6Link",
    "P6LinkMemory",
    "P6Rule",
    "ProgressVerification",
    "ScheduleSettings",
]

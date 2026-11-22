from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

QTY = Numeric(18, 4)
HOURS = Numeric(8, 2)
MEASURE = Numeric(7, 1)


class DailyLog(Base, TimestampMixin):
    """One crew's shift: the header of the day's log."""

    __tablename__ = "workface_logs"
    __table_args__ = (
        UniqueConstraint("crew_id", "work_date", "shift", name="uq_workface_logs_crew_day_shift"),
        Index("ix_workface_logs_project_date", "project_id", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    crew_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_crews.id", ondelete="RESTRICT"))
    work_date: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(10), default="day")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    supervisor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    area_node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    weather: Mapped[str | None] = mapped_column(String(120), default=None)
    """Manual for now (a local Australian provider is TD-594)."""
    temp_min_c: Mapped[Decimal | None] = mapped_column(MEASURE, default=None)
    temp_max_c: Mapped[Decimal | None] = mapped_column(MEASURE, default=None)
    wind_kmh: Mapped[Decimal | None] = mapped_column(MEASURE, default=None)
    rain_mm: Mapped[Decimal | None] = mapped_column(MEASURE, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    submitted_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    signed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    sign_note: Mapped[str | None] = mapped_column(Text, default=None)
    progress_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    """Quantities added to the nodes' ``earned_qty`` (once, at sign-off)."""


class LogHours(Base):
    """A person's hours: on a work anchor, or against a delay or overhead code."""

    __tablename__ = "workface_log_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    log_id: Mapped[int] = mapped_column(Integer, ForeignKey("workface_logs.id", ondelete="CASCADE"), index=True)
    person: Mapped[str] = mapped_column(String(120))
    hours: Mapped[Decimal] = mapped_column(HOURS)
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    trade: Mapped[str | None] = mapped_column(String(60), default=None)
    anchor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True, default=None
    )
    delay_code: Mapped[str | None] = mapped_column(String(20), default=None)
    overhead_code: Mapped[str | None] = mapped_column(String(20), default=None)
    note: Mapped[str | None] = mapped_column(String(300), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class LogQuantity(Base):
    """Quantity installed today, on a progress-unit node (or the work anchor itself)."""

    __tablename__ = "workface_log_quantities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    log_id: Mapped[int] = mapped_column(Integer, ForeignKey("workface_logs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"))
    anchor_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True)
    qty: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    note: Mapped[str | None] = mapped_column(String(300), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class LogDelay(Base):
    """A delay event: what stopped the crew, for how long, and where."""

    __tablename__ = "workface_log_delays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    log_id: Mapped[int] = mapped_column(Integer, ForeignKey("workface_logs.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    hours: Mapped[Decimal] = mapped_column(HOURS)
    anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class LogEquipment(Base):
    __tablename__ = "workface_log_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    log_id: Mapped[int] = mapped_column(Integer, ForeignKey("workface_logs.id", ondelete="CASCADE"), index=True)
    equipment: Mapped[str] = mapped_column(String(120))
    hours: Mapped[Decimal] = mapped_column(HOURS)
    status: Mapped[str] = mapped_column(String(20), default="operating")
    anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    note: Mapped[str | None] = mapped_column(String(300), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)

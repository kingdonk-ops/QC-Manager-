from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

QTY = Numeric(18, 4)
HOURS = Numeric(10, 2)


class Crew(Base, TimestampMixin):
    """A named crew with its supervisor. Members are names (field workers may have no login), optionally a user."""

    __tablename__ = "planner_crews"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_planner_crews_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str | None] = mapped_column(String(60), default=None)
    supervisor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    members: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"name": ..., "trade": ..., "user_id": ...}]``."""
    shift_hours: Mapped[Decimal] = mapped_column(HOURS, default=Decimal("10"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkPlan(Base, TimestampMixin):
    """A look-ahead, shutdown or campaign window. Its work anchors are an ``asset_collections`` row of kind ``work_plan``."""

    __tablename__ = "planner_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), default="look_ahead")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    collection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_collections.id", ondelete="SET NULL"), default=None
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    client_ref: Mapped[str | None] = mapped_column(String(60), default=None)
    schedule_activity_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``schedule`` activities the plan covers (no foreign key: ``schedule`` is optional)."""
    milestones: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"name": "Isolation start", "date": "2026-11-24"}]``."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class WorkPack(Base, TimestampMixin):
    """A job card: a crew's piece of a plan, listing work anchors with planned quantities and hours."""

    __tablename__ = "planner_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_plans.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    crew_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("planner_crews.id", ondelete="SET NULL"), default=None)
    supervisor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    planned_start: Mapped[date | None] = mapped_column(Date, default=None)
    planned_end: Mapped[date | None] = mapped_column(Date, default=None)
    schedule_activity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    access: Mapped[str | None] = mapped_column(String(20), default=None)
    """none / scaffold / ewp / rope."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class WorkPackLine(Base, TimestampMixin):
    __tablename__ = "planner_pack_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    pack_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_packs.id", ondelete="CASCADE"), index=True)
    anchor_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True)
    """Always a work-anchor node: picked nodes resolve through ``asset_tree.service.work_anchor_for``."""
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    activity_code: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(String(300), default=None)
    planned_qty: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    planned_hours: Mapped[Decimal | None] = mapped_column(HOURS, default=None)


class Prerequisite(Base, TimestampMixin):
    """Something that must be in place before a pack can start: materials, a permit, a scaffold..."""

    __tablename__ = "planner_prerequisites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    pack_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_packs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    cleared_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class PlanConstraint(Base, TimestampMixin):
    """The constraint log: what stands between a plan and the workface, who removes it and by when."""

    __tablename__ = "planner_constraints"
    __table_args__ = (Index("ix_planner_constraints_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("planner_plans.id", ondelete="CASCADE"), default=None)
    pack_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("planner_packs.id", ondelete="CASCADE"), default=None)
    anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    raised_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolution: Mapped[str | None] = mapped_column(Text, default=None)


class DailyAssignment(Base, TimestampMixin):
    """One crew on one work anchor on one day: a cell of the board, and a line of that crew's daily plan."""

    __tablename__ = "planner_assignments"
    __table_args__ = (
        UniqueConstraint("crew_id", "work_date", "anchor_id", name="uq_planner_assignments_cell"),
        Index("ix_planner_assignments_project_date", "project_id", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_plans.id", ondelete="CASCADE"), index=True)
    crew_id: Mapped[int] = mapped_column(Integer, ForeignKey("planner_crews.id", ondelete="CASCADE"))
    anchor_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"))
    work_date: Mapped[date] = mapped_column(Date)
    pack_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("planner_packs.id", ondelete="CASCADE"), default=None)
    planned_hours: Mapped[Decimal | None] = mapped_column(HOURS, default=None)
    note: Mapped[str | None] = mapped_column(String(300), default=None)

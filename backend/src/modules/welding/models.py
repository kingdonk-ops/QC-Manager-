from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

DIM = Numeric(10, 3)


class WeldingSettings(Base):
    """A project's NDE percentages per weld category, continuity window and repair limits."""

    __tablename__ = "welding_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    nde_rates: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    continuity_days: Mapped[int] = mapped_column(Integer, default=183)
    max_repairs: Mapped[int] = mapped_column(Integer, default=2)
    progressive_count: Mapped[int] = mapped_column(Integer, default=2)


class Pqr(Base, TimestampMixin):
    __tablename__ = "welding_pqrs"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_welding_pqrs_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    process: Mapped[str] = mapped_column(String(40))
    standard_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    base_material_group: Mapped[str | None] = mapped_column(String(60), default=None)
    thickness_qualified: Mapped[str | None] = mapped_column(String(60), default=None)
    tested_on: Mapped[date | None] = mapped_column(Date, default=None)
    laboratory: Mapped[str | None] = mapped_column(String(200), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class Wps(Base, TimestampMixin):
    __tablename__ = "welding_wps"
    __table_args__ = (UniqueConstraint("project_id", "code", "revision", name="uq_welding_wps_code_rev"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    process: Mapped[str] = mapped_column(String(40))
    """SMAW, GTAW, GMAW, FCAW, SAW, or a combination such as GTAW/SMAW."""
    revision: Mapped[str] = mapped_column(String(10), default="0")
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    standard_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    base_material_group: Mapped[str | None] = mapped_column(String(60), default=None)
    filler_material: Mapped[str | None] = mapped_column(String(120), default=None)
    positions: Mapped[list] = mapped_column(JSON, default_factory=list)
    joint_types: Mapped[list] = mapped_column(JSON, default_factory=list)
    thickness_min: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    thickness_max: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    diameter_min: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    diameter_max: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    pwht: Mapped[bool] = mapped_column(Boolean, default=False)
    pqr_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("welding_pqrs.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    approved_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class Welder(Base, TimestampMixin):
    __tablename__ = "welding_welders"
    __table_args__ = (UniqueConstraint("project_id", "stamp", name="uq_welding_welders_stamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    stamp: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    contact_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A ``contacts`` contact (plain id)."""
    employer: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(12), default="active")
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class Qualification(Base, TimestampMixin):
    """A welder performance qualification (WPQ): for one WPS, or for a process across WPSs."""

    __tablename__ = "welding_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    welder_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welders.id", ondelete="CASCADE"), index=True)
    process: Mapped[str] = mapped_column(String(40))
    qualified_on: Mapped[date] = mapped_column(Date)
    wps_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("welding_wps.id", ondelete="SET NULL"), default=None)
    standard_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    positions: Mapped[list] = mapped_column(JSON, default_factory=list)
    material_groups: Mapped[list] = mapped_column(JSON, default_factory=list)
    thickness_min: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    thickness_max: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    diameter_min: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    expires_on: Mapped[date | None] = mapped_column(Date, default=None)
    continuity_last_on: Mapped[date | None] = mapped_column(Date, default=None)
    certificate_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(12), default="valid")
    verified_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class ContinuityEntry(Base, TimestampMixin):
    """Evidence that a welder used a process on a day (keeps the qualification alive)."""

    __tablename__ = "welding_continuity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    welder_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welders.id", ondelete="CASCADE"), index=True)
    process: Mapped[str] = mapped_column(String(40))
    welded_on: Mapped[date] = mapped_column(Date)
    qualification_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("welding_qualifications.id", ondelete="SET NULL"), default=None
    )
    weld_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("welding_welds.id", ondelete="SET NULL"), default=None)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class Weld(Base, TimestampMixin):
    """Weld data for an ``asset_items`` row of type ``weld``."""

    __tablename__ = "welding_welds"
    __table_args__ = (
        UniqueConstraint("item_id", name="uq_welding_welds_item"),
        Index("ix_welding_welds_project_drawing", "project_id", "drawing_ref"),
        Index("ix_welding_welds_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="CASCADE"))
    weld_number: Mapped[str] = mapped_column(String(60))
    """The joint id on the isometric."""
    drawing_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    line_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    joint_type: Mapped[str] = mapped_column(String(12), default="butt")
    weld_category: Mapped[str] = mapped_column(String(40), default="normal")
    position: Mapped[str | None] = mapped_column(String(10), default=None)
    diameter: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    """Nominal size, inches."""
    schedule: Mapped[str | None] = mapped_column(String(20), default=None)
    thickness: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    """Wall thickness, mm."""
    material_1: Mapped[str | None] = mapped_column(String(80), default=None)
    material_2: Mapped[str | None] = mapped_column(String(80), default=None)
    wps_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("welding_wps.id", ondelete="RESTRICT"), default=None)
    status: Mapped[str] = mapped_column(String(12), default="fit_up")
    fit_up_on: Mapped[date | None] = mapped_column(Date, default=None)
    welded_on: Mapped[date | None] = mapped_column(Date, default=None)
    visual_result: Mapped[str] = mapped_column(String(10), default="pending")
    visual_on: Mapped[date | None] = mapped_column(Date, default=None)
    pwht_required: Mapped[bool] = mapped_column(Boolean, default=False)
    pwht_on: Mapped[date | None] = mapped_column(Date, default=None)
    nde_required: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """``{method: percent}``; from the category's rates unless set by hand."""
    repair_count: Mapped[int] = mapped_column(Integer, default=0)
    replaces_weld_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("welding_welds.id", ondelete="SET NULL"), default=None
    )
    accepted_on: Mapped[date | None] = mapped_column(Date, default=None)
    accepted_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class WeldPass(Base):
    """Who welded which pass. ``repair_seq`` 0 is the original weld, 1 is R1, 2 is R2."""

    __tablename__ = "welding_weld_passes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    weld_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welds.id", ondelete="CASCADE"), index=True)
    welder_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welders.id", ondelete="RESTRICT"), index=True)
    pass_name: Mapped[str] = mapped_column(String(30), default="all")
    repair_seq: Mapped[int] = mapped_column(Integer, default=0)
    qualification_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("welding_qualifications.id", ondelete="SET NULL"), default=None
    )


class WeldRepair(Base, TimestampMixin):
    __tablename__ = "welding_repairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    weld_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welds.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    repaired_on: Mapped[date] = mapped_column(Date)
    defect: Mapped[str | None] = mapped_column(String(300), default=None)
    cause_result_id: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class NdeRequest(Base, TimestampMixin):
    __tablename__ = "welding_nde_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    requested_on: Mapped[date | None] = mapped_column(Date, default=None)
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    contractor: Mapped[str | None] = mapped_column(String(200), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class NdeResult(Base, TimestampMixin):
    """One examination of one weld by one method: pending until the result is in."""

    __tablename__ = "welding_nde_results"
    __table_args__ = (Index("ix_welding_nde_results_weld_method", "weld_id", "method"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    weld_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_welds.id", ondelete="CASCADE"))
    method: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(12), default="random")
    repair_seq: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[int] = mapped_column(Integer, default=0)
    """Progressive tier: 1 and 2 add welds per rejection, 3 is every remaining weld of the welder."""
    triggered_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("welding_nde_results.id", ondelete="SET NULL"), default=None
    )
    request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("welding_nde_requests.id", ondelete="SET NULL"), index=True, default=None
    )
    result: Mapped[str] = mapped_column(String(10), default="pending")
    examined_on: Mapped[date | None] = mapped_column(Date, default=None)
    report_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    technician: Mapped[str | None] = mapped_column(String(200), default=None)
    defect: Mapped[str | None] = mapped_column(String(300), default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class BoltedJoint(Base, TimestampMixin):
    """A flanged joint under flange management. Each breakout and make-up is recorded against it (TD-590)."""

    __tablename__ = "welding_bolted_joints"
    __table_args__ = (UniqueConstraint("project_id", "joint_ref", name="uq_welding_bolted_joints_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True)
    joint_ref: Mapped[str] = mapped_column(String(60))
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    drawing_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    line_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    size: Mapped[str | None] = mapped_column(String(20), default=None)
    rating: Mapped[str | None] = mapped_column(String(20), default=None)
    gasket: Mapped[str | None] = mapped_column(String(120), default=None)
    bolt_spec: Mapped[str | None] = mapped_column(String(120), default=None)
    bolt_count: Mapped[int | None] = mapped_column(Integer, default=None)
    method: Mapped[str] = mapped_column(String(10), default="torque")
    target_value: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    unit: Mapped[str] = mapped_column(String(10), default="Nm")
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("5"))
    status: Mapped[str] = mapped_column(String(12), default="new")
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class JointEvent(Base, TimestampMixin):
    __tablename__ = "welding_joint_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    joint_id: Mapped[int] = mapped_column(Integer, ForeignKey("welding_bolted_joints.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    performed_on: Mapped[date] = mapped_column(Date)
    performed_by: Mapped[str | None] = mapped_column(String(200), default=None)
    equipment_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``calibration`` equipment used (torque wrench, tensioning tool), checked by the calibration gate."""
    applied_value: Mapped[Decimal | None] = mapped_column(DIM, default=None)
    pass_values: Mapped[list] = mapped_column(JSON, default_factory=list)
    gasket_replaced: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(300), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

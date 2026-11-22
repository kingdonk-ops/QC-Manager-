from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .calc import DEFAULT_DEW_POINT_MARGIN_C, DftRule


class CoatingSystem(Base, TimestampMixin):
    """A coating specification: surface preparation, profile, and the coats with their DFT limits."""

    __tablename__ = "coatings_systems"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_coatings_systems_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    surface_prep_standard: Mapped[str | None] = mapped_column(String(120), default=None)
    """e.g. ``ISO 8501-1 Sa 2½``."""
    profile_min_um: Mapped[float | None] = mapped_column(Float, default=None)
    profile_max_um: Mapped[float | None] = mapped_column(Float, default=None)
    coats: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"name": "Primer", "product": "Zinc-rich epoxy", "dft_min_um": 60, "dft_max_um": 120}, ...]``"""
    dft_rule: Mapped[str] = mapped_column(String(10), default=DftRule.EIGHTY_TWENTY.value)
    dew_point_margin_c: Mapped[float] = mapped_column(Float, default=DEFAULT_DEW_POINT_MARGIN_C)
    max_rh_pct: Mapped[float | None] = mapped_column(Float, default=85.0)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class CoatingJob(Base, TimestampMixin):
    """Coating one work anchor (or item) to one system. Its stages are the hold points."""

    __tablename__ = "coatings_jobs"
    __table_args__ = (Index("ix_coatings_jobs_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    system_id: Mapped[int] = mapped_column(Integer, ForeignKey("coatings_systems.id", ondelete="RESTRICT"))
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    dft_rule: Mapped[str] = mapped_column(String(10), default=DftRule.EIGHTY_TWENTY.value)
    status: Mapped[str] = mapped_column(String(20), default="open")
    """``open``, ``in_progress``, ``passed`` (every hold point released) or ``failed``."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class CoatingStage(Base, TimestampMixin):
    """A hold point: surface preparation, then one per coat, released in order."""

    __tablename__ = "coatings_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("coatings_jobs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    """``surface_prep`` or ``coat``."""
    name: Mapped[str] = mapped_column(String(120))
    product: Mapped[str | None] = mapped_column(String(200), default=None)
    dft_min_um: Mapped[float | None] = mapped_column(Float, default=None)
    dft_max_um: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    batch_numbers: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"product": "...", "batch": "B1234", "expiry": "2027-03-01"}]``"""
    measured_profile_um: Mapped[float | None] = mapped_column(Float, default=None)
    cleanliness: Mapped[str | None] = mapped_column(String(40), default=None)
    released_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)


class EnvironmentalReading(Base, TimestampMixin):
    __tablename__ = "coatings_env_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("coatings_jobs.id", ondelete="CASCADE"), index=True)
    stage_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("coatings_stages.id", ondelete="SET NULL"))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    air_temp_c: Mapped[float | None] = mapped_column(Float)
    surface_temp_c: Mapped[float] = mapped_column(Float)
    rh_pct: Mapped[float | None] = mapped_column(Float)
    dew_point_c: Mapped[float] = mapped_column(Float)
    margin_c: Mapped[float] = mapped_column(Float)
    required_margin_c: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    failures: Mapped[list] = mapped_column(JSON, default_factory=list)
    equipment_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    taken_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)


class DftSet(Base, TimestampMixin):
    """One set of spot readings on one coat, with its statistics and verdict."""

    __tablename__ = "coatings_dft_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("coatings_jobs.id", ondelete="CASCADE"), index=True)
    stage_id: Mapped[int] = mapped_column(Integer, ForeignKey("coatings_stages.id", ondelete="CASCADE"), index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(200))
    readings: Mapped[list] = mapped_column(JSON)
    rule: Mapped[str] = mapped_column(String(10))
    dft_min_um: Mapped[float] = mapped_column(Float)
    dft_max_um: Mapped[float | None] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer)
    mean: Mapped[float] = mapped_column(Float)
    minimum: Mapped[float] = mapped_column(Float)
    maximum: Mapped[float] = mapped_column(Float)
    pct_within: Mapped[float] = mapped_column(Float)
    pct_below_min: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    failures: Mapped[list] = mapped_column(JSON, default_factory=list)
    equipment_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    taken_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

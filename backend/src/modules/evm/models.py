from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import Curve, EacMethod

Hours = Numeric(14, 2)
Money = Numeric(16, 2)
Percent = Numeric(7, 3)


class WorkPackage(Base, TimestampMixin):
    """A control account's unit of work: budget hours spread over its planned dates by a curve."""

    __tablename__ = "evm_work_packages"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_evm_work_packages_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(300))
    control_account: Mapped[str | None] = mapped_column(String(60), default=None)
    wbs: Mapped[str | None] = mapped_column(String(60), default=None)
    discipline: Mapped[str | None] = mapped_column(String(60), default=None)
    planned_start: Mapped[date | None] = mapped_column(Date, default=None)
    planned_finish: Mapped[date | None] = mapped_column(Date, default=None)
    budget_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal(0))
    budget_cost: Mapped[Decimal | None] = mapped_column(Money, default=None)
    curve: Mapped[str] = mapped_column(String(20), default=Curve.LINEAR.value)
    schedule_activity_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    """A ``schedule`` activity this package follows, for a later sync of dates and hours."""
    cvr_cost_head_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The ``cvr`` cost head the package's cost rolls into (no foreign key: ``cvr`` is optional)."""
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ProgressRecord(Base, TimestampMixin):
    """Cumulative progress of one package as at one data date."""

    __tablename__ = "evm_progress"
    __table_args__ = (UniqueConstraint("work_package_id", "data_date", name="uq_evm_progress_package_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    work_package_id: Mapped[int] = mapped_column(Integer, ForeignKey("evm_work_packages.id", ondelete="CASCADE"), index=True)
    data_date: Mapped[date] = mapped_column(Date)
    percent_complete: Mapped[Decimal] = mapped_column(Percent, default=Decimal(0))
    actual_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal(0))
    actual_cost: Mapped[Decimal | None] = mapped_column(Money, default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class EvmSettings(Base, TimestampMixin):
    """A project's current data date and preferred EAC method."""

    __tablename__ = "evm_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    data_date: Mapped[date | None] = mapped_column(Date, default=None)
    eac_method: Mapped[str] = mapped_column(String(20), default=EacMethod.CPI.value)


class BudgetSnapshot(Base, TimestampMixin):
    """A frozen copy of every package's budget and planned curve. One may be the active baseline."""

    __tablename__ = "evm_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    packages: Mapped[list] = mapped_column(JSON, default_factory=list)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

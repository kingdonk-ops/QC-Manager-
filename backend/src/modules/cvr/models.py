from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)


class CostHead(Base, TimestampMixin):
    """One line of the reconciliation: what it was budgeted at, what it has cost, what it has earned."""

    __tablename__ = "cvr_cost_heads"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_cvr_cost_heads_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    budget: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    cost_to_date: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    value_to_date: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    forecast_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    forecast_value: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))


class CashflowPeriod(Base, TimestampMixin):
    """One month of planned and actual cost and value."""

    __tablename__ = "cvr_cashflow"
    __table_args__ = (UniqueConstraint("project_id", "period", name="uq_cvr_cashflow_project_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    period: Mapped[date] = mapped_column(Date)
    planned_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    actual_cost: Mapped[Decimal | None] = mapped_column(Money, default=None)
    planned_value: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    actual_value: Mapped[Decimal | None] = mapped_column(Money, default=None)

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)
Probability = Numeric(2, 1)


class Risk(Base, TimestampMixin):
    __tablename__ = "risk_risks"
    __table_args__ = (Index("ix_risk_risks_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(20), default="technical")
    cause: Mapped[str | None] = mapped_column(Text, default=None)
    effect: Mapped[str | None] = mapped_column(Text, default=None)
    probability: Mapped[Decimal] = mapped_column(Probability, default=Decimal("0.5"))
    impact: Mapped[str] = mapped_column(String(10), default="medium")
    cost_impact: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    schedule_impact_days: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None)
    mitigation: Mapped[str | None] = mapped_column(Text, default=None)
    contingency: Mapped[str | None] = mapped_column(Text, default=None)
    residual_probability: Mapped[Decimal | None] = mapped_column(Probability, default=None)
    residual_impact: Mapped[str | None] = mapped_column(String(10), default=None)
    response: Mapped[str | None] = mapped_column(String(10), default=None)
    status: Mapped[str] = mapped_column(String(20), default="identified")
    review_date: Mapped[date | None] = mapped_column(Date, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

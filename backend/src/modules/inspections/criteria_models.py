"""The per-project acceptance-criteria library. Limits are kept as short text so free-text criteria and plain
decimals can coexist; ``tolerance.py`` parses them as exact decimals."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class AcceptanceCriterion(Base, TimestampMixin):
    """One reusable acceptance criterion. Inspection records, checklist items, material records, PMI tests and
    as-built records point at it by id; once any of them is judged against it, its limits are frozen."""

    __tablename__ = "inspections_criteria"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_inspections_criteria_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    standards_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    discipline: Mapped[str | None] = mapped_column(String(100), default=None)
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    characteristic: Mapped[str | None] = mapped_column(String(200), default=None)
    method: Mapped[str | None] = mapped_column(String(200), default=None)
    unit: Mapped[str | None] = mapped_column(String(30), default=None)
    rule_type: Mapped[str] = mapped_column(String(12), default="free_text")
    nominal: Mapped[str | None] = mapped_column(String(40), default=None)
    lower_limit: Mapped[str | None] = mapped_column(String(40), default=None)
    upper_limit: Mapped[str | None] = mapped_column(String(40), default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    supplementary: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

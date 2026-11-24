from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class MdrOverride(Base, TimestampMixin):
    """A manager's decision to let a dossier issue past outstanding blockers. The blocker snapshot is exactly what the
    override covers; the covered gates stay pending and carry this record's reference."""

    __tablename__ = "mdr_overrides"
    __table_args__ = (Index("ix_mdr_overrides_dossier_reference", "dossier_id", "reference", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    dossier_id: Mapped[int] = mapped_column(Integer, ForeignKey("mdr_dossiers.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    reference: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    blockers: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{check, reference, message}]`` at the time of the override: the only findings it covers."""
    gate_numbers: Mapped[list] = mapped_column(JSON, default_factory=list)
    """Numbers of the pending gates that were annotated."""
    report_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The documentation report raised with the override; no foreign key, the issues module is optional."""
    report_code: Mapped[str | None] = mapped_column(String(100), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)

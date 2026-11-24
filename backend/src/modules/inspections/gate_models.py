"""Standalone quality gates: a control point attached to an asset node, an Item, an inspection record, a task or a
dossier that stays pending until a party of enough authority releases it, a manager waives it (not a hold) or it is
voided. Decided gates are permanent evidence."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class QualityGate(Base, TimestampMixin):
    __tablename__ = "inspections_gates"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_inspections_gates_number"),
        Index("ix_inspections_gates_attachment", "project_id", "attachment_kind", "attachment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    number: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(14), default="hold")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    authority: Mapped[str] = mapped_column(String(32), default="contractor_qa")
    """The level a release must assert or exceed."""
    inspection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections.id", ondelete="RESTRICT"), index=True, default=None
    )
    """A record of the single inspection register (checklist inspection or ITP line) that must have passed first."""
    criterion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_criteria.id", ondelete="RESTRICT"), index=True, default=None
    )
    attachment_kind: Mapped[str | None] = mapped_column(String(12), default=None)
    attachment_id: Mapped[int | None] = mapped_column(Integer, default=None)
    package_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    blocks_progress: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    released_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    released_level: Mapped[str | None] = mapped_column(String(32), default=None)
    """The level the releasing user asserted, not the level the gate required."""
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    release_justification: Mapped[str | None] = mapped_column(Text, default=None)
    release_ip: Mapped[str | None] = mapped_column(String(64), default=None)
    release_digest: Mapped[str | None] = mapped_column(String(64), default=None)
    waived_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    waiver_reason: Mapped[str | None] = mapped_column(Text, default=None)
    approval_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    supplementary: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    override_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A dossier issue override that covers this gate. The gate stays pending; no foreign key, the override table
    belongs to another module."""
    override_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    """The covering override's reference, shown beside the pending gate."""

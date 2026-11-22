from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import DEFAULT_INTERVAL_DAYS, ModificationStatus, ScaffoldStatus, Tag


class Scaffold(Base, TimestampMixin):
    """One scaffold, from its build request to its dismantling. The request is the record in status ``requested``."""

    __tablename__ = "scaffolds_scaffolds"
    __table_args__ = (
        Index("ix_scaffolds_scaffolds_project_status", "project_id", "status"),
        Index("ix_scaffolds_scaffolds_node", "node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"))
    """Where it stands, and the work anchor or area it serves."""
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    location_text: Mapped[str | None] = mapped_column(String(300), default=None)
    purpose: Mapped[str | None] = mapped_column(Text, default=None)
    scaffold_type: Mapped[str] = mapped_column(String(30), default="independent")
    duty_class: Mapped[str] = mapped_column(String(20), default="medium")
    max_load_kpa: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=None)
    dimensions: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """``{"length_m", "width_m", "height_m", "lifts", "bays"}``, any subset."""
    status: Mapped[str] = mapped_column(String(30), default=ScaffoldStatus.REQUESTED.value)
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    requested_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    custodian_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    approved_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    erected_on: Mapped[date | None] = mapped_column(Date, default=None)
    dismantle_requested_on: Mapped[date | None] = mapped_column(Date, default=None)
    dismantled_on: Mapped[date | None] = mapped_column(Date, default=None)
    inspection_interval_days: Mapped[int] = mapped_column(Integer, default=DEFAULT_INTERVAL_DAYS)
    tag_status: Mapped[str] = mapped_column(String(10), default=Tag.NONE.value)
    """The last inspection's tag. Read ``effective_tag`` for what applies now (overdue turns it red)."""
    tag_no: Mapped[str | None] = mapped_column(String(40), default=None)
    tag_restrictions: Mapped[str | None] = mapped_column(Text, default=None)
    last_inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_inspection_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    hire_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    """Per day, in the project's currency."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class ScaffoldLink(Base):
    """Further work a scaffold serves: another node (asset, RSW) besides the one it stands at."""

    __tablename__ = "scaffolds_links"

    scaffold_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scaffolds_scaffolds.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class ScaffoldInspection(Base, TimestampMixin):
    """One inspection, and the tag it hung on the scaffold."""

    __tablename__ = "scaffolds_inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    scaffold_id: Mapped[int] = mapped_column(Integer, ForeignKey("scaffolds_scaffolds.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inspector_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    tag: Mapped[str] = mapped_column(String(10))
    tag_no: Mapped[str | None] = mapped_column(String(40), default=None)
    restrictions: Mapped[str | None] = mapped_column(Text, default=None)
    checklist: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"item": "Base plates and sole boards", "ok": true, "note": null}, ...]``"""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ScaffoldModification(Base, TimestampMixin):
    __tablename__ = "scaffolds_modifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    scaffold_id: Mapped[int] = mapped_column(Integer, ForeignKey("scaffolds_scaffolds.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default=ModificationStatus.REQUESTED.value)
    requested_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    decided_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

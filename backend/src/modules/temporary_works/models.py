"""Temporary works register: items and their permits.

Nothing derived is stored: a permit's validity, an item's gates, breach, overdue state and the clearance percentage are
all worked out at read time for an as-of day from these rows."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import DEFAULT_RETENTION_DAYS, ItemStatus, PermitStatus


class TemporaryWorksItem(Base, TimestampMixin):
    """One item of temporary works: a scaffold, a prop, an excavation support and so on."""

    __tablename__ = "temporary_works_items"
    __table_args__ = (
        UniqueConstraint("project_id", "reference", name="uq_temporary_works_items_reference"),
        Index("ix_temporary_works_items_project_status", "project_id", "status"),
        Index("ix_temporary_works_items_scaffold", "scaffold_id"),
        Index("ix_temporary_works_items_deleted", "deleted_kind", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    reference: Mapped[str] = mapped_column(String(60))
    """Entered by the user; unique within the project."""
    title: Mapped[str] = mapped_column(String(300))
    family: Mapped[str] = mapped_column(String(24))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    design_check_category: Mapped[int | None] = mapped_column(Integer, default=None)
    """Zero to three; the rigour of the independent check rises with it. Empty until assigned."""
    designer: Mapped[str | None] = mapped_column(String(200), default=None)
    checker: Mapped[str | None] = mapped_column(String(200), default=None)
    coordinator_name: Mapped[str | None] = mapped_column(String(200), default=None)
    coordinator_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(24), default=ItemStatus.IDENTIFIED.value)
    held_from: Mapped[str | None] = mapped_column(String(24), default=None)
    """The status the item was in when it went on hold, so it can resume only there."""
    required_load_on: Mapped[date | None] = mapped_column(Date, default=None)
    required_strike_on: Mapped[date | None] = mapped_column(Date, default=None)
    design_due_on: Mapped[date | None] = mapped_column(Date, default=None)
    location: Mapped[str | None] = mapped_column(String(300), default=None)
    asset_node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    scaffold_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A scaffold of the same project, as a plain identifier (no foreign key) so the scaffolds module stays optional."""
    related_refs: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """Soft cross-references to related records elsewhere, keyed by what they are."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    breach_notified_on: Mapped[date | None] = mapped_column(Date, default=None)
    """The day a breach was last announced; set once per breach and cleared when the breach clears."""
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Soft delete: a deleted item is a tombstone, hidden from every list and count and never removed, so audit entries
    still resolve. Its reference stays reserved until the scheduled purge removes a recycle-bin record."""
    deleted_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    deleted_kind: Mapped[str | None] = mapped_column(String(8), default=None)
    """Where the tombstone sits: ``bin`` (the recycle bin; purged after the retention) or ``folder`` (the hidden Deleted
    folder; kept indefinitely). Empty on a live record; a deleted record with no kind reads as the folder."""


class TemporaryWorksPermit(Base, TimestampMixin):
    """A permit to load, strike or dismantle one item. Its project always equals its item's project."""

    __tablename__ = "temporary_works_permits"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_temporary_works_permits_number"),
        Index("ix_temporary_works_permits_project_status", "project_id", "status"),
        Index("ix_temporary_works_permits_deleted", "deleted_kind", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("temporary_works_items.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(40))
    """Entered by the user; unique within the project."""
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default=PermitStatus.DRAFT.value)
    issued_by_name: Mapped[str | None] = mapped_column(String(200), default=None)
    issued_on: Mapped[date | None] = mapped_column(Date, default=None)
    valid_from: Mapped[date | None] = mapped_column(Date, default=None)
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)
    closed_on: Mapped[date | None] = mapped_column(Date, default=None)
    closed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    inspection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A soft reference to an inspection record; no foreign key."""
    design_check_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    expiry_notified_on: Mapped[date | None] = mapped_column(Date, default=None)
    """The day the expiring-soon notice went out, so it is sent once."""
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Soft delete of a draft permit: hidden from every list. Its number stays reserved until the scheduled purge removes
    a recycle-bin record."""
    deleted_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    deleted_kind: Mapped[str | None] = mapped_column(String(8), default=None)
    """``bin`` or ``folder``, as on an item."""


class TemporaryWorksSettings(Base, TimestampMixin):
    """A project's own settings for the register. No row means the defaults."""

    __tablename__ = "temporary_works_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    bin_retention_days: Mapped[int] = mapped_column(Integer, default=DEFAULT_RETENTION_DAYS)
    """Days a deleted draft stays in the recycle bin before the scheduled purge may remove it (one to sixty)."""
    updated_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

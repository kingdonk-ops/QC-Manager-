"""P6 mirror tables: imports with their change-impact report, name-grammar rules, activity-to-asset links,
remembered manual links, verified progress and the actuals exports sent back to P6.

Activities themselves live in ``schedule_activities`` (``p6_activity_id`` is their identity), so the Gantt,
CPM and baselines work on a mirrored programme exactly as on a hand-built one.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class P6Import(Base, TimestampMixin):
    """One uploaded schedule file: ``previewed`` → ``committed`` or ``discarded``.

    ``staging`` holds the parsed activities, WBS and relationships until the planner commits; the original
    file is kept in ``files`` (``file_id``) with its SHA-256, never changed.
    """

    __tablename__ = "schedule_p6_imports"
    __table_args__ = (Index("ix_schedule_p6_imports_project_sha", "project_id", "sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(20))
    source_project: Mapped[str | None] = mapped_column(String(200), default=None)
    data_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="previewed")
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    summary: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    staging: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    options: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    committed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class P6Change(Base):
    """One detected change of an import. ``new`` is exactly what commit writes unless ``excluded``."""

    __tablename__ = "schedule_p6_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    import_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_p6_imports.id", ondelete="CASCADE"), index=True)
    p6_activity_id: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(300))
    change_type: Mapped[str] = mapped_column(String(30))
    activity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("schedule_activities.id", ondelete="SET NULL"), default=None
    )
    old: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    new: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    impact: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)


class P6Rule(Base, TimestampMixin):
    """A project's P6 mapping rule.

    * ``grammar``: a regular expression with named groups (level keys, or ``asset``, ``anchor_code``,
      ``activity_type``, ``suffix``, ``window``) tried in ``sort_order`` against ``source`` (name, code or wbs).
    * ``eligibility``: ``params = {field, op, values}``; a matching activity is mirrored but out of scope.
    * ``alias``: ``pattern`` is the spelling found in P6, ``params.to`` the spelling to use.
    """

    __tablename__ = "schedule_p6_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    pattern: Mapped[str] = mapped_column(String(1000), default="")
    source: Mapped[str] = mapped_column(String(20), default="name")
    params: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class P6Link(Base, TimestampMixin):
    """An activity ↔ breakdown node link (many-to-many). Re-imports never move a confirmed link: a different
    parse raises a ``proposed`` one for the planner."""

    __tablename__ = "schedule_p6_links"
    __table_args__ = (UniqueConstraint("activity_id", "node_id", name="uq_schedule_p6_links_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedule_activities.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"), index=True)
    progress_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    """The progress unit the activity measures (e.g. its activity-type node under the RSW); else ``node_id``."""
    work_window: Mapped[str | None] = mapped_column(String(40), default=None)
    method: Mapped[str] = mapped_column(String(20), default="name_grammar")
    """``name_grammar``, ``manual`` or ``remembered``."""
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    parsed: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class P6LinkMemory(Base, TimestampMixin):
    """A manual link remembered by the activity's normalised name, applied to later imports."""

    __tablename__ = "schedule_p6_link_memory"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_schedule_p6_link_memory_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(300))
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"))
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class ProgressVerification(Base, TimestampMixin):
    """Verified quantity to date on a progress-unit node.

    Counts only when it is backed by evidence: an inspection that is completed or closed with no failed
    item, or (without one) the attestation of a holder of ``schedule.review``. Self-reported
    ``asset_nodes.earned_qty`` is shown beside it as "reported" and never counts as earned (KERP TD-563).
    """

    __tablename__ = "schedule_progress_verifications"
    __table_args__ = (Index("ix_schedule_progress_verifications_node", "node_id", "verified_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="CASCADE"))
    verified_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    verified_on: Mapped[date] = mapped_column(Date)
    inspection_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="SET NULL"), default=None)
    verified_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)


class P6Export(Base):
    """One actuals export for the scheduler; ``rows`` is what was sent, so it can be downloaded again."""

    __tablename__ = "schedule_p6_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(20))
    data_date: Mapped[date] = mapped_column(Date)
    rows: Mapped[list] = mapped_column(JSON, default_factory=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)

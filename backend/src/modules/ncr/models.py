"""The issues engine: one issue record (punch or NCR, table ``ncr_reports`` kept from the NCR module),
CAPA actions, layered revisioned templates, categories, default template per category x type, flag
override ledger and informational links of project-level issues.

Library rows (templates, categories, defaults) have ``project_id`` NULL; a project's own rows override
them (copied, never overlaid: a project template keeps ``derived_from_id``).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class IssueCategory(Base, TimestampMixin):
    """A value of the category list. Keys are never re-keyed or deleted once used, only deactivated."""

    __tablename__ = "ncr_categories"
    __table_args__ = (Index("ix_ncr_categories_project_key", "project_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), default=None)
    key: Mapped[str] = mapped_column(String(40), default="general")
    label: Mapped[str] = mapped_column(String(100), default="General")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    allows_project_level: Mapped[bool] = mapped_column(Boolean, default=False)
    """Issues of this category may be raised without an anchor (audit, H&S, vehicle, pre-start ...)."""
    pack_key: Mapped[str | None] = mapped_column(String(40), default=None)


class IssueTemplate(Base, TimestampMixin):
    """An issue template: the type and category are fixed, everything else is in its revisions."""

    __tablename__ = "ncr_templates"
    __table_args__ = (Index("ix_ncr_templates_project_key", "project_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), default=None)
    key: Mapped[str] = mapped_column(String(80), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    issue_type: Mapped[str] = mapped_column(String(10), default="punch")
    category: Mapped[str] = mapped_column(String(40), default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    derived_from_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ncr_templates.id", ondelete="SET NULL"), default=None
    )
    pack_key: Mapped[str | None] = mapped_column(String(40), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class IssueTemplateRevision(Base, TimestampMixin):
    """A draft, or a frozen published revision. Issues pin the revision they were raised on."""

    __tablename__ = "ncr_template_revisions"
    __table_args__ = (Index("ix_ncr_template_revisions_template", "template_id", "number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("ncr_templates.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    name: Mapped[str] = mapped_column(String(200), default="")
    fields: Mapped[list] = mapped_column(JSON, default_factory=list)
    """Field definitions: ``{key, label, type, step, required, options, help, unit, min, max}``."""
    default_origin: Mapped[str] = mapped_column(String(20), default="qa")
    default_visibility: Mapped[str] = mapped_column(String(10), default="internal")
    default_mdr_effect: Mapped[str] = mapped_column(String(15), default="blocks")
    completion_effect: Mapped[str] = mapped_column(String(10), default="blocks")
    default_severity: Mapped[str | None] = mapped_column(String(10), default=None)
    default_punch_category: Mapped[str | None] = mapped_column(String(1), default=None)
    separate_close: Mapped[bool] = mapped_column(Boolean, default=False)
    """Punch only: keep ``verified`` as a state and close in a separate action (by someone other than the rectifier)."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    published_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class IssueDefaultTemplate(Base, TimestampMixin):
    """The template pre-selected when raising an issue of this category and type."""

    __tablename__ = "ncr_default_templates"
    __table_args__ = (Index("ix_ncr_default_templates_lookup", "project_id", "category", "issue_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), default=None)
    category: Mapped[str] = mapped_column(String(40), default="general")
    issue_type: Mapped[str] = mapped_column(String(10), default="punch")
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ncr_templates.id", ondelete="CASCADE"), default=None)


class Ncr(Base, TimestampMixin):
    """One issue: a punch item or an NCR. Fixed system fields here; template answers in ``answers``."""

    __tablename__ = "ncr_reports"
    __table_args__ = (
        Index("ix_ncr_reports_project_status", "project_id", "status"),
        Index("ix_ncr_reports_project_type", "project_id", "issue_type"),
        Index("ix_ncr_reports_inspection", "inspection_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    issue_type: Mapped[str] = mapped_column(String(10), default="ncr")
    category: Mapped[str] = mapped_column(String(40), default="general")
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ncr_templates.id", ondelete="SET NULL"), default=None)
    template_revision_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ncr_template_revisions.id", ondelete="SET NULL"), default=None
    )
    answers: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    raised_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    raised_on: Mapped[date | None] = mapped_column(Date, default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    responsible_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    responsible_contact_id: Mapped[int | None] = mapped_column(Integer, default=None)
    responsible_company_id: Mapped[int | None] = mapped_column(Integer, default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    origin: Mapped[str] = mapped_column(String(20), default="qa")
    source: Mapped[str] = mapped_column(String(20), default="other")
    source_reference: Mapped[str | None] = mapped_column(String(200), default=None)
    inspection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The inspection the issue was raised from (``source_inspection_id`` in KERP)."""
    inspection_item_id: Mapped[int | None] = mapped_column(Integer, default=None)
    closed_by_inspection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    spec_reference: Mapped[str | None] = mapped_column(String(200), default=None)
    severity: Mapped[str] = mapped_column(String(10), default="minor")
    punch_category: Mapped[str | None] = mapped_column(String(1), default=None)
    status: Mapped[str] = mapped_column(String(30), default="open")
    # anchors (exactly one of node / item, or neither for a project-level issue)
    anchor_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), index=True, default=None
    )
    anchor_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), index=True, default=None
    )
    anchor_role: Mapped[str | None] = mapped_column(String(20), default=None)
    work_anchor_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    location_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    # flags (copied from the template revision at raise; changed only through audited overrides)
    visibility: Mapped[str] = mapped_column(String(10), default="internal")
    mdr_effect: Mapped[str] = mapped_column(String(15), default="blocks")
    completion_effect: Mapped[str] = mapped_column(String(10), default="blocks")
    client_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    client_seen_channel: Mapped[str | None] = mapped_column(String(20), default=None)
    # NCR analysis
    root_cause_category: Mapped[str | None] = mapped_column(String(20), default=None)
    root_cause_description: Mapped[str | None] = mapped_column(Text, default=None)
    disposition: Mapped[str | None] = mapped_column(String(30), default=None)
    disposition_notes: Mapped[str | None] = mapped_column(Text, default=None)
    concession_reference: Mapped[str | None] = mapped_column(String(100), default=None)
    disposition_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    # workflow actors
    rectified_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    """Who performed the latest open -> rectified (the rectification being verified)."""
    verified_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    effectiveness_statement: Mapped[str | None] = mapped_column(Text, default=None)
    # links (both directions are new records; nothing is converted)
    upgraded_from_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ncr_reports.id", ondelete="SET NULL"), default=None
    )
    escalated_from_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ncr_reports.id", ondelete="SET NULL"), default=None
    )
    successor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ncr_reports.id", ondelete="SET NULL"), default=None)
    void_reason: Mapped[str | None] = mapped_column(Text, default=None)
    voided_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # cost of quality
    rework_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    delay_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    other_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    days_delay: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class NcrAction(Base, TimestampMixin):
    """A corrective or preventive action (CAPA) on an NCR."""

    __tablename__ = "ncr_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    ncr_id: Mapped[int] = mapped_column(Integer, ForeignKey("ncr_reports.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="corrective")
    responsible_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    verification_criteria: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    cancel_reason: Mapped[str | None] = mapped_column(Text, default=None)
    verified_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    verification_notes: Mapped[str | None] = mapped_column(Text, default=None)


class IssueFlagOverride(Base):
    """The audit ledger of per-issue flag overrides. Loosening entries are counted in QMS KPIs."""

    __tablename__ = "ncr_flag_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey("ncr_reports.id", ondelete="CASCADE"), index=True)
    flag: Mapped[str] = mapped_column(String(20))
    old_value: Mapped[str] = mapped_column(String(15))
    new_value: Mapped[str] = mapped_column(String(15))
    reason: Mapped[str] = mapped_column(Text)
    loosening: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)


class IssueLink(Base):
    """An informational link of an issue to a node or Item (project-level issues). Never rolls up or blocks."""

    __tablename__ = "ncr_issue_links"
    __table_args__ = (Index("ix_ncr_issue_links_target", "target_kind", "target_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey("ncr_reports.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[int] = mapped_column(Integer)

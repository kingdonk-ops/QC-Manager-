"""One inspection engine (KERP TD-002): templates of kind ``inspection`` or ``itp``, one record table for both
kinds, ITP instances on an asset anchor, inspection requests (call-outs), signatures, competencies and
delegations."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .criteria_models import AcceptanceCriterion as AcceptanceCriterion  # registers the table; re-exported
from .gate_models import QualityGate as QualityGate  # registers the table; re-exported


class ChecklistTemplate(Base, TimestampMixin):
    """A reusable template. ``kind=inspection``: ``sections`` is ``[{title, items: [{text, response_type, unit,
    min_value, max_value, requires_photo_on_fail, guidance}]}]``. ``kind=itp``: ``activities`` is the ordered
    plan ``[{key, title, verifying_document, form_template_id, acceptance_criteria, spec_ref,
    required_qualification, points: {contractor, client, third_party}}]``. Records copy what they need, so
    editing a template never changes past results; every content or settings change is a new revision."""

    __tablename__ = "inspections_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    activity: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[list] = mapped_column(JSON, default_factory=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    kind: Mapped[str] = mapped_column(String(12), default="inspection")
    area: Mapped[str] = mapped_column(String(30), default="general")
    issue_category: Mapped[str | None] = mapped_column(String(60), default=None)
    is_formal: Mapped[bool] = mapped_column(Boolean, default=False)
    """Formal records go through submit → review and count toward QA progress; informal ones are record-only."""
    audit_scope: Mapped[str | None] = mapped_column(String(10), default=None)
    """``internal`` / ``external`` for an audit template; None otherwise."""
    linked_issue_types: Mapped[list] = mapped_column(JSON, default_factory=list)
    requires_client_signature: Mapped[bool] = mapped_column(Boolean, default=False)
    required_qualification: Mapped[str | None] = mapped_column(String(120), default=None)
    """A competency the inspector must hold, valid on the signing date, to sign records of this template."""
    activities: Mapped[list] = mapped_column(JSON, default_factory=list)
    item_type_key: Mapped[str | None] = mapped_column(String(64), default=None)
    """ITP: the asset Item type it is written for (an Item anchor must match)."""
    work_type: Mapped[str | None] = mapped_column(String(100), default=None)
    client_document_number: Mapped[str | None] = mapped_column(String(100), default=None)


class TemplateRevision(Base):
    """A frozen copy of a template's content and settings at one version, with its SHA-256."""

    __tablename__ = "inspections_template_revisions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_inspections_template_revisions_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections_templates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class InspectionSettings(Base):
    """Per-project settings."""

    __tablename__ = "inspections_settings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    starters_seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    min_notice_hours: Mapped[int] = mapped_column(Integer, default=24)
    """Notice a call-out with an external Hold or Witness point must give."""
    block_short_notice: Mapped[bool] = mapped_column(Boolean, default=False)
    """Off: short notice is a warning; on: issuing or rescheduling with short notice is refused."""
    no_show_grace_minutes: Mapped[int] = mapped_column(Integer, default=30)
    allow_self_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_report_on_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    """On: a failed record without a criterion raises a report too (off keeps the task-by-default follow-up)."""


class ItpInstance(Base, TimestampMixin):
    """An ITP template applied to one anchor (an ``inspection_anchor`` node or an Item). Its lines are
    ``kind=itp`` inspection records."""

    __tablename__ = "inspections_itp_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_templates.id", ondelete="SET NULL"), default=None
    )
    template_name: Mapped[str] = mapped_column(String(200), default="")
    template_version: Mapped[int] = mapped_column(Integer, default=1)
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True, default=None
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_items.id", ondelete="RESTRICT"), index=True, default=None
    )
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class Inspection(Base, TimestampMixin):
    __tablename__ = "inspections"
    __table_args__ = (Index("ix_inspections_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_templates.id", ondelete="SET NULL"), default=None
    )
    template_name: Mapped[str | None] = mapped_column(String(200), default=None)
    template_version: Mapped[int | None] = mapped_column(Integer, default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    area: Mapped[str | None] = mapped_column(String(200), default=None)
    trade: Mapped[str | None] = mapped_column(String(100), default=None)
    inspector_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    scheduled_date: Mapped[date | None] = mapped_column(Date, default=None)
    inspected_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    not_applicable: Mapped[int] = mapped_column(Integer, default=0)
    unanswered: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float | None] = mapped_column(Float, default=None)
    """passed / (passed + failed) as a percentage, N/A excluded; None until something is scored."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # --- one-engine fields (KERP) ---
    kind: Mapped[str] = mapped_column(String(12), default="inspection")
    category: Mapped[str] = mapped_column(String(30), default="general")
    """The template's Area (``qa_itp``, ``safety_prestart``...). Named ``category`` here because ``area`` is
    the free-text area of the location."""
    is_formal: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_scope: Mapped[str | None] = mapped_column(String(10), default=None)
    requires_client_signature: Mapped[bool] = mapped_column(Boolean, default=False)
    required_qualification: Mapped[str | None] = mapped_column(String(120), default=None)
    template_revision_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_template_revisions.id", ondelete="SET NULL"), default=None
    )
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"), index=True, default=None
    )
    """Anchor (``qa_itp`` only): a node whose level has the ``inspection_anchor`` role."""
    item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_items.id", ondelete="RESTRICT"), index=True, default=None
    )
    """Anchor (``qa_itp`` only): an asset Item."""
    location_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    """Project-level records: where the check was done. Informational, never rolls up."""
    itp_instance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_itp_instances.id", ondelete="CASCADE"), index=True, default=None
    )
    itp_position: Mapped[int | None] = mapped_column(Integer, default=None)
    points: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """ITP line: intervention point per party, ``{"contractor": "H", "client": "W", "third_party": "none"}``."""
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, default=None)
    verifying_document: Mapped[str | None] = mapped_column(String(300), default=None)
    spec_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    hold_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    hold_released_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    proposed_result: Mapped[str | None] = mapped_column(String(10), default=None)
    result: Mapped[str | None] = mapped_column(String(10), default=None)
    """``pass`` / ``fail`` once completed (KERP INSPECTED_PASSED / INSPECTED_FAILED)."""
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    submitted_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    return_reason: Mapped[str | None] = mapped_column(Text, default=None)
    self_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # --- acceptance criteria ---
    criterion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_criteria.id", ondelete="RESTRICT"), index=True, default=None
    )
    """A record-level acceptance criterion (an ITP line copies its activity's)."""
    measured_value: Mapped[str | None] = mapped_column(String(40), default=None)
    conditional: Mapped[bool] = mapped_column(Boolean, default=False)
    """Accepted with a condition: the result stays ``pass`` and a report is raised."""
    report_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The latest report raised from the record as a whole (earlier ones stay on the issue register)."""
    proposed_severity: Mapped[str | None] = mapped_column(String(10), default=None)
    """The report severity the inspector proposed on submit, used when the reviewer names none."""


class InspectionItem(Base):
    """One checklist line of an inspection: the template's wording, copied, and the answer."""

    __tablename__ = "inspections_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(String(500))
    response_type: Mapped[str] = mapped_column(String(20), default="pass_fail")
    unit: Mapped[str | None] = mapped_column(String(30), default=None)
    min_value: Mapped[float | None] = mapped_column(Float, default=None)
    max_value: Mapped[float | None] = mapped_column(Float, default=None)
    requires_photo_on_fail: Mapped[bool] = mapped_column(Boolean, default=False)
    guidance: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str | None] = mapped_column(String(10), default=None)
    """What the inspector chose: pass, fail or na."""
    reading: Mapped[float | None] = mapped_column(Float, default=None)
    outcome: Mapped[str | None] = mapped_column(String(10), default=None)
    """The scored result: a numeric reading outside its limits is a fail whatever was chosen."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    follow_up: Mapped[str | None] = mapped_column(String(10), default=None)
    task_id: Mapped[int | None] = mapped_column(Integer, default=None)
    ncr_id: Mapped[int | None] = mapped_column(Integer, default=None)
    criterion_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inspections_criteria.id", ondelete="RESTRICT"), index=True, default=None
    )
    """The criterion whose limits and unit were copied onto this item when the record was created."""


class InspectionLink(Base):
    """An informational link from a project-level record to a node, Item or equipment. Never rolls up."""

    __tablename__ = "inspections_links"
    __table_args__ = (Index("ix_inspections_links_target", "target_kind", "target_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(12))
    target_id: Mapped[int] = mapped_column(Integer)


class AnswerComment(Base):
    """A reviewer's (or inspector's) comment on one answer, per review round. Append-only."""

    __tablename__ = "inspections_answer_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections_items.id", ondelete="CASCADE"))
    review_round: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class InspectionSignature(Base):
    """One sign-off: who (a snapshot), as what, which competencies were checked, over which content hash.

    Rows are never deleted. A change to the record after signing voids every valid or provisional
    signature whose ``content_sha256`` no longer matches."""

    __tablename__ = "inspections_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12))
    signer_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    signer_snapshot: Mapped[dict] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str | None] = mapped_column(String(12), default=None)
    """Client co-sign: ``portal``, ``on_device`` or ``scan``."""
    competency_snapshot: Mapped[list] = mapped_column(JSON, default_factory=list)
    intent_text: Mapped[str | None] = mapped_column(Text, default=None)
    intent_version: Mapped[int | None] = mapped_column(Integer, default=None)
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """Who entered it, when not the signer (on-device and scanned co-signs)."""
    on_behalf_of_user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    delegation_id: Mapped[int | None] = mapped_column(Integer, default=None)
    signature_image: Mapped[str | None] = mapped_column(Text, default=None)
    """A drawn signature (data URL), on-device co-sign."""
    scan_file_id: Mapped[int | None] = mapped_column(Integer, default=None)
    signer_name_stated: Mapped[str | None] = mapped_column(String(200), default=None)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rejected_reason: Mapped[str | None] = mapped_column(Text, default=None)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    void_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)


class Competency(Base, TimestampMixin):
    """A qualification a person holds (ticket, certificate, VOC), with its expiry. Checked as of the signing date."""

    __tablename__ = "inspections_competencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    qualification: Mapped[str] = mapped_column(String(120))
    level: Mapped[str | None] = mapped_column(String(60), default=None)
    number: Mapped[str | None] = mapped_column(String(100), default=None)
    issuer: Mapped[str | None] = mapped_column(String(200), default=None)
    issued_on: Mapped[date | None] = mapped_column(Date, default=None)
    expires_on: Mapped[date | None] = mapped_column(Date, default=None)
    """None: does not expire."""
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class Delegation(Base, TimestampMixin):
    """A narrow, time-boxed acting delegate. Confers no authority: the delegate needs the permission themself."""

    __tablename__ = "inspections_delegations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    delegator_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"))
    delegate_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


# --- inspection requests (call-outs) -----------------------------------------------------------------


class InspectionRequest(Base, TimestampMixin):
    """A Request for Inspection: one inspection event at one time window, linking the ITP lines or QA
    inspections it calls out, with one row per party."""

    __tablename__ = "inspections_requests"
    __table_args__ = (Index("ix_inspections_requests_project_start", "project_id", "scheduled_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    code: Mapped[str | None] = mapped_column(String(20), default=None)
    """Allocated at first issue; drafts have none."""
    discipline: Mapped[str | None] = mapped_column(String(40), default=None)
    location_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    location_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    requested_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    required_notice_hours: Mapped[int] = mapped_column(Integer, default=0)
    notice_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notice_met: Mapped[bool | None] = mapped_column(Boolean, default=None)
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    outcome_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    outcome_reason: Mapped[str | None] = mapped_column(String(60), default=None)
    outcome_note: Mapped[str | None] = mapped_column(Text, default=None)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, default=None)


class RequestLink(Base):
    """An inspection record (ITP line or QA inspection) called out by a request."""

    __tablename__ = "inspections_request_links"

    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inspections_requests.id", ondelete="CASCADE"), primary_key=True
    )
    inspection_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), primary_key=True)
    prior_status: Mapped[str | None] = mapped_column(String(20), default=None)


class RequestParty(Base):
    """One party on a request: its intervention point, attendance, and the validity of its notice."""

    __tablename__ = "inspections_request_parties"
    __table_args__ = (UniqueConstraint("request_id", "party", name="uq_inspections_request_parties_party"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections_requests.id", ondelete="CASCADE"), index=True)
    party: Mapped[str] = mapped_column(String(12))
    point: Mapped[str] = mapped_column(String(4), default="none")
    point_source: Mapped[str] = mapped_column(String(8), default="itp")
    witness_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    attendance: Mapped[str] = mapped_column(String(10), default="pending")
    attendance_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    attendance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    waiver_ref: Mapped[str | None] = mapped_column(String(200), default=None)
    notice_valid_at_outcome: Mapped[bool | None] = mapped_column(Boolean, default=None)


class RequestRecipient(Base):
    """Someone a party's call-out notifies: a user (in-app and e-mail) or a contact (e-mail only)."""

    __tablename__ = "inspections_request_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("inspections_requests.id", ondelete="CASCADE"), index=True)
    party: Mapped[str] = mapped_column(String(12))
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), default=None)
    contact_id: Mapped[int | None] = mapped_column(Integer, default=None)
    on_behalf_of_user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """Added as the active delegate of this user."""
    delivery: Mapped[str] = mapped_column(String(10), default="pending")
    delivery_reason: Mapped[str | None] = mapped_column(String(30), default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

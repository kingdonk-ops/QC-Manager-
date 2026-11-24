from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from ..common.schemas import EncodableText, PartialUpdate
from .constants import Area, AuditScope, FollowUp, InspectionStatus, Kind, LinkKind, Point, ProposedResult, ResponseType, Result
from .dashboard_schemas import InspectionDashboard as InspectionDashboard  # re-exported: moved to dashboard_schemas
from .dashboard_schemas import InspectionSettingsRead as InspectionSettingsRead
from .dashboard_schemas import InspectionSettingsUpdate as InspectionSettingsUpdate
from .dashboard_schemas import InspectionTrendGroup as InspectionTrendGroup
from .dashboard_schemas import InspectionTrendMonth as InspectionTrendMonth
from .dashboard_schemas import InspectionTrendPoint as InspectionTrendPoint
from .dashboard_schemas import InspectionTrends as InspectionTrends
from .signatory_rules import DEFAULT_REQUIRED, MAX_REQUIRED, MIN_REQUIRED, collected_from_rows

Short = Annotated[str | None, Field(max_length=200)]
Reading = Annotated[float, Field(ge=-1e9, le=1e9)]
Qualification = Annotated[str | None, Field(max_length=120)]
ReportSeverity = Annotated[str, Field(pattern=r"^(minor|major|critical)$")]


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=500)]
    response_type: ResponseType = ResponseType.PASS_FAIL
    unit: Annotated[str | None, Field(max_length=30)] = None
    min_value: Reading | None = Field(None, description="Lowest acceptable reading (numeric items)")
    max_value: Reading | None = Field(None, description="Highest acceptable reading (numeric items)")
    requires_photo_on_fail: bool = False
    guidance: Annotated[str | None, Field(max_length=2000)] = None
    criterion_id: int | None = Field(None, ge=1, description="An acceptance criterion; numeric limits and unit are copied")

    @model_validator(mode="after")
    def _limits(self) -> "ChecklistItem":
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value is above max_value")
        return self


class ChecklistSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=200)]
    items: Annotated[list[ChecklistItem], Field(max_length=200)] = []


class ItpPoints(BaseModel):
    """The intervention point of each party on one ITP activity: Hold, Witness, Review, Surveillance or none."""

    model_config = ConfigDict(extra="forbid")

    contractor: Point = Point.NONE
    client: Point = Point.NONE
    third_party: Point = Point.NONE


class ItpActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str | None, Field(max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")] = Field(
        None, description="Stable key; defaults to the position"
    )
    title: Annotated[str, Field(min_length=1, max_length=300)]
    verifying_document: Annotated[str | None, Field(max_length=300)] = Field(
        None, description="The record that proves it: an ITR form, test certificate, report..."
    )
    form_template_id: int | None = Field(
        None, ge=1, description="A formal inspection template whose checklist the line carries (the ITR form)"
    )
    acceptance_criteria: Annotated[str | None, Field(max_length=2000)] = None
    criterion_id: int | None = Field(None, ge=1, description="Library criterion the line carries at record level")
    spec_ref: Annotated[str | None, Field(max_length=200)] = None
    required_qualification: Qualification = None
    required_signatories: Annotated[
        int, Field(strict=True, ge=MIN_REQUIRED, le=MAX_REQUIRED, description="Distinct people who must sign (1 to 10)")
    ] = DEFAULT_REQUIRED
    points: ItpPoints = ItpPoints()


class TemplateSettings(BaseModel):
    """The settings KERP keeps on a template revision. Changing area, formal or audit scope needs ``inspections.manage``."""

    area: Area = Field(Area.GENERAL, description="Only qa_itp records anchor to the asset tree")
    issue_category: Annotated[str | None, Field(max_length=60)] = None
    is_formal: bool = Field(False, description="Formal: submit → review and counts toward QA progress; else record-only")
    audit_scope: AuditScope | None = None
    linked_issue_types: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=20)] = []
    requires_client_signature: bool = False
    required_qualification: Qualification = None


class ChecklistTemplateIn(EncodableText, TemplateSettings):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    kind: Kind = Kind.INSPECTION
    trade: Annotated[str | None, Field(max_length=100)] = None
    activity: Short = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    sections: Annotated[list[ChecklistSection], Field(max_length=50)] = []
    activities: Annotated[list[ItpActivity], Field(max_length=200)] = []
    item_type_key: Annotated[str | None, Field(max_length=64)] = None
    work_type: Annotated[str | None, Field(max_length=100)] = None
    client_document_number: Annotated[str | None, Field(max_length=100)] = None
    active: bool = True

    @model_validator(mode="after")
    def _kind(self) -> "ChecklistTemplateIn":
        if self.kind == Kind.ITP:
            if self.sections:
                raise ValueError("An ITP template has activities, not sections")
            if not self.activities:
                raise ValueError("An ITP template needs at least one activity")
            # ITP templates are always formal QA/ITP plans (KERP: the tick is locked on).
            self.is_formal, self.area = True, Area.QA_ITP
        elif self.activities:
            raise ValueError("Only an ITP template has activities")
        return self


class ChecklistTemplateUpdate(EncodableText, PartialUpdate):
    """Changing the content or settings bumps the version; records already started keep their copy."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = (
        "name",
        "sections",
        "active",
        "activities",
        "area",
        "is_formal",
        "linked_issue_types",
        "requires_client_signature",
    )

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    activity: Short = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    sections: Annotated[list[ChecklistSection] | None, Field(max_length=50)] = None
    activities: Annotated[list[ItpActivity] | None, Field(max_length=200)] = None
    active: bool | None = None
    area: Area | None = None
    issue_category: Annotated[str | None, Field(max_length=60)] = None
    is_formal: bool | None = None
    audit_scope: AuditScope | None = None
    linked_issue_types: Annotated[list[Annotated[str, Field(max_length=60)]] | None, Field(max_length=20)] = None
    requires_client_signature: bool | None = None
    required_qualification: Qualification = None
    item_type_key: Annotated[str | None, Field(max_length=64)] = None
    work_type: Annotated[str | None, Field(max_length=100)] = None
    client_document_number: Annotated[str | None, Field(max_length=100)] = None


class ChecklistTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str = "inspection"
    trade: str | None
    activity: str | None
    description: str | None
    version: int
    sections: list[ChecklistSection]
    activities: list[ItpActivity] = []
    active: bool
    area: str = "general"
    issue_category: str | None = None
    is_formal: bool = False
    audit_scope: str | None = None
    linked_issue_types: list[str] = []
    requires_client_signature: bool = False
    required_qualification: str | None = None
    item_type_key: str | None = None
    work_type: str | None = None
    client_document_number: str | None = None
    item_count: int = 0
    updated_at: datetime | None = None


class TemplateRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    version: int
    content_sha256: str
    snapshot: dict[str, Any]
    created_by_id: int | None
    created_at: datetime | None


class ChecklistStarterSeed(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: LinkKind
    id: int = Field(ge=1)


class InspectionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    template_id: int = Field(ge=1)
    title: Annotated[str | None, Field(max_length=300)] = Field(None, description="Defaults to the template's name")
    location: Short = None
    area: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = Field(None, description="Defaults to the template's trade")
    inspector_id: int | None = Field(None, ge=1)
    scheduled_date: date | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None
    criterion_id: int | None = Field(None, ge=1, description="A record-level acceptance criterion of this project")
    measured_value: Annotated[str | None, Field(max_length=40)] = None
    node_id: int | None = Field(None, ge=1, description="qa_itp only: an inspection-anchor node")
    item_id: int | None = Field(None, ge=1, description="qa_itp only: an asset Item")
    location_node_id: int | None = Field(None, ge=1, description="Other areas: where the check was done (informational)")
    links: Annotated[list[LinkIn], Field(max_length=20)] = Field(
        [], description="Other areas: informational links to nodes, Items or equipment (at most one equipment)"
    )


class InspectionUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title",)

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    location: Short = None
    area: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    inspector_id: int | None = Field(None, ge=1)
    scheduled_date: date | None = None
    inspected_date: date | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None
    criterion_id: int | None = Field(None, ge=1, description="Refused while a result stands; reopen first")
    measured_value: Annotated[str | None, Field(max_length=40)] = None


class InspectionItemAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    result: Result | None = Field(None, description="pass, fail or na; send null to clear")
    reading: Reading | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class InspectionItemsFill(EncodableText):
    """Answers for some or all items. Fields left out of an answer keep their value."""

    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[InspectionItemAnswer], Field(min_length=1, max_length=500)]


class InspectionStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: InspectionStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class InspectionFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(ge=1)
    action: FollowUp = FollowUp.TASK
    assignee_id: int | None = Field(None, ge=1, description="Task assignee, or the NCR's responsible user")
    due_date: date | None = None
    severity: Annotated[str, Field(pattern=r"^(minor|major|critical)$")] = "minor"


class InspectionCompletion(EncodableText):
    """Completes an informal inspection. Each failed item gets a task unless ``follow_ups`` says ``ncr`` (or ``none``)."""

    model_config = ConfigDict(extra="forbid")

    follow_ups: Annotated[list[InspectionFollowUp], Field(max_length=500)] = []
    default_assignee_id: int | None = Field(None, ge=1)
    default_due_date: date | None = None
    allow_unanswered: bool = Field(False, description="Complete even with unanswered items")
    note: Annotated[str | None, Field(max_length=2000)] = None
    conditional: bool | None = Field(
        None, description="Accepted with a condition: the result stays pass and a report is raised (omitted: false)"
    )
    measured_value: Annotated[str | None, Field(max_length=40)] = None
    report_severity: ReportSeverity | None = Field(None, description="Severity of the report raised (default: major / minor)")


class InspectionSubmit(EncodableText):
    """Submit a formal record for review. Signs it as the inspector when there is no valid inspector signature yet."""

    model_config = ConfigDict(extra="forbid")

    proposed_result: ProposedResult
    accept_intent: bool = Field(False, description="The inspector accepts the signing statement")
    allow_unanswered: bool = False
    note: Annotated[str | None, Field(max_length=2000)] = None
    conditional: bool | None = Field(None, description="Proposed: accepted with a condition (result pass; omitted: false)")
    measured_value: Annotated[str | None, Field(max_length=40)] = None
    report_severity: ReportSeverity | None = Field(None, description="Proposed severity of the report raised on approval")


class AnswerCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(ge=1)
    body: Annotated[str, Field(min_length=1, max_length=2000)]


class InspectionReview(EncodableText):
    """Approve (the record takes the proposed result and its follow-ups are raised) or return with a reason."""

    model_config = ConfigDict(extra="forbid")

    decision: Annotated[str, Field(pattern=r"^(approve|return)$")]
    reason: Annotated[str | None, Field(max_length=2000)] = Field(None, description="Required to return")
    comments: Annotated[list[AnswerCommentIn], Field(max_length=200)] = []
    accept_intent: bool = Field(False, description="Required to approve: the reviewer accepts the signing statement")
    follow_ups: Annotated[list[InspectionFollowUp], Field(max_length=500)] = []
    default_assignee_id: int | None = Field(None, ge=1)
    default_due_date: date | None = None
    report_severity: ReportSeverity | None = Field(None, description="Overrides the severity proposed on submit")

    @model_validator(mode="after")
    def _reason(self) -> "InspectionReview":
        if self.decision == "return" and not (self.reason or "").strip():
            raise ValueError("A return needs a reason")
        return self


class InspectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    section: str
    text: str
    response_type: str
    unit: str | None
    min_value: float | None
    max_value: float | None
    requires_photo_on_fail: bool
    guidance: str | None
    result: str | None
    reading: float | None
    outcome: str | None
    notes: str | None
    follow_up: str | None
    task_id: int | None
    ncr_id: int | None
    criterion_id: int | None = None
    photo_count: int = 0


class AnswerCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    review_round: int
    body: str
    author_id: int | None
    author_name: str | None = None
    created_at: datetime | None
    resolved_at: datetime | None


class LinkRead(BaseModel):
    kind: str
    id: int
    label: str | None = None


class SignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    status: str
    mode: str | None
    signer_user_id: int | None
    signer_snapshot: dict[str, Any]
    competency_snapshot: list[dict[str, Any]]
    content_sha256: str
    signed_at: datetime
    intent_text: str | None
    review_round: int
    recorded_by_id: int | None
    on_behalf_of_user_id: int | None
    delegation_id: int | None
    scan_file_id: int | None
    signer_name_stated: str | None
    has_image: bool = False
    confirmed_at: datetime | None
    rejected_reason: str | None
    voided_at: datetime | None
    void_reason: str | None


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    kind: str = "inspection"
    category: str = "general"
    is_formal: bool = False
    audit_scope: str | None = None
    requires_client_signature: bool = False
    required_qualification: str | None = None
    template_id: int | None
    template_name: str | None
    template_version: int | None
    template_revision_id: int | None = None
    location: str | None
    area: str | None
    trade: str | None
    inspector_id: int | None
    inspector_name: str | None = None
    scheduled_date: date | None
    inspected_date: date | None
    status: str
    notes: str | None
    passed: int
    failed: int
    not_applicable: int
    unanswered: int
    total: int = 0
    pass_rate: float | None
    completed_at: datetime | None
    created_at: datetime | None = None
    node_id: int | None = None
    item_id: int | None = None
    anchor_label: str | None = None
    location_node_id: int | None = None
    links: list[LinkRead] = []
    itp_instance_id: int | None = None
    itp_position: int | None = None
    points: dict[str, str] = {}
    acceptance_criteria: str | None = None
    verifying_document: str | None = None
    spec_ref: str | None = None
    hold_released_at: datetime | None = None
    hold_released_by_id: int | None = None
    proposed_result: str | None = None
    result: str | None = None
    submitted_at: datetime | None = None
    submitted_by_id: int | None = None
    review_round: int = 0
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None
    return_reason: str | None = None
    self_approved: bool = False
    criterion_id: int | None = None
    measured_value: str | None = None
    conditional: bool = False
    report_id: int | None = None
    content_sha256: str | None = None
    required_signatories: int = DEFAULT_REQUIRED
    items: list[InspectionItemRead] = []
    signatures: list[SignatureRead] = []
    comments: list[AnswerCommentRead] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def signatories_collected(self) -> int | None:
        """Distinct people whose valid signature covers the current content; known only on a full read."""
        if self.content_sha256 is None:
            return None
        return collected_from_rows(self.signatures, self.content_sha256)


class EligibilityFinding(BaseModel):
    code: str
    message: str
    blocking: bool = True


class InspectionEligibility(BaseModel):
    action: str
    eligible: bool
    findings: list[EligibilityFinding]

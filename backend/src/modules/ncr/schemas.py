from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText, PartialUpdate
from .constants import (
    ActionKind,
    ActionStatus,
    AnchorKind,
    CompletionEffect,
    Disposition,
    Flag,
    IssueType,
    MdrEffect,
    NcrStatus,
    Origin,
    PunchCategory,
    RootCause,
    Severity,
    Source,
    Visibility,
)
from .templates import FieldDef

Cost = Annotated[Decimal, Field(max_digits=14, decimal_places=2, ge=0)]
Short = Annotated[str | None, Field(max_length=200)]
Text = Annotated[str | None, Field(max_length=20000)]
Reason = Annotated[str, Field(min_length=3, max_length=2000)]
Answers = Annotated[dict[str, Any], Field(max_length=200)]
CategoryKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class IssueLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AnchorKind
    target_id: int = Field(ge=1)


class NcrCreate(EncodableText):
    """Raise an NCR (the original NCR route). The issue type is ``ncr``; the template is the category's default."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Text = None
    raised_on: date | None = Field(None, description="Defaults to today")
    location: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    responsible_user_id: int | None = Field(None, ge=1)
    responsible_contact_id: int | None = Field(None, ge=1, description="A contact from the directory")
    responsible_company_id: int | None = Field(None, ge=1, description="A company from the directory")
    source: Source = Source.OTHER
    source_reference: Short = None
    inspection_id: int | None = Field(None, ge=1)
    inspection_item_id: int | None = Field(None, ge=1)
    spec_reference: Short = Field(None, description="Specification clause or drawing reference")
    severity: Severity = Severity.MINOR


class IssueCreate(EncodableText):
    """Raise a punch item or an NCR. The template decides the type, category and flag defaults.

    Without ``template_id`` the project's default template for ``category`` x ``issue_type`` is used.
    Anchor to a node or an Item; leave both out for a project-level issue (only categories that allow it).
    """

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    issue_type: IssueType | None = None
    template_id: int | None = Field(None, ge=1)
    category: CategoryKey | None = None
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Text = None
    origin: Origin | None = None
    source: Source = Source.OTHER
    source_reference: Short = None
    severity: Severity | None = None
    punch_category: PunchCategory | None = None
    anchor_node_id: int | None = Field(None, ge=1)
    anchor_item_id: int | None = Field(None, ge=1)
    location_node_id: int | None = Field(None, ge=1, description="Project-level issues only: informational location")
    links: Annotated[list[IssueLinkIn], Field(max_length=50)] = []
    location: Short = Field(None, description="Free-text location")
    trade: Annotated[str | None, Field(max_length=100)] = None
    spec_reference: Short = None
    responsible_user_id: int | None = Field(None, ge=1)
    responsible_contact_id: int | None = Field(None, ge=1)
    responsible_company_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    inspection_id: int | None = Field(None, ge=1)
    inspection_item_id: int | None = Field(None, ge=1)
    answers: Answers = {}


class NcrUpdate(EncodableText, PartialUpdate):
    """Only the fields sent change. The status changes through ``/status`` (or ``/issues/{id}/transition``).

    Disposition and root cause are read-only once their NCR step is completed.
    """

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE: ClassVar[tuple[str, ...]] = (
        "title",
        "severity",
        "source",
        "rework_cost",
        "delay_cost",
        "other_cost",
        "days_delay",
    )

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    description: Text = None
    raised_on: date | None = None
    location: Short = None
    trade: Annotated[str | None, Field(max_length=100)] = None
    responsible_user_id: int | None = Field(None, ge=1)
    responsible_contact_id: int | None = Field(None, ge=1)
    responsible_company_id: int | None = Field(None, ge=1)
    source: Source | None = None
    source_reference: Short = None
    spec_reference: Short = None
    severity: Severity | None = None
    root_cause_category: RootCause | None = None
    root_cause_description: Text = None
    disposition: Disposition | None = None
    disposition_notes: Text = None
    concession_reference: Annotated[str | None, Field(max_length=100)] = Field(
        None, description="The client's concession / deviation number, for a use-as-is or repair disposition"
    )
    rework_cost: Cost | None = None
    delay_cost: Cost | None = None
    other_cost: Cost | None = None
    days_delay: Annotated[int | None, Field(ge=0, le=10000)] = None


class IssueUpdate(NcrUpdate):
    """Details, template answers (merged, per step), punch category and due date."""

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = (*NcrUpdate.NOT_NULLABLE, "punch_category", "answers")

    punch_category: PunchCategory | None = None
    due_date: date | None = None
    answers: Answers | None = Field(None, description="Merged into the answers; fields of completed steps are read-only")
    closed_by_inspection_id: int | None = Field(None, ge=1)


class NcrStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: NcrStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class Transition(EncodableText):
    """Move an issue one step. Rejecting a punch (rectified -> open) and an ineffective NCR (effectiveness ->
    corrective_action) need a ``note``; closing an NCR needs ``attest: true`` (the effectiveness sign-off)."""

    model_config = ConfigDict(extra="forbid")

    to: NcrStatus
    note: Annotated[str | None, Field(max_length=2000)] = None
    attest: bool = False
    closed_by_inspection_id: int | None = Field(None, ge=1, description="The re-inspection that proved the fix")


class VoidIssue(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class FlagOverride(EncodableText):
    model_config = ConfigDict(extra="forbid")

    flag: Flag
    value: Annotated[str, Field(max_length=20)]
    reason: Reason


class Upgrade(EncodableText):
    model_config = ConfigDict(extra="forbid")

    template_id: int | None = Field(None, ge=1, description="Default: the project's NCR template for the punch's category")
    note: Annotated[str | None, Field(max_length=2000)] = None


class RaiseExternal(EncodableText):
    """Carry over only what you pick: the description, answers by key, and photos by file id."""

    model_config = ConfigDict(extra="forbid")

    template_id: int | None = Field(None, ge=1)
    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    carry_description: bool = True
    carry_answers: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=200)] = []
    carry_photos: Annotated[list[int], Field(max_length=200)] = []


class NcrActionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=5000)]
    kind: ActionKind = ActionKind.CORRECTIVE
    responsible_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    verification_criteria: Annotated[str | None, Field(max_length=5000)] = None


class NcrActionUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("description", "kind", "status")

    description: Annotated[str | None, Field(min_length=1, max_length=5000)] = None
    kind: ActionKind | None = None
    responsible_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    verification_criteria: Annotated[str | None, Field(max_length=5000)] = None
    status: ActionStatus | None = Field(
        None, description="`done` records you as completer; `verified` as verifier; `cancelled` needs `cancel_reason`"
    )
    verification_notes: Annotated[str | None, Field(max_length=5000)] = None
    cancel_reason: Annotated[str | None, Field(max_length=2000)] = None


class NcrActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ncr_id: int
    description: str
    kind: str
    responsible_id: int | None
    responsible_name: str | None = None
    due_date: date | None
    overdue: bool = False
    verification_criteria: str | None
    status: str
    completed_at: datetime | None
    completed_by_id: int | None = None
    cancel_reason: str | None = None
    verified_by_id: int | None
    verified_by_name: str | None = None
    verified_at: datetime | None
    verification_notes: str | None


class IssueLinkRead(BaseModel):
    kind: str
    target_id: int
    label: str | None = None


class NcrRead(BaseModel):
    """One issue (punch or NCR). The original NCR fields plus the issues engine's fixed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    issue_type: str = "ncr"
    category: str = "general"
    template_id: int | None = None
    template_revision_id: int | None = None
    template_name: str | None = None
    answers: dict[str, Any] = {}
    description: str | None
    raised_by_id: int | None
    raised_by_name: str | None = None
    raised_on: date | None
    location: str | None
    trade: str | None
    responsible_user_id: int | None
    responsible_user_name: str | None = None
    responsible_contact_id: int | None
    responsible_contact_name: str | None = None
    responsible_company_id: int | None
    responsible_company_name: str | None = None
    due_date: date | None = None
    origin: str = "qa"
    source: str
    source_reference: str | None
    inspection_id: int | None
    inspection_item_id: int | None
    closed_by_inspection_id: int | None = None
    spec_reference: str | None
    severity: str
    punch_category: str | None = None
    status: str
    is_open: bool = True
    anchor_node_id: int | None = None
    anchor_item_id: int | None = None
    anchor_role: str | None = None
    anchor_label: str | None = None
    work_anchor_node_id: int | None = None
    location_node_id: int | None = None
    location_label: str | None = None
    links: list[IssueLinkRead] = []
    visibility: str = "internal"
    mdr_effect: str = "blocks"
    completion_effect: str = "blocks"
    client_seen_at: datetime | None = None
    root_cause_category: str | None
    root_cause_description: str | None
    disposition: str | None
    disposition_notes: str | None
    concession_reference: str | None
    disposition_by_id: int | None = None
    rectified_by_id: int | None = None
    verified_by_id: int | None = None
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    effectiveness_statement: str | None = None
    upgraded_from_id: int | None = None
    escalated_from_id: int | None = None
    successor_id: int | None = None
    void_reason: str | None = None
    voided_at: datetime | None = None
    rework_cost: Decimal
    delay_cost: Decimal
    other_cost: Decimal
    total_cost: Decimal = Decimal(0)
    days_delay: int
    open_actions: int = 0
    actions: list[NcrActionRead] = []
    created_at: datetime | None = None
    closed_at: datetime | None = None


class FlagOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    flag: str
    old_value: str
    new_value: str
    reason: str
    loosening: bool
    actor_id: int | None
    actor_name: str | None = None
    created_at: datetime | None


# --- templates ---------------------------------------------------------------------------------------


class TemplateFlags(BaseModel):
    default_origin: Origin | None = None
    default_visibility: Visibility | None = None
    default_mdr_effect: MdrEffect | None = None
    completion_effect: CompletionEffect | None = None
    default_severity: Severity | None = None
    default_punch_category: PunchCategory | None = None
    separate_close: bool | None = None


class TemplateCreate(EncodableText, TemplateFlags):
    """A new issue template (draft revision 1). Omit ``fields`` to start from the type's ``general`` template.
    Omit ``project_id`` for a library template (needs ``ncr.configure``)."""

    model_config = ConfigDict(extra="forbid")

    project_id: int | None = Field(None, ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    issue_type: IssueType
    category: CategoryKey = "general"
    fields: Annotated[list[FieldDef], Field(max_length=200)] | None = None


class TemplateDraft(EncodableText, TemplateFlags):
    """Edit the draft revision (started from the latest published one when there is none)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None
    fields: Annotated[list[FieldDef], Field(max_length=200)] | None = None


class CategoryUpsert(EncodableText):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    is_active: bool | None = None
    sort_order: Annotated[int | None, Field(ge=0, le=10000)] = None
    allows_project_level: bool | None = None


class DefaultTemplateSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = Field(None, ge=1)
    category: CategoryKey
    issue_type: IssueType
    template_id: int = Field(ge=1)

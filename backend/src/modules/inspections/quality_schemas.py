"""Request and response bodies for ITP instances, inspection requests, signing, competencies and delegations."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common.schemas import EncodableText, PartialUpdate, within_utc_range
from .constants import Attendance, CosignMode, DelegationKind, Delivery, Outcome, Party, Point

# --- ITP -----------------------------------------------------------------------------------------------


class ItpInstanceCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    template_id: int = Field(ge=1)
    node_id: int | None = Field(None, ge=1, description="An inspection-anchor node")
    item_id: int | None = Field(None, ge=1, description="An asset Item")


class ItpLineRead(BaseModel):
    id: int
    code: str
    position: int | None
    title: str
    status: str
    result: str | None
    points: dict[str, str]
    acceptance_criteria: str | None
    verifying_document: str | None
    spec_ref: str | None
    required_qualification: str | None
    criterion_id: int | None = None
    item_count: int
    has_hold: bool
    hold_released_at: datetime | None
    hold_released_by_id: int | None
    blocked: bool
    blocked_by: list[str]
    gate_state: str = "review"
    """``review``, ``passed``, ``released``, ``blocked`` or ``pending``: the line's traffic light."""
    gate_satisfied: bool = True
    gate_reason: str | None = None
    witness_status: str
    witness_by_party: dict[str, str]
    request: dict[str, Any] | None


class ItpInstanceRead(BaseModel):
    id: int
    project_id: int
    code: str
    template_id: int | None
    template_name: str
    template_version: int
    node_id: int | None
    item_id: int | None
    anchor_label: str | None
    status: str
    lines_total: int
    lines_done: int
    progress: float
    holds_open: int
    created_at: datetime | None
    lines: list[ItpLineRead] = []


class HoldReleaseBody(EncodableText):
    model_config = ConfigDict(extra="forbid")

    accept_intent: bool = Field(False, description="The signer accepts the release statement")
    on_behalf_of_user_id: int | None = Field(None, ge=1, description="Sign as the active delegate of this person")


# --- signing -------------------------------------------------------------------------------------------


class InspectionSign(EncodableText):
    """The inspector's formal sign-off of the current content."""

    model_config = ConfigDict(extra="forbid")

    accept_intent: bool


class CosignBody(EncodableText):
    """The client's co-signature. ``portal``: the caller is the client, signing in their own account.
    ``on_device`` (drawn on the inspector's device) and ``scan`` (a scanned paper signature) name the client
    and stay provisional until that client confirms in their own account."""

    model_config = ConfigDict(extra="forbid")

    mode: CosignMode
    accept_intent: bool = False
    client_user_id: int | None = Field(None, ge=1, description="on_device / scan: the client's account")
    signer_name: Annotated[str | None, Field(max_length=200)] = Field(None, description="The name the client wrote")
    signature_image: Annotated[str | None, Field(max_length=200_000, pattern=r"^data:image/(png|jpeg|svg\+xml);base64,")] = None
    scan_file_id: int | None = Field(None, ge=1, description="scan: the uploaded file (entity inspection, this record)")

    @model_validator(mode="after")
    def _by_mode(self) -> "CosignBody":
        if self.mode == CosignMode.PORTAL:
            if not self.accept_intent:
                raise ValueError("Accept the co-sign statement (accept_intent)")
        else:
            if not self.client_user_id:
                raise ValueError("Name the client's account (client_user_id)")
            if self.mode == CosignMode.ON_DEVICE and not self.signature_image:
                raise ValueError("An on-device co-sign needs the drawn signature")
            if self.mode == CosignMode.SCAN and not self.scan_file_id:
                raise ValueError("A scanned co-sign needs the uploaded scan")
        return self


class CosignDecision(EncodableText):
    model_config = ConfigDict(extra="forbid")

    decision: Annotated[str, Field(pattern=r"^(confirm|reject)$")]
    reason: Annotated[str | None, Field(max_length=2000)] = None
    accept_intent: bool = False

    @model_validator(mode="after")
    def _rules(self) -> "CosignDecision":
        if self.decision == "reject" and not (self.reason or "").strip():
            raise ValueError("A rejection needs a reason")
        if self.decision == "confirm" and not self.accept_intent:
            raise ValueError("Accept the co-sign statement (accept_intent)")
        return self


class PendingCosign(BaseModel):
    signature_id: int
    inspection_id: int
    project_id: int
    code: str
    title: str
    mode: str | None
    signed_at: datetime
    recorded_by_id: int | None


# --- competencies --------------------------------------------------------------------------------------


class CompetencyIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(ge=1)
    qualification: Annotated[str, Field(min_length=1, max_length=120)]
    level: Annotated[str | None, Field(max_length=60)] = None
    number: Annotated[str | None, Field(max_length=100)] = None
    issuer: Annotated[str | None, Field(max_length=200)] = None
    issued_on: date | None = None
    expires_on: date | None = Field(None, description="Leave empty for a qualification that doesn't expire")
    verified: bool = False
    notes: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _dates(self) -> "CompetencyIn":
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expires_on is before issued_on")
        return self


class CompetencyUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("qualification", "verified")

    qualification: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    level: Annotated[str | None, Field(max_length=60)] = None
    number: Annotated[str | None, Field(max_length=100)] = None
    issuer: Annotated[str | None, Field(max_length=200)] = None
    issued_on: date | None = None
    expires_on: date | None = None
    verified: bool | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class CompetencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    user_name: str | None = None
    qualification: str
    level: str | None
    number: str | None
    issuer: str | None
    issued_on: date | None
    expires_on: date | None
    verified: bool
    notes: str | None
    valid_today: bool = False
    expires_in_days: int | None = None


# --- delegations ---------------------------------------------------------------------------------------


class DelegationIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    delegator_id: int | None = Field(None, ge=1, description="Defaults to you; someone else's needs inspections.manage")
    delegate_id: int = Field(ge=1)
    kind: DelegationKind
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime
    reason: Annotated[str | None, Field(max_length=2000)] = None

    _range = field_validator("starts_at", "ends_at")(within_utc_range)


class DelegationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    delegator_id: int
    delegator_name: str | None = None
    delegate_id: int
    delegate_name: str | None = None
    kind: str
    starts_at: datetime
    ends_at: datetime
    reason: str | None
    revoked_at: datetime | None
    active: bool = False


# --- inspection requests -------------------------------------------------------------------------------


class CalloutPartyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party: Party
    point: Point | None = Field(None, description="Defaults to the strongest point of the linked ITP lines")
    witness_user_id: int | None = Field(None, ge=1, description="A named witness for this party (notified)")
    recipient_user_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=50)] = []
    contact_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=50)] = Field(
        [], description="Client or third-party contacts without an account, notified by e-mail"
    )


class CalloutCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    scheduled_start: AwareDatetime
    duration_minutes: int = Field(60, ge=15, le=720)
    discipline: Annotated[str | None, Field(max_length=40)] = None
    location_ref: Annotated[str | None, Field(max_length=200)] = None
    location_node_id: int | None = Field(None, ge=1)
    notes: Annotated[str | None, Field(max_length=5000)] = None
    inspection_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=50)]
    parties: Annotated[list[CalloutPartyIn], Field(max_length=3)] = []

    _range = field_validator("scheduled_start")(within_utc_range)


class CalloutUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title", "scheduled_start", "duration_minutes", "inspection_ids")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    scheduled_start: AwareDatetime | None = None
    duration_minutes: int | None = Field(None, ge=15, le=720)
    discipline: Annotated[str | None, Field(max_length=40)] = None
    location_ref: Annotated[str | None, Field(max_length=200)] = None
    notes: Annotated[str | None, Field(max_length=5000)] = None
    inspection_ids: Annotated[list[Annotated[int, Field(ge=1)]] | None, Field(min_length=1, max_length=50)] = None

    _range = field_validator("scheduled_start")(within_utc_range)


class CalloutConfirm(EncodableText):
    model_config = ConfigDict(extra="forbid")

    confirmation_ref: Annotated[str | None, Field(max_length=200)] = Field(
        None, description="Required when a reviewer records the confirmation on the party's behalf"
    )


class CalloutAcknowledge(EncodableText):
    model_config = ConfigDict(extra="forbid")

    recipient_id: int | None = Field(None, ge=1, description="A reviewer recording a contact's acknowledgement")


class CalloutAttendance(EncodableText):
    model_config = ConfigDict(extra="forbid")

    party: Party
    attendance: Annotated[str, Field(pattern=f"^({Attendance.ATTENDED.value}|{Attendance.ABSENT.value})$")]


class CalloutWaive(EncodableText):
    model_config = ConfigDict(extra="forbid")

    party: Party
    waiver_ref: Annotated[str | None, Field(max_length=200)] = None


class CalloutOutcome(EncodableText):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    reason: Annotated[str | None, Field(max_length=60)] = Field(
        None, description="failed: work_not_ready, access_not_available, weather, permit_not_issued, ..."
    )
    note: Annotated[str | None, Field(max_length=2000)] = None
    occurred_at: AwareDatetime | None = None

    _range = field_validator("occurred_at")(within_utc_range)


class CalloutReschedule(EncodableText):
    model_config = ConfigDict(extra="forbid")

    scheduled_start: AwareDatetime
    reason: Annotated[str, Field(min_length=1, max_length=2000)]

    _range = field_validator("scheduled_start")(within_utc_range)


class CalloutCancel(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str | None, Field(max_length=2000)] = None


class CalloutRecipientDelivery(EncodableText):
    model_config = ConfigDict(extra="forbid")

    delivery: Delivery
    reason: Annotated[str | None, Field(max_length=30, pattern=r"^(bounced|suppressed|no_channel|provider_error)$")] = None


class CalloutRecipientRead(BaseModel):
    id: int
    user_id: int | None
    contact_id: int | None
    name: str | None
    on_behalf_of_user_id: int | None
    on_behalf_of_name: str | None
    delivery: str
    delivery_reason: str | None
    delivered_at: datetime | None
    acknowledged_at: datetime | None


class CalloutPartyRead(BaseModel):
    id: int
    party: str
    point: str
    point_source: str
    external_hw: bool
    witness_user_id: int | None
    witness_name: str | None
    attendance: str
    attendance_at: datetime | None
    waiver_ref: str | None
    notice_delivery: str
    notice_delivery_reason: str | None
    notice_valid_at_outcome: bool | None
    acknowledged: bool
    recipients: list[CalloutRecipientRead]


class CalloutRead(BaseModel):
    id: int
    project_id: int
    code: str | None
    title: str
    discipline: str | None
    status: str
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int
    location_ref: str | None
    location_node_id: int | None
    notes: str | None
    requested_by_id: int | None
    requested_by_name: str | None
    issued_at: datetime | None
    required_notice_hours: int
    notice_given_at: datetime | None
    notice_met: bool | None
    reschedule_count: int
    confirmed_by_id: int | None
    confirmed_at: datetime | None
    outcome_by_id: int | None
    outcome_at: datetime | None
    outcome_reason: str | None
    outcome_note: str | None
    cancelled_reason: str | None
    strongest_point: str
    inspections: list[dict[str, Any]]
    parties: list[CalloutPartyRead]
    findings: list[dict[str, Any]] = []


class CalloutCalendarEvent(BaseModel):
    id: int
    code: str | None
    title: str
    discipline: str | None
    status: str
    start: datetime
    end: datetime
    location_ref: str | None
    strongest_point: str
    inspections: list[str]
    parties: list[dict[str, Any]]

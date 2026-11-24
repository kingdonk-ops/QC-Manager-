from enum import StrEnum


class InspectionStatus(StrEnum):
    PLANNED = "planned"
    """KERP ``PENDING``."""
    REQUESTED = "requested"
    """KERP ``INSPECTION_REQUESTED``: on an issued inspection request (call-out)."""
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    """A formal record waiting for review; answers are read-only."""
    RETURNED = "returned"
    """Sent back by the reviewer with a reason; answers editable again."""
    COMPLETED = "completed"
    """KERP ``INSPECTED_PASSED`` / ``INSPECTED_FAILED`` (see ``result``)."""
    CLOSED = "closed"
    """KERP ``LOCKED_FOR_TURNOVER``."""


FLOW: dict[str, set[str]] = {
    InspectionStatus.PLANNED: {InspectionStatus.IN_PROGRESS, InspectionStatus.REQUESTED},
    InspectionStatus.REQUESTED: {InspectionStatus.PLANNED, InspectionStatus.IN_PROGRESS, InspectionStatus.SUBMITTED},
    InspectionStatus.IN_PROGRESS: {InspectionStatus.PLANNED, InspectionStatus.COMPLETED, InspectionStatus.SUBMITTED},
    InspectionStatus.SUBMITTED: {InspectionStatus.RETURNED, InspectionStatus.COMPLETED},
    InspectionStatus.RETURNED: {InspectionStatus.SUBMITTED},
    InspectionStatus.COMPLETED: {InspectionStatus.CLOSED, InspectionStatus.IN_PROGRESS},
    InspectionStatus.CLOSED: {InspectionStatus.COMPLETED},
}
"""``completed`` is reached only through ``/complete`` (informal) or ``/review`` (formal); ``requested``,
``submitted`` and ``returned`` only through inspection requests, ``/submit`` and ``/review``."""

DEDICATED = {InspectionStatus.REQUESTED, InspectionStatus.SUBMITTED, InspectionStatus.RETURNED}
EDITABLE = {InspectionStatus.PLANNED, InspectionStatus.REQUESTED, InspectionStatus.IN_PROGRESS, InspectionStatus.RETURNED}


class Kind(StrEnum):
    INSPECTION = "inspection"
    ITP = "itp"


class Area(StrEnum):
    """KERP ``category``, shown as *Area*. Only ``qa_itp`` records anchor to the asset tree."""

    QA_ITP = "qa_itp"
    SAFETY_PRESTART = "safety_prestart"
    EQUIPMENT_CHECK = "equipment_check"
    REPAIR_FAULT = "repair_fault"
    HEALTH_SAFETY = "health_safety"
    GENERAL = "general"


class AuditScope(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class LinkKind(StrEnum):
    NODE = "node"
    ITEM = "item"
    EQUIPMENT = "equipment"


class Party(StrEnum):
    CONTRACTOR = "contractor"
    CLIENT = "client"
    THIRD_PARTY = "third_party"


class Point(StrEnum):
    HOLD = "H"
    WITNESS = "W"
    REVIEW = "R"
    SURVEILLANCE = "S"
    NONE = "none"


POINT_STRENGTH = {"H": 4, "W": 3, "R": 2, "S": 1, "none": 0}
EXTERNAL_PARTIES = (Party.CLIENT.value, Party.THIRD_PARTY.value)


def external_hw(points: dict[str, str]) -> dict[str, str]:
    """Parties other than the contractor whose point is Hold or Witness: only these need notice and a witness."""
    return {p: v for p, v in (points or {}).items() if p in EXTERNAL_PARTIES and v in ("H", "W")}


def has_hold(points: dict[str, str]) -> bool:
    return "H" in (points or {}).values()


class Result(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NA = "na"


class ProposedResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class FollowUp(StrEnum):
    TASK = "task"
    NCR = "ncr"
    NONE = "none"


class GroupBy(StrEnum):
    TRADE = "trade"
    LOCATION = "location"


class ResponseType(StrEnum):
    PASS_FAIL = "pass_fail"
    """Pass, fail or N/A."""
    NUMERIC = "numeric"
    """A reading checked against min/max acceptance limits (N/A allowed too)."""


# --- signing -----------------------------------------------------------------------------------------


class SignatureRole(StrEnum):
    INSPECTOR = "inspector"
    REVIEWER = "reviewer"
    HOLD_RELEASE = "hold_release"
    CLIENT = "client"
    ADDITIONAL_SIGNATORY = "additional_signatory"
    """An extra distinct signer on an ITP line that needs more than one signatory."""


class CosignMode(StrEnum):
    PORTAL = "portal"
    """The client signs in their own account: a full co-signature."""
    ON_DEVICE = "on_device"
    """Drawn on the inspector's device: provisional until the client confirms in their own account."""
    SCAN = "scan"
    """A scanned paper signature: provisional until the client confirms in their own account."""


class SignatureStatus(StrEnum):
    VALID = "valid"
    PROVISIONAL = "provisional"
    VOID = "void"
    REJECTED = "rejected"


INTENT = {
    SignatureRole.INSPECTOR: "I, {name}, performed inspection {code} and confirm the recorded results are true and complete.",
    SignatureRole.REVIEWER: "I, {name}, reviewed inspection {code} and accept its result.",
    SignatureRole.HOLD_RELEASE: "I, {name}, release hold point {code} and confirm the work meets the stated acceptance "
    "criteria.",
    SignatureRole.CLIENT: "I, {name}, co-sign inspection {code} for the client.",
    SignatureRole.ADDITIONAL_SIGNATORY: "I, {name}, sign inspection {code} as an additional signatory and confirm the "
    "recorded results are true and complete.",
}
INTENT_VERSION = 1


class DelegationKind(StrEnum):
    HOLD_POINT = "hold_point"
    """Call-outs naming the delegator as witness, and hold releases on their behalf."""
    REVIEW = "review"


MAX_DELEGATION_DAYS = 90


# --- inspection requests -----------------------------------------------------------------------------


class RequestStatus(StrEnum):
    DRAFT = "draft"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    WITNESSED = "witnessed"
    WAIVED = "waived"
    NO_SHOW = "no_show"
    FAILED = "failed"
    CANCELLED = "cancelled"


LIVE_REQUEST = (RequestStatus.DRAFT.value, RequestStatus.REQUESTED.value, RequestStatus.CONFIRMED.value)
OPEN_REQUEST = (RequestStatus.REQUESTED.value, RequestStatus.CONFIRMED.value)


class Attendance(StrEnum):
    PENDING = "pending"
    ATTENDED = "attended"
    ABSENT = "absent"
    WAIVED = "waived"


class Delivery(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Outcome(StrEnum):
    WITNESSED = "witnessed"
    NO_SHOW = "no_show"
    FAILED = "failed"


class WitnessStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    NONE = "none"
    PENDING = "pending"
    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"


# --- acceptance criteria -----------------------------------------------------------------------------


class RuleType(StrEnum):
    """How a criterion judges a measured value. Only minimum, maximum and range compare numbers."""

    RANGE = "range"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    BOOLEAN = "boolean"
    FREE_TEXT = "free_text"


class ToleranceResult(StrEnum):
    """The verdict of a numeric criterion; anything that cannot be decided is never read as conforming."""

    WITHIN = "within"
    OUT_OF_TOLERANCE = "out_of_tolerance"
    NOT_ASSESSED = "not_assessed"


# --- quality gates -----------------------------------------------------------------------------------


class GateKind(StrEnum):
    """What a standalone gate stands for. Only a hold blocks progress by default and a hold is never waived."""

    HOLD = "hold"
    WITNESS = "witness"
    SURVEILLANCE = "surveillance"
    REVIEW = "review"


class GateStatus(StrEnum):
    """Pending until decided; released, waived and void are permanent."""

    PENDING = "pending"
    RELEASED = "released"
    WAIVED = "waived"
    VOID = "void"


class Authority(StrEnum):
    """The party level a gate needs and a release asserts, listed from lowest to highest in ``gate_rules``."""

    QUALITY_CONTROL = "contractor_qc"
    QUALITY_ASSURANCE = "contractor_qa"
    CLIENT = "client"
    THIRD_PARTY_INSPECTOR = "third_party_inspector"
    JURISDICTION = "authority_having_jurisdiction"


class AttachmentKind(StrEnum):
    """What a gate is attached to, so the can-proceed query can find it."""

    NODE = "node"
    ITEM = "item"
    INSPECTION = "inspection"
    TASK = "task"
    DOSSIER = "dossier"

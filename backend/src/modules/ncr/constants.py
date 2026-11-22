"""The issues engine's fixed vocabulary: two issue types whose workflows are code, plus the flag values.

Everything else a project wants to capture is a template field (see ``templates.py``).
"""

from enum import StrEnum


class IssueType(StrEnum):
    PUNCH = "punch"
    NCR = "ncr"


class NcrStatus(StrEnum):
    """Every status an issue can hold. ``open`` is the raise step of both types (for an NCR: containment)."""

    OPEN = "open"
    # punch
    RECTIFIED = "rectified"
    VERIFIED = "verified"
    # NCR
    DISPOSITION = "disposition"
    ROOT_CAUSE = "root_cause"
    CORRECTIVE_ACTION = "corrective_action"
    EFFECTIVENESS = "effectiveness"
    # terminal
    CLOSED = "closed"
    VOID = "void"
    UPGRADED = "upgraded"
    ESCALATED = "escalated"


S = NcrStatus

PUNCH_FLOW: dict[str, set[str]] = {
    S.OPEN: {S.RECTIFIED},
    # verify accepts (-> verified, closed in the same action unless the template keeps a separate close) or rejects
    S.RECTIFIED: {S.VERIFIED, S.OPEN},
    S.VERIFIED: {S.CLOSED},
}

NCR_FLOW: dict[str, set[str]] = {
    S.OPEN: {S.DISPOSITION},
    S.DISPOSITION: {S.ROOT_CAUSE},
    S.ROOT_CAUSE: {S.CORRECTIVE_ACTION},
    S.CORRECTIVE_ACTION: {S.EFFECTIVENESS},
    # ineffective -> back to corrective action, with a reason
    S.EFFECTIVENESS: {S.CLOSED, S.CORRECTIVE_ACTION},
}

FLOWS: dict[str, dict[str, set[str]]] = {IssueType.PUNCH: PUNCH_FLOW, IssueType.NCR: NCR_FLOW}

TERMINAL = frozenset({S.CLOSED.value, S.VOID.value, S.UPGRADED.value, S.ESCALATED.value})
"""Anything else is "open" in gates, tiles and registers."""

LIFECYCLES: dict[str, list[str]] = {
    IssueType.PUNCH: [S.OPEN, S.RECTIFIED, S.VERIFIED, S.CLOSED],
    IssueType.NCR: [S.OPEN, S.DISPOSITION, S.ROOT_CAUSE, S.CORRECTIVE_ACTION, S.EFFECTIVENESS, S.CLOSED],
}

STEPS: dict[str, list[str]] = {
    IssueType.PUNCH: ["raise", "rectify", "verify"],
    IssueType.NCR: ["raise", "containment", "disposition", "root_cause", "corrective_action", "effectiveness"],
}
"""Template sections belong to one step; their fields are filled during it and read-only after."""

STEP_AT: dict[str, dict[str, int]] = {
    IssueType.PUNCH: {S.OPEN: 0, S.RECTIFIED: 2, S.VERIFIED: 3},
    IssueType.NCR: {S.OPEN: 0, S.DISPOSITION: 2, S.ROOT_CAUSE: 3, S.CORRECTIVE_ACTION: 4, S.EFFECTIVENESS: 5},
}
"""The first step still open in each status: fields of this step and later ones are editable."""

DONE = 99


class Severity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class PunchCategory(StrEnum):
    A = "A"  # hold: safety, test or operational blocker; blocks work completion
    B = "B"  # post-completion snag; must be cleared before final handover
    C = "C"  # information / record update


class Origin(StrEnum):
    """Why the issue was raised. ``client`` and ``external_audit`` lock the flags (never internal, never excluded)."""

    CLIENT = "client"
    QA = "qa"
    INTERNAL_AUDIT = "internal_audit"
    EXTERNAL_AUDIT = "external_audit"
    CONSTRUCTION = "construction"
    SUPPLIER = "supplier"


LOCKED_ORIGINS = frozenset({Origin.CLIENT.value, Origin.EXTERNAL_AUDIT.value})


class Source(StrEnum):
    """Where the issue was found."""

    INSPECTION = "inspection"
    AUDIT = "audit"
    CLIENT = "client"
    SUPPLIER = "supplier"
    WALKDOWN = "walkdown"
    OTHER = "other"


class Visibility(StrEnum):
    INTERNAL = "internal"
    CLIENT = "client"


class MdrEffect(StrEnum):
    BLOCKS = "blocks"
    REGISTER_ONLY = "register_only"
    EXCLUDED = "excluded"


MDR_RANK = {MdrEffect.EXCLUDED.value: 0, MdrEffect.REGISTER_ONLY.value: 1, MdrEffect.BLOCKS.value: 2}


class CompletionEffect(StrEnum):
    BLOCKS = "blocks"
    NONE = "none"


class Flag(StrEnum):
    VISIBILITY = "visibility"
    MDR_EFFECT = "mdr_effect"
    COMPLETION_EFFECT = "completion_effect"


class RootCause(StrEnum):
    MATERIAL = "material"
    WORKMANSHIP = "workmanship"
    DESIGN = "design"
    PROCESS = "process"
    PROCEDURE = "procedure"
    EQUIPMENT = "equipment"
    TRAINING = "training"
    SUBCONTRACTOR = "subcontractor"
    SUPPLIER = "supplier"
    OTHER = "other"


class Disposition(StrEnum):
    REWORK = "rework"
    REPAIR = "repair"
    USE_AS_IS = "use_as_is"
    SCRAP = "scrap"
    RETURN_TO_SUPPLIER = "return_to_supplier"


NEEDS_CONCESSION = frozenset({Disposition.USE_AS_IS.value, Disposition.REPAIR.value})


class ActionKind(StrEnum):
    CORRECTIVE = "corrective"
    PREVENTIVE = "preventive"


class ActionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


class FieldType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    SELECT = "select"
    MULTISELECT = "multiselect"
    CHECKBOX = "checkbox"
    PHOTO = "photo"


class RevisionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class AnchorKind(StrEnum):
    NODE = "node"
    ITEM = "item"


EFFECTIVENESS_STATEMENT = (
    "I verify that the corrective actions of NCR {code} are implemented and effective, "
    "and that the non-conformance is resolved."
)

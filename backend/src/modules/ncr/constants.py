from enum import StrEnum


class NcrStatus(StrEnum):
    OPEN = "open"
    UNDER_INVESTIGATION = "under_investigation"
    CORRECTIVE_ACTION_PLANNED = "corrective_action_planned"
    CORRECTIVE_ACTION_TAKEN = "corrective_action_taken"
    VERIFIED = "verified"
    CLOSED = "closed"


FLOW: dict[str, set[str]] = {
    NcrStatus.OPEN: {NcrStatus.UNDER_INVESTIGATION},
    NcrStatus.UNDER_INVESTIGATION: {NcrStatus.CORRECTIVE_ACTION_PLANNED},
    NcrStatus.CORRECTIVE_ACTION_PLANNED: {NcrStatus.CORRECTIVE_ACTION_TAKEN},
    NcrStatus.CORRECTIVE_ACTION_TAKEN: {NcrStatus.VERIFIED},
    # A failed verification sends the NCR back to planning.
    NcrStatus.VERIFIED: {NcrStatus.CLOSED, NcrStatus.CORRECTIVE_ACTION_PLANNED},
    NcrStatus.CLOSED: set(),
}


class Severity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class Source(StrEnum):
    INSPECTION = "inspection"
    AUDIT = "audit"
    CLIENT = "client"
    SUPPLIER = "supplier"
    OTHER = "other"


class RootCause(StrEnum):
    MATERIAL = "material"
    WORKMANSHIP = "workmanship"
    DESIGN = "design"
    PROCESS = "process"
    SUPPLIER = "supplier"
    OTHER = "other"


class Disposition(StrEnum):
    REWORK = "rework"
    REPAIR = "repair"
    USE_AS_IS = "use_as_is"
    SCRAP = "scrap"
    RETURN_TO_SUPPLIER = "return_to_supplier"


class ActionKind(StrEnum):
    CORRECTIVE = "corrective"
    PREVENTIVE = "preventive"


class ActionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VERIFIED = "verified"
    CANCELLED = "cancelled"

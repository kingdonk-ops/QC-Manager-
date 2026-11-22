from enum import StrEnum


class PlanKind(StrEnum):
    LOOK_AHEAD = "look_ahead"
    SHUTDOWN = "shutdown"
    CAMPAIGN = "campaign"
    BREAK_IN = "break_in"
    RECOVERY = "recovery"
    OTHER = "other"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    IN_EXECUTION = "in_execution"
    CLOSED = "closed"
    CANCELLED = "cancelled"


PLAN_FLOW: dict[str, set[str]] = {
    "draft": {"issued", "cancelled"},
    "issued": {"draft", "in_execution", "cancelled"},
    "in_execution": {"closed", "cancelled"},
    "closed": set(),
    "cancelled": set(),
}


class PackStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DEFERRED = "deferred"


PACK_FLOW: dict[str, set[str]] = {
    "planned": {"ready", "deferred"},
    "ready": {"planned", "in_progress", "deferred"},
    "in_progress": {"ready", "done", "deferred"},
    "done": {"in_progress"},
    "deferred": {"planned"},
}


class PrerequisiteKind(StrEnum):
    MATERIALS = "materials"
    PERMIT = "permit"
    SCAFFOLD = "scaffold"
    DRAWINGS = "drawings"
    ISOLATION = "isolation"
    INSPECTION = "inspection"
    EQUIPMENT = "equipment"
    LABOUR = "labour"
    OTHER = "other"


class PrerequisiteStatus(StrEnum):
    PENDING = "pending"
    CLEARED = "cleared"
    NOT_REQUIRED = "not_required"


class ConstraintCategory(StrEnum):
    ENGINEERING = "engineering"
    MATERIALS = "materials"
    SCAFFOLD = "scaffold"
    PERMITS = "permits"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    PRECEDING = "preceding"
    CLIENT = "client"
    WEATHER = "weather"
    OTHER = "other"


class ConstraintStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Severity(StrEnum):
    WARNING = "warning"
    BLOCKER = "blocker"


MAX_BOARD_DAYS = 62
"""The longest window the board lays out (a two-month shutdown)."""

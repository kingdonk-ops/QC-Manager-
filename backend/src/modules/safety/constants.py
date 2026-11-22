from enum import IntEnum, StrEnum


class IncidentType(StrEnum):
    INJURY = "injury"
    NEAR_MISS = "near_miss"
    PROPERTY_DAMAGE = "property_damage"
    ENVIRONMENTAL = "environmental"
    DANGEROUS_OCCURRENCE = "dangerous_occurrence"


class IncidentStatus(StrEnum):
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    ACTIONS_OPEN = "actions_open"
    CLOSED = "closed"


FLOW: dict[str, set[str]] = {
    IncidentStatus.REPORTED: {IncidentStatus.INVESTIGATING, IncidentStatus.CLOSED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.ACTIONS_OPEN, IncidentStatus.CLOSED},
    IncidentStatus.ACTIONS_OPEN: {IncidentStatus.CLOSED, IncidentStatus.INVESTIGATING},
    IncidentStatus.CLOSED: {IncidentStatus.INVESTIGATING},
}


class ObservationKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ObservationCategory(StrEnum):
    PPE = "ppe"
    HOUSEKEEPING = "housekeeping"
    WORKING_AT_HEIGHT = "working_at_height"
    MANUAL_HANDLING = "manual_handling"
    TOOLS_EQUIPMENT = "tools_equipment"
    HOT_WORK = "hot_work"
    SCAFFOLDING = "scaffolding"
    CHEMICALS = "chemicals"
    PERMITS = "permits"
    BEHAVIOUR = "behaviour"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"


class ObservationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ParentType(StrEnum):
    INCIDENT = "incident"
    OBSERVATION = "observation"


class ActionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


OPEN_ACTIONS = (ActionStatus.OPEN.value, ActionStatus.IN_PROGRESS.value)


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


def risk_band(score: int | None) -> str | None:
    """Severity × likelihood on a 5×5 matrix: 1-4 low, 5-9 medium, 10-14 high, 15-25 extreme."""
    if score is None:
        return None
    if score >= 15:
        return RiskBand.EXTREME.value
    if score >= 10:
        return RiskBand.HIGH.value
    if score >= 5:
        return RiskBand.MEDIUM.value
    return RiskBand.LOW.value


TRIR_BASE = 200_000
"""OSHA convention: 100 full-time workers × 2,000 hours a year."""
LTIFR_BASE = 1_000_000
"""Per million hours worked."""


class RateBase(IntEnum):
    """The hours base a rate is expressed per."""

    PER_200K = TRIR_BASE
    PER_MILLION = LTIFR_BASE

from enum import StrEnum

DEFAULT_INTERVAL_DAYS = 7
"""Periodic re-inspection interval unless a scaffold sets its own."""


class ScaffoldStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ERECTING = "erecting"
    ERECTED = "erected"
    """Built, awaiting the handover inspection."""
    IN_USE = "in_use"
    MODIFYING = "modifying"
    DISMANTLE_REQUESTED = "dismantle_requested"
    DISMANTLING = "dismantling"
    DISMANTLED = "dismantled"


S = ScaffoldStatus

FLOW: dict[str, set[str]] = {
    S.REQUESTED: {S.APPROVED, S.REJECTED, S.CANCELLED},
    S.APPROVED: {S.ERECTING, S.CANCELLED},
    S.ERECTING: {S.ERECTED},
    S.ERECTED: {S.MODIFYING, S.DISMANTLE_REQUESTED},
    S.IN_USE: {S.MODIFYING, S.DISMANTLE_REQUESTED},
    S.MODIFYING: {S.ERECTED},
    S.DISMANTLE_REQUESTED: {S.DISMANTLING, S.IN_USE, S.ERECTED},
    S.DISMANTLING: {S.DISMANTLED},
    S.REJECTED: set(),
    S.CANCELLED: set(),
    S.DISMANTLED: set(),
}
"""Hand-made steps. ``erected -> in_use`` happens only through a passing inspection."""

STANDING = {S.ERECTED, S.IN_USE, S.MODIFYING, S.DISMANTLE_REQUESTED, S.DISMANTLING}
"""Physically on site: these count hire days and need inspections."""

CLOSED = {S.REJECTED, S.CANCELLED, S.DISMANTLED}

APPROVE_STEPS = {S.APPROVED, S.REJECTED, S.DISMANTLING}
"""Steps that need ``scaffolds.approve`` (a build request, and the go-ahead to dismantle)."""


class Tag(StrEnum):
    NONE = "none"
    GREEN = "green"
    """Safe for use."""
    YELLOW = "yellow"
    """Restricted use: read the restrictions on the tag."""
    RED = "red"
    """Do not use: unsafe, incomplete, or the inspection is overdue."""


USABLE_TAGS = {Tag.GREEN.value, Tag.YELLOW.value}


class ScaffoldType(StrEnum):
    INDEPENDENT = "independent"
    TOWER = "tower"
    MOBILE = "mobile"
    BIRDCAGE = "birdcage"
    HANGING = "hanging"
    CANTILEVER = "cantilever"
    SYSTEM = "system"
    TUBE_AND_FITTING = "tube_and_fitting"
    OTHER = "other"


class DutyClass(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SPECIAL = "special"


class InspectionKind(StrEnum):
    HANDOVER = "handover"
    PERIODIC = "periodic"
    WEATHER = "weather"
    MODIFICATION = "modification"
    INCIDENT = "incident"
    AD_HOC = "ad_hoc"


class ModificationStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


MOD_FLOW: dict[str, set[str]] = {
    ModificationStatus.REQUESTED: {ModificationStatus.APPROVED, ModificationStatus.REJECTED},
    ModificationStatus.APPROVED: {ModificationStatus.COMPLETED},
    ModificationStatus.REJECTED: set(),
    ModificationStatus.COMPLETED: set(),
}

from enum import StrEnum


class NdeMethod(StrEnum):
    RT = "rt"
    UT = "ut"
    MT = "mt"
    PT = "pt"
    PMI = "pmi"
    HARDNESS = "hardness"


class WeldStatus(StrEnum):
    FIT_UP = "fit_up"
    WELDED = "welded"
    NDE_PENDING = "nde_pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CUT_OUT = "cut_out"


class WpsStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


WPS_FLOW: dict[str, set[str]] = {
    WpsStatus.DRAFT: {WpsStatus.APPROVED, WpsStatus.WITHDRAWN},
    WpsStatus.APPROVED: {WpsStatus.WITHDRAWN},
    WpsStatus.WITHDRAWN: {WpsStatus.DRAFT},
}


class WelderStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class QualificationStatus(StrEnum):
    VALID = "valid"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class QualificationState(StrEnum):
    """Worked out on the day: what the matrix shows."""

    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    LAPSED = "lapsed"
    """Continuity lapsed: no welding with the process inside the window."""
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class NdeReason(StrEnum):
    RANDOM = "random"
    """Picked to meet the sampling percentage."""
    FULL = "full"
    """100 % for the method on this weld category."""
    PROGRESSIVE = "progressive"
    """Extra welds of the same welder after a rejection (tier 1, 2, then all)."""
    REPAIR = "repair"
    """Re-examination of a repaired weld."""
    CLIENT = "client"


SAMPLING_REASONS = {NdeReason.RANDOM.value, NdeReason.FULL.value, NdeReason.CLIENT.value}


class NdeResultValue(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class NdeRequestStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


NDE_REQUEST_FLOW: dict[str, set[str]] = {
    NdeRequestStatus.DRAFT: {NdeRequestStatus.ISSUED, NdeRequestStatus.CANCELLED},
    NdeRequestStatus.ISSUED: {NdeRequestStatus.COMPLETED, NdeRequestStatus.CANCELLED},
    NdeRequestStatus.COMPLETED: set(),
    NdeRequestStatus.CANCELLED: set(),
}


class JointType(StrEnum):
    BUTT = "butt"
    FILLET = "fillet"
    SOCKET = "socket"
    BRANCH = "branch"
    SEAL = "seal"
    OTHER = "other"


class VisualResult(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class BoltedJointStatus(StrEnum):
    NEW = "new"
    MADE_UP = "made_up"
    BROKEN_OUT = "broken_out"


class JointEventKind(StrEnum):
    BREAKOUT = "breakout"
    MAKE_UP = "make_up"


class TighteningMethod(StrEnum):
    TORQUE = "torque"
    TENSION = "tension"


DEFAULT_NDE_RATES: dict[str, dict[str, float]] = {
    "normal": {"rt": 5.0},
    "category_d": {},
    "category_m": {"rt": 20.0, "pt": 5.0},
    "high_pressure": {"rt": 100.0},
    "severe_cyclic": {"rt": 100.0, "mt": 100.0},
}
"""Percent of welds examined per method, by weld category (ASME B31.3 style defaults; edit per project)."""

WELD_ENTITY = "weld"
WPS_ENTITY = "welding_wps"
NDE_REQUEST_ENTITY = "nde_request"
JOINT_ENTITY = "bolted_joint"
WELD_ITEM_TYPE = "weld"

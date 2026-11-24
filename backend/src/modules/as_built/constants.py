from enum import StrEnum


class AsBuiltStatus(StrEnum):
    DRAFT = "draft"
    SURVEYED = "surveyed"
    VERIFIED = "verified"
    RECORDED = "recorded"
    """Signed as a valid legal record; locked."""
    SUPERSEDED = "superseded"
    """A verified record replaced by a correction; kept as evidence."""
    VOID = "void"


class CaptureMethod(StrEnum):
    LASER_SCAN = "laser_scan"
    PHOTOGRAMMETRY = "photogrammetry"
    TOTAL_STATION = "total_station"
    SATELLITE_POSITIONING = "satellite_positioning"
    TAPE = "tape"
    DRONE_LIDAR = "drone_lidar"
    MODEL_EXTRACTION = "model_extraction"
    MANUAL = "manual"


class AccuracyClass(StrEnum):
    SURVEY = "survey"
    STANDARD = "standard"
    COARSE = "coarse"


class SourceKind(StrEnum):
    POINT_CLOUD_SCAN = "point_cloud_scan"
    POINT_CLOUD_REGISTRATION = "point_cloud_registration"
    TAKEOFF_MEASUREMENT = "takeoff_measurement"
    DOCUMENT = "document"
    MANUAL = "manual"


FLOW: dict[str, set[str]] = {
    AsBuiltStatus.DRAFT: {AsBuiltStatus.SURVEYED, AsBuiltStatus.VOID},
    AsBuiltStatus.SURVEYED: {AsBuiltStatus.VERIFIED, AsBuiltStatus.VOID},
    AsBuiltStatus.VERIFIED: {AsBuiltStatus.RECORDED, AsBuiltStatus.SUPERSEDED},
    AsBuiltStatus.RECORDED: set(),
    AsBuiltStatus.SUPERSEDED: set(),
    AsBuiltStatus.VOID: set(),
}
"""Every move a record can make. A survey may also be repeated while the record is surveyed (it stays surveyed)."""

ACTION_FOR: dict[str, str] = {
    AsBuiltStatus.SURVEYED: "survey",
    AsBuiltStatus.VERIFIED: "verify",
    AsBuiltStatus.RECORDED: "sign",
}
"""The dedicated action that reaches a status; an ordinary edit never does."""

EDIT_MOVES: frozenset[tuple[str, str]] = frozenset(
    {
        (AsBuiltStatus.DRAFT, AsBuiltStatus.VOID),
        (AsBuiltStatus.SURVEYED, AsBuiltStatus.VOID),
        (AsBuiltStatus.VERIFIED, AsBuiltStatus.SUPERSEDED),
    }
)
"""The only status moves an ordinary edit may make."""

SURVEYABLE = (AsBuiltStatus.DRAFT.value, AsBuiltStatus.SURVEYED.value)
JUDGED = (AsBuiltStatus.SURVEYED.value, AsBuiltStatus.VERIFIED.value, AsBuiltStatus.SUPERSEDED.value)
"""A survey has been recorded: the measured value and criterion no longer change by edit."""
LOCKED = (AsBuiltStatus.RECORDED.value, AsBuiltStatus.VOID.value)
KEPT = (AsBuiltStatus.VERIFIED.value, AsBuiltStatus.SUPERSEDED.value)
"""Never rewritten: a correction supersedes the record and a new one is made."""
DELETABLE = (AsBuiltStatus.DRAFT.value, AsBuiltStatus.SURVEYED.value, AsBuiltStatus.VOID.value)

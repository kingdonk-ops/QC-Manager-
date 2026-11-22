from enum import StrEnum


class InspectionStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"


FLOW: dict[str, set[str]] = {
    InspectionStatus.PLANNED: {InspectionStatus.IN_PROGRESS},
    InspectionStatus.IN_PROGRESS: {InspectionStatus.PLANNED, InspectionStatus.COMPLETED},
    InspectionStatus.COMPLETED: {InspectionStatus.CLOSED, InspectionStatus.IN_PROGRESS},
    InspectionStatus.CLOSED: {InspectionStatus.COMPLETED},
}
"""``completed`` is reached only through ``/complete``, which scores and raises the follow-up actions."""


class ResponseType(StrEnum):
    PASS_FAIL = "pass_fail"
    """Pass, fail or N/A."""
    NUMERIC = "numeric"
    """A reading checked against min/max acceptance limits (N/A allowed too)."""


class Result(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NA = "na"


class FollowUp(StrEnum):
    TASK = "task"
    NCR = "ncr"
    NONE = "none"


class GroupBy(StrEnum):
    TRADE = "trade"
    LOCATION = "location"

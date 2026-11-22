from enum import StrEnum


class Cadence(StrEnum):
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"


class MeetingStatus(StrEnum):
    PLANNED = "planned"
    HELD = "held"
    MINUTES_ISSUED = "minutes_issued"
    CANCELLED = "cancelled"


class ActionStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


FLOW: dict[str, set[str]] = {
    MeetingStatus.PLANNED: {MeetingStatus.HELD, MeetingStatus.CANCELLED},
    MeetingStatus.HELD: {MeetingStatus.PLANNED, MeetingStatus.MINUTES_ISSUED},
    MeetingStatus.MINUTES_ISSUED: {MeetingStatus.HELD},
    MeetingStatus.CANCELLED: {MeetingStatus.PLANNED},
}
"""Allowed status changes. Minutes are issued from ``held`` through ``POST /{id}/issue``, which may re-issue."""

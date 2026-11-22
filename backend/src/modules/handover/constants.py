from datetime import timedelta
from enum import StrEnum


class HandoverStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"


FLOW: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"draft", "acknowledged"},
    "acknowledged": set(),
}


class Shift(StrEnum):
    DAY = "day"
    NIGHT = "night"


class ItemKind(StrEnum):
    OPEN_ITEM = "open_item"
    SAFETY = "safety"
    PERMIT = "permit"
    EQUIPMENT = "equipment"
    WIP = "wip"
    ISSUE = "issue"


ITEM_STATUSES: dict[str, tuple[str, ...]] = {
    "open_item": ("open", "closed"),
    "safety": ("open", "closed"),
    "permit": ("active", "suspended", "closed"),
    "equipment": ("operational", "defective", "isolated", "out_of_service"),
    "wip": ("in_progress", "on_hold", "complete"),
    "issue": ("open", "closed"),
}
"""Allowed statuses per kind; the first is the default."""

STILL_OPEN = {"open", "active", "suspended", "defective", "isolated", "out_of_service", "in_progress", "on_hold"}
"""Statuses carried forward into the next handover for the same area."""

REMIND_AFTER = timedelta(hours=1)
"""First reminder to the incoming supervisor this long after submission."""
REMIND_EVERY = timedelta(hours=2)
ESCALATE_AFTER_REMINDERS = 3
"""After this many reminders the author is told the handover is still unacknowledged."""

"""Pure rules for where a deleted draft goes, when the recycle bin may be emptied and when a record may be restored.

A draft that has no history beyond its creation goes to the recycle bin: restorable, and physically removed by the
scheduled purge once the project's retention has passed. Any other draft goes to the hidden Deleted folder: restorable,
never removed. The rules are fail-safe: a fact that is missing, malformed or negative reads as history, and an unknown
or missing deleted kind reads as the folder, so nothing is ever purged on doubtful evidence. This file imports neither
the web framework nor the database layer."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .constants import BIN, DEFAULT_RETENTION_DAYS, FOLDER, MAX_RETENTION_DAYS, MIN_RETENTION_DAYS
from .rules import Finding

NOT_DELETED = "not-deleted"
ITEM_DELETED = "item-deleted"
BAD_RETENTION = "bad-retention"

NON_HISTORY_VERBS = frozenset({"created", "deleted", "restored", "purged"})
"""Audit verbs (the last part of an action name) that are not history: the creation of the record itself and the
delete, restore and purge steps of the bin. Every other audit entry for the record is history."""

ITEM_LINK_FIELDS = ("scaffold_id", "related_refs")
PERMIT_LINK_FIELDS = ("inspection_id",)
"""The fields that tie a record to another record elsewhere. Placement fields chosen at creation (asset node,
coordinator) are not links in this sense. Kept in one place so a product decision can change the list."""


@dataclass(frozen=True)
class RecordHistory:
    """What is known about a record at the moment it is deleted. Every field is required: a fact nobody supplied can
    never read as 'no history'.

    ``audit_actions``: the action name of each audit entry about the record.
    ``status_changes``: the number of status history rows.
    ``permits``: the number of permits it has ever had, deleted ones included (always zero for a permit).
    ``links``: the number of link fields that are set (see ``count_links``)."""

    audit_actions: Iterable[str]
    status_changes: int
    permits: int
    links: int


def _none(count: object) -> bool:
    return isinstance(count, int) and not isinstance(count, bool) and count == 0


def _verb(action: object) -> str | None:
    return action.rsplit(".", 1)[-1] if isinstance(action, str) else None


def count_links(record: object, fields: Iterable[str]) -> int:
    """How many of ``fields`` are set on ``record`` (not empty, not blank)."""
    count = 0
    for name in fields:
        value = getattr(record, name, None)
        if value is not None and value != {} and value != [] and value != "":
            count += 1
    return count


def has_history_beyond_creation(history: RecordHistory) -> bool:
    """Whether removing the record would touch the audit chain: it has an audit entry other than its creation (and the
    bin's own delete, restore and purge steps), a status change, a permit (even a deleted one) or a link."""
    if not (_none(history.status_changes) and _none(history.permits) and _none(history.links)):
        return True
    try:
        actions = list(history.audit_actions)
    except TypeError:
        return True
    return any(_verb(action) not in NON_HISTORY_VERBS for action in actions)


def deletion_destination(history: RecordHistory) -> str:
    """The recycle bin for a record with no history beyond its creation, otherwise the Deleted folder."""
    return FOLDER if has_history_beyond_creation(history) else BIN


def in_bin(kind: object) -> bool:
    """Only an explicit bin kind is the recycle bin; anything else, missing included, is the Deleted folder."""
    return kind == BIN


# --- retention and purge ------------------------------------------------------------------------------------------


def retention_days(value: object) -> int:
    """The retention to apply: a whole number of days from the minimum to the maximum, otherwise the default."""
    if isinstance(value, int) and not isinstance(value, bool) and MIN_RETENTION_DAYS <= value <= MAX_RETENTION_DAYS:
        return value
    return DEFAULT_RETENTION_DAYS


def retention_refusal(value: object) -> Finding | None:
    """Why a retention setting is refused (``None`` when it may be saved)."""
    if isinstance(value, int) and not isinstance(value, bool) and MIN_RETENTION_DAYS <= value <= MAX_RETENTION_DAYS:
        return None
    return Finding(BAD_RETENTION, f"Retention is a whole number of days from {MIN_RETENTION_DAYS} to {MAX_RETENTION_DAYS}.")


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def purge_on(deleted_at: object, retention: object) -> datetime | None:
    """The moment a bin record becomes due for the purge, or ``None`` when it has no deletion time."""
    if not isinstance(deleted_at, datetime):
        return None
    return _aware(deleted_at) + timedelta(days=retention_days(retention))


def purge_due(kind: object, deleted_at: object, retention: object, now: datetime) -> bool:
    """Whether the scheduled purge may physically remove the record: it is in the recycle bin (never the folder, never a
    record of unknown kind) and the retention has fully passed. The moment itself is due."""
    if not in_bin(kind):
        return False
    due = purge_on(deleted_at, retention)
    return due is not None and _aware(now) >= due


# --- restore ------------------------------------------------------------------------------------------------------


def restore_refusal(deleted_at: object, parent_deleted: bool = False) -> Finding | None:
    """Why a record cannot be restored: it is not deleted, or (for a permit) its item is still deleted."""
    if deleted_at is None:
        return Finding(NOT_DELETED, "The record is not deleted.")
    if parent_deleted:
        return Finding(ITEM_DELETED, "The permit's item is deleted: restore the item first.")
    return None

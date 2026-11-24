"""Vocabulary of the temporary works register, and the status sets the rules are built on.

The status sets that carry a product decision (what counts as overdue, which statuses need an independent check or a
named coordinator) live here, in one place, so a later decision changes them without touching the rule files."""

from datetime import UTC, date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

SITE_TIME_ZONE = "Australia/Perth"
"""The day the register is judged on unless the caller names one. Matches the destination's report scheduling default."""

EXPIRING_SOON_DAYS = 3
"""A live permit whose last valid day is this close, or closer, gets an advisory warning and one notice."""


def site_today(now: datetime | None = None) -> date:
    """The current calendar day at the site. ``now`` is for tests and for callers that already hold the clock."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(SITE_TIME_ZONE)).date()


class Family(StrEnum):
    FALSEWORK = "falsework"
    FORMWORK = "formwork"
    PROPPING = "propping"
    EXCAVATION_SUPPORT = "excavation_support"
    SCAFFOLD = "scaffold"
    FACADE_RETENTION = "facade_retention"
    CRANE_BASE = "crane_base"
    EDGE_PROTECTION = "edge_protection"
    DEWATERING = "dewatering"
    HOARDING = "hoarding"
    OTHER = "other"


class ItemStatus(StrEnum):
    IDENTIFIED = "identified"
    DESIGN_BRIEF = "design_brief"
    DESIGN_SUBMITTED = "design_submitted"
    DESIGN_CHECKED = "design_checked"
    APPROVED_TO_LOAD = "approved_to_load"
    LOADED = "loaded"
    IN_USE = "in_use"
    APPROVED_TO_STRIKE = "approved_to_strike"
    STRUCK = "struck"
    REMOVED = "removed"
    ON_HOLD = "on_hold"
    """A side status: it has no position in the main flow."""


S = ItemStatus

MAIN_FLOW: tuple[str, ...] = (
    S.IDENTIFIED.value,
    S.DESIGN_BRIEF.value,
    S.DESIGN_SUBMITTED.value,
    S.DESIGN_CHECKED.value,
    S.APPROVED_TO_LOAD.value,
    S.LOADED.value,
    S.IN_USE.value,
    S.APPROVED_TO_STRIKE.value,
    S.STRUCK.value,
    S.REMOVED.value,
)
"""The ten main-flow statuses in order; on hold is the eleventh status and sits outside it."""

ITEM_STATUSES: tuple[str, ...] = (*MAIN_FLOW, S.ON_HOLD.value)
CATEGORIES: tuple[int, ...] = (0, 1, 2, 3)
"""Design check categories; the rigour of the independent check rises with the category."""
UNASSIGNED = "unassigned"
UNKNOWN = "unknown"


class PermitKind(StrEnum):
    LOAD = "load"
    STRIKE = "strike"
    DISMANTLE = "dismantle"


class PermitStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    ACTIVE = "active"
    EXPIRED = "expired"
    CLOSED = "closed"


PERMIT_KINDS: tuple[str, ...] = tuple(k.value for k in PermitKind)
PERMIT_STATUSES: tuple[str, ...] = tuple(s.value for s in PermitStatus)

LIVE_PERMIT_STATUSES = frozenset({PermitStatus.ISSUED.value, PermitStatus.ACTIVE.value})
"""The only permit statuses that can be valid; a draft, expired, closed or unknown status never is."""

BEARING_LOAD = frozenset({S.LOADED.value, S.IN_USE.value})
"""Statuses in which the work carries load: without a valid permit to load these are a breach."""


def _span(first: ItemStatus, last: ItemStatus) -> frozenset[str]:
    return frozenset(MAIN_FLOW[MAIN_FLOW.index(first.value) : MAIN_FLOW.index(last.value) + 1])


DESIGN_CLEARED = _span(S.DESIGN_CHECKED, S.REMOVED)
"""Counted by the design clearance percentage: design checked and every later main-flow status (not on hold)."""

INDEPENDENT_CHECK_STATUSES = _span(S.DESIGN_CHECKED, S.APPROVED_TO_STRIKE)
"""From these statuses a category two or three item needs a named checker who is not the designer."""

COORDINATOR_STATUSES = _span(S.APPROVED_TO_LOAD, S.APPROVED_TO_STRIKE)
"""From these statuses an item must name its temporary works coordinator, by name or by user."""

LOAD_SETTLED = _span(S.LOADED, S.REMOVED) | {S.ON_HOLD.value}
"""Overdue to load never applies in these statuses (user decision: an item is overdue until it has actually been
loaded, so approved to load still counts as overdue; on hold is never overdue)."""

STRIKE_PENDING = frozenset({S.LOADED.value, S.IN_USE.value, S.APPROVED_TO_STRIKE.value})
"""Overdue to strike applies only in these statuses (recommended default: not before loaded, not on hold)."""

DRAFT_ITEM_STATUS = S.IDENTIFIED.value
"""The draft state of an item: the only status it can be deleted in, and the one a return to draft goes back to."""

ITEM_ENTITY = "temporary_works_item"
PERMIT_ENTITY = "temporary_works_permit"
SETTINGS_ENTITY = "temporary_works_settings"
"""Entity names under which status history, audit entries, notices and tasks refer to the record kinds."""

BIN = "bin"
FOLDER = "folder"
DELETED_KINDS: tuple[str, ...] = (BIN, FOLDER)
"""Where a deleted draft goes. The recycle bin (``bin``) holds records with no history beyond their creation; the hidden
Deleted folder (``folder``) holds every other one and is never emptied. A missing or unknown kind reads as the folder."""

DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 60
"""How long a record stays in the recycle bin before the scheduled purge may remove it: a project setting, with this
default and range."""

SCAFFOLD_USABLE_TAGS = frozenset({"green", "yellow"})
"""The effective scaffold tags that read as usable."""


def label(value: object) -> str:
    """A status or kind as plain words: ``approved_to_load`` becomes ``approved to load``."""
    return str(value).replace("_", " ")

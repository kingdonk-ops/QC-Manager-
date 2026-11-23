"""Pure rules of the temporary works register: permit validity, the load and strike gates, the bearing-load breach,
overdue load and strike, the design clearance percentage, status and category counting, and advisory warnings.

Every function takes the as-of day as an argument and reads plain attributes from the items and permits it is given,
so it works on stored rows and on simple stand-ins alike. Nothing here is stored. The rules fail safe: a gate answers
cleared only on positive evidence, and a missing, unknown or out-of-vocabulary value reads as shut or as a breach and
never raises. This file imports neither the web framework nor the database layer."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, NamedTuple

from .constants import (
    BEARING_LOAD,
    CATEGORIES,
    DESIGN_CLEARED,
    EXPIRING_SOON_DAYS,
    ITEM_STATUSES,
    LIVE_PERMIT_STATUSES,
    LOAD_SETTLED,
    SCAFFOLD_USABLE_TAGS,
    STRIKE_PENDING,
    UNASSIGNED,
    UNKNOWN,
    PermitKind,
    label,
)


class Finding(NamedTuple):
    """A rule outcome: which rule spoke, and the plain-language explanation."""

    rule: str
    message: str


class Breach(NamedTuple):
    """An item bearing load without a valid permit to load."""

    item_id: int | None
    reference: str | None
    title: str | None
    reason: str


# --- reading values defensively ----------------------------------------------------------------------


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _bounds(permit: Any) -> tuple[bool, date | None, date | None]:
    """Whether the window is readable, and its start and end (``None`` leaves that side open). A bound that is
    present but not a calendar day makes the window unreadable, and an unreadable window is never valid."""
    start, end = getattr(permit, "valid_from", None), getattr(permit, "valid_to", None)
    if (start is not None and _as_day(start) is None) or (end is not None and _as_day(end) is None):
        return False, None, None
    return True, _as_day(start), _as_day(end)


def _ref(item: Any) -> str:
    return _text(getattr(item, "reference", None)) or "The item"


# --- permits and gates -------------------------------------------------------------------------------


def permit_valid_on(permit: Any, day: Any) -> bool:
    """Valid only when issued or active and ``day`` lies inside the window, inclusive at both ends; a missing start or
    end leaves that side open. Draft, expired, closed and unknown statuses are never valid."""
    today = _as_day(day)
    if today is None or _text(getattr(permit, "status", None)) not in LIVE_PERMIT_STATUSES:
        return False
    readable, start, end = _bounds(permit)
    if not readable:
        return False
    return (start is None or start <= today) and (end is None or today <= end)


def valid_permits(permits: Iterable[Any], kind: PermitKind, day: Any) -> list[Any]:
    return [p for p in permits if getattr(p, "kind", None) == kind.value and permit_valid_on(p, day)]


def prerequisites_met(permit: Any) -> bool:
    """Both the design check and the inspection are recorded; anything but an explicit yes reads as missing."""
    return getattr(permit, "design_check_accepted", None) is True and getattr(permit, "inspection_passed", None) is True


def missing_prerequisites(permit: Any) -> list[str]:
    missing = []
    if getattr(permit, "design_check_accepted", None) is not True:
        missing.append("design check accepted")
    if getattr(permit, "inspection_passed", None) is not True:
        missing.append("inspection passed")
    return missing


def load_gate_open(permits: Iterable[Any], day: Any) -> bool:
    """Cleared to load: a valid permit to load that records both prerequisites. The item's own status plays no part."""
    return any(prerequisites_met(p) for p in valid_permits(permits, PermitKind.LOAD, day))


def strike_gate_open(permits: Iterable[Any], day: Any) -> bool:
    """Cleared to strike: a valid permit to strike. A permit to dismantle does not open this gate, and the
    prerequisite flags have no effect on it."""
    return bool(valid_permits(permits, PermitKind.STRIKE, day))


# --- breach ------------------------------------------------------------------------------------------


def has_valid_load_permit(permits: Iterable[Any], day: Any) -> bool:
    return bool(valid_permits(permits, PermitKind.LOAD, day))


def is_breach(status: Any, permits: Iterable[Any], day: Any) -> bool:
    """Loaded or in use with no valid permit to load. The prerequisite flags are not part of this test."""
    return _text(status) in BEARING_LOAD and not has_valid_load_permit(permits, day)


def breach_reason(status: Any, day: Any) -> str:
    when = _as_day(day)
    return f"The item is {label(status)} with no valid permit to load on {when.isoformat() if when else day}."


def find_breaches(items: Iterable[Any], permits_by_item: Mapping[Any, Sequence[Any]], day: Any) -> list[Breach]:
    out = []
    for item in items:
        status, item_id = getattr(item, "status", None), getattr(item, "id", None)
        if is_breach(status, permits_by_item.get(item_id, ()), day):
            reference, title = getattr(item, "reference", None), getattr(item, "title", None)
            out.append(Breach(item_id, reference, title, breach_reason(status, day)))
    return out


def is_compliant(breaches: Sequence[Breach]) -> bool:
    """The register is compliant exactly when there is no breach. Warnings never change this."""
    return not breaches


# --- overdue -----------------------------------------------------------------------------------------


def overdue_to_load(item: Any, day: Any) -> bool:
    """A required load day strictly before ``day`` while the item has not reached loaded (approved to load still
    counts) and is not on hold. The boundary day is not overdue and a missing date never is."""
    required, today = _as_day(getattr(item, "required_load_on", None)), _as_day(day)
    if required is None or today is None or _text(getattr(item, "status", None)) in LOAD_SETTLED:
        return False
    return required < today


def overdue_to_strike(item: Any, day: Any) -> bool:
    """A required strike day strictly before ``day`` while the item is loaded, in use or approved to strike."""
    required, today = _as_day(getattr(item, "required_strike_on", None)), _as_day(day)
    if required is None or today is None or _text(getattr(item, "status", None)) not in STRIKE_PENDING:
        return False
    return required < today


# --- clearance and counting --------------------------------------------------------------------------


def design_clearance(statuses: Iterable[Any]) -> Decimal | None:
    """Items at design checked or any later main-flow status over all items, times 100, rounded half up to two
    decimals. An empty register has no percentage (``None``), which is never read as zero."""
    values = list(statuses)
    if not values:
        return None
    cleared = sum(1 for s in values if _text(s) in DESIGN_CLEARED)
    return (Decimal(cleared) * 100 / Decimal(len(values))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def status_counts(statuses: Iterable[Any]) -> dict[str, int]:
    """Every known status present (zero when empty). A value outside the vocabulary is still counted, under its own
    key, so the counts always sum to the total."""
    counts = dict.fromkeys(ITEM_STATUSES, 0)
    for raw in statuses:
        key = _text(raw) or UNKNOWN
        counts[key] = counts.get(key, 0) + 1
    return counts


def category_counts(categories: Iterable[Any]) -> dict[str, int]:
    """Categories zero to three and an unassigned bucket, zero-filled; an out-of-vocabulary value is counted under
    its own key and never dropped."""
    counts = {**{str(c): 0 for c in CATEGORIES}, UNASSIGNED: 0}
    for raw in categories:
        key = UNASSIGNED if raw is None else str(raw)
        counts[key] = counts.get(key, 0) + 1
    return counts


# --- advisory warnings (never affect compliance) -----------------------------------------------------


def bearing_load_warning(item: Any, permits: Sequence[Any], day: Any) -> Finding | None:
    """Bearing load under a valid permit to load that lacks a prerequisite: not a breach, but worth saying."""
    if _text(getattr(item, "status", None)) not in BEARING_LOAD:
        return None
    valid = valid_permits(permits, PermitKind.LOAD, day)
    if not valid or any(prerequisites_met(p) for p in valid):
        return None
    nearest = min(valid, key=lambda p: len(missing_prerequisites(p)))
    missing = " and ".join(missing_prerequisites(nearest))
    number = _text(getattr(nearest, "number", None)) or "the permit"
    return Finding(
        "prerequisites-missing",
        f"{_ref(item)} is {label(item.status)} but its permit to load {number} does not record: {missing}.",
    )


def lapses_within(permit: Any, day: Any, days: int = EXPIRING_SOON_DAYS) -> bool:
    """A live permit whose last valid day is today or within ``days`` days."""
    today, end = _as_day(day), _as_day(getattr(permit, "valid_to", None))
    if today is None or end is None or _text(getattr(permit, "status", None)) not in LIVE_PERMIT_STATUSES:
        return False
    return 0 <= (end - today).days <= days


def lapsing_warnings(item: Any, permits: Iterable[Any], day: Any) -> list[Finding]:
    out = []
    for permit in permits:
        if lapses_within(permit, day):
            number = _text(getattr(permit, "number", None)) or "A permit"
            last_day = _as_day(getattr(permit, "valid_to", None))
            kind = label(getattr(permit, "kind", None))
            out.append(Finding("permit-lapsing", f"{_ref(item)}: permit {number} ({kind}) is valid only until {last_day}."))
    return out


def scaffold_state_warning(item: Any, effective_tag: Any, inspection_overdue: Any) -> Finding | None:
    """A linked scaffold that is not tagged green or yellow, or whose inspection is overdue (or unknown)."""
    usable = _text(effective_tag) in SCAFFOLD_USABLE_TAGS
    if usable and inspection_overdue is False:
        return None
    reasons = []
    if not usable:
        reasons.append(f"its tag reads {_text(effective_tag) or 'unknown'}")
    if inspection_overdue is not False:
        reasons.append("its inspection is overdue" if inspection_overdue is True else "its inspection state is unknown")
    return Finding("scaffold-not-usable", f"{_ref(item)}: the linked scaffold is not usable: {' and '.join(reasons)}.")

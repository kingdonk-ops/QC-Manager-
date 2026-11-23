"""Pure guarded transitions for items and permits, and the entry preconditions of the safety-critical statuses.

Items move one step forward along the main flow, one step back with a note, to on hold from any live status, and back
from on hold only to the status they were held from; removed is terminal. Permits move draft to issued, issued to
active, issued or active to closed; expired is set only by the sweep. The entry preconditions are checks over facts
the caller supplies (the facts default to the shut answer, so a missing fact never clears anything). These tables are
the recommended defaults and are kept together here so a later product decision can relax them in one place. This
file imports neither the web framework nor the database layer."""

from dataclasses import dataclass

from .constants import CATEGORIES, DRAFT_ITEM_STATUS, ITEM_STATUSES, MAIN_FLOW, PermitStatus
from .constants import ItemStatus as S
from .rules import Finding

ON_HOLD = S.ON_HOLD.value
LIVE_ITEM_STATUSES = frozenset(MAIN_FLOW[:-1])
"""Every main-flow status except removed: an item in one of these can be put on hold."""

PERMIT_FLOW: dict[str, frozenset[str]] = {
    PermitStatus.DRAFT.value: frozenset({PermitStatus.ISSUED.value}),
    PermitStatus.ISSUED.value: frozenset({PermitStatus.ACTIVE.value, PermitStatus.CLOSED.value}),
    PermitStatus.ACTIVE.value: frozenset({PermitStatus.CLOSED.value}),
    PermitStatus.EXPIRED.value: frozenset(),
    PermitStatus.CLOSED.value: frozenset(),
}
"""Moves a person can make through the issue, activate and close actions."""
SWEEP_EXPIRES = frozenset({PermitStatus.ISSUED.value, PermitStatus.ACTIVE.value})
"""The only statuses the sweep may move to expired."""

# rule ids
UNKNOWN_STATUS = "unknown-status"
NO_CHANGE = "no-change"
TERMINAL = "terminal"
ONE_STEP = "one-step"
NOTE_REQUIRED = "note-required"
HELD_FROM = "held-from"
NOT_LIVE = "not-live"
CATEGORY_REQUIRED = "category-required"
COORDINATOR_REQUIRED = "coordinator-required"
LOAD_GATE = "load-gate"
SCAFFOLD_NOT_USABLE = "scaffold-not-usable"
IN_USE_FROM_LOADED = "in-use-from-loaded"
NO_LOAD_PERMIT = "no-valid-load-permit"
STRIKE_GATE = "strike-gate"
REASON_REQUIRED = "reason-required"
ALREADY_DRAFT = "already-draft"
NOT_DRAFT = "not-draft"
HAS_PERMITS = "has-permits"


def _index(status: object) -> int | None:
    return MAIN_FLOW.index(status) if isinstance(status, str) and status in MAIN_FLOW else None


def _words(status: str) -> str:
    return status.replace("_", " ")


def item_move(current: object, target: object, held_from: object = None, note: str | None = None) -> Finding | None:
    """Why an item may not move from ``current`` to ``target`` (``None`` when the move is allowed)."""
    if not (isinstance(current, str) and current in ITEM_STATUSES and isinstance(target, str) and target in ITEM_STATUSES):
        return Finding(UNKNOWN_STATUS, "That status is not part of the temporary works flow.")
    if current == target:
        return Finding(NO_CHANGE, f"The item is already {_words(current)}.")
    if current == S.REMOVED:
        return Finding(TERMINAL, "A removed item cannot change status.")
    if target == ON_HOLD:
        if current not in LIVE_ITEM_STATUSES:
            return Finding(NOT_LIVE, f"An item that is {_words(current)} cannot be put on hold.")
        return None
    if current == ON_HOLD:
        if held_from != target:
            return Finding(HELD_FROM, "An item on hold can resume only at the status it was held from.")
        return None
    here, there = _index(current), _index(target)
    if here is None or there is None or abs(there - here) != 1:
        return Finding(ONE_STEP, f"An item moves one step at a time: {_words(current)} cannot go to {_words(target)}.")
    if there < here and not (note and note.strip()):
        return Finding(NOTE_REQUIRED, "Moving an item back a step needs a note saying why.")
    return None


def allowed_next(current: object, held_from: object = None) -> list[str]:
    """The statuses an item can move to from ``current`` (a step back also needs a note), for display."""
    if not isinstance(current, str) or current not in ITEM_STATUSES or current == S.REMOVED:
        return []
    if current == ON_HOLD:
        return [held_from] if isinstance(held_from, str) and held_from in LIVE_ITEM_STATUSES else []
    here = MAIN_FLOW.index(current)
    steps = [MAIN_FLOW[i] for i in (here + 1, here - 1) if 0 <= i < len(MAIN_FLOW)]
    return [*steps, ON_HOLD]


def held_from_after(current: str, target: str) -> str | None:
    """The status to remember after a move: the one being left when going on hold, otherwise nothing."""
    return current if target == ON_HOLD else None


def permit_move(current: object, target: object, *, sweep: bool = False) -> Finding | None:
    """Why a permit may not move from ``current`` to ``target``. Only the sweep sets expired, and only from a live
    status; no action reaches expired."""
    if not (isinstance(current, str) and current in PERMIT_FLOW and isinstance(target, str) and target in PERMIT_FLOW):
        return Finding(UNKNOWN_STATUS, "That status is not part of the permit flow.")
    if target == PermitStatus.EXPIRED:
        if sweep and current in SWEEP_EXPIRES:
            return None
        return Finding(ONE_STEP, "Only the hourly sweep sets a permit to expired, and only from issued or active.")
    if target not in PERMIT_FLOW[current]:
        return Finding(ONE_STEP, f"A permit that is {current} cannot become {target}.")
    return None


def _reason_given(reason: object) -> bool:
    return isinstance(reason, str) and bool(reason.strip())


def item_return_to_draft(current: object, reason: object) -> Finding | None:
    """Why an item may not be sent back to draft (``None`` when it may). Any status but draft qualifies, and the reason
    is mandatory."""
    if not (isinstance(current, str) and current in ITEM_STATUSES):
        return Finding(UNKNOWN_STATUS, "That status is not part of the temporary works flow.")
    if current == DRAFT_ITEM_STATUS:
        return Finding(ALREADY_DRAFT, "The item is already in draft.")
    if not _reason_given(reason):
        return Finding(REASON_REQUIRED, "Sending an item back to draft needs a reason.")
    return None


def permit_return_to_draft(current: object, reason: object) -> Finding | None:
    """Why a permit may not be sent back to draft: draft itself, an unknown status or a missing reason."""
    if not (isinstance(current, str) and current in PERMIT_FLOW):
        return Finding(UNKNOWN_STATUS, "That status is not part of the permit flow.")
    if current == PermitStatus.DRAFT:
        return Finding(ALREADY_DRAFT, "The permit is already in draft.")
    if not _reason_given(reason):
        return Finding(REASON_REQUIRED, "Sending a permit back to draft needs a reason.")
    return None


def item_delete_refusal(status: object, live_permits: int) -> Finding | None:
    """An item is deleted only in draft, and only once every one of its permits has been deleted first. Any status that
    is not draft, known or not, is refused."""
    if status != DRAFT_ITEM_STATUS:
        return Finding(NOT_DRAFT, "Only an item in draft can be deleted: send it back to draft first, with a reason.")
    if live_permits > 0:
        return Finding(HAS_PERMITS, "Delete each of the item's permits first (a permit must be in draft to be deleted).")
    return None


def permit_delete_refusal(status: object) -> Finding | None:
    """A permit is deleted only while it is a draft."""
    if status != PermitStatus.DRAFT:
        return Finding(NOT_DRAFT, "Only a permit in draft can be deleted: send it back to draft first, with a reason.")
    return None


@dataclass(frozen=True)
class EntryFacts:
    """What the caller knows when an item asks to enter a status. Every field defaults to the shut answer."""

    category: int | None = None
    coordinator_named: bool = False
    load_gate_open: bool = False
    load_permit_valid: bool = False
    strike_gate_open: bool = False
    scaffold_linked: bool = False
    scaffold_tag_usable: bool = False
    scaffold_inspection_overdue: bool = True


def entry_refusal(current: str, target: str, facts: EntryFacts) -> Finding | None:
    """The precondition that stops an item entering ``target``, if any. A step back, or going on hold, is never
    stopped here; resuming from hold into a status is judged like entering it."""
    here, there = _index(current), _index(target)
    if target == ON_HOLD or (here is not None and there is not None and there < here):
        return None
    if target == S.APPROVED_TO_LOAD:
        if facts.category not in CATEGORIES:
            return Finding(CATEGORY_REQUIRED, "Approval to load needs a design check category.")
        if not facts.coordinator_named:
            return Finding(COORDINATOR_REQUIRED, "Approval to load needs a named temporary works coordinator.")
    elif target == S.LOADED:
        if not facts.load_gate_open:
            return Finding(
                LOAD_GATE, "Loading needs a valid permit to load that records both the design check and the inspection."
            )
        if facts.scaffold_linked and not (facts.scaffold_tag_usable and not facts.scaffold_inspection_overdue):
            return Finding(SCAFFOLD_NOT_USABLE, "The linked scaffold must be tagged green or yellow and inspected on time.")
    elif target == S.IN_USE:
        if current not in (S.LOADED, ON_HOLD):
            return Finding(IN_USE_FROM_LOADED, "An item goes into use only from loaded.")
        if not facts.load_permit_valid:
            return Finding(NO_LOAD_PERMIT, "Use needs a valid permit to load.")
    elif target == S.STRUCK and not facts.strike_gate_open:
        return Finding(STRIKE_GATE, "Striking needs a valid permit to strike.")
    return None


def plan_item_move(current: object, target: object, held_from: object, note: str | None, facts: EntryFacts) -> Finding | None:
    """The guarded move followed by the entry preconditions: the first thing that stops the item, or ``None``."""
    refusal = item_move(current, target, held_from, note)
    if refusal is not None:
        return refusal
    if not (isinstance(current, str) and isinstance(target, str)):  # item_move has already accepted both as text
        return Finding(UNKNOWN_STATUS, "That status is not part of the temporary works flow.")
    return entry_refusal(current, target, facts)

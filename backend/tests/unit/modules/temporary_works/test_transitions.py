"""Temporary works guarded transitions: the item flow, the permit flow and the entry preconditions."""

from typing import Any

import pytest

from src.modules.temporary_works import transitions as t
from src.modules.temporary_works.constants import ITEM_STATUSES, MAIN_FLOW, PERMIT_STATUSES
from src.modules.temporary_works.transitions import (
    EntryFacts,
    allowed_next,
    entry_refusal,
    held_from_after,
    item_move,
    permit_move,
    plan_item_move,
)

PAIRS = list(zip(MAIN_FLOW, MAIN_FLOW[1:], strict=False))
LIVE = list(MAIN_FLOW[:-1])


def open_facts(**extra: Any) -> EntryFacts:
    """Every gate open and a usable scaffold, so a test shuts exactly the thing it is about."""
    values = {
        "category": 2,
        "coordinator_named": True,
        "load_gate_open": True,
        "load_permit_valid": True,
        "strike_gate_open": True,
        "scaffold_linked": False,
        "scaffold_tag_usable": True,
        "scaffold_inspection_overdue": False,
    }
    return EntryFacts(**{**values, **extra})


# --- the vocabulary ----------------------------------------------------------------------------------------


def test_there_are_eleven_item_statuses_with_on_hold_outside_the_main_flow():
    assert len(ITEM_STATUSES) == 11
    assert len(MAIN_FLOW) == 10
    assert "on_hold" not in MAIN_FLOW
    assert MAIN_FLOW[0] == "identified"
    assert MAIN_FLOW[-1] == "removed"


# --- items: forward, back, hold ----------------------------------------------------------------------------


@pytest.mark.parametrize(("current", "target"), PAIRS)
def test_an_item_moves_one_step_forward(current: str, target: str):
    assert item_move(current, target) is None


@pytest.mark.parametrize(("current", "target"), list(zip(MAIN_FLOW, MAIN_FLOW[2:], strict=False)))
def test_an_item_cannot_skip_a_step_forward(current: str, target: str):
    refusal = item_move(current, target)
    assert refusal is not None
    assert refusal.rule == t.ONE_STEP


@pytest.mark.parametrize(("earlier", "later"), PAIRS[:-1])
def test_an_item_moves_one_step_back_only_with_a_note(earlier: str, later: str):
    assert item_move(later, earlier, note="Design reissued") is None
    for note in (None, "", "   "):
        refusal = item_move(later, earlier, note=note)
        assert refusal is not None
        assert refusal.rule == t.NOTE_REQUIRED


def test_an_item_cannot_skip_a_step_back():
    refusal = item_move("loaded", "design_checked", note="why")
    assert refusal is not None
    assert refusal.rule == t.ONE_STEP


def test_a_removed_item_is_terminal():
    for target in ITEM_STATUSES:
        refusal = item_move("removed", target, note="why")
        assert refusal is not None
        assert refusal.rule in (t.TERMINAL, t.NO_CHANGE)
    assert item_move("removed", "struck", note="back").rule == t.TERMINAL  # type: ignore[union-attr]


def test_an_item_cannot_move_to_the_status_it_already_has():
    assert item_move("loaded", "loaded").rule == t.NO_CHANGE  # type: ignore[union-attr]
    assert item_move("on_hold", "on_hold", held_from="loaded").rule == t.NO_CHANGE  # type: ignore[union-attr]


@pytest.mark.parametrize("current", LIVE)
def test_any_live_status_can_go_on_hold(current: str):
    assert item_move(current, "on_hold") is None


def test_a_removed_item_cannot_go_on_hold():
    assert item_move("removed", "on_hold") is not None


@pytest.mark.parametrize("held", LIVE)
def test_an_item_on_hold_resumes_only_at_the_status_it_was_held_from(held: str):
    assert item_move("on_hold", held, held_from=held) is None
    other = next(s for s in LIVE if s != held)
    refusal = item_move("on_hold", other, held_from=held)
    assert refusal is not None
    assert refusal.rule == t.HELD_FROM


def test_an_item_on_hold_with_no_remembered_status_resumes_nowhere():
    for target in LIVE:
        assert item_move("on_hold", target, held_from=None) is not None


@pytest.mark.parametrize(
    ("current", "target"),
    [("mystery", "loaded"), ("loaded", "mystery"), (None, "loaded"), ("loaded", None), (7, "loaded"), ("", "")],
)
def test_an_unknown_status_is_refused_and_never_raises(current: Any, target: Any):
    refusal = item_move(current, target)
    assert refusal is not None
    assert refusal.rule == t.UNKNOWN_STATUS


@pytest.mark.parametrize("current", ITEM_STATUSES)
def test_allowed_next_agrees_with_item_move(current: str):
    held = "in_use" if current == "on_hold" else None
    listed = set(allowed_next(current, held))
    for target in ITEM_STATUSES:
        allowed = item_move(current, target, held, note="why") is None
        assert (target in listed) is allowed, (current, target)


def test_allowed_next_for_removed_and_unknown_is_empty():
    assert allowed_next("removed") == []
    assert allowed_next("mystery") == []
    assert allowed_next(None) == []
    assert allowed_next("on_hold") == []


def test_held_from_remembers_the_status_left_only_when_going_on_hold():
    assert held_from_after("loaded", "on_hold") == "loaded"
    assert held_from_after("on_hold", "loaded") is None
    assert held_from_after("loaded", "in_use") is None


# --- permits -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target"),
    [("draft", "issued"), ("issued", "active"), ("issued", "closed"), ("active", "closed")],
)
def test_a_permit_moves_along_draft_issued_active_closed(current: str, target: str):
    assert permit_move(current, target) is None


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "active"),
        ("draft", "closed"),
        ("issued", "draft"),
        ("active", "issued"),
        ("active", "draft"),
        ("closed", "active"),
        ("closed", "issued"),
        ("closed", "draft"),
        ("expired", "closed"),
        ("expired", "issued"),
        ("expired", "active"),
        ("draft", "draft"),
        ("issued", "issued"),
    ],
)
def test_every_other_permit_move_is_refused(current: str, target: str):
    assert permit_move(current, target) is not None


@pytest.mark.parametrize("current", ["issued", "active"])
def test_only_the_sweep_sets_expired_and_only_from_a_live_status(current: str):
    assert permit_move(current, "expired") is not None
    assert permit_move(current, "expired", sweep=False) is not None
    assert permit_move(current, "expired", sweep=True) is None


@pytest.mark.parametrize("current", ["draft", "expired", "closed"])
def test_the_sweep_cannot_expire_a_permit_that_is_not_live(current: str):
    assert permit_move(current, "expired", sweep=True) is not None


@pytest.mark.parametrize(
    ("current", "target"), [("mystery", "issued"), ("draft", "mystery"), (None, "issued"), ("draft", None)]
)
def test_an_unknown_permit_status_is_refused_and_never_raises(current: Any, target: Any):
    assert permit_move(current, target) is not None


def test_the_permit_table_covers_every_permit_status():
    assert set(t.PERMIT_FLOW) == set(PERMIT_STATUSES)
    assert t.PERMIT_FLOW["expired"] == frozenset()
    assert t.PERMIT_FLOW["closed"] == frozenset()
    assert all("expired" not in targets for targets in t.PERMIT_FLOW.values())


# --- entry preconditions ------------------------------------------------------------------------------------


def test_the_default_facts_are_all_shut():
    facts = EntryFacts()
    assert facts.category is None
    assert not (facts.coordinator_named or facts.load_gate_open or facts.load_permit_valid or facts.strike_gate_open)
    assert not facts.scaffold_tag_usable
    assert facts.scaffold_inspection_overdue


def test_approved_to_load_needs_a_category():
    assert entry_refusal("design_checked", "approved_to_load", open_facts()) is None
    refusal = entry_refusal("design_checked", "approved_to_load", open_facts(category=None))
    assert refusal is not None
    assert refusal.rule == t.CATEGORY_REQUIRED
    assert entry_refusal("design_checked", "approved_to_load", open_facts(category=0)) is None
    assert entry_refusal("design_checked", "approved_to_load", open_facts(category=4)) is not None


def test_approved_to_load_needs_the_coordinator_rule():
    refusal = entry_refusal("design_checked", "approved_to_load", open_facts(coordinator_named=False))
    assert refusal is not None
    assert refusal.rule == t.COORDINATOR_REQUIRED


def test_loaded_needs_the_load_gate_open():
    assert entry_refusal("approved_to_load", "loaded", open_facts()) is None
    refusal = entry_refusal("approved_to_load", "loaded", open_facts(load_gate_open=False))
    assert refusal is not None
    assert refusal.rule == t.LOAD_GATE
    assert "design check" in refusal.message
    assert "inspection" in refusal.message


def test_a_linked_scaffold_must_be_usable_and_inspected_on_time_to_load():
    linked = {"scaffold_linked": True}
    assert entry_refusal("approved_to_load", "loaded", open_facts(**linked)) is None
    for shut in ({"scaffold_tag_usable": False}, {"scaffold_inspection_overdue": True}):
        refusal = entry_refusal("approved_to_load", "loaded", open_facts(**linked, **shut))
        assert refusal is not None
        assert refusal.rule == t.SCAFFOLD_NOT_USABLE


def test_an_unlinked_item_ignores_the_scaffold_facts():
    shut = open_facts(scaffold_linked=False, scaffold_tag_usable=False, scaffold_inspection_overdue=True)
    assert entry_refusal("approved_to_load", "loaded", shut) is None


def test_in_use_needs_a_valid_permit_to_load_and_comes_from_loaded():
    assert entry_refusal("loaded", "in_use", open_facts()) is None
    refusal = entry_refusal("loaded", "in_use", open_facts(load_permit_valid=False))
    assert refusal is not None
    assert refusal.rule == t.NO_LOAD_PERMIT
    assert entry_refusal("approved_to_load", "in_use", open_facts()).rule == t.IN_USE_FROM_LOADED  # type: ignore[union-attr]


def test_the_load_gate_fact_alone_does_not_open_use():
    assert entry_refusal("loaded", "in_use", open_facts(load_gate_open=True, load_permit_valid=False)) is not None


def test_struck_needs_the_strike_gate_open():
    assert entry_refusal("approved_to_strike", "struck", open_facts()) is None
    refusal = entry_refusal("approved_to_strike", "struck", open_facts(strike_gate_open=False))
    assert refusal is not None
    assert refusal.rule == t.STRIKE_GATE


def test_resuming_from_hold_into_a_gated_status_is_judged_like_entering_it():
    assert entry_refusal("on_hold", "loaded", open_facts(load_gate_open=False)) is not None
    assert entry_refusal("on_hold", "loaded", open_facts()) is None
    assert entry_refusal("on_hold", "in_use", open_facts()) is None
    assert entry_refusal("on_hold", "in_use", open_facts(load_permit_valid=False)) is not None
    assert entry_refusal("on_hold", "struck", open_facts(strike_gate_open=False)) is not None


def test_going_on_hold_or_a_step_back_is_never_stopped_by_an_entry_check():
    shut = EntryFacts()
    assert entry_refusal("loaded", "on_hold", shut) is None
    assert entry_refusal("in_use", "loaded", shut) is None
    assert entry_refusal("approved_to_load", "design_checked", shut) is None
    assert entry_refusal("struck", "approved_to_strike", shut) is None


@pytest.mark.parametrize("target", ["identified", "design_submitted", "design_checked", "approved_to_strike", "removed"])
def test_statuses_without_a_precondition_are_never_stopped_by_the_facts(target: str):
    assert entry_refusal("design_brief", target, EntryFacts()) is None


# --- the guarded move and the entry check together ----------------------------------------------------------


def test_the_flow_is_checked_before_the_entry_preconditions():
    refusal = plan_item_move("design_checked", "loaded", None, None, EntryFacts())
    assert refusal is not None
    assert refusal.rule == t.ONE_STEP


def test_a_legal_step_with_open_facts_is_allowed_all_the_way_along_the_flow():
    for current, target in PAIRS:
        assert plan_item_move(current, target, None, None, open_facts()) is None, (current, target)


def test_a_legal_step_with_shut_facts_stops_at_the_first_gated_status():
    stopped = [target for current, target in PAIRS if plan_item_move(current, target, None, None, EntryFacts()) is not None]
    assert stopped == ["approved_to_load", "loaded", "in_use", "struck"]


def test_an_unreadable_status_is_refused_by_the_combined_check_too():
    assert plan_item_move(None, "loaded", None, None, open_facts()) is not None
    assert plan_item_move("loaded", 5, None, None, open_facts()) is not None

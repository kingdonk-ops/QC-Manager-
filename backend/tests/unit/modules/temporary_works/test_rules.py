"""Temporary works rules: permit validity, the load and strike gates, the breach test, overdue load and strike, design
clearance, counting and the advisory warnings. Every test pins the as-of day; none reads the clock."""

import ast
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.modules.temporary_works.constants import ITEM_STATUSES, MAIN_FLOW, PermitKind, site_today
from src.modules.temporary_works.rules import (
    bearing_load_warning,
    breach_reason,
    category_counts,
    design_clearance,
    find_breaches,
    is_breach,
    is_compliant,
    lapses_within,
    lapsing_warnings,
    load_gate_open,
    missing_prerequisites,
    overdue_to_load,
    overdue_to_strike,
    permit_valid_on,
    scaffold_state_warning,
    status_counts,
    strike_gate_open,
    valid_permits,
)

TODAY = date(2026, 3, 10)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
PACKAGE = Path(__file__).resolve().parents[4] / "src" / "modules" / "temporary_works"


def permit(
    kind: str = "load",
    status: str = "issued",
    valid_from: Any = TODAY - timedelta(days=7),
    valid_to: Any = TODAY + timedelta(days=7),
    design: Any = True,
    inspection: Any = True,
    number: str = "P-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        status=status,
        valid_from=valid_from,
        valid_to=valid_to,
        design_check_accepted=design,
        inspection_passed=inspection,
        number=number,
    )


def item(status: str, **extra: Any) -> SimpleNamespace:
    values = {"id": 1, "reference": "TW-1", "title": "Slab props", "required_load_on": None, "required_strike_on": None}
    return SimpleNamespace(status=status, **{**values, **extra})


# --- the site day -----------------------------------------------------------------------------------------


def test_the_site_day_is_the_perth_day_not_the_utc_day():
    assert site_today(datetime(2026, 3, 9, 17, 0, tzinfo=UTC)) == date(2026, 3, 10)
    assert site_today(datetime(2026, 3, 9, 15, 59, tzinfo=UTC)) == date(2026, 3, 9)
    assert site_today(datetime(2026, 3, 9, 17, 0)) == date(2026, 3, 10)  # a naive moment is read as UTC


# --- permit validity ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["issued", "active"])
def test_a_live_permit_is_valid_through_its_last_window_day_and_not_the_day_after(status: str):
    p = permit(status=status, valid_to=TODAY)
    assert permit_valid_on(p, TODAY)
    assert not permit_valid_on(p, TOMORROW)


def test_the_window_is_inclusive_at_the_start():
    p = permit(valid_from=TODAY)
    assert permit_valid_on(p, TODAY)
    assert not permit_valid_on(p, YESTERDAY)


def test_a_missing_end_leaves_the_window_open_and_a_missing_start_too():
    assert permit_valid_on(permit(valid_from=YESTERDAY, valid_to=None), TODAY)
    assert not permit_valid_on(permit(valid_from=TOMORROW, valid_to=None), TODAY)
    assert permit_valid_on(permit(valid_from=None, valid_to=TODAY), TODAY)
    assert permit_valid_on(permit(valid_from=None, valid_to=None), TODAY)


@pytest.mark.parametrize("status", ["draft", "expired", "closed", "voided", "", None, 3])
def test_draft_expired_closed_and_unknown_statuses_are_never_valid(status: Any):
    assert not permit_valid_on(permit(status=status), TODAY)


@pytest.mark.parametrize("day", [None, "2026-03-10", 20260310])
def test_an_unreadable_day_is_never_valid(day: Any):
    assert not permit_valid_on(permit(), day)


def test_an_unreadable_window_bound_is_never_valid():
    assert not permit_valid_on(permit(valid_to="2026-03-31"), TODAY)
    assert not permit_valid_on(permit(valid_from="last week"), TODAY)


def test_a_datetime_bound_is_read_as_its_day():
    assert permit_valid_on(permit(valid_to=datetime(2026, 3, 10, 23, 0)), TODAY)


def test_valid_permits_filters_by_kind_and_validity():
    permits = [permit("load"), permit("strike"), permit("load", status="draft"), permit("dismantle")]
    assert len(valid_permits(permits, PermitKind.LOAD, TODAY)) == 1
    assert len(valid_permits(permits, PermitKind.DISMANTLE, TODAY)) == 1


# --- the gates ----------------------------------------------------------------------------------------------


def test_the_load_gate_opens_only_with_a_valid_permit_that_records_both_prerequisites():
    assert load_gate_open([permit()], TODAY)
    assert not load_gate_open([permit(inspection=False)], TODAY)
    assert not load_gate_open([permit(design=False)], TODAY)
    assert not load_gate_open([permit(design=False, inspection=False)], TODAY)
    assert not load_gate_open([permit(status="draft")], TODAY)
    assert not load_gate_open([permit(valid_to=YESTERDAY)], TODAY)
    assert not load_gate_open([], TODAY)


def test_the_two_prerequisites_must_be_on_the_same_permit():
    permits = [permit(design=True, inspection=False, number="A"), permit(design=False, inspection=True, number="B")]
    assert not load_gate_open(permits, TODAY)


@pytest.mark.parametrize("flag", [None, 1, "yes", "true"])
def test_a_prerequisite_flag_counts_only_when_it_is_exactly_true(flag: Any):
    assert not load_gate_open([permit(design=flag)], TODAY)
    assert not load_gate_open([permit(inspection=flag)], TODAY)


def test_a_permit_to_strike_or_dismantle_never_opens_the_load_gate():
    assert not load_gate_open([permit(kind="strike"), permit(kind="dismantle")], TODAY)
    assert not load_gate_open([permit(kind="scaffolding")], TODAY)


def test_only_a_valid_permit_to_strike_opens_the_strike_gate():
    assert not strike_gate_open([permit(kind="dismantle")], TODAY)
    assert strike_gate_open([permit(kind="strike", design=False, inspection=False)], TODAY)
    assert not strike_gate_open([permit(kind="strike", status="draft")], TODAY)
    assert not strike_gate_open([permit(kind="strike", valid_to=YESTERDAY)], TODAY)
    assert not strike_gate_open([permit(kind="load")], TODAY)
    assert not strike_gate_open([], TODAY)


def test_missing_prerequisites_names_each_gap():
    assert missing_prerequisites(permit()) == []
    assert missing_prerequisites(permit(design=False)) == ["design check accepted"]
    assert missing_prerequisites(permit(design=False, inspection=None)) == ["design check accepted", "inspection passed"]


# --- breach -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["loaded", "in_use"])
@pytest.mark.parametrize(
    "permits",
    [
        [],
        [permit(status="draft")],
        [permit(status="expired")],
        [permit(status="closed")],
        [permit(valid_to=YESTERDAY)],
        [permit(valid_from=TOMORROW)],
        [permit(kind="strike")],
        [permit(kind="dismantle")],
    ],
)
def test_loaded_or_in_use_without_a_valid_permit_to_load_is_a_breach(status: str, permits: list[Any]):
    assert is_breach(status, permits, TODAY)


@pytest.mark.parametrize("status", ["loaded", "in_use"])
def test_a_valid_permit_to_load_clears_the_breach_whatever_the_prerequisite_flags(status: str):
    assert not is_breach(status, [permit()], TODAY)
    assert not is_breach(status, [permit(design=False, inspection=False)], TODAY)


@pytest.mark.parametrize(
    "status",
    ["identified", "design_checked", "approved_to_load", "approved_to_strike", "struck", "on_hold", "bogus", None],
)
def test_other_statuses_are_never_a_breach_whatever_their_permits(status: Any):
    assert not is_breach(status, [], TODAY)


def test_the_breach_reason_names_the_status_and_the_date():
    reason = breach_reason("in_use", TODAY)
    assert "in use" in reason
    assert "2026-03-10" in reason


def test_the_register_lists_each_breach_and_is_compliant_only_without_any():
    items = [
        item("in_use", id=1, reference="TW-1", title="Props"),
        item("approved_to_load", id=2, reference="TW-2"),
        item("loaded", id=3, reference="TW-3"),
        item("loaded", id=4, reference="TW-4"),
    ]
    permits = {3: [permit()], 1: [permit(status="draft")]}
    breaches = find_breaches(items, permits, TODAY)
    assert [(b.item_id, b.reference, b.title) for b in breaches] == [(1, "TW-1", "Props"), (4, "TW-4", "Slab props")]
    assert all("2026-03-10" in b.reason for b in breaches)
    assert not is_compliant(breaches)
    assert is_compliant(find_breaches(items[1:3], permits, TODAY))
    assert is_compliant([])


def test_a_permit_that_lapses_makes_a_loaded_item_a_breach_on_the_later_day_only():
    permits = {1: [permit(valid_to=TODAY)]}
    loaded = [item("loaded")]
    assert find_breaches(loaded, permits, TODAY) == []
    assert len(find_breaches(loaded, permits, TOMORROW)) == 1


# --- overdue ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("identified", True),
        ("design_brief", True),
        ("design_submitted", True),
        ("design_checked", True),
        ("approved_to_load", True),
        ("loaded", False),
        ("in_use", False),
        ("approved_to_strike", False),
        ("struck", False),
        ("removed", False),
        ("on_hold", False),
    ],
)
def test_overdue_to_load_holds_until_the_item_is_loaded_and_never_on_hold(status: str, expected: bool):
    assert overdue_to_load(item(status, required_load_on=YESTERDAY), TODAY) is expected


def test_overdue_to_load_needs_a_date_strictly_before_the_day():
    assert not overdue_to_load(item("design_checked", required_load_on=TODAY), TODAY)
    assert not overdue_to_load(item("design_checked", required_load_on=TOMORROW), TODAY)
    assert not overdue_to_load(item("design_checked", required_load_on=None), TODAY)
    assert not overdue_to_load(item("design_checked", required_load_on=YESTERDAY), None)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("identified", False),
        ("design_checked", False),
        ("approved_to_load", False),
        ("loaded", True),
        ("in_use", True),
        ("approved_to_strike", True),
        ("struck", False),
        ("removed", False),
        ("on_hold", False),
    ],
)
def test_overdue_to_strike_follows_the_recommended_status_set(status: str, expected: bool):
    assert overdue_to_strike(item(status, required_strike_on=YESTERDAY), TODAY) is expected


def test_overdue_to_strike_needs_a_date_strictly_before_the_day():
    assert not overdue_to_strike(item("in_use", required_strike_on=TODAY), TODAY)
    assert not overdue_to_strike(item("in_use", required_strike_on=None), TODAY)


# --- clearance ----------------------------------------------------------------------------------------------


def test_clearance_counts_design_checked_and_later_and_leaves_on_hold_out():
    assert design_clearance(["identified", "design_checked", "loaded", "on_hold"]) == Decimal("50.00")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["design_checked", "identified", "identified"], "33.33"),
        (["design_checked", "removed", "identified"], "66.67"),
        (["design_checked", "identified"], "50.00"),
        (["design_checked"], "100.00"),
        (["identified"], "0.00"),
    ],
)
def test_clearance_rounds_to_two_decimals(statuses: list[str], expected: str):
    result = design_clearance(statuses)
    assert result == Decimal(expected)
    assert str(result) == expected


def test_clearance_rounds_half_up_not_to_even():
    statuses = ["design_checked"] + ["identified"] * 31  # 1 of 32 is exactly 3.125
    assert str(design_clearance(statuses)) == "3.13"


def test_an_empty_register_has_no_clearance_figure_rather_than_zero():
    assert design_clearance([]) is None


def test_an_out_of_vocabulary_status_counts_in_the_total_but_never_as_cleared():
    assert design_clearance(["design_checked", "mystery"]) == Decimal("50.00")


# --- counting -----------------------------------------------------------------------------------------------


def test_status_counts_list_every_status_with_zeros_and_sum_to_the_total():
    counts = status_counts(["identified", "loaded", "loaded", "on_hold"])
    assert list(counts) == list(ITEM_STATUSES)
    assert len(counts) == 11
    assert counts["loaded"] == 2
    assert counts["removed"] == 0
    assert sum(counts.values()) == 4


def test_a_stray_status_is_counted_and_never_dropped():
    counts = status_counts(["identified", "mystery", None, ""])
    assert counts["mystery"] == 1
    assert counts["unknown"] == 2
    assert sum(counts.values()) == 4
    assert all(counts[s] == 0 for s in MAIN_FLOW if s != "identified")


def test_category_counts_zero_fill_zero_to_three_and_unassigned():
    counts = category_counts([1, 3, None])
    assert counts == {"0": 0, "1": 1, "2": 0, "3": 1, "unassigned": 1}
    assert sum(counts.values()) == 3


def test_a_stray_category_is_counted_under_its_own_key():
    counts = category_counts([1, 7, "x", None])
    assert counts["7"] == 1
    assert counts["x"] == 1
    assert sum(counts.values()) == 4


def test_an_empty_register_counts_to_zero_everywhere():
    assert sum(status_counts([]).values()) == 0
    assert category_counts([]) == {"0": 0, "1": 0, "2": 0, "3": 0, "unassigned": 0}


# --- advisory warnings --------------------------------------------------------------------------------------


def test_bearing_load_under_a_valid_permit_missing_a_prerequisite_warns_but_is_not_a_breach():
    loaded = item("loaded")
    permits = [permit(inspection=False)]
    warning = bearing_load_warning(loaded, permits, TODAY)
    assert warning is not None
    assert warning.rule == "prerequisites-missing"
    assert "inspection passed" in warning.message
    assert "TW-1" in warning.message
    assert not is_breach("loaded", permits, TODAY)


def test_no_prerequisite_warning_when_the_gate_is_open_or_the_item_is_not_bearing_load_or_is_a_breach():
    assert bearing_load_warning(item("in_use"), [permit()], TODAY) is None
    assert bearing_load_warning(item("approved_to_load"), [permit(inspection=False)], TODAY) is None
    assert bearing_load_warning(item("loaded"), [permit(status="draft", inspection=False)], TODAY) is None
    assert bearing_load_warning(item("loaded"), [], TODAY) is None


def test_another_valid_permit_with_both_prerequisites_silences_the_warning():
    permits = [permit(inspection=False, number="A"), permit(number="B")]
    assert bearing_load_warning(item("loaded"), permits, TODAY) is None


@pytest.mark.parametrize(("days", "expected"), [(0, True), (1, True), (3, True), (4, False), (-1, False)])
def test_a_live_permit_lapsing_within_three_days_is_flagged(days: int, expected: bool):
    p = permit(valid_to=TODAY + timedelta(days=days))
    assert lapses_within(p, TODAY) is expected
    assert bool(lapsing_warnings(item("in_use"), [p], TODAY)) is expected


def test_only_live_permits_with_an_end_day_can_be_lapsing():
    assert not lapses_within(permit(status="draft", valid_to=TOMORROW), TODAY)
    assert not lapses_within(permit(status="closed", valid_to=TOMORROW), TODAY)
    assert not lapses_within(permit(valid_to=None), TODAY)


def test_the_lapsing_warning_names_the_permit_and_its_last_day():
    [warning] = lapsing_warnings(item("in_use"), [permit(valid_to=TOMORROW, number="PL-9")], TODAY)
    assert warning.rule == "permit-lapsing"
    assert "PL-9" in warning.message
    assert "2026-03-11" in warning.message


@pytest.mark.parametrize("tag", ["green", "yellow"])
def test_a_usable_scaffold_with_an_inspection_up_to_date_gives_no_warning(tag: str):
    assert scaffold_state_warning(item("loaded"), tag, False) is None


@pytest.mark.parametrize(
    ("tag", "overdue"),
    [("red", False), ("none", False), (None, False), ("green", True), ("yellow", True), ("green", None), ("blue", False)],
)
def test_a_scaffold_that_is_not_usable_or_not_inspected_in_time_warns(tag: Any, overdue: Any):
    warning = scaffold_state_warning(item("loaded"), tag, overdue)
    assert warning is not None
    assert warning.rule == "scaffold-not-usable"
    assert "TW-1" in warning.message


# --- the files stay pure ------------------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("name", ["rules.py", "validation.py", "transitions.py", "constants.py"])
def test_the_pure_files_import_neither_the_web_framework_nor_the_database_layer(name: str):
    imported = _imported_modules(PACKAGE / name)
    forbidden = ("fastapi", "starlette", "sqlalchemy", "pydantic", "src")
    assert not [m for m in imported if m.split(".")[0] in forbidden or m.startswith("..")]


@pytest.mark.parametrize(
    "name", ["constants.py", "permissions.py", "manifest.py", "models.py", "rules.py", "validation.py", "transitions.py"]
)
def test_the_foundation_files_do_not_import_the_scaffolds_module(name: str):
    assert not [m for m in _imported_modules(PACKAGE / name) if "scaffolds" in m]

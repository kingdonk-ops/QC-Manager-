"""Temporary works validation: the independent check, the coordinator rule, date order on items and permits, the
prerequisites of a live permit to load, and the decision whether an update revalidates at all."""

from datetime import date
from typing import Any

import pytest

from src.modules.temporary_works.validation import (
    CLOSED_BEFORE_ISSUED,
    COORDINATOR,
    INDEPENDENT_CHECK,
    ITEM_RULE_FIELDS,
    LATE_DESIGN_DUE,
    LOAD_PREREQUISITE_DESIGN,
    LOAD_PREREQUISITE_INSPECTION,
    PERMIT_RULE_FIELDS,
    STRIKE_BEFORE_LOAD,
    VALID_TO_BEFORE_FROM,
    merged,
    rules_apply,
    validate_item,
    validate_permit,
)


def checked_item(**extra: Any) -> dict[str, Any]:
    base = {"status": "design_checked", "design_check_category": 2, "designer": "Dana Lee", "checker": "Sam Ortiz"}
    return {**base, "coordinator_name": "Pat Kerr", **extra}


def rules_of(findings: list[Any]) -> list[str]:
    return [f.rule for f in findings]


# --- the independent check ----------------------------------------------------------------------------------


@pytest.mark.parametrize("category", [2, 3])
@pytest.mark.parametrize("checker", ["dana lee", "  DANA LEE  ", "Dana Lee", "", "   ", None])
def test_a_category_two_or_three_item_at_design_checked_needs_a_checker_other_than_the_designer(category: int, checker: Any):
    result = validate_item(checked_item(design_check_category=category, checker=checker))
    assert rules_of(result.errors) == [INDEPENDENT_CHECK]
    assert not result.ok


@pytest.mark.parametrize("category", [2, 3])
def test_a_different_checker_is_accepted(category: int):
    assert validate_item(checked_item(design_check_category=category)).ok


@pytest.mark.parametrize("category", [0, 1, None])
def test_categories_zero_one_and_unassigned_are_not_subject_to_the_rule(category: Any):
    assert validate_item(checked_item(design_check_category=category, checker="Dana Lee")).ok
    assert validate_item(checked_item(design_check_category=category, checker=None)).ok


@pytest.mark.parametrize("status", ["identified", "design_brief", "design_submitted"])
def test_earlier_statuses_are_not_subject_to_the_rule(status: str):
    assert validate_item(checked_item(status=status, checker="dana lee")).ok


@pytest.mark.parametrize("status", ["design_checked", "approved_to_load", "loaded", "in_use", "approved_to_strike"])
def test_the_rule_holds_from_design_checked_through_approved_to_strike(status: str):
    assert rules_of(validate_item(checked_item(status=status, checker="DANA LEE")).errors) == [INDEPENDENT_CHECK]


@pytest.mark.parametrize("status", ["struck", "removed", "on_hold"])
def test_the_rule_does_not_reach_struck_removed_or_on_hold(status: str):
    assert validate_item(checked_item(status=status, checker="DANA LEE")).ok


def test_a_missing_designer_does_not_excuse_a_missing_checker():
    result = validate_item(checked_item(designer=None, checker=None))
    assert rules_of(result.errors) == [INDEPENDENT_CHECK]


def test_a_named_checker_with_no_designer_is_accepted():
    assert validate_item(checked_item(designer=None, checker="Sam Ortiz")).ok


@pytest.mark.parametrize("category", [True, "2", 2.0])
def test_a_category_that_is_not_a_whole_number_is_not_read_as_two_or_three(category: Any):
    assert validate_item(checked_item(design_check_category=category, checker=None)).ok


# --- the coordinator ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["approved_to_load", "loaded", "in_use", "approved_to_strike"])
def test_a_coordinator_is_needed_from_approved_to_load_through_approved_to_strike(status: str):
    result = validate_item({"status": status, "design_check_category": 1})
    assert rules_of(result.errors) == [COORDINATOR]


@pytest.mark.parametrize("status", ["identified", "design_brief", "design_submitted", "design_checked", "struck", "removed"])
def test_no_coordinator_is_needed_outside_that_span(status: str):
    assert validate_item({"status": status, "design_check_category": 1}).ok


def test_a_coordinator_name_or_a_coordinator_user_satisfies_the_rule():
    assert validate_item({"status": "approved_to_load", "coordinator_name": "Pat Kerr"}).ok
    assert validate_item({"status": "approved_to_load", "coordinator_user_id": 12}).ok
    assert not validate_item({"status": "approved_to_load", "coordinator_name": "  "}).ok
    assert not validate_item({"status": "approved_to_load", "coordinator_name": "", "coordinator_user_id": None}).ok


# --- dates on items -----------------------------------------------------------------------------------------


def test_a_required_strike_before_the_required_load_is_an_error():
    values = {"status": "identified", "required_load_on": date(2026, 3, 10), "required_strike_on": date(2026, 3, 1)}
    assert rules_of(validate_item(values).errors) == [STRIKE_BEFORE_LOAD]


def test_strike_on_or_after_load_is_accepted():
    same = validate_item({"required_load_on": date(2026, 3, 10), "required_strike_on": date(2026, 3, 10)})
    later = validate_item({"required_load_on": date(2026, 3, 10), "required_strike_on": date(2026, 4, 1)})
    assert same.ok
    assert later.ok


def test_a_design_due_after_the_required_load_is_only_a_warning():
    result = validate_item({"status": "identified", "required_load_on": date(2026, 3, 10), "design_due_on": date(2026, 3, 15)})
    assert result.ok
    assert result.errors == []
    assert rules_of(result.warnings) == [LATE_DESIGN_DUE]


def test_a_design_due_on_the_load_day_gives_no_warning():
    result = validate_item({"required_load_on": date(2026, 3, 10), "design_due_on": date(2026, 3, 10)})
    assert result.warnings == []


def test_missing_dates_never_trigger_a_date_rule():
    assert validate_item({"required_strike_on": date(2026, 3, 1)}) == ([], [])
    assert validate_item({"required_load_on": date(2026, 3, 1)}) == ([], [])
    assert validate_item({"design_due_on": date(2026, 3, 1)}) == ([], [])


def test_errors_and_warnings_come_back_together():
    result = validate_item(
        checked_item(
            checker=None,
            required_load_on=date(2026, 3, 10),
            required_strike_on=date(2026, 3, 1),
            design_due_on=date(2026, 3, 12),
        )
    )
    assert sorted(rules_of(result.errors)) == sorted([INDEPENDENT_CHECK, STRIKE_BEFORE_LOAD])
    assert rules_of(result.warnings) == [LATE_DESIGN_DUE]


# --- permits ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["issued", "active"])
def test_a_live_permit_to_load_with_neither_prerequisite_has_one_error_per_missing_flag(status: str):
    result = validate_permit({"kind": "load", "status": status, "design_check_accepted": False, "inspection_passed": False})
    assert rules_of(result.errors) == [LOAD_PREREQUISITE_DESIGN, LOAD_PREREQUISITE_INSPECTION]


def test_one_missing_flag_gives_one_error():
    only_design = validate_permit({"kind": "load", "status": "issued", "design_check_accepted": True})
    assert rules_of(only_design.errors) == [LOAD_PREREQUISITE_INSPECTION]
    only_inspection = validate_permit({"kind": "load", "status": "active", "inspection_passed": True})
    assert rules_of(only_inspection.errors) == [LOAD_PREREQUISITE_DESIGN]


def test_both_flags_recorded_gives_no_error():
    assert validate_permit({"kind": "load", "status": "issued", "design_check_accepted": True, "inspection_passed": True}).ok


@pytest.mark.parametrize("status", ["draft", "expired", "closed"])
def test_a_permit_to_load_that_is_not_live_carries_no_prerequisite_error(status: str):
    assert validate_permit({"kind": "load", "status": status}).ok


@pytest.mark.parametrize("kind", ["strike", "dismantle"])
def test_a_permit_to_strike_or_dismantle_needs_no_prerequisites(kind: str):
    assert validate_permit({"kind": kind, "status": "issued", "design_check_accepted": False, "inspection_passed": False}).ok


def test_a_valid_to_before_valid_from_is_an_error():
    values = {"kind": "strike", "status": "draft", "valid_from": date(2026, 3, 10), "valid_to": date(2026, 3, 9)}
    assert rules_of(validate_permit(values).errors) == [VALID_TO_BEFORE_FROM]


def test_a_one_day_window_is_accepted():
    assert validate_permit({"valid_from": date(2026, 3, 10), "valid_to": date(2026, 3, 10)}).ok


def test_a_closed_day_before_the_issued_day_is_an_error():
    values = {"kind": "strike", "status": "closed", "issued_on": date(2026, 3, 10), "closed_on": date(2026, 3, 9)}
    assert rules_of(validate_permit(values).errors) == [CLOSED_BEFORE_ISSUED]
    assert validate_permit({"issued_on": date(2026, 3, 10), "closed_on": date(2026, 3, 10)}).ok


def test_permits_never_have_warnings():
    assert validate_permit({"kind": "load", "status": "draft"}).warnings == []


# --- whether an update revalidates ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(ITEM_RULE_FIELDS))
def test_every_rule_relevant_item_field_triggers_revalidation(field: str):
    assert rules_apply({field: None}, ITEM_RULE_FIELDS)


@pytest.mark.parametrize("field", sorted(PERMIT_RULE_FIELDS))
def test_every_rule_relevant_permit_field_triggers_revalidation(field: str):
    assert rules_apply({field: None}, PERMIT_RULE_FIELDS)


def test_an_update_touching_only_notes_title_or_location_runs_no_rules():
    assert not rules_apply({"notes": "see drawing", "title": "Props", "location": "Level 2"}, ITEM_RULE_FIELDS)
    assert not rules_apply({"conditions": "no more than 3 kPa"}, PERMIT_RULE_FIELDS)
    assert not rules_apply({}, ITEM_RULE_FIELDS)


def test_the_two_field_sets_cover_the_fields_the_rules_read():
    people = {"status", "design_check_category", "designer", "checker", "coordinator_name", "coordinator_user_id"}
    assert people <= ITEM_RULE_FIELDS
    assert {"required_load_on", "required_strike_on", "design_due_on"} <= ITEM_RULE_FIELDS
    permit_fields = {"kind", "status", "valid_from", "valid_to", "closed_on", "design_check_accepted", "inspection_passed"}
    assert permit_fields <= PERMIT_RULE_FIELDS


def test_an_update_is_judged_on_the_stored_record_merged_with_the_change():
    stored = checked_item(checker="Sam Ortiz")
    assert validate_item(merged(stored, {"notes": "x"})).ok
    changed = merged(stored, {"checker": "dana lee"})
    assert rules_of(validate_item(changed).errors) == [INDEPENDENT_CHECK]
    assert stored["checker"] == "Sam Ortiz"  # the stored record itself is untouched
    assert validate_item(merged(stored, {"checker": None, "design_check_category": 1})).ok


def test_a_stored_record_that_would_now_fail_is_not_judged_when_only_notes_change():
    stored = checked_item(checker="dana lee")  # stored in a state that fails the rule
    changes = {"notes": "updated"}
    assert not validate_item(stored).ok
    assert not rules_apply(changes, ITEM_RULE_FIELDS)  # so the caller never runs the rules for this update

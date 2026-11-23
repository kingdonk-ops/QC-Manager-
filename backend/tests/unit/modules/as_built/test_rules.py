"""As-built rules: tolerance result, status flow, ordinary-edit refusals, action preconditions, the attestation digest
and the report context lines."""

import re
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from src.modules.as_built.constants import ACTION_FOR, DELETABLE, FLOW, AsBuiltStatus
from src.modules.as_built.rules import (
    CLIENT_ERROR,
    CONFLICT,
    allowed_transitions,
    attestation_digest,
    attestation_snapshot,
    deletion_error,
    edit_refusal,
    report_lines,
    sign_error,
    survey_error,
    tolerance_result,
    verify_error,
)

STATUSES = [s.value for s in AsBuiltStatus]


def _criterion(rule: str, lower: str | None = None, upper: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(rule_type=rule, lower_limit=lower, upper_limit=upper)


# --- tolerance result ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("measured", "expected"), [("360", "within"), ("355", "within"), ("320", "out_of_tolerance")])
def test_a_minimum_criterion_judges_inclusively(measured: str, expected: str):
    assert tolerance_result(_criterion("minimum", lower="355"), measured) == expected


@pytest.mark.parametrize(("measured", "expected"), [("50", "within"), ("60", "out_of_tolerance")])
def test_a_maximum_criterion_judges_inclusively(measured: str, expected: str):
    assert tolerance_result(_criterion("maximum", upper="50"), measured) == expected


@pytest.mark.parametrize(
    ("lower", "upper", "measured", "expected"),
    [
        ("10", "20", "10", "within"),
        ("10", "20", "20", "within"),
        ("10", "20", "9.99", "out_of_tolerance"),
        ("10", "20", "20.01", "out_of_tolerance"),
        ("10", "20", "21", "out_of_tolerance"),
        ("-2.5", "2.5", "-1.25", "within"),
        ("-2.5", "2.5", "-3", "out_of_tolerance"),
    ],
)
def test_a_range_criterion_is_inclusive_on_both_ends_and_handles_negatives_and_decimals(
    lower: str, upper: str, measured: str, expected: str
):
    assert tolerance_result(_criterion("range", lower, upper), measured) == expected


@pytest.mark.parametrize(
    "criterion",
    [
        None,
        _criterion("free_text"),
        _criterion("boolean"),
        _criterion("minimum"),
        _criterion("maximum", lower="1"),
        _criterion("range", lower="10"),
    ],
)
def test_what_cannot_be_decided_is_never_conforming(criterion: Any):
    assert tolerance_result(criterion, "15") == "not_assessed"


@pytest.mark.parametrize("measured", ["15 mm", "abc", "", None, "1,5", "1e3"])
def test_a_value_that_is_not_a_plain_decimal_is_not_assessed(measured: str | None):
    assert tolerance_result(_criterion("range", "10", "20"), measured) == "not_assessed"


def test_there_is_no_unit_conversion():
    assert tolerance_result(_criterion("range", "10", "20"), "0.015") == "out_of_tolerance"


# --- the flow --------------------------------------------------------------------------------------------


def test_the_allowed_transitions_are_exactly_the_flow():
    assert {s: allowed_transitions(s) for s in STATUSES} == {
        "draft": {"surveyed", "void"},
        "surveyed": {"verified", "void"},
        "verified": {"recorded", "superseded"},
        "recorded": set(),
        "superseded": set(),
        "void": set(),
    }
    assert set(FLOW) == set(STATUSES)
    assert ACTION_FOR == {"surveyed": "survey", "verified": "verify", "recorded": "sign"}


@pytest.mark.parametrize("status", STATUSES)
def test_the_actions_need_exactly_their_status(status: str):
    assert (survey_error(status) is None) is (status in ("draft", "surveyed"))
    assert (verify_error(status) is None) is (status == "surveyed")
    assert (sign_error(status) is None) is (status == "verified")


def test_an_action_refusal_names_the_current_status_and_the_required_step():
    assert "draft" in (verify_error("draft") or "") and "survey" in (verify_error("draft") or "")
    assert "surveyed" in (sign_error("surveyed") or "") and "verified" in (sign_error("surveyed") or "")
    assert "recorded" in (survey_error("recorded") or "")


# --- ordinary edits --------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["recorded", "void"])
def test_a_recorded_or_void_record_cannot_be_edited_at_all(status: str):
    refusal = edit_refusal(status, {"title": "New"}, {"title": "Old"})
    assert refusal is not None and refusal.kind == CLIENT_ERROR and status in refusal.message


@pytest.mark.parametrize(("current", "target"), [("draft", "surveyed"), ("draft", "verified"), ("surveyed", "verified")])
def test_an_edit_never_sets_surveyed_or_verified(current: str, target: str):
    refusal = edit_refusal(current, {"status": target}, {"status": current})
    assert refusal is not None and refusal.kind == CONFLICT
    assert ACTION_FOR[target] in refusal.message


def test_an_edit_never_sets_recorded():
    refusal = edit_refusal("verified", {"status": "recorded"}, {"status": "verified"})
    assert refusal is not None and refusal.kind == CONFLICT and "sign" in refusal.message


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "void"),
        ("surveyed", "void"),
        ("verified", "superseded"),
    ],
)
def test_an_edit_may_void_an_unjudged_record_and_supersede_a_verified_one(current: str, target: str):
    assert edit_refusal(current, {"status": target}, {"status": current}) is None


@pytest.mark.parametrize(
    ("current", "target"),
    [("verified", "void"), ("verified", "draft"), ("superseded", "draft"), ("superseded", "void"), ("surveyed", "draft")],
)
def test_a_verified_or_superseded_record_moves_nowhere_but_to_superseded(current: str, target: str):
    refusal = edit_refusal(current, {"status": target}, {"status": current})
    assert refusal is not None and refusal.kind == CLIENT_ERROR


def test_a_draft_record_can_change_its_measured_value_and_criterion_by_edit():
    stored = {"measured_value": "10", "criterion_id": 1, "title": "Slab"}
    assert edit_refusal("draft", {"measured_value": "12", "criterion_id": 2, "title": "Slab 2"}, stored) is None


@pytest.mark.parametrize("changes", [{"measured_value": "12"}, {"criterion_id": 9}])
def test_after_a_survey_the_measured_value_and_criterion_change_only_by_a_new_survey(changes: dict[str, Any]):
    stored = {"measured_value": "10", "criterion_id": 1}
    refusal = edit_refusal("surveyed", changes, stored)
    assert refusal is not None and refusal.kind == CONFLICT and "survey" in refusal.message


def test_re_sending_a_stored_value_is_not_a_change():
    stored = {"measured_value": "10", "criterion_id": 1, "title": "Slab"}
    assert edit_refusal("surveyed", {"measured_value": "10", "criterion_id": 1, "title": "Slab edge"}, stored) is None


def test_a_verified_record_is_never_rewritten_but_can_be_superseded():
    stored = {"title": "Slab", "status": "verified"}
    refusal = edit_refusal("verified", {"title": "Slab 2"}, stored)
    assert refusal is not None and refusal.kind == CONFLICT and "Supersede" in refusal.message
    assert edit_refusal("verified", {"status": "superseded", "title": "Slab 2"}, stored) is not None
    assert edit_refusal("verified", {"status": "superseded"}, stored) is None
    assert edit_refusal("verified", {"status": "verified", "title": "Slab"}, stored) is None


def test_a_superseded_record_is_not_rewritten_either():
    refusal = edit_refusal("superseded", {"location": "Bay 4"}, {"location": "Bay 3"})
    assert refusal is not None and refusal.kind == CONFLICT


# --- deletion --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", STATUSES)
def test_deleting_is_refused_from_verified_onward(status: str):
    assert (deletion_error(status) is None) is (status in DELETABLE)
    assert set(DELETABLE) == {"draft", "surveyed", "void"}
    if status in ("verified", "recorded", "superseded"):
        assert status in (deletion_error(status) or "")


# --- the attestation digest ------------------------------------------------------------------------------


def _record(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": 7,
        "number": "ASB-001",
        "title": "Slab level",
        "capture_method": "total_station",
        "instrument": "TS-16",
        "calibration_ref": "CAL-9",
        "coordinate_system": "Local grid",
        "surveyed_on": date(2026, 11, 20),
        "surveyed_by_id": 3,
        "accuracy_class": "survey",
        "accuracy_value": "2",
        "accuracy_unit": "mm",
        "criterion_id": 4,
        "measured_value": "360",
        "tolerance_result": "within",
        "deviation_value": None,
    }
    return SimpleNamespace(**{**base, **over})


def test_the_snapshot_holds_identity_capture_accuracy_criterion_value_result_decision_and_signer():
    snapshot = attestation_snapshot(_record(), valid=True, signer_id=11)
    assert snapshot == {
        "id": 7,
        "number": "ASB-001",
        "title": "Slab level",
        "capture": ["total_station", "TS-16", "CAL-9", "Local grid", "2026-11-20", 3],
        "accuracy": ["survey", "2", "mm"],
        "criterion_id": 4,
        "measured_value": "360",
        "tolerance_result": "within",
        "valid": True,
        "signer_id": 11,
    }


def test_the_digest_is_64_hexadecimal_characters_and_does_not_depend_on_key_order():
    snapshot = attestation_snapshot(_record(), valid=True, signer_id=11)
    reordered = dict(reversed(list(snapshot.items())))
    assert list(reordered) != list(snapshot)
    assert re.fullmatch(r"[0-9a-f]{64}", attestation_digest(snapshot))
    assert attestation_digest(reordered) == attestation_digest(snapshot)


def test_the_digest_changes_when_any_covered_field_changes():
    base = attestation_digest(attestation_snapshot(_record(), valid=True, signer_id=11))
    changed = [
        attestation_snapshot(_record(tolerance_result="out_of_tolerance"), valid=True, signer_id=11),
        attestation_snapshot(_record(measured_value="361"), valid=True, signer_id=11),
        attestation_snapshot(_record(criterion_id=5), valid=True, signer_id=11),
        attestation_snapshot(_record(instrument="TS-17"), valid=True, signer_id=11),
        attestation_snapshot(_record(accuracy_value="3"), valid=True, signer_id=11),
        attestation_snapshot(_record(), valid=False, signer_id=11),
        attestation_snapshot(_record(), valid=True, signer_id=12),
    ]
    digests = {attestation_digest(s) for s in changed}
    assert base not in digests and len(digests) == len(changed)


def test_an_undated_survey_is_a_null_date_in_the_snapshot():
    assert attestation_snapshot(_record(surveyed_on=None), valid=True, signer_id=1)["capture"][4] is None


# --- the report lines ------------------------------------------------------------------------------------


def test_the_report_names_capture_method_instrument_accuracy_deviation_and_verifier_notes():
    lines = report_lines(_record(deviation_value="12"), "  Re-measure after grouting  ")
    assert lines == [
        "Capture method: total station.",
        "Instrument: TS-16.",
        "Accuracy class: survey, value 2 mm.",
        "Deviation value: 12.",
        "Verifier notes: Re-measure after grouting",
    ]


def test_the_report_leaves_out_what_the_record_does_not_have():
    bare = _record(instrument=None, accuracy_value=None, accuracy_unit=None, deviation_value=None)
    assert report_lines(bare) == ["Capture method: total station.", "Accuracy class: survey."]
    assert report_lines(bare, "   ") == ["Capture method: total station.", "Accuracy class: survey."]

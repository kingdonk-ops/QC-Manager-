"""Automatic report wording: title, description, structured source data and default severities."""

from src.modules.inspections.ncr_text import (
    DESCRIPTION_MAX,
    TITLE_MAX,
    default_severity,
    description,
    event_title,
    source_data,
)
from src.modules.inspections.tolerance import clause


def test_title_names_the_event_the_number_and_the_title_and_is_bounded():
    title = event_title("inspection_failed", "INS-007", "Cladding laps")
    assert title == "Failed inspection INS-007 Cladding laps"
    assert event_title("material_rejected", "REC-1", "x" * 1000).startswith("Rejected material REC-1 x")
    assert len(event_title("item_failed", "INS-1 #2", "y" * 1000)) == TITLE_MAX


def test_description_states_it_was_raised_automatically_and_keeps_the_record_text():
    text = description(
        source_label="inspection",
        number="INS-007",
        record_description="Lap check on rack 3",
        result_notes="Laps open upward",
        context=["Supplier: Acme", ""],
        clause="Criterion C-1 - Overlap.",
    )
    lines = text.split("\n")
    assert lines[0] == "Raised automatically from inspection INS-007."
    assert lines[1] == "Lap check on rack 3"
    assert lines[2] == "Result notes: Laps open upward"
    assert lines[3] == "Supplier: Acme"
    assert lines[-1] == "Criterion C-1 - Overlap."
    assert len(lines) == 5


def test_description_quotes_the_criterion_and_measured_value_through_the_clause():
    quoted = clause("WT-1", "Wall thickness", upper="50", measured="60")
    text = description(source_label="inspection", number="INS-1", clause=quoted)
    assert "WT-1" in text and "Wall thickness" in text
    assert "inclusive upper bound 50" in text and "Measured value: 60." in text


def test_without_a_criterion_the_description_has_no_tolerance_wording_and_data_keeps_the_value():
    text = description(source_label="inspection", number="INS-2", record_description="Gap too wide")
    assert "Criterion" not in text and "Tolerance" not in text and "Measured value" not in text
    data = source_data(
        source_kind="inspection", record_id=5, number="INS-2", outcome="fail", criterion_id=None, measured_value=7
    )
    assert data["measured_value"] == "7" and data["criterion_id"] is None and data["automatic"] is True


def test_description_is_bounded():
    assert len(description(source_label="inspection", number="INS-3", record_description="z" * 10000)) == DESCRIPTION_MAX


def test_source_data_carries_identity_outcome_and_extra_facts():
    data = source_data(
        source_kind="material_receipt",
        record_id=9,
        number="REC-9",
        outcome="conditional",
        criterion_id=3,
        measured_value=None,
        report_kind="material",
        heat_number="H-1",
    )
    assert data == {
        "automatic": True,
        "source_kind": "material_receipt",
        "record_id": 9,
        "record_number": "REC-9",
        "outcome": "conditional",
        "criterion_id": 3,
        "measured_value": None,
        "report_kind": "material",
        "heat_number": "H-1",
    }


def test_severity_defaults_fail_to_major_and_conditional_to_minor():
    assert default_severity("fail") == "major"
    assert default_severity("conditional") == "minor"
    assert default_severity("pass") == "minor"

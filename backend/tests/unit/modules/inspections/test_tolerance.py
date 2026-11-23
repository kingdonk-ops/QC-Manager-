"""Tolerance rules: exact-decimal, inclusive verdicts, range-order validation and the criterion clause."""

from types import SimpleNamespace

import pytest

from src.modules.inspections.constants import ToleranceResult
from src.modules.inspections.tolerance import (
    SWAP_MESSAGE,
    clause,
    criterion_clause,
    judge,
    judge_criterion,
    parse_decimal,
    range_order_error,
)

WITHIN = ToleranceResult.WITHIN
OUT = ToleranceResult.OUT_OF_TOLERANCE
NOT_ASSESSED = ToleranceResult.NOT_ASSESSED


@pytest.mark.parametrize(
    ("measured", "expected"),
    [("10", WITHIN), ("20", WITHIN), ("9.99", OUT), ("20.01", OUT), ("15", WITHIN)],
)
def test_range_boundaries_are_inclusive(measured: str, expected: ToleranceResult):
    assert judge("range", "10", "20", measured) == expected


def test_maximum_and_negative_range():
    assert judge("maximum", None, "50", "50") == WITHIN
    assert judge("maximum", None, "50", "60") == OUT
    assert judge("range", "-2.5", "2.5", "-1.25") == WITHIN
    assert judge("range", "-2.5", "2.5", "-3") == OUT


@pytest.mark.parametrize(("measured", "expected"), [("360", WITHIN), ("355", WITHIN), ("320", OUT)])
def test_minimum_uses_only_the_lower_limit(measured: str, expected: ToleranceResult):
    assert judge("minimum", "355", "10", measured) == expected


def test_undecidable_cases_are_never_conforming():
    assert judge_criterion(None, "5") == NOT_ASSESSED
    assert judge("free_text", "1", "2", "1.5") == NOT_ASSESSED
    assert judge("boolean", "1", "2", "1.5") == NOT_ASSESSED
    assert judge(None, "1", "2", "1.5") == NOT_ASSESSED
    assert judge("minimum", None, None, "5") == NOT_ASSESSED
    assert judge("maximum", "1", None, "5") == NOT_ASSESSED
    assert judge("range", "10", None, "15") == NOT_ASSESSED
    assert judge("range", "ten", "20", "15") == NOT_ASSESSED
    assert judge("range", "10", "20", None) == NOT_ASSESSED


@pytest.mark.parametrize("text", ["15 mm", "1,5", "1e3", "", "abc", ".", "0x10", "--1"])
def test_measured_text_must_be_a_plain_decimal(text: str):
    assert parse_decimal(text) is None
    assert judge("range", "10", "20", text) == NOT_ASSESSED


def test_no_unit_conversion_between_value_and_limits():
    # 0.015 (metres, say) against millimetre limits is simply out of tolerance
    assert judge("range", "10", "20", "0.015") == OUT


def test_exact_decimal_comparison_has_no_float_error():
    assert judge("maximum", None, "0.3", "0.30000000000000004") == OUT
    assert judge("range", "0.1", "0.3", "0.3") == WITHIN


def test_judge_criterion_reads_the_criterion_fields():
    crit = SimpleNamespace(rule_type="range", lower_limit="50", upper_limit="55")
    assert judge_criterion(crit, "52") == WITHIN
    assert judge_criterion(crit, "48") == OUT


def test_range_order_validation_rejects_only_a_swapped_range():
    assert range_order_error("range", "20", "10") == SWAP_MESSAGE
    assert range_order_error("range", "15", "15") is None
    assert range_order_error("range", "ten", "5") is None
    assert range_order_error("range", "10", None) is None
    assert range_order_error("minimum", "20", "10") is None
    assert range_order_error("maximum", "20", "10") is None


def test_clause_shows_a_zero_limit_and_omits_empty_ones():
    text = clause("DFT-1", "Dry film", standards_ref="ISO 19840", nominal="50", lower="", upper="0", measured="60")
    assert text.startswith("Criterion DFT-1 - Dry film (ISO 19840).")
    assert "nominal 50" in text
    assert "inclusive upper bound 0" in text
    assert "lower bound" not in text
    assert "Measured value: 60." in text


def test_clause_without_limits_ends_after_name_and_standards():
    assert clause("C-1", "Thickness", standards_ref="AS 1234") == "Criterion C-1 - Thickness (AS 1234)."
    assert clause("C-1", "Thickness") == "Criterion C-1 - Thickness."


def test_criterion_clause_reads_the_criterion_fields():
    crit = SimpleNamespace(code="C-2", title="Overlap", standards_ref=None, nominal=None, lower_limit="50", upper_limit=None)
    assert criterion_clause(crit, "48") == "Criterion C-2 - Overlap. Tolerance: inclusive lower bound 50. Measured value: 48."

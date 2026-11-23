"""Pure tolerance rules for acceptance criteria: exact-decimal, inclusive verdicts and the criterion clause used in
report wording. Imports neither the web framework nor the database layer.

A measured value is judged only when the rule is minimum, maximum or range, the value is a plain decimal and the
limits the rule needs are plain decimals. The nominal value is descriptive and never compared; no unit conversion
of any kind exists, so the value must be entered in the unit the limits use."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import RuleType, ToleranceResult

_PLAIN_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", re.ASCII)
_NUMERIC_RULES = (RuleType.MINIMUM.value, RuleType.MAXIMUM.value, RuleType.RANGE.value)
SWAP_MESSAGE = "The lower limit is above the upper limit; swap them."


def parse_decimal(text: Any) -> Decimal | None:
    """A plain decimal (optional sign, optional fraction) or None: no locale formats, exponents or unit letters."""
    if text is None:
        return None
    s = str(text).strip()
    if not _PLAIN_DECIMAL.fullmatch(s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def judge(rule_type: str | None, lower: Any, upper: Any, measured: Any) -> ToleranceResult:
    """Within, out of tolerance or not assessed. Every boundary is inclusive."""
    if rule_type not in _NUMERIC_RULES:
        return ToleranceResult.NOT_ASSESSED
    value = parse_decimal(measured)
    if value is None:
        return ToleranceResult.NOT_ASSESSED
    needs_lower = rule_type in (RuleType.MINIMUM.value, RuleType.RANGE.value)
    needs_upper = rule_type in (RuleType.MAXIMUM.value, RuleType.RANGE.value)
    low = parse_decimal(lower) if needs_lower else None
    high = parse_decimal(upper) if needs_upper else None
    if (needs_lower and low is None) or (needs_upper and high is None):
        return ToleranceResult.NOT_ASSESSED
    if (low is not None and value < low) or (high is not None and value > high):
        return ToleranceResult.OUT_OF_TOLERANCE
    return ToleranceResult.WITHIN


def judge_criterion(criterion: Any | None, measured: Any) -> ToleranceResult:
    """Judge against any object with ``rule_type``, ``lower_limit`` and ``upper_limit``; no criterion is not assessed."""
    if criterion is None:
        return ToleranceResult.NOT_ASSESSED
    return judge(criterion.rule_type, criterion.lower_limit, criterion.upper_limit, measured)


def range_order_error(rule_type: str | None, lower: Any, upper: Any) -> str | None:
    """A swap message only for a range rule whose two limits both parse and whose lower limit exceeds the upper one.
    Equal limits, non-numeric or partial limits and the other rule types pass untouched."""
    if rule_type != RuleType.RANGE.value:
        return None
    low, high = parse_decimal(lower), parse_decimal(upper)
    if low is not None and high is not None and low > high:
        return SWAP_MESSAGE
    return None


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def clause(
    code: str,
    title: str,
    *,
    standards_ref: str | None = None,
    nominal: Any = None,
    lower: Any = None,
    upper: Any = None,
    measured: Any = None,
) -> str:
    """The criterion wording of a report: code and title, the standards reference when present, then the nominal
    value and the inclusive bounds each only when non-empty (a zero limit is shown), then the measured value."""
    text = f"Criterion {code} - {title}"
    if _present(standards_ref):
        text += f" ({standards_ref})"
    text += "."
    bounds = []
    if _present(nominal):
        bounds.append(f"nominal {nominal}")
    if _present(lower):
        bounds.append(f"inclusive lower bound {lower}")
    if _present(upper):
        bounds.append(f"inclusive upper bound {upper}")
    if bounds:
        text += f" Tolerance: {', '.join(bounds)}."
    if _present(measured):
        text += f" Measured value: {measured}."
    return text


def criterion_clause(criterion: Any, measured: Any = None) -> str:
    """``clause`` for a criterion row."""
    return clause(
        criterion.code,
        criterion.title,
        standards_ref=criterion.standards_ref,
        nominal=criterion.nominal,
        lower=criterion.lower_limit,
        upper=criterion.upper_limit,
        measured=measured,
    )

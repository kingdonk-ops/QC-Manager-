"""Pure validation of items and permits: rules that refuse a save (errors) and rules that only advise (warnings).

The rules judge a plain mapping of field values, so on an update the caller merges the stored record with the pending
change first and passes the result. ``rules_apply`` says whether an update touches a rule-relevant field at all; an
update that does not (a change to notes only, say) runs no rules. This file imports neither the web framework nor the
database layer."""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, NamedTuple

from .constants import COORDINATOR_STATUSES, INDEPENDENT_CHECK_STATUSES, LIVE_PERMIT_STATUSES, PermitKind
from .rules import Finding

ITEM_RULE_FIELDS = frozenset(
    {
        "status",
        "design_check_category",
        "designer",
        "checker",
        "coordinator_name",
        "coordinator_user_id",
        "required_load_on",
        "required_strike_on",
        "design_due_on",
    }
)
PERMIT_RULE_FIELDS = frozenset(
    {"kind", "status", "valid_from", "valid_to", "issued_on", "closed_on", "design_check_accepted", "inspection_passed"}
)

INDEPENDENT_CHECK = "independent-check"
COORDINATOR = "coordinator"
STRIKE_BEFORE_LOAD = "strike-before-load"
LATE_DESIGN_DUE = "late-design-due"
VALID_TO_BEFORE_FROM = "valid-to-before-from"
CLOSED_BEFORE_ISSUED = "closed-before-issued"
LOAD_PREREQUISITE_DESIGN = "load-prerequisite-design-check"
LOAD_PREREQUISITE_INSPECTION = "load-prerequisite-inspection"


class Findings(NamedTuple):
    """Errors refuse the save; warnings are returned to the caller and never block."""

    errors: list[Finding]
    warnings: list[Finding]

    @property
    def ok(self) -> bool:
        return not self.errors


def rules_apply(changes: Mapping[str, Any], fields: frozenset[str]) -> bool:
    """True when the update supplies at least one rule-relevant field."""
    return any(key in fields for key in changes)


def merged(stored: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """The stored record with the pending change laid over it: what the rules must judge."""
    return {**stored, **changes}


def _name(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _category(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def validate_item(values: Mapping[str, Any]) -> Findings:
    """Independent check, coordinator and date-order rules for an item (the full merged record)."""
    errors: list[Finding] = []
    warnings: list[Finding] = []
    status = values.get("status")

    if _category(values.get("design_check_category")) in (2, 3) and status in INDEPENDENT_CHECK_STATUSES:
        checker, designer = _name(values.get("checker")), _name(values.get("designer"))
        if not checker:
            errors.append(Finding(INDEPENDENT_CHECK, "A category 2 or 3 item needs a named checker from design checked."))
        elif checker == designer:
            errors.append(Finding(INDEPENDENT_CHECK, "The checker must be someone other than the designer."))

    coordinator_named = bool(_name(values.get("coordinator_name"))) or values.get("coordinator_user_id") is not None
    if status in COORDINATOR_STATUSES and not coordinator_named:
        errors.append(Finding(COORDINATOR, "A temporary works coordinator must be named from approved to load onward."))

    load, strike, due = (_day(values.get(k)) for k in ("required_load_on", "required_strike_on", "design_due_on"))
    if load and strike and strike < load:
        errors.append(Finding(STRIKE_BEFORE_LOAD, "The required strike date is earlier than the required load date."))
    if load and due and due > load:
        warnings.append(Finding(LATE_DESIGN_DUE, "The design is due after the required load date."))
    return Findings(errors, warnings)


def validate_permit(values: Mapping[str, Any]) -> Findings:
    """Date order and, for a live permit to load, one error per missing prerequisite (the full merged record)."""
    errors: list[Finding] = []
    valid_from, valid_to = _day(values.get("valid_from")), _day(values.get("valid_to"))
    issued, closed = _day(values.get("issued_on")), _day(values.get("closed_on"))
    if valid_from and valid_to and valid_to < valid_from:
        errors.append(Finding(VALID_TO_BEFORE_FROM, "The permit's valid-to day is earlier than its valid-from day."))
    if issued and closed and closed < issued:
        errors.append(Finding(CLOSED_BEFORE_ISSUED, "The permit's closed day is earlier than its issued day."))
    if values.get("kind") == PermitKind.LOAD and values.get("status") in LIVE_PERMIT_STATUSES:
        if values.get("design_check_accepted") is not True:
            errors.append(Finding(LOAD_PREREQUISITE_DESIGN, "A live permit to load must record the design check."))
        if values.get("inspection_passed") is not True:
            errors.append(Finding(LOAD_PREREQUISITE_INSPECTION, "A live permit to load must record the inspection."))
    return Findings(errors, [])

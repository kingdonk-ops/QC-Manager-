"""Rule sets that check a bill and score it.

A rule is a function from the bill to findings ``{rule_id, severity, position_id, message}``;
``position_id`` is ``None`` for a finding about the bill as a whole. Rule sets:

* ``boq_quality``: missing quantity, unit, rate or text, zero totals, duplicate codes, rates
  that are zero with no resources, override rates far above the catalog, empty sections.
* ``din276``: cost group (Kostengruppe) present, a three-digit KG 100-800, groups 300 and 400
  present for building works, and each child within its parent's group.
* ``nrm``: element code present, ``group.element.sub-element`` format, group elements 0-14,
  and each level one deeper than its parent's.
* ``masterformat``: section number present, ``NN NN NN`` (optionally ``.NN``) format, divisions
  00-49, and children in their parent's division.

The score is ``100 × max(0, 1 − Σ weight / (10 × N))`` rounded to a whole percent, where an error
weighs 10, a warning 3 and an info 1, and ``N`` is the number of rows (at least 1). So a bill with
an error on every row scores 0, and a clean bill scores 100.
"""

import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]
WEIGHTS: dict[str, int] = {"error": 10, "warning": 3, "info": 1}
HIGH_RATE_FACTOR = Decimal(3)
"""An override rate more than this many times the catalog rate is flagged."""


@dataclass
class VLine:
    resource_id: int
    resource_code: str
    rate: Decimal
    catalog_rate: Decimal
    rate_override: Decimal | None = None


@dataclass
class VNode:
    id: int
    parent_id: int | None
    kind: str
    ordinal: str
    depth: int = 0
    code: str | None = None
    short_text: str | None = None
    unit: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    total: Decimal = Decimal(0)
    classification: str | None = None
    has_children: bool = False
    lines: list[VLine] = field(default_factory=list)

    @property
    def is_item(self) -> bool:
        """A priced line: a position without sub-positions."""
        return self.kind != "section" and not self.has_children


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    message: str
    position_id: int | None = None

    def dump(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "severity": self.severity, "message": self.message, "position_id": self.position_id}


Bill = list[VNode]
Rule = Callable[[Bill], Iterable[Finding]]


def _label(n: VNode) -> str:
    return f"{n.ordinal} {n.short_text or ''}".strip()


def _parent_map(bill: Bill) -> dict[int, VNode]:
    return {n.id: n for n in bill}


# --- BOQ quality ---------------------------------------------------------------------------------------


def q_missing_text(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if not (n.short_text or "").strip():
            yield Finding("BQ01", "error", f"{n.ordinal} has no short text", n.id)


def q_missing_quantity(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if n.is_item and n.quantity is None:
            yield Finding("BQ02", "error", f"{_label(n)}: no quantity", n.id)


def q_missing_unit(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if n.is_item and not (n.unit or "").strip():
            yield Finding("BQ03", "error", f"{_label(n)}: no unit", n.id)


def q_missing_rate(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if not n.is_item or (n.unit_rate or 0) != 0:
            continue
        if n.lines:
            yield Finding("BQ04", "warning", f"{_label(n)}: its resources give a rate of zero", n.id)
        else:
            yield Finding("BQ04", "error", f"{_label(n)}: no rate and no resources", n.id)


def q_zero_total(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if n.is_item and n.quantity is not None and (n.unit_rate or 0) != 0 and n.total == 0:
            yield Finding("BQ05", "warning", f"{_label(n)}: the total is zero", n.id)


def q_duplicate_codes(bill: Bill) -> Iterator[Finding]:
    codes = Counter((n.code or "").strip().lower() for n in bill if (n.code or "").strip())
    for n in bill:
        code = (n.code or "").strip()
        if code and codes[code.lower()] > 1:
            yield Finding("BQ06", "error", f"{_label(n)}: the code {code} is used {codes[code.lower()]} times", n.id)


def q_high_rate(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        for line in n.lines:
            if line.rate_override is not None and line.catalog_rate > 0:
                if line.rate_override > line.catalog_rate * HIGH_RATE_FACTOR:
                    yield Finding(
                        "BQ07",
                        "warning",
                        f"{_label(n)}: {line.resource_code} at {line.rate_override} is over "
                        f"{HIGH_RATE_FACTOR}× the catalog rate of {line.catalog_rate}",
                        n.id,
                    )


def q_empty_sections(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if n.kind == "section" and not n.has_children:
            yield Finding("BQ08", "warning", f"{_label(n)}: the section is empty", n.id)


def q_empty_bill(bill: Bill) -> Iterator[Finding]:
    if not any(n.is_item for n in bill):
        yield Finding("BQ09", "info", "The bill has no positions yet")


# --- DIN 276 -------------------------------------------------------------------------------------------

KG = re.compile(r"^(?:KG\s*)?([1-8]\d{2})$", re.IGNORECASE)


def _kg(n: VNode) -> str | None:
    match = KG.match((n.classification or "").strip())
    return match.group(1) if match else None


def _kg_prefix(code: str) -> str:
    """``300`` → ``3``, ``340`` → ``34``, ``341`` → ``341``: the part a child must start with."""
    return code.rstrip("0") or code[0]


def din_present(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if not (n.classification or "").strip():
            severity: Severity = "error" if n.is_item else "warning"
            yield Finding("DIN01", severity, f"{_label(n)}: no DIN 276 cost group", n.id)


def din_format(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        value = (n.classification or "").strip()
        if value and _kg(n) is None:
            yield Finding("DIN02", "error", f"{_label(n)}: '{value}' isn't a cost group KG 100-800 (three digits)", n.id)


def din_required_groups(bill: Bill) -> Iterator[Finding]:
    groups = {code[0] for n in bill if (code := _kg(n))}
    if not bill:
        return
    for group, name in (("3", "300 (building construction)"), ("4", "400 (building services)")):
        if group not in groups:
            yield Finding("DIN03", "error", f"No position in cost group {name}")


def din_hierarchy(bill: Bill) -> Iterator[Finding]:
    by_id = _parent_map(bill)
    for n in bill:
        parent = by_id.get(n.parent_id) if n.parent_id else None
        mine, theirs = _kg(n), _kg(parent) if parent else None
        if mine and theirs and not mine.startswith(_kg_prefix(theirs)):
            yield Finding("DIN04", "warning", f"{_label(n)}: KG {mine} isn't within its parent's KG {theirs}", n.id)


def din_levels(bill: Bill) -> Iterator[Finding]:
    """Completeness per level: every first-level group used should have a section of its own."""
    first_level_sections = {code[0] for n in bill if n.kind == "section" and (code := _kg(n)) and code.endswith("00")}
    used = {code[0] for n in bill if n.is_item and (code := _kg(n))}
    for group in sorted(used - first_level_sections):
        yield Finding("DIN05", "info", f"Cost group {group}00 is priced but has no section of its own")


# --- NRM -----------------------------------------------------------------------------------------------

NRM_CODE = re.compile(r"^\d{1,2}(\.\d{1,2}){0,2}$")


def nrm_present(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if not (n.classification or "").strip():
            severity: Severity = "error" if n.is_item else "warning"
            yield Finding("NRM01", severity, f"{_label(n)}: no NRM element code", n.id)


def nrm_format(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        value = (n.classification or "").strip()
        if not value:
            continue
        if not NRM_CODE.match(value):
            yield Finding("NRM02", "error", f"{_label(n)}: '{value}' isn't group.element.sub-element (e.g. 2.6.1)", n.id)
        elif int(value.split(".")[0]) > 14:
            yield Finding("NRM03", "warning", f"{_label(n)}: group element {value.split('.')[0]} is outside 0-14", n.id)


def nrm_hierarchy(bill: Bill) -> Iterator[Finding]:
    by_id = _parent_map(bill)
    for n in bill:
        parent = by_id.get(n.parent_id) if n.parent_id else None
        mine, theirs = (n.classification or "").strip(), ((parent.classification or "").strip() if parent else "")
        if not (mine and theirs and NRM_CODE.match(mine) and NRM_CODE.match(theirs)) or mine == theirs:
            continue
        if not mine.startswith(theirs + ".") or mine.count(".") != theirs.count(".") + 1:
            yield Finding("NRM04", "warning", f"{_label(n)}: {mine} should sit one level below its parent's {theirs}", n.id)


# --- MasterFormat --------------------------------------------------------------------------------------

MF_CODE = re.compile(r"^(\d{2}) ?(\d{2}) ?(\d{2})(\.\d{2})?$")


def mf_present(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        if not (n.classification or "").strip():
            severity: Severity = "error" if n.is_item else "warning"
            yield Finding("MF01", severity, f"{_label(n)}: no MasterFormat section", n.id)


def mf_format(bill: Bill) -> Iterator[Finding]:
    for n in bill:
        value = (n.classification or "").strip()
        if not value:
            continue
        match = MF_CODE.match(value)
        if not match or " " not in value:
            yield Finding("MF02", "error", f"{_label(n)}: '{value}' isn't a section number NN NN NN", n.id)
        elif int(match.group(1)) > 49:
            yield Finding("MF03", "error", f"{_label(n)}: division {match.group(1)} is outside 00-49", n.id)


def mf_hierarchy(bill: Bill) -> Iterator[Finding]:
    by_id = _parent_map(bill)
    for n in bill:
        parent = by_id.get(n.parent_id) if n.parent_id else None
        mine = MF_CODE.match((n.classification or "").strip())
        theirs = MF_CODE.match((parent.classification or "").strip()) if parent else None
        if mine and theirs and mine.group(1) != theirs.group(1):
            yield Finding(
                "MF04", "warning", f"{_label(n)}: division {mine.group(1)} differs from its parent's {theirs.group(1)}", n.id
            )


RULESETS: dict[str, list[Rule]] = {
    "boq_quality": [
        q_missing_text,
        q_missing_quantity,
        q_missing_unit,
        q_missing_rate,
        q_zero_total,
        q_duplicate_codes,
        q_high_rate,
        q_empty_sections,
        q_empty_bill,
    ],
    "din276": [din_present, din_format, din_required_groups, din_hierarchy, din_levels],
    "nrm": [nrm_present, nrm_format, nrm_hierarchy],
    "masterformat": [mf_present, mf_format, mf_hierarchy],
}


def score(findings: Iterable[Finding], rows: int) -> int:
    penalty = sum(WEIGHTS[f.severity] for f in findings)
    return round(100 * max(0.0, 1 - penalty / (10 * max(1, rows))))


def validate(bill: Bill, ruleset: str) -> dict[str, Any]:
    findings = [f for rule in RULESETS[ruleset] for f in rule(bill)]
    order = {"error": 0, "warning": 1, "info": 2}
    position = {n.id: i for i, n in enumerate(bill)}
    findings.sort(key=lambda f: (position.get(f.position_id, -1) if f.position_id else -1, order[f.severity]))
    counts = Counter(f.severity for f in findings)
    return {
        "ruleset": ruleset,
        "score": score(findings, len(bill)),
        "errors": counts["error"],
        "warnings": counts["warning"],
        "infos": counts["info"],
        "findings": [f.dump() for f in findings],
    }

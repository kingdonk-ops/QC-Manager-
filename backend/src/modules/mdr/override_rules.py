"""Pure rules of the dossier issue override: which readiness checks may be overridden, what blocks and can be covered,
how stored overrides turn a failing check into the overridden status, and the wording of the documentation report.

Plain functions over plain values: this file imports neither the web framework nor the database layer."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

OVERRIDDEN = "overridden"
"""A check status that does not fail: every finding of the check is covered by an override."""
GATE_CHECK = "quality_gates"
ISSUES_CHECK = "issues_blocking"
OVERRIDABLE_CHECKS: tuple[str, ...] = (GATE_CHECK, ISSUES_CHECK)
"""The only checks an override may cover: pending quality holds and open blocking issues. Plan hold points, incomplete
inspections, calibration and client acceptance are never overridden."""
MAX_REPORT_TITLE = 300
"""The width of the issues module's title column; a long dossier code must not make the report insert fail."""
SEVERITIES: tuple[str, ...] = ("minor", "major", "critical")
DEFAULT_SEVERITY = "major"
MAX_REFERENCE = 100
Pair = tuple[str, str]
"""``(check key, finding reference)``: what an override covers."""


def clean_reason(reason: str | None) -> str:
    """The reason without surrounding whitespace; empty when nothing was given."""
    return (reason or "").strip()


def normalise_severity(value: str | None) -> str:
    """Omitted means major; anything outside minor, major and critical is a programming or input error."""
    if value is None:
        return DEFAULT_SEVERITY
    if value not in SEVERITIES:
        raise ValueError(f"Severity must be one of {', '.join(SEVERITIES)}.")
    return value


def is_overridable(check_key: str) -> bool:
    return check_key in OVERRIDABLE_CHECKS


def override_reference(dossier_code: str, sequence: int) -> str:
    """The reference shown beside every covered gate: the dossier code and the override's position in its history."""
    suffix = f"-OVR-{sequence:02d}"
    return dossier_code[: MAX_REFERENCE - len(suffix)] + suffix


def _failing(checks: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [c for c in checks if c["blocking"] and c["status"] == "fail"]


@dataclass(frozen=True)
class Assessment:
    """What stands between the checks and an override."""

    unavailable: list[str] = field(default_factory=list)
    """Titles of overridable checks that could not run: the override fails closed."""
    non_overridable: list[str] = field(default_factory=list)
    """Titles of failing blocking checks that an override may never cover."""
    uncoverable: list[str] = field(default_factory=list)
    """Messages of findings without a stable reference: they cannot be matched, so they refuse the override."""
    blockers: list[dict[str, Any]] = field(default_factory=list)
    """``{check, reference, message}`` of every finding an override would cover."""

    @property
    def refusal(self) -> str | None:
        """Why the override is refused as a client error, or ``None`` when it may go ahead."""
        if self.unavailable:
            return "An override needs every covered check to run; not available: " + "; ".join(self.unavailable) + "."
        if self.non_overridable:
            return "These checks are never overridden and still fail: " + "; ".join(self.non_overridable) + "."
        if self.uncoverable:
            return "These findings carry no reference, so an override cannot cover them: " + "; ".join(self.uncoverable) + "."
        return None

    @property
    def nothing_blocks(self) -> bool:
        return not self.blockers and self.refusal is None


def assess(checks: Sequence[Mapping[str, Any]]) -> Assessment:
    """Sort the gate's rows into what makes an override impossible and what it would cover."""
    unavailable = [c["title"] for c in checks if is_overridable(c["key"]) and c["status"] == "not_available"]
    non_overridable = [c["title"] for c in _failing(checks) if not is_overridable(c["key"])]
    blockers: list[dict[str, Any]] = []
    uncoverable: list[str] = []
    for row in _failing(checks):
        if not is_overridable(row["key"]):
            continue
        for finding in row["findings"]:
            if finding.get("reference"):
                blockers.append({"check": row["key"], "reference": finding["reference"], "message": finding["message"]})
            else:
                uncoverable.append(finding["message"])
    return Assessment(unavailable, non_overridable, uncoverable, blockers)


def gate_numbers(blockers: Iterable[Mapping[str, Any]]) -> list[str]:
    """The quality gate numbers among the blockers, in the order given and without repeats."""
    return list(dict.fromkeys(b["reference"] for b in blockers if b["check"] == GATE_CHECK))


def covered_pairs(snapshots: Iterable[Iterable[Mapping[str, Any]]]) -> set[Pair]:
    """Everything the stored overrides cover, from their blocker snapshots. A blocker created later is not in any
    snapshot, so it stays uncovered."""
    return {(b["check"], b["reference"]) for snapshot in snapshots for b in snapshot if b.get("reference")}


def split_findings(
    check_key: str, findings: Iterable[Mapping[str, Any]], covered: set[Pair]
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Findings split into ``(covered, uncovered)`` by reference; a finding without a reference is never covered."""
    done: list[Mapping[str, Any]] = []
    open_: list[Mapping[str, Any]] = []
    for finding in findings:
        reference = finding.get("reference")
        (done if reference and (check_key, reference) in covered else open_).append(finding)
    return done, open_


def apply_overrides(checks: Sequence[Mapping[str, Any]], covered: set[Pair]) -> list[dict[str, Any]]:
    """The gate rows with stored overrides applied (the input is not changed).

    A failing check whose findings are all covered becomes ``overridden``; a failing check with any uncovered finding
    keeps failing and lists only what is uncovered. Rows that pass, are not available or are not covered stay as they
    were."""
    out: list[dict[str, Any]] = []
    for row in checks:
        copy = {**row, "findings": list(row["findings"])}
        if covered and row["status"] == "fail" and is_overridable(row["key"]):
            done, open_ = split_findings(row["key"], row["findings"], covered)
            if done:
                note = f"{len(done)} finding(s) covered by a manager override; the records stay open."
                if open_:
                    copy.update(findings=list(open_), detail=note)
                else:
                    copy.update(status=OVERRIDDEN, findings=list(done), detail=note)
        out.append(copy)
    return out


def counts_payload(plain: int | None, overridden: int | None, open_reports: int | None) -> dict[str, int | None]:
    """The counts the gate response carries; ``None`` means that source is not available."""
    return {
        "plain_pending_holds": None if plain is None else max(plain, 0),
        "overridden_pending_holds": None if overridden is None else max(overridden, 0),
        "open_reports": None if open_reports is None else max(open_reports, 0),
    }


def report_title(dossier_code: str, reference: str) -> str:
    return f"{dossier_code} issued past outstanding blockers ({reference})"[:MAX_REPORT_TITLE]


def report_description(
    dossier_code: str, reference: str, purpose: str, reason: str, blockers: Sequence[Mapping[str, Any]]
) -> str:
    """Documentation report text: who is covered and why, then every outstanding blocker."""
    lines = [
        f"A manager overrode the readiness gate of dossier {dossier_code} for a {purpose} issue ({reference}).",
        f"Reason: {reason}",
        "Outstanding at the time, left open and not closed by the override:",
    ]
    lines += [f"- {b['reference']}: {b['message']}" for b in blockers]
    return "\n".join(lines)


def report_source_data(dossier_id: int, reference: str, severity: str, blockers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "source_kind": "mdr_override",
        "report_kind": "documentation",
        "dossier_id": dossier_id,
        "override_reference": reference,
        "severity": severity,
        "blockers": [{"check": b["check"], "reference": b["reference"]} for b in blockers],
    }

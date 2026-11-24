"""The pure override rules: what may be overridden, what blocks and what an override covers, how stored overrides change
a check's status, the counts payload and the documentation report wording. Plain values only; no database."""

from typing import Any

import pytest

from src.modules.mdr import override_rules as rules
from src.modules.mdr.schemas import CheckRead


def finding(reference: str | None, message: str = "Pending hold gate") -> dict[str, Any]:
    return {"message": message, "reference": reference, "link": None}


def row(
    key: str, status: str, findings: list[dict[str, Any]] | None = None, *, blocking: bool = True, title: str | None = None
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title or f"Title of {key}",
        "module": "x",
        "blocking": blocking,
        "status": status,
        "findings": findings or [],
        "detail": None,
    }


GATES = "quality_gates"
ISSUES = "issues_blocking"


# --- which checks may be overridden -------------------------------------------------------------------------


def test_only_the_quality_gate_and_open_issues_checks_may_be_overridden():
    assert set(rules.OVERRIDABLE_CHECKS) == {GATES, ISSUES}
    assert rules.is_overridable(GATES) and rules.is_overridable(ISSUES)
    for never in ("itp_hold_points", "inspections_complete", "equipment_calibrated", "client_acceptance", "ncr_open"):
        assert not rules.is_overridable(never)


def test_the_readiness_check_schema_reports_whether_it_is_overridable():
    def dumped(key: str) -> dict[str, Any]:
        return CheckRead.model_validate(row(key, "fail")).model_dump()

    assert dumped(GATES)["overridable"] is True
    assert dumped(ISSUES)["overridable"] is True
    assert dumped("inspections_complete")["overridable"] is False


# --- reason, severity and reference ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "\n\t "])
def test_a_missing_or_blank_reason_cleans_to_nothing(raw: str | None):
    assert rules.clean_reason(raw) == ""


def test_a_reason_is_trimmed_and_otherwise_kept():
    assert rules.clean_reason("  Client accepted the risk \n") == "Client accepted the risk"


def test_severity_defaults_to_major_and_only_minor_major_critical_are_accepted():
    assert rules.normalise_severity(None) == "major" == rules.DEFAULT_SEVERITY
    assert [rules.normalise_severity(s) for s in ("minor", "major", "critical")] == ["minor", "major", "critical"]
    for bad in ("", "blocker", "Major", "high"):
        with pytest.raises(ValueError, match="Severity"):
            rules.normalise_severity(bad)


def test_the_override_reference_carries_the_dossier_code_and_the_position_and_fits_the_column():
    assert rules.override_reference("MDR-0007", 1) == "MDR-0007-OVR-01"
    assert rules.override_reference("MDR-0007", 12) == "MDR-0007-OVR-12"
    long = rules.override_reference("X" * 300, 3)
    assert len(long) == rules.MAX_REFERENCE and long.endswith("-OVR-03")


def test_the_report_title_fits_the_issues_title_column_even_for_a_very_long_dossier_code():
    code = "X" * 200  # the dossier code column is wider than the report title column
    assert len(rules.report_title(code, rules.override_reference(code, 1))) <= rules.MAX_REPORT_TITLE
    assert rules.report_title("MDR-0007", "MDR-0007-OVR-01") == "MDR-0007 issued past outstanding blockers (MDR-0007-OVR-01)"


# --- assessing the gate rows ----------------------------------------------------------------------------------


def test_failing_quality_and_issue_findings_become_blockers_with_their_references():
    checks = [
        row(GATES, "fail", [finding("GATE-1", "Pending hold gate: Pre-pour"), finding("GATE-2")]),
        row(ISSUES, "fail", [finding("NCR-9", "Open issue")]),
        row("itp_hold_points", "pass"),
    ]
    got = rules.assess(checks)
    assert got.refusal is None and got.nothing_blocks is False
    assert [(b["check"], b["reference"]) for b in got.blockers] == [(GATES, "GATE-1"), (GATES, "GATE-2"), (ISSUES, "NCR-9")]
    assert got.blockers[0]["message"] == "Pending hold gate: Pre-pour"


def test_a_clear_dossier_has_nothing_to_override():
    got = rules.assess([row(GATES, "pass"), row(ISSUES, "pass"), row("inspections_complete", "pass")])
    assert got.blockers == [] and got.refusal is None and got.nothing_blocks is True


def test_an_already_overridden_check_and_a_non_blocking_failure_block_nothing():
    advisory = row("advisory", "fail", [finding("A-1")], blocking=False)
    got = rules.assess([row(GATES, "overridden", [finding("GATE-1")]), advisory])
    assert got.blockers == [] and got.refusal is None and got.nothing_blocks is True


@pytest.mark.parametrize("key", ["itp_hold_points", "inspections_complete", "equipment_calibrated", "client_acceptance"])
def test_a_failing_check_that_is_never_overridden_refuses_and_is_named(key: str):
    got = rules.assess([row(GATES, "fail", [finding("GATE-1")]), row(key, "fail", [finding("X-1")], title="The named check")])
    assert got.non_overridable == ["The named check"]
    assert got.refusal is not None and "The named check" in got.refusal and "never overridden" in got.refusal
    assert got.nothing_blocks is False


@pytest.mark.parametrize("key", [GATES, ISSUES])
def test_a_covered_check_that_is_not_available_fails_closed(key: str):
    got = rules.assess([row(key, "not_available", title="The covered check"), row(GATES if key == ISSUES else ISSUES, "pass")])
    assert got.unavailable == ["The covered check"]
    assert got.refusal is not None and "not available" in got.refusal and "The covered check" in got.refusal


def test_a_check_that_is_not_covered_and_not_available_does_not_refuse():
    got = rules.assess([row(GATES, "fail", [finding("GATE-1")]), row("equipment_calibrated", "not_available")])
    assert got.refusal is None and len(got.blockers) == 1


def test_a_finding_without_a_reference_cannot_be_covered_and_refuses():
    got = rules.assess([row(ISSUES, "fail", [finding(None, "Free text only"), finding("", "Empty reference")])])
    assert got.uncoverable == ["Free text only", "Empty reference"] and got.blockers == []
    assert got.refusal is not None and "no reference" in got.refusal and "Free text only" in got.refusal


def test_the_refusal_reports_an_unavailable_check_before_a_non_overridable_one():
    holds = row("itp_hold_points", "fail", [finding("L-1")], title="Holds")
    got = rules.assess([row(GATES, "not_available", title="Gates"), holds])
    assert got.refusal is not None and got.refusal.startswith("An override needs every covered check to run")


def test_gate_numbers_are_the_quality_gate_blockers_in_order_without_repeats():
    blockers = [
        {"check": GATES, "reference": "GATE-2", "message": "m"},
        {"check": ISSUES, "reference": "NCR-1", "message": "m"},
        {"check": GATES, "reference": "GATE-1", "message": "m"},
        {"check": GATES, "reference": "GATE-2", "message": "m"},
    ]
    assert rules.gate_numbers(blockers) == ["GATE-2", "GATE-1"]
    assert rules.gate_numbers([]) == []


# --- what stored overrides cover --------------------------------------------------------------------------------


def test_covered_pairs_come_from_the_snapshots_and_skip_entries_without_a_reference():
    snapshots = [
        [{"check": GATES, "reference": "GATE-1"}, {"check": ISSUES, "reference": "NCR-1"}],
        [{"check": GATES, "reference": "GATE-2"}, {"check": GATES, "reference": None}, {"check": GATES}],
    ]
    assert rules.covered_pairs(snapshots) == {(GATES, "GATE-1"), (ISSUES, "NCR-1"), (GATES, "GATE-2")}
    assert rules.covered_pairs([]) == set()


def test_findings_split_into_covered_and_uncovered_by_check_and_reference():
    covered = {(GATES, "GATE-1")}
    findings = [finding("GATE-1"), finding("GATE-2"), finding(None)]
    done, open_ = rules.split_findings(GATES, findings, covered)
    assert [f["reference"] for f in done] == ["GATE-1"]
    assert [f["reference"] for f in open_] == ["GATE-2", None]
    done, open_ = rules.split_findings(ISSUES, findings, covered)  # the same reference under another check is not covered
    assert done == [] and len(open_) == 3


def test_a_check_whose_findings_are_all_covered_becomes_overridden_and_does_not_fail():
    checks = [row(GATES, "fail", [finding("GATE-1"), finding("GATE-2")]), row(ISSUES, "pass")]
    out = rules.apply_overrides(checks, {(GATES, "GATE-1"), (GATES, "GATE-2")})
    assert out[0]["status"] == rules.OVERRIDDEN == "overridden"
    assert [f["reference"] for f in out[0]["findings"]] == ["GATE-1", "GATE-2"]
    assert "2 finding(s) covered" in out[0]["detail"]
    assert out[1]["status"] == "pass"
    assert not any(c["blocking"] and c["status"] == "fail" for c in out)  # nothing refuses an issue


def test_any_uncovered_finding_keeps_the_check_failing_and_lists_only_what_is_uncovered():
    checks = [row(GATES, "fail", [finding("GATE-1"), finding("GATE-3")])]
    out = rules.apply_overrides(checks, {(GATES, "GATE-1")})
    assert out[0]["status"] == "fail"
    assert [f["reference"] for f in out[0]["findings"]] == ["GATE-3"]
    assert "1 finding(s) covered" in out[0]["detail"]


def test_a_finding_without_a_reference_is_never_covered():
    out = rules.apply_overrides([row(ISSUES, "fail", [finding(None)])], {(ISSUES, "None"), (ISSUES, "")})
    assert out[0]["status"] == "fail" and len(out[0]["findings"]) == 1


def test_a_check_that_is_never_overridden_is_not_changed_even_if_a_pair_names_it():
    checks = [row("itp_hold_points", "fail", [finding("L-1")])]
    out = rules.apply_overrides(checks, {("itp_hold_points", "L-1")})
    assert out[0]["status"] == "fail"


def test_rows_that_pass_are_unavailable_or_uncovered_stay_as_they_were_and_the_input_is_not_changed():
    checks = [
        row(GATES, "pass"),
        row(ISSUES, "not_available", title="Issues"),
        row(GATES, "fail", [finding("GATE-9")]),
    ]
    snapshot = [dict(c, findings=list(c["findings"])) for c in checks]
    out = rules.apply_overrides(checks, {(GATES, "GATE-1")})
    assert [c["status"] for c in out] == ["pass", "not_available", "fail"]
    assert checks == snapshot  # the gate rows are copied, not edited in place
    assert out[2] is not checks[2]


def test_nothing_is_applied_without_stored_overrides():
    checks = [row(GATES, "fail", [finding("GATE-1")])]
    assert rules.apply_overrides(checks, set()) == checks


def test_the_snapshot_is_only_the_listed_blockers_so_the_report_gets_no_entry_of_its_own():
    # the documentation report is non-blocking, so it never shows up as a failing finding and needs no coverage
    assert not hasattr(rules, "snapshot_with_report")
    snapshot = [{"check": GATES, "reference": "GATE-1", "message": "Pending hold"}]
    assert rules.covered_pairs([snapshot]) == {(GATES, "GATE-1")}
    # an open blocking report that is not on the override stays uncovered and keeps the issues check failing
    out = rules.apply_overrides([row(ISSUES, "fail", [finding("NCR-0042")])], rules.covered_pairs([snapshot]))
    assert out[0]["status"] == "fail" and [f["reference"] for f in out[0]["findings"]] == ["NCR-0042"]


def test_a_blocker_created_after_the_override_is_not_in_any_snapshot_and_still_fails():
    snapshot = [{"check": GATES, "reference": "GATE-1", "message": "m"}]
    out = rules.apply_overrides([row(GATES, "fail", [finding("GATE-1"), finding("GATE-2")])], rules.covered_pairs([snapshot]))
    assert out[0]["status"] == "fail" and [f["reference"] for f in out[0]["findings"]] == ["GATE-2"]


# --- counts and report wording ----------------------------------------------------------------------------------


def test_the_counts_payload_keeps_zero_and_unavailable_apart_and_never_goes_negative():
    assert rules.counts_payload(0, 0, 0) == {"plain_pending_holds": 0, "overridden_pending_holds": 0, "open_reports": 0}
    assert rules.counts_payload(2, 3, 1) == {"plain_pending_holds": 2, "overridden_pending_holds": 3, "open_reports": 1}
    assert rules.counts_payload(None, None, None) == {
        "plain_pending_holds": None,
        "overridden_pending_holds": None,
        "open_reports": None,
    }
    assert rules.counts_payload(-1, 4, None) == {"plain_pending_holds": 0, "overridden_pending_holds": 4, "open_reports": None}


def test_the_report_wording_names_the_dossier_the_reference_the_reason_and_every_blocker():
    blockers = [
        {"check": GATES, "reference": "GATE-1", "message": "Pending hold gate: Pre-pour"},
        {"check": ISSUES, "reference": "NCR-9", "message": "NCR-9 Open issue"},
    ]
    title = rules.report_title("MDR-0007", "MDR-0007-OVR-01")
    text = rules.report_description("MDR-0007", "MDR-0007-OVR-01", "review", "Client accepted the risk", blockers)
    assert "MDR-0007" in title and "MDR-0007-OVR-01" in title
    assert "MDR-0007" in text and "MDR-0007-OVR-01" in text and "review" in text and "Reason: Client accepted the risk" in text
    assert "- GATE-1: Pending hold gate: Pre-pour" in text and "- NCR-9: NCR-9 Open issue" in text
    assert "left open" in text  # the override annotates; it does not close anything


def test_the_report_source_data_marks_a_documentation_report_and_lists_blocker_references_only():
    blockers = [{"check": GATES, "reference": "GATE-1", "message": "free text"}]
    data = rules.report_source_data(7, "MDR-0007-OVR-01", "major", blockers)
    assert data["report_kind"] == "documentation" and data["source_kind"] == "mdr_override"
    assert (data["dossier_id"], data["override_reference"], data["severity"]) == (7, "MDR-0007-OVR-01", "major")
    assert data["blockers"] == [{"check": GATES, "reference": "GATE-1"}]

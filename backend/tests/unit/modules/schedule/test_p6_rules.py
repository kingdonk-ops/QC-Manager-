"""P6 name grammar, aliases, eligibility and the change-impact diff, without a database."""

from types import SimpleNamespace

import pytest

from src.modules.schedule.p6_rules import DEFAULT_RULES, GrammarError, build, compile_pattern, eligible, norm, parse
from src.modules.schedule.p6_service import Existing, diff, row_hash


def rules(**override):
    rows = [
        SimpleNamespace(**{"id": n, "enabled": True, "pattern": "", "source": "name", "params": {}, **r})
        for n, r in enumerate(DEFAULT_RULES, 1)
    ]
    for r in rows:
        if r.kind == "grammar" and override:
            r.params = {**r.params, **override}
    return build(rows)


def row(name: str, **kw):
    return {"p6_id": kw.pop("p6_id", "A1"), "name": name, "wbs_path": "", "task_type": "TT_Task", **kw}


@pytest.mark.parametrize(
    ("name", "groups", "window"),
    [
        ("101 / B / 305", {"asset": "101", "activity_type": "B", "anchor_code": "305"}, None),
        ("TK-1002 / SCA Erect / 410.2", {"asset": "TK-1002", "activity_type": "SCA Erect", "anchor_code": "410.2"}, None),
        ("101 / B / 512-21", {"asset": "101", "activity_type": "B", "anchor_code": "512-21"}, None),
        ("101 / B / 512 Online", {"asset": "101", "activity_type": "B", "anchor_code": "512"}, "Online"),
        ("101 / SCA-Dism / 512.1-16 Shut", {"asset": "101", "activity_type": "SCA Dism", "anchor_code": "512.1-16"}, "Shut"),
    ],
)
def test_default_grammar(name, groups, window):
    parsed = parse(row(name), rules())
    assert parsed.groups == groups
    assert parsed.window == window


def test_suffix_and_window_defaults_are_configurable():
    parsed = parse(row("101 / B / 512-21 Online"), rules(suffix="same", window="separate"))
    assert parsed.groups["anchor_code"] == "512 Online"
    assert parsed.window is None


def test_names_outside_the_grammar_are_not_guessed():
    assert parse(row("Mobilise crane"), rules()).groups is None
    assert parse(row("101 / B / RSW"), rules()).groups is None


def test_eligibility_rules():
    rs = rules()
    assert eligible(row("101 / B / 305", task_type="TT_Mile"), parse(row("101 / B / 305"), rs), rs) == (
        False,
        "Milestones never expect work",
    )
    prov = row("101 / Prov.Sums / 305")
    assert eligible(prov, parse(prov, rs), rs)[0] is False
    ok = row("101 / P / 305")
    assert eligible(ok, parse(ok, rs), rs) == (True, None)


def test_norm_and_bad_patterns():
    assert norm(" tk-1002 ") == norm("TK 1002") == "TK 1002"
    with pytest.raises(GrammarError):
        compile_pattern("(unclosed")
    with pytest.raises(GrammarError):
        compile_pattern(r"\d+")  # no named group


def _row(pid: str, name: str, **kw):
    r = {
        "p6_id": pid,
        "guid": kw.pop("guid", f"G{pid}"),
        "name": name,
        "type": "task",
        "planned_start": "2026-03-02",
        "planned_finish": "2026-03-06",
        "duration": 5,
        **kw,
    }
    r["hash"] = row_hash(r)
    return r


def test_diff_classifies_every_change():
    old_a = _row("A1", "Excavate")
    old_b = _row("A2", "Pour")
    old_c = _row("A3", "Strip")
    existing = {
        "A1": Existing(1, "A1", "GA1", "active", dict(old_a), ["S / 101 / 305"]),
        "A2": Existing(2, "A2", "GA2", "active", dict(old_b)),
        "A3": Existing(3, "A3", "GA3", "active", dict(old_c)),
        "A9": Existing(9, "A9", "GA9", "removed_from_schedule", dict(_row("A9", "Old"))),
    }
    rows = [
        _row("A1", "Excavate", planned_start="2026-03-04", planned_finish="2026-03-10"),
        _row("A2", "Pour"),
        _row("A4", "Strip", guid="GA3"),
        _row("A5", "New thing"),
        _row("A9", "Old"),
    ]
    changes, counts = diff(rows, existing, {"A5": 55})
    got = {(c["p6_activity_id"], c["change_type"]) for c in changes}
    assert got == {("A1", "dates_changed"), ("A4", "renumbered"), ("A5", "adopted"), ("A9", "restored")}
    assert counts["unchanged"] == 2  # A2, and A4 once renumbered
    dates = next(c for c in changes if c["change_type"] == "dates_changed")
    assert dates["impact"] == {"linked_nodes": ["S / 101 / 305"], "start_shift_days": 2, "finish_shift_days": 4}
    gone, _ = diff([_row("A2", "Pour")], {k: v for k, v in existing.items() if k != "A9"}, {})
    assert {(c["p6_activity_id"], c["change_type"]) for c in gone} == {("A1", "removed"), ("A3", "removed")}

"""P6 name grammar, aliases, eligibility and the change-impact diff, without a database."""

from types import SimpleNamespace

import pytest

from src.modules.schedule.p6_rules import (
    DEFAULT_RULES,
    GrammarError,
    build,
    compile_pattern,
    eligible,
    expand_list,
    groups_for,
    link_info,
    norm,
    parse,
)
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


# --- several RSWs in one name, qualifiers and WBS levels ------------------------------------------


@pytest.mark.parametrize(
    ("name", "anchors", "qualifier", "window"),
    [
        ("CV-01 / WFE / 902 - 903 - 904", ["902", "903", "904"], None, None),
        ("CV-01 / WFE / 728 - 732", ["728", "729", "730", "731", "732"], None, None),
        ("CV-01 / WFE / 904 - 905 Props", ["904", "905"], "Props", None),
        ("CV-01 / WFE / 410.2 - 410.5 Shut", ["410.2", "410.5"], None, "Shut"),
        ("CV-01 / B / 305 OHP", ["305"], "OHP", None),
        ("CV-01 / B / 305 - Access", ["305"], "Access", None),
        ("CV-01 / B / 305-North", ["305"], "North", None),
        ("CV-01 / B / 305 Water Diversion", ["305"], "Water Diversion", None),
        ("CV-01 / B / 512-21", ["512-21"], None, None),
        ("CV-01 / B / 512 Online", ["512"], None, "Online"),
    ],
)
def test_lists_ranges_and_qualifiers(name, anchors, qualifier, window):
    parsed = parse(row(name), rules())
    assert parsed.anchors == anchors
    assert parsed.groups is not None and parsed.groups["anchor_code"] == anchors[0]
    assert (parsed.qualifier, parsed.window) == (qualifier, window)


@pytest.mark.parametrize("name", ["CV-01 / P / 410-2-3", "CV-01 / Prov Sums / Painters", "Site mobilisation"])
def test_unclear_codes_stay_unmatched(name):
    assert parse(row(name), rules()).groups is None


def test_expand_list_never_guesses_a_long_or_backwards_range():
    assert expand_list("905 - 902") == ["905", "902"]
    assert expand_list("100 - 900") == ["100", "900"]  # longer than max_range: as listed
    assert expand_list("100 - 104", max_range=3) == ["100", "104"]
    assert expand_list("098 - 101") == ["098", "099", "100", "101"]
    assert expand_list("902 - 903 - 903") == ["902", "903"]


def test_groups_for_and_link_info():
    parsed = parse(row("CV-01 / WFE / 728 - 730 OHP"), rules())
    assert [g["anchor_code"] for g in groups_for(parsed)] == ["728", "729", "730"]
    info = link_info(parsed)
    assert info["qualifier"] == "OHP" and info["anchors"] == ["728", "729", "730"]
    single = parse(row("CV-01 / B / 305"), rules())
    assert groups_for(single) == [single.groups] and "anchors" not in link_info(single)


def test_wbs_levels_add_breakdown_levels_from_the_wbs():
    rows = [
        SimpleNamespace(**{"id": n, "enabled": True, "pattern": "", "source": "name", "params": {}, **r})
        for n, r in enumerate(DEFAULT_RULES, 1)
    ]
    rows += [
        SimpleNamespace(
            id=90,
            kind="wbs_level",
            name="Region",
            enabled=True,
            pattern="",
            source="name",
            sort_order=0,
            params={"depth": 2, "level": "site"},
        ),
        SimpleNamespace(
            id=91,
            kind="wbs_level",
            name="Site",
            enabled=True,
            pattern="",
            source="name",
            sort_order=1,
            params={"depth": 3, "level": "area", "value": "code"},
        ),
        SimpleNamespace(
            id=92,
            kind="wbs_level",
            name="Too deep",
            enabled=True,
            pattern="",
            source="name",
            sort_order=2,
            params={"depth": 9, "level": "zone"},
        ),
    ]
    chain = [{"code": "8", "name": "Construction"}, {"code": "2", "name": "North Region"}, {"code": "EI", "name": "Island"}]
    parsed = parse(row("CV-01 / B / 305", wbs_chain=chain), build(rows))
    assert parsed.groups is not None
    assert (parsed.groups["site"], parsed.groups["area"]) == ("North Region", "EI")
    assert "zone" not in parsed.groups
    # A name the grammar can't read is still unmatched: the WBS alone never makes a link.
    assert parse(row("Mobilisation", wbs_chain=chain), build(rows)).groups is None

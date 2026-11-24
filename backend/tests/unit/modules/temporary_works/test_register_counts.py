"""The register figures for a pinned day: counts, the clearance percentage, gates, breaches, overdue lists, advisory
warnings and the response bodies. The computation reads plain attributes, so stand-ins are enough and no database is
needed. Nothing reads the clock."""

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

from src.modules.temporary_works.constants import CATEGORIES, ITEM_STATUSES
from src.modules.temporary_works.register import load_status_body, rollup_body, summarise

DAY = date(2026, 3, 10)
YESTERDAY = DAY - timedelta(days=1)
TOMORROW = DAY + timedelta(days=1)


def item(item_id: int, status: str, **extra: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": item_id,
        "reference": f"TW-{item_id}",
        "title": f"Item {item_id}",
        "family": "propping",
        "status": status,
        "design_check_category": None,
        "required_load_on": None,
        "required_strike_on": None,
        "scaffold_id": None,
        **extra,
    }
    return SimpleNamespace(**values)


def permit(item_id: int, **extra: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": item_id * 10,
        "item_id": item_id,
        "number": f"P-{item_id}",
        "kind": "load",
        "status": "issued",
        "valid_from": YESTERDAY - timedelta(days=6),
        "valid_to": DAY + timedelta(days=6),
        "design_check_accepted": True,
        "inspection_passed": True,
        **extra,
    }
    return SimpleNamespace(**values)


def run(items: list[SimpleNamespace], permits: list[SimpleNamespace], day: date = DAY, **kwargs: Any) -> dict[str, Any]:
    grouped: dict[int, list[SimpleNamespace]] = {}
    for p in permits:
        grouped.setdefault(p.item_id, []).append(p)
    return rollup_body(summarise(items, grouped, day, **kwargs))


# --- clearance and counting -----------------------------------------------------------------------------------


def test_clearance_is_a_half_up_two_decimal_string_and_absent_for_an_empty_register():
    four = [item(1, "identified"), item(2, "design_checked"), item(3, "loaded"), item(4, "on_hold")]
    assert run(four, [permit(3)])["design_clearance"] == "50.00"
    one_of_three = [item(1, "identified"), item(2, "design_brief"), item(3, "design_checked")]
    two_of_three = [item(1, "identified"), item(2, "approved_to_load"), item(3, "removed")]
    assert run(one_of_three, [])["design_clearance"] == "33.33"
    assert run(two_of_three, [])["design_clearance"] == "66.67"
    assert run([], [])["design_clearance"] is None


def test_an_empty_register_is_compliant_with_zero_filled_tables_and_empty_lists():
    body = run([], [])
    assert body["total"] == 0
    assert body["compliant"] is True
    assert body["as_of"] == DAY
    assert body["status_counts"] == dict.fromkeys(ITEM_STATUSES, 0)
    assert len(body["status_counts"]) == 11
    assert body["category_counts"] == {**{str(c): 0 for c in CATEGORIES}, "unassigned": 0}
    for key in ("breaches", "gates", "overdue_to_load", "overdue_to_strike", "warnings"):
        assert body[key] == [], key


def test_counts_cover_every_status_and_category_and_still_sum_to_the_total_with_a_stray_value():
    items = [
        item(1, "identified", design_check_category=1),
        item(2, "design_checked", design_check_category=3, family="scaffold"),
        item(3, "design_checked"),
        item(4, "not-a-status", design_check_category=7),
    ]
    body = run(items, [])
    assert body["total"] == 4
    assert body["status_counts"]["identified"] == 1
    assert body["status_counts"]["design_checked"] == 2
    assert body["status_counts"]["loaded"] == 0
    assert body["status_counts"]["not-a-status"] == 1  # counted under its own key, never dropped
    assert sum(body["status_counts"].values()) == 4
    assert {k: v for k, v in body["category_counts"].items() if v} == {"1": 1, "3": 1, "unassigned": 1, "7": 1}
    assert body["category_counts"]["0"] == body["category_counts"]["2"] == 0
    assert sum(body["category_counts"].values()) == 4


# --- gates ------------------------------------------------------------------------------------------------------


def gates(items: list[SimpleNamespace], permits: list[SimpleNamespace], day: date = DAY) -> dict[int, tuple[bool, bool]]:
    body = run(items, permits, day)
    return {g["item_id"]: (g["load_gate_open"], g["strike_gate_open"]) for g in body["gates"]}


def test_the_load_gate_needs_a_valid_permit_to_load_with_both_prerequisites_whatever_the_item_status():
    cases = {
        1: permit(1),
        2: permit(2, inspection_passed=False),
        3: permit(3, design_check_accepted=False),
        4: permit(4, status="draft"),
        5: permit(5, valid_to=YESTERDAY),
        6: permit(6, valid_from=None, valid_to=None, status="active"),  # open on both sides
        7: permit(7, valid_from=TOMORROW),
        8: permit(8, kind="dismantle"),
        9: permit(9, status="weird"),
    }
    items = [item(i, "design_brief") for i in cases]  # the item's own status plays no part
    opened = {i: gate[0] for i, gate in gates(items, list(cases.values())).items()}
    assert opened == {1: True, 2: False, 3: False, 4: False, 5: False, 6: True, 7: False, 8: False, 9: False}
    assert gates([item(10, "approved_to_load")], [])[10] == (False, False)


def test_a_permit_is_valid_on_its_last_day_and_not_the_day_after():
    ends_today = [permit(1, valid_to=DAY)]
    assert gates([item(1, "approved_to_load")], ends_today, DAY)[1][0] is True
    assert gates([item(1, "approved_to_load")], ends_today, TOMORROW)[1][0] is False


def test_only_a_valid_permit_to_strike_opens_the_strike_gate_and_the_flags_do_not_matter():
    items = [item(1, "approved_to_strike"), item(2, "approved_to_strike"), item(3, "approved_to_strike")]
    opened = gates(
        items,
        [
            permit(1, kind="dismantle"),
            permit(2, kind="strike", design_check_accepted=False, inspection_passed=False),
            permit(3, kind="strike", status="closed"),
        ],
    )
    assert [opened[i][1] for i in (1, 2, 3)] == [False, True, False]


# --- breach and compliance -----------------------------------------------------------------------------------


def test_bearing_load_with_no_valid_permit_to_load_is_a_breach_naming_the_status_and_the_day():
    statuses = ["in_use", "loaded", "approved_to_load", "approved_to_strike", "on_hold"]
    items = [item(i, status) for i, status in enumerate(statuses, start=1)]
    body = run(items, [permit(1, status="draft")])
    assert [b["item_id"] for b in body["breaches"]] == [1, 2]
    assert "in use" in body["breaches"][0]["reason"]
    assert "2026-03-10" in body["breaches"][0]["reason"]
    assert body["breaches"][0]["reference"] == "TW-1"
    assert body["compliant"] is False


def test_a_valid_permit_clears_the_breach_and_the_prerequisite_flags_are_not_part_of_the_test():
    items = [item(1, "in_use"), item(2, "loaded")]
    body = run(items, [permit(1), permit(2, design_check_accepted=False, inspection_passed=False)])
    assert body["breaches"] == []
    assert body["compliant"] is True


def test_a_later_as_of_day_turns_a_cleared_item_into_a_breach_without_anything_being_stored():
    items = [item(1, "loaded")]
    permits = [permit(1, valid_to=DAY)]
    assert run(items, permits, DAY)["compliant"] is True
    later = run(items, permits, TOMORROW)
    assert [b["item_id"] for b in later["breaches"]] == [1]
    assert items[0].status == "loaded"  # judged, not changed


# --- overdue --------------------------------------------------------------------------------------------------


def test_overdue_to_load_follows_the_status_set_and_never_on_the_boundary_day():
    items = [
        item(1, "design_checked", required_load_on=YESTERDAY),
        item(2, "approved_to_load", required_load_on=YESTERDAY),
        item(3, "on_hold", required_load_on=YESTERDAY),
        item(4, "design_checked", required_load_on=DAY),
        item(5, "design_checked"),
        item(6, "identified", required_load_on=YESTERDAY),
    ]
    body = run(items, [])
    assert [i["id"] for i in body["overdue_to_load"]] == [1, 2, 6]
    assert body["overdue_to_load"][0]["required_load_on"] == "2026-03-09"
    assert body["overdue_to_load"][0]["required_strike_on"] is None
    assert body["overdue_to_load"][0]["reference"] == "TW-1"


def test_overdue_to_strike_counts_only_loaded_in_use_and_approved_to_strike_items():
    statuses = ["in_use", "struck", "removed", "design_checked", "on_hold", "loaded", "approved_to_strike"]
    items = [item(i, status, required_strike_on=YESTERDAY) for i, status in enumerate(statuses, start=1)]
    body = run(items, [permit(1), permit(6)])
    assert [i["id"] for i in body["overdue_to_strike"]] == [1, 6, 7]
    assert run([item(1, "in_use", required_strike_on=DAY)], [permit(1)])["overdue_to_strike"] == []


# --- warnings and strays --------------------------------------------------------------------------------------


def test_warnings_are_advice_that_never_changes_the_compliant_flag():
    items = [item(1, "loaded"), item(2, "in_use", scaffold_id=5), item(3, "approved_to_load")]
    permits = [
        permit(1, inspection_passed=False),  # valid, bearing load, a prerequisite missing
        permit(2, valid_to=DAY + timedelta(days=2)),  # lapsing within three days
        permit(3, kind="strike", valid_to=DAY + timedelta(days=30)),
    ]
    body = run(items, permits, scaffold_reads={5: ("red", True)})
    rules = [(w["item_id"], w["rule"]) for w in body["warnings"]]
    assert (1, "prerequisites-missing") in rules
    assert (2, "permit-lapsing") in rules
    assert (2, "scaffold-not-usable") in rules
    assert not [r for r in rules if r[0] == 3]
    assert body["breaches"] == []
    assert body["compliant"] is True


def test_a_linked_scaffold_that_is_missing_reads_as_unknown_and_with_the_module_off_nothing_is_said():
    items = [item(1, "design_checked", scaffold_id=9)]
    assert [w["rule"] for w in run(items, [], scaffold_reads={})["warnings"]] == ["scaffold-not-usable"]
    assert run(items, [], scaffold_reads=None)["warnings"] == []  # scaffolds module off
    assert run(items, [], scaffold_reads={9: ("green", False)})["warnings"] == []
    assert run([item(2, "design_checked")], [], scaffold_reads={})["warnings"] == []  # unlinked items have no such field


def test_a_stray_status_kind_or_permit_status_does_not_break_the_rollup():
    items = [item(1, "bogus"), item(2, "loaded"), item(3, None)]
    permits = [permit(1, kind="bogus", status="weird"), permit(2, kind=None, status=None), permit(3, valid_to="not a day")]
    body = run(items, permits)
    assert body["total"] == 3
    assert [b["item_id"] for b in body["breaches"]] == [2]  # a permit that is not clearly valid never clears anything
    assert sum(body["status_counts"].values()) == 3


def test_the_load_status_body_carries_only_the_gates_and_breaches():
    items = [item(1, "in_use"), item(2, "approved_to_load")]
    body = load_status_body(summarise(items, {}, DAY))
    assert set(body) == {"as_of", "total", "compliant", "gates", "breaches"}
    assert body["total"] == 2
    assert body["compliant"] is False
    assert [g["item_id"] for g in body["gates"]] == [1, 2]
    assert all(g["load_gate_open"] is False and g["strike_gate_open"] is False for g in body["gates"])

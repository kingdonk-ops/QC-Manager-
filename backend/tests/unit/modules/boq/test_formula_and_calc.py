from decimal import Decimal as D

import pytest

from src.modules.boq import calc, exchange
from src.modules.boq.formula import FormulaError, evaluate


@pytest.mark.parametrize(
    ("formula", "value"),
    [
        ("2*3.5+1.2", "8.2"),
        ("= 2 * (3 + 4)", "14"),
        ("-3+5", "2"),
        ("10/4", "2.5"),
        ("2^3", "8"),
        ("-2^2", "-4"),
        ("3,5 x 2", "7.0"),
        ("1.5 × 4", "6.0"),
        ("((1))", "1"),
        ("4 ÷ 2", "2"),
        ("--1", "1"),
    ],
)
def test_formulas_evaluate(formula: str, value: str):
    assert evaluate(formula) == D(value)


@pytest.mark.parametrize(
    "formula",
    [
        "",
        "2*",
        "(1+2",
        "1+2)",
        "1/0",
        "2**3",
        "abc",
        "__import__('os')",
        "1.2.3",
        "2^0.5",
        "2^99",
        "(" * 40 + "1" + ")" * 40,
        "9" * 201,
    ],
)
def test_bad_formulas_are_refused(formula: str):
    with pytest.raises(FormulaError):
        evaluate(formula)


def _tree() -> list[calc.Node]:
    return [
        calc.Node(1, None, sort=0, kind="section"),
        calc.Node(2, 1, sort=0, quantity=D(10), unit_rate=D("2.5")),
        calc.Node(3, 1, sort=1, quantity=D(4), lines=[calc.Line(D("1.05"), D("12.50")), calc.Line(D("0.35"), D(60))]),
        calc.Node(4, None, sort=1, kind="section"),
        calc.Node(5, 4, sort=0, quantity=D(1)),  # a position broken into sub-positions
        calc.Node(6, 5, sort=0, quantity=D(3), unit_rate=D(7)),
        calc.Node(7, 5, sort=1, quantity=D(1), lines=[calc.Line(D(2), D(10), waste_pct=D(10))]),
    ]


def test_rates_come_from_resources_and_totals_roll_up():
    result = calc.rollup(_tree())
    assert result[3].unit_rate == D("34.1250")
    assert result[3].total == D("136.50")
    assert result[1].total == D("161.50")
    assert result[7].unit_rate == D("22.0000")  # 2 × 1.1 × 10
    assert result[5].total == D("43.00") and result[5].has_children
    assert result[4].total == D("43.00")
    assert calc.net_total(_tree(), result) == D("204.50")


def test_ordinals_and_depths():
    result = calc.rollup(_tree())
    assert [(i, result[i].ordinal, result[i].depth) for i in (1, 2, 3, 4, 5, 6, 7)] == [
        (1, "1", 0),
        (2, "1.1", 1),
        (3, "1.2", 1),
        (4, "2", 0),
        (5, "2.1", 1),
        (6, "2.1.1", 2),
        (7, "2.1.2", 2),
    ]


def test_ordinals_renumber_after_a_move():
    nodes = _tree()
    by_id = {n.id: n for n in nodes}
    # move 3 into section 4, above 5
    by_id[3].parent_id = 4
    for sort, nid in enumerate(calc.reorder([5], 3, before_id=5)):
        by_id[nid].sort = sort
    order = [(n.id, ordinal) for n, _, ordinal in calc.depth_first(nodes)]
    assert order == [(1, "1"), (2, "1.1"), (4, "2"), (3, "2.1"), (5, "2.2"), (6, "2.2.1"), (7, "2.2.2")]
    assert calc.rollup(nodes)[1].total == D("25.00")


def test_reorder_and_descendants():
    assert calc.reorder([1, 2, 3], 3, before_id=1) == [3, 1, 2]
    assert calc.reorder([1, 2, 3], 1, before_id=None) == [2, 3, 1]
    assert calc.reorder([1, 2], 9, before_id=2) == [1, 9, 2]
    assert calc.descendants(_tree(), 4) == {5, 6, 7}


def test_markups():
    totals = calc.markups(D("1000"), D(10), D(5), D(2), D(19))
    assert totals == {
        "net_total": D("1000.00"),
        "overhead": D("100.00"),
        "profit": D("55.00"),
        "contingency": D("20.00"),
        "subtotal": D("1175.00"),
        "tax": D("223.25"),
        "grand_total": D("1398.25"),
    }


def test_import_hierarchy_from_ordinals_and_levels():
    rows = [
        {"No": "1", "Text": "Section", "Unit": None, "Qty": None},
        {"No": "1.1", "Text": "Item", "Unit": "m", "Qty": "1.234,5"},
        {"No": "1.2", "Text": "Group", "Unit": None, "Qty": None},
        {"No": "1.2.1", "Text": "Sub", "Unit": "pcs", "Qty": 2},
        {"No": "2", "Text": "Loose", "Unit": "m", "Qty": 3},
    ]
    built, errors = exchange.rows_from_table(rows, {"ordinal": "No", "short_text": "Text", "unit": "Unit", "quantity": "Qty"})
    assert errors == []
    assert [(r.depth, r.parent, r.kind) for r in built] == [
        (0, None, "section"),
        (1, 0, "position"),
        (2 - 1, 0, "section"),
        (2, 2, "position"),
        (0, None, "position"),
    ]
    assert built[1].fields["quantity"] == D("1234.5")

    levels = [{"L": 1, "T": "A"}, {"L": 2, "T": "B", "Q": 1}, {"L": 3, "T": "C", "Q": 1}, {"L": 2, "T": "D", "Q": 1}]
    built, _ = exchange.rows_from_table(levels, {"level": "L", "short_text": "T", "quantity": "Q"})
    assert [r.parent for r in built] == [None, 0, 1, 0]
    assert exchange.auto_mapping(["OZ", "Kurztext", "Menge", "EP", "Einheit"]) == {
        "ordinal": "OZ",
        "short_text": "Kurztext",
        "unit": "Einheit",
        "quantity": "Menge",
        "rate": "EP",
    }


def test_gaeb_import_refuses_entities():
    with pytest.raises(exchange.ImportError_):
        exchange.rows_from_gaeb(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><GAEB/>')
    with pytest.raises(exchange.ImportError_):
        exchange.rows_from_gaeb(b"<GAEB><Award/></GAEB>")

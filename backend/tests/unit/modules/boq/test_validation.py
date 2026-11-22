from decimal import Decimal as D

from src.modules.boq.validation import Finding, VLine, VNode, score, validate


def _ids(report: dict, rule: str) -> list[int | None]:
    return [f["position_id"] for f in report["findings"] if f["rule_id"] == rule]


def _item(id: int, parent: int | None, ordinal: str, **kw) -> VNode:
    base = {"short_text": f"Item {id}", "unit": "m", "quantity": D(1), "unit_rate": D(10), "total": D(10)}
    return VNode(id, parent, "position", ordinal, **{**base, **kw})


def test_score_formula():
    assert score([], 5) == 100
    assert score([Finding("x", "error", "")], 1) == 0
    assert score([Finding("x", "error", ""), Finding("y", "warning", "")], 4) == 68  # 1 - 13/40
    assert score([Finding("x", "info", "")] * 50, 1) == 0
    assert score([], 0) == 100


def test_boq_quality_rules():
    bill = [
        VNode(1, None, "section", "1", short_text="Section", has_children=True),
        _item(2, 1, "1.1", code="A1"),
        _item(3, 1, "1.2", code="a1", quantity=None, total=D(0)),
        _item(4, 1, "1.3", unit=None),
        _item(5, 1, "1.4", unit_rate=D(0), total=D(0)),
        _item(
            6,
            1,
            "1.5",
            unit_rate=D(0),
            total=D(0),
            lines=[VLine(1, "R1", D(0), D(0))],
        ),
        _item(7, 1, "1.6", lines=[VLine(1, "R1", D(100), D(10), rate_override=D(100))]),
        VNode(8, None, "section", "2", short_text="Empty"),
        _item(9, None, "3", short_text="", quantity=D(0), total=D(0)),
    ]
    report = validate(bill, "boq_quality")
    assert _ids(report, "BQ01") == [9]
    assert _ids(report, "BQ02") == [3]
    assert _ids(report, "BQ03") == [4]
    assert _ids(report, "BQ04") == [5, 6]
    assert [f["severity"] for f in report["findings"] if f["rule_id"] == "BQ04"] == ["error", "warning"]
    assert _ids(report, "BQ05") == [9]
    assert _ids(report, "BQ06") == [2, 3]
    assert _ids(report, "BQ07") == [7]
    assert _ids(report, "BQ08") == [8]
    assert 0 <= report["score"] < 100
    assert validate([], "boq_quality")["findings"][0]["rule_id"] == "BQ09"


def test_clean_bill_scores_100():
    bill = [VNode(1, None, "section", "1", short_text="S", has_children=True), _item(2, 1, "1.1")]
    assert validate(bill, "boq_quality")["score"] == 100


def test_din276():
    bill = [
        VNode(1, None, "section", "1", short_text="Building", classification="300", has_children=True),
        _item(2, 1, "1.1", classification="KG 330"),
        _item(3, 1, "1.2", classification="420"),
        _item(4, 1, "1.3", classification="950"),
        _item(5, 1, "1.4"),
    ]
    report = validate(bill, "din276")
    assert _ids(report, "DIN01") == [5]
    assert _ids(report, "DIN02") == [4]
    assert _ids(report, "DIN03") == []  # 300 and 400 both present
    assert _ids(report, "DIN04") == [3]
    assert _ids(report, "DIN05") == [None]  # 400 priced without a 400 section
    complete = [
        VNode(1, None, "section", "1", short_text="300", classification="300", has_children=True),
        _item(2, 1, "1.1", classification="330"),
        VNode(3, None, "section", "2", short_text="400", classification="400", has_children=True),
        _item(4, 3, "2.1", classification="KG 420"),
    ]
    assert validate(complete, "din276")["findings"] == []
    assert _ids(
        validate([_item(1, None, "1", classification="330"), _item(2, None, "2", classification="420")], "din276"), "DIN05"
    ) == [None, None]


def test_din276_required_groups():
    only_300 = [_item(1, None, "1", classification="330")]
    messages = [f["message"] for f in validate(only_300, "din276")["findings"] if f["rule_id"] == "DIN03"]
    assert len(messages) == 1 and "400" in messages[0]


def test_nrm():
    bill = [
        VNode(1, None, "section", "1", short_text="Superstructure", classification="2", has_children=True),
        VNode(2, 1, "section", "1.1", short_text="Frame", classification="2.1", has_children=True),
        _item(3, 2, "1.1.1", classification="2.1.1"),
        _item(4, 2, "1.1.2", classification="3.1.1"),
        _item(5, 2, "1.1.3", classification="2-1"),
        _item(6, 2, "1.1.4", classification="22.1.1"),
        _item(7, 2, "1.1.5"),
    ]
    report = validate(bill, "nrm")
    assert _ids(report, "NRM01") == [7]
    assert _ids(report, "NRM02") == [5]
    assert _ids(report, "NRM03") == [6]
    assert _ids(report, "NRM04") == [4, 6]


def test_masterformat():
    bill = [
        VNode(1, None, "section", "1", short_text="Thermal", classification="07 00 00", has_children=True),
        _item(2, 1, "1.1", classification="07 21 13"),
        _item(3, 1, "1.2", classification="072113"),
        _item(4, 1, "1.3", classification="55 10 00"),
        _item(5, 1, "1.4", classification="09 91 23.13"),
        _item(6, 1, "1.5"),
    ]
    report = validate(bill, "masterformat")
    assert _ids(report, "MF01") == [6]
    assert _ids(report, "MF02") == [3]
    assert _ids(report, "MF03") == [4]
    assert _ids(report, "MF04") == [4, 5]

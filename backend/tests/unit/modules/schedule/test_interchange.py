"""Reading P6 XER, P6 XML and MS Project XML, and writing MS Project XML that reads back."""

from datetime import date
from pathlib import Path

import pytest

from src.modules.schedule.interchange import (
    ExportActivity,
    ImportFormatError,
    detect,
    parse,
    parse_msp_xml,
    parse_xer_calendar,
    write_msp_xml,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def by_code(imported):
    return {a.code: a for a in imported.activities}


def test_detects_formats_by_content():
    assert detect(load("demo.xer")) == "xer"
    assert detect(load("demo_p6.xml")) == "p6_xml"
    assert detect(load("demo_msp.xml")) == "msp_xml"
    with pytest.raises(ImportFormatError):
        detect(b"name,start\nfoo,2026-01-01\n")


def test_xer_activities_wbs_links_and_calendar():
    x = parse(load("demo.xer"))
    assert x.format == "xer" and x.project_name == "DEMO-1"
    acts = by_code(x)
    assert set(acts) == {"CIV", "MEP", "A1000", "A1010", "A1020", "M1030"}
    assert acts["CIV"].type == "summary" and acts["CIV"].parent_key is None
    assert acts["A1000"].parent_key == acts["CIV"].key
    assert (acts["A1000"].wbs_code, acts["A1010"].wbs_code, acts["A1020"].wbs_code) == ("1.1", "1.2", "2.1")
    assert acts["A1000"].duration == 5 and acts["A1010"].duration == 3 and acts["A1020"].duration == 10
    assert acts["A1000"].percent_complete == 100 and acts["A1000"].actual_finish == date(2026, 1, 12)
    assert acts["A1010"].actual_start == date(2026, 1, 13) and acts["A1010"].percent_complete == 50
    assert acts["A1000"].budget_hours == 120
    assert acts["M1030"].type == "milestone" and acts["M1030"].duration == 0
    assert (acts["A1020"].constraint_type, acts["A1020"].constraint_date) == ("snet", date(2026, 1, 14))
    assert acts["M1030"].constraint_type == "fnlt"
    links = {(lk.predecessor, lk.successor): (lk.type, lk.lag) for lk in x.links}
    key = {c: a.key for c, a in acts.items()}
    assert links == {
        (key["A1000"], key["A1010"]): ("FS", 0),
        (key["A1010"], key["A1020"]): ("SS", 1),
        (key["A1020"], key["M1030"]): ("FF", -2),
        (key["A1010"], key["M1030"]): ("SF", 0),
    }
    assert x.working_days == [0, 1, 2, 3, 4]
    assert x.holidays == [date(2026, 1, 9)]  # the half-day exception on the 16th is still worked
    assert x.data_date == date(2026, 1, 5)


def test_xer_calendar_with_a_weekend_day_worked():
    blob = "(0||DaysOfWeek()((0||1()())(0||7()((0||0(s|08:00|f|12:00)())))(0||2()((0||0(s|08:00|f|16:00)())))))"
    assert parse_xer_calendar(blob) == ([0, 5], [])


def test_p6_xml_activities_wbs_links_and_calendar():
    x = parse(load("demo_p6.xml"))
    assert x.format == "p6_xml" and x.project_name == "XML-DEMO"
    acts = by_code(x)
    assert acts["STR"].type == "summary" and acts["L1"].parent_key == acts["STR"].key
    assert acts["S100"].parent_key == acts["L1"].key
    assert acts["S100"].wbs_code == "1.1.1" and acts["MS1"].wbs_code == "1.2"
    assert acts["S100"].duration == 5 and acts["S110"].duration == 3  # ten-hour days
    assert acts["S110"].constraint_type == "snet" and acts["S110"].constraint_date == date(2026, 1, 12)
    assert acts["MS1"].type == "milestone"
    assert sorted((lk.type, lk.lag) for lk in x.links) == [("FS", -1), ("SS", 2)]
    assert x.working_days == [0, 1, 2, 3, 4, 5]
    assert x.holidays == [date(2026, 1, 26)]
    assert x.data_date == date(2026, 1, 5)


def test_msp_xml_tasks_outline_links_and_calendar():
    x = parse(load("demo_msp.xml"))
    assert x.format == "msp_xml" and x.project_name == "MSP demo"
    acts = by_code(x)
    assert "0" not in acts  # the project summary task
    assert acts["1"].type == "summary" and acts["2"].parent_key == acts["1"].key and acts["4"].parent_key is None
    assert acts["2"].wbs_code == "1.1" and acts["2"].duration == 5 and acts["2"].budget_hours == 120
    assert acts["2"].actual_start == date(2026, 1, 5) and acts["2"].percent_complete == 40
    assert acts["3"].constraint_type == "fnlt" and acts["3"].constraint_date == date(2026, 1, 30)
    assert acts["4"].type == "milestone"
    links = sorted((lk.predecessor, lk.successor, lk.type, lk.lag) for lk in x.links)
    assert links == [("task:2", "task:3", "FS", 2), ("task:2", "task:4", "SS", 0), ("task:3", "task:4", "FF", -1)]
    assert x.working_days == [0, 1, 2, 3, 4]
    assert x.holidays == [date(2026, 1, 19), date(2026, 1, 20)]
    assert x.data_date == date(2026, 1, 7)


def test_xml_with_entity_declarations_is_refused():
    evil = (
        b'<?xml version="1.0"?><!DOCTYPE p [<!ENTITY a "aaaa">]>'
        b'<Project xmlns="http://schemas.microsoft.com/project"><Tasks/></Project>'
    )
    with pytest.raises(ImportFormatError):
        parse(evil)


def _row(uid, wbs, name, level, summary, milestone, duration, start, finish, pct, constraint, cdate, astart, notes, preds):
    return ExportActivity(
        uid, wbs, name, level, summary, milestone, duration, start, finish, pct, constraint, cdate, astart, None, notes, preds
    )


def test_msp_xml_round_trip():
    jan = date(2026, 1, 5)
    rows = [
        _row(1, "1", "Phase & co", 1, True, False, 3, jan, date(2026, 1, 7), 0, "asap", None, None, None, []),
        _row(2, "1.1", "Dig", 2, False, False, 3, jan, date(2026, 1, 7), 50, "snet", jan, jan, "n", []),
        _row(
            3, "2", "Done", 1, False, True, 0, date(2026, 1, 8), date(2026, 1, 8), 0, "asap", None, None, None, [(2, "FF", -1)]
        ),
    ]
    body = write_msp_xml("Demo <1>", jan, rows, [0, 1, 2, 3, 4], [date(2026, 1, 26)])
    back = parse_msp_xml(body)
    assert back.project_name == "Demo <1>"
    assert [a.name for a in back.activities] == ["Phase & co", "Dig", "Done"]
    assert back.activities[1].parent_key == back.activities[0].key
    assert back.activities[1].constraint_type == "snet" and back.activities[1].duration == 3
    assert [(lk.type, lk.lag) for lk in back.links] == [("FF", -1)]
    assert back.holidays == [date(2026, 1, 26)] and back.working_days == [0, 1, 2, 3, 4]

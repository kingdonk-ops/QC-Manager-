"""Progress import parsing, and the roll-ups and S-curve built from plain package plans."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.modules.evm import importer, service
from src.modules.evm.constants import Basis, EacMethod, GroupBy, Interval


def test_headers_match_loosely():
    assert importer.mapping(["WP Code", "% Complete", "Actual Hours", "Remarks"]) == {
        "code": "WP Code",
        "percent": "% Complete",
        "actual_hours": "Actual Hours",
        "comment": "Remarks",
    }


def test_parse_percent_and_hours():
    rows, issues = importer.parse(
        ["code", "percent", "actual hours"],
        [
            {"code": "A1", "percent": 45, "actual hours": "12.5"},
            {"code": "A2", "percent": "60%", "actual hours": None},
            {"code": "", "percent": 1, "actual hours": 1},
        ],
    )
    assert issues == []
    assert [(r["code"], r["percent_complete"], r["actual_hours"]) for r in rows] == [
        ("A1", Decimal("45.000"), Decimal("12.50")),
        ("A2", Decimal("60.000"), None),
    ]


def test_fractions_from_an_excel_percent_column():
    rows, _ = importer.parse(["code", "percent"], [{"code": "A", "percent": 0.25}, {"code": "B", "percent": 1}])
    assert [r["percent_complete"] for r in rows] == [Decimal("25.000"), Decimal("100.000")]


def test_bad_values_are_reported_by_row():
    rows, issues = importer.parse(
        ["code", "percent", "actual hours"],
        [
            {"code": "A", "percent": "lots", "actual hours": 1},
            {"code": "B", "percent": 140, "actual hours": 1},
            {"code": "C", "percent": 50, "actual hours": -3},
            {"code": "D", "percent": 50, "actual hours": 3},
        ],
    )
    assert [r["code"] for r in rows] == ["D"]
    assert [row for row, _ in issues] == [2, 3, 4]


def test_missing_columns():
    assert importer.parse(["name"], [])[1] == [(1, "No 'code' column.")]
    assert importer.parse(["code", "name"], [])[1] == [(1, "No 'percent' or 'actual hours' column.")]


# --- roll-ups ------------------------------------------------------------------------------------------


def plan(pid: int, code: str, account: str | None, hours: float, cost: float | None = None) -> service.Plan:
    return service.Plan(
        id=pid,
        code=code,
        name=code,
        control_account=account,
        discipline="Civil" if pid % 2 else "Mech",
        start=date(2026, 1, 1),
        finish=date(2026, 1, 10),
        hours=hours,
        cost=cost,
        curve="linear",
    )


def progress(on: date, percent: float, hours: float, cost: float | None = None) -> service.Progress:
    return service.Progress(on=on, percent=percent, actual_hours=hours, actual_cost=cost, comment=None)


@pytest.fixture
def setup() -> tuple[list[service.Plan], service.History]:
    plans = [plan(1, "A", "CA-1", 100, 1000), plan(2, "B", "CA-1", 100), plan(3, "C", None, 200, 4000)]
    hist = service.History(
        by_package={
            1: [progress(date(2026, 1, 3), 20, 30, 300), progress(date(2026, 1, 5), 40, 50, 500)],
            3: [progress(date(2026, 1, 5), 50, 80, 1600)],
        }
    )
    return plans, hist


def test_progress_as_of_takes_the_latest_record(setup):
    _, hist = setup
    assert hist.as_of(1, date(2026, 1, 2)) is None
    assert hist.as_of(1, date(2026, 1, 4)).percent == 20
    assert hist.as_of(1, date(2026, 2, 1)).percent == 40
    assert hist.as_of(2, date(2026, 2, 1)) is None


def test_project_rollup_on_hours(setup):
    plans, hist = setup
    total, rows = service.metrics(plans, hist, date(2026, 1, 5), Basis.HOURS, GroupBy.PROJECT, EacMethod.CPI)
    # PV: half of every package (400 x 0.5); EV: 40 + 0 + 100; AC: 50 + 0 + 80
    assert (total["bac"], total["pv"], total["ev"], total["ac"]) == (400, 200, 140, 130)
    assert total["spi"] == 0.7
    assert total["cpi"] == round(140 / 130, 4)
    assert rows[0]["key"] == "project"
    assert rows[0]["packages"] == 3


def test_rollup_by_control_account(setup):
    plans, hist = setup
    _, rows = service.metrics(plans, hist, date(2026, 1, 5), Basis.HOURS, GroupBy.ACCOUNT, EacMethod.CPI)
    assert [(r["key"], r["bac"], r["ev"], r["packages"]) for r in rows] == [
        ("CA-1", 200, 40, 2),
        (service.NO_GROUP, 200, 100, 1),
    ]


def test_package_rows_and_no_progress(setup):
    plans, hist = setup
    _, rows = service.metrics(plans, hist, date(2026, 1, 5), Basis.HOURS, GroupBy.PACKAGE, EacMethod.CPI)
    b = next(r for r in rows if r["key"] == "B")
    assert b["ev"] == 0
    assert b["ac"] == 0
    assert b["cpi"] is None
    assert b["eac"] is None
    assert b["spi"] == 0


def test_cost_basis_skips_packages_without_a_cost_budget(setup):
    plans, hist = setup
    total, rows = service.metrics(plans, hist, date(2026, 1, 5), Basis.COST, GroupBy.PACKAGE, EacMethod.CPI)
    assert [r["key"] for r in rows] == ["A", "C"]
    assert (total["bac"], total["ev"], total["ac"]) == (5000, 400 + 2000, 2100)
    # productivity stays in hours on the cost basis
    assert total["productivity"] == round(140 / 130, 4)


def test_s_curve_weekly(setup):
    plans, hist = setup
    project = cast(Any, SimpleNamespace(id=1, start_date=None, end_date=None, currency="AUD"))
    curve = service.s_curve(plans, hist, project, date(2026, 1, 5), Interval.WEEK, Basis.HOURS, EacMethod.CPI)
    points = curve["points"]
    # weeks starting 29 Dec, 5 Jan; the packages run 1-10 Jan
    assert [p["period_start"] for p in points][:2] == [date(2025, 12, 29), date(2026, 1, 5)]
    assert points[0]["pv"] == 160  # 4 of 10 days by Sun 4 Jan
    assert points[0]["ev"] == 20  # A at 20%
    assert points[0]["ac"] == 30
    assert points[1]["ev"] == 140  # as at the data date inside the week
    assert points[1]["forecast"] == 130  # the forecast starts from AC at the data date
    assert points[-1]["pv"] == 400
    assert points[-1]["forecast"] == curve["eac"]
    assert all(p["ev"] is None for p in points if p["period_start"] > date(2026, 1, 5))
    assert sum(p["period_pv"] for p in points) == pytest.approx(400)

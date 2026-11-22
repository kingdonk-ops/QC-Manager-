"""The reporting registry's pure parts: due dates, filters, pivots, KPI colours, column guessing."""

from datetime import UTC, date, datetime

import pytest

from src.infrastructure.reporting import Column, Dataset, ImportField, Kpi
from src.infrastructure.reporting.export import display
from src.infrastructure.reporting.schemas import auto_mapping
from src.infrastructure.reporting.tables import FilterError, apply_filters, number, pivot, pivot_table
from src.modules.reporting.schedules import next_run


async def _no_rows(db, project_id, filters):
    return []


DATASET = Dataset(
    "demo",
    "demo",
    "Demo",
    [Column("status", "Status"), Column("amount", "Amount", "money"), Column("due", "Due", "date"), Column("ok", "OK", "bool")],
    rows=_no_rows,
)

ROWS = [
    {"status": "Open", "amount": 100, "due": date(2026, 1, 5), "ok": True},
    {"status": "open", "amount": "250.50", "due": date(2026, 2, 1), "ok": False},
    {"status": "closed", "amount": None, "due": None, "ok": True},
]


# --- schedules -----------------------------------------------------------------------------------------


def test_a_weekly_schedule_runs_next_on_its_weekday_in_its_time_zone():
    # Sunday 22 Nov 2026 08:00 UTC is 16:00 in Perth; the next Monday 07:00 AWST is Sunday 29 Nov 23:00 UTC.
    after = datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
    assert next_run("weekly", "07:00", "Australia/Perth", after, weekday=0) == datetime(2026, 11, 22, 23, 0, tzinfo=UTC)
    # Exactly at the due time, it moves on a week.
    due = datetime(2026, 11, 22, 23, 0, tzinfo=UTC)
    assert next_run("weekly", "07:00", "Australia/Perth", due, weekday=0) == datetime(2026, 11, 29, 23, 0, tzinfo=UTC)


def test_a_daily_schedule_runs_later_today_or_tomorrow():
    after = datetime(2026, 11, 22, 0, 30, tzinfo=UTC)  # 08:30 in Perth
    assert next_run("daily", "09:00", "Australia/Perth", after) == datetime(2026, 11, 22, 1, 0, tzinfo=UTC)
    assert next_run("daily", "08:00", "Australia/Perth", after) == datetime(2026, 11, 23, 0, 0, tzinfo=UTC)


def test_a_monthly_schedule_falls_back_to_the_last_day_of_short_months():
    after = datetime(2027, 2, 1, tzinfo=UTC)
    assert next_run("monthly", "06:00", "UTC", after, day_of_month=31) == datetime(2027, 2, 28, 6, 0, tzinfo=UTC)
    assert next_run("monthly", "06:00", "UTC", datetime(2027, 3, 1, tzinfo=UTC), day_of_month=31) == datetime(
        2027, 3, 31, 6, 0, tzinfo=UTC
    )


def test_wall_clock_time_holds_across_daylight_saving():
    # Sydney moves to daylight time on 4 Oct 2026: 07:00 local is 21:00 UTC before and 20:00 UTC after.
    before = next_run("daily", "07:00", "Australia/Sydney", datetime(2026, 10, 1, 12, tzinfo=UTC))
    after = next_run("daily", "07:00", "Australia/Sydney", datetime(2026, 10, 10, 12, tzinfo=UTC))
    assert (before.hour, after.hour) == (21, 20)


# --- filters -------------------------------------------------------------------------------------------


def test_filters_compare_by_column_type():
    assert len(apply_filters(DATASET, ROWS, {"status": "OPEN"})) == 2
    assert len(apply_filters(DATASET, ROWS, {"status": ["closed", "x"]})) == 1
    assert len(apply_filters(DATASET, ROWS, {"amount": {"gt": 150}})) == 1
    assert len(apply_filters(DATASET, ROWS, {"due": {"gte": "2026-01-01", "lt": "2026-02-01"}})) == 1
    assert len(apply_filters(DATASET, ROWS, {"due": {"empty": True}})) == 1
    assert len(apply_filters(DATASET, ROWS, {"ok": "yes"})) == 2
    assert len(apply_filters(DATASET, ROWS, {"status": {"contains": "pe"}})) == 2


def test_filters_refuse_unknown_columns_and_operators():
    with pytest.raises(FilterError):
        apply_filters(DATASET, ROWS, {"nope": 1})
    with pytest.raises(FilterError):
        apply_filters(DATASET, ROWS, {"amount": {"about": 1}})


def test_numbers_read_spreadsheet_money():
    assert number("$1,250.50") == 1250.5
    assert number("(300)") == -300
    assert number("lots") is None
    assert number(True) is None
    assert display(1234.5, "money") == "1,234.50"
    assert display(True, "bool") == "Yes"


# --- pivot ---------------------------------------------------------------------------------------------


def test_pivot_totals_come_from_raw_values_not_cell_averages():
    rows = [
        {"region": "AU", "status": "on", "budget": 100},
        {"region": "AU", "status": "on", "budget": 200},
        {"region": "AU", "status": "over", "budget": 600},
        {"region": "UK", "status": "on", "budget": 50},
    ]
    result = pivot(rows, ["region"], ["status"], [("budget", "avg"), ("*", "count")])
    assert result["row_keys"] == [["AU"], ["UK"]]
    assert result["column_keys"] == [["on"], ["over"]]
    assert result["cells"][0] == [[150.0, 2.0], [600.0, 1.0]]
    assert result["cells"][1] == [[50.0, 1.0], [None, None]]
    assert result["row_totals"][0] == [300.0, 3.0]  # not (150 + 600) / 2
    assert result["column_totals"][0] == [116.666667, 3.0]
    assert result["grand_total"] == [237.5, 4.0]

    headers, table = pivot_table(result, {"region": "Region", "budget": "Budget"})
    assert headers[0] == "Region" and headers[1] == "on · Budget (avg)"
    assert table[-1][0] == "Total"


def test_pivot_with_no_dimensions_is_one_grand_total():
    result = pivot([{"x": 1}, {"x": 3}], [], [], [("x", "sum"), ("x", "max"), ("x", "min")])
    assert result["cells"] == [[[4.0, 3.0, 1.0]]]


# --- KPIs and import mapping ---------------------------------------------------------------------------


async def _zero(db, project_id):
    return 0


def test_kpi_status_reads_thresholds_in_the_good_direction():
    up = Kpi("k", "m", "Margin", _zero, thresholds=(10, 0))
    assert [up.status(v) for v in (12, 5, -1, None)] == ["good", "warning", "bad", "neutral"]
    down = Kpi("k", "m", "Overdue", _zero, good="down", thresholds=(0, 5))
    assert [down.status(v) for v in (0, 3, 6)] == ["good", "warning", "bad"]
    assert Kpi("k", "m", "Count", _zero).status(4) == "neutral"


def test_auto_mapping_matches_keys_labels_and_aliases_once():
    fields = [
        ImportField("code", "Code", aliases=("cost code",)),
        ImportField("budget", "Budget"),
        ImportField("forecast_cost", "Forecast cost", aliases=("forecast", "eac")),
    ]
    assert auto_mapping(fields, ["Cost Code", "BUDGET", "EAC", "Notes"]) == {
        "code": "Cost Code",
        "budget": "BUDGET",
        "forecast_cost": "EAC",
    }

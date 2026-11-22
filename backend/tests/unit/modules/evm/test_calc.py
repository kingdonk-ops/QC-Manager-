"""Earned value formulas, planned distribution curves and periods, against worked textbook figures."""

from datetime import date

import pytest

from src.modules.evm import calc
from src.modules.evm.constants import Curve, EacMethod, Interval


def approx(value: float | None, expected: float) -> bool:
    return value is not None and value == pytest.approx(expected, abs=1e-4)


# --- the classic worked example: BAC 1000, PV 500, EV 400, AC 450 -------------------------------------


@pytest.fixture
def textbook() -> calc.Metrics:
    return calc.compute(bac=1000, pv=500, ev=400, ac=450)


def test_variances(textbook: calc.Metrics):
    assert textbook.sv == -100
    assert textbook.cv == -50


def test_performance_indices(textbook: calc.Metrics):
    assert approx(textbook.spi, 0.8)
    assert approx(textbook.cpi, 400 / 450)


def test_eac_by_cpi_is_the_default(textbook: calc.Metrics):
    assert approx(textbook.eac, 1125)
    assert approx(textbook.etc, 675)
    assert approx(textbook.vac, -125)


def test_eac_at_budget_rate():
    m = calc.compute(1000, 500, 400, 450, EacMethod.BUDGET_RATE)
    assert approx(m.eac, 1050)
    assert approx(m.etc, 600)
    assert approx(m.vac, -50)


def test_eac_by_cpi_and_spi():
    m = calc.compute(1000, 500, 400, 450, EacMethod.CPI_SPI)
    # 450 + 600 / (0.8889 x 0.8) = 450 + 843.75
    assert approx(m.eac, 1293.75)


def test_tcpi_to_bac_and_to_eac(textbook: calc.Metrics):
    assert approx(textbook.tcpi, 600 / 550)
    assert approx(textbook.tcpi_eac, 600 / 675)


def test_percentages_and_productivity(textbook: calc.Metrics):
    assert approx(textbook.percent_planned, 50)
    assert approx(textbook.percent_complete, 40)
    assert approx(textbook.productivity, 400 / 450)


def test_productivity_uses_hours_when_given():
    m = calc.compute(10_000, 5000, 4000, 6000, earned_hours=80, actual_hours=100)
    assert approx(m.productivity, 0.8)
    assert approx(m.cpi, 4000 / 6000)


def test_ahead_and_under_budget():
    m = calc.compute(bac=200, pv=100, ev=120, ac=100)
    assert approx(m.spi, 1.2)
    assert approx(m.cpi, 1.2)
    assert m.sv == 20
    assert m.cv == 20
    assert approx(m.eac, 200 / 1.2)
    assert m.vac is not None and m.vac > 0


# --- zero divisions answer None -----------------------------------------------------------------------


def test_no_progress_at_all():
    m = calc.compute(bac=100, pv=0, ev=0, ac=0)
    assert m.spi is None
    assert m.cpi is None
    assert m.eac is None
    assert m.etc is None
    assert m.vac is None
    assert m.tcpi_eac is None
    assert m.productivity is None
    assert approx(m.tcpi, 1.0)
    assert approx(m.percent_complete, 0)


def test_zero_actuals_leave_cpi_and_eac_empty():
    m = calc.compute(bac=100, pv=50, ev=40, ac=0)
    assert approx(m.spi, 0.8)
    assert m.cpi is None
    assert m.eac is None
    assert calc.compute(100, 50, 40, 0, EacMethod.BUDGET_RATE).eac == 60
    assert calc.compute(100, 50, 40, 0, EacMethod.CPI_SPI).eac is None


def test_nothing_earned_yet_gives_a_zero_cpi_but_no_eac():
    m = calc.compute(bac=100, pv=50, ev=0, ac=20)
    assert m.cpi == 0
    assert m.spi == 0
    assert m.eac is None
    assert calc.compute(100, 50, 0, 20, EacMethod.CPI_SPI).eac is None


def test_tcpi_with_the_budget_spent_is_none():
    m = calc.compute(bac=100, pv=100, ev=80, ac=100)
    assert m.tcpi is None
    assert approx(m.eac, 125)
    assert approx(m.tcpi_eac, 20 / 25)


def test_zero_budget():
    m = calc.compute(bac=0, pv=0, ev=0, ac=0)
    assert m.percent_complete is None
    assert m.percent_planned is None
    assert m.tcpi is None


def test_ratio():
    assert calc.ratio(1, 4) == 0.25
    assert calc.ratio(1, 0) is None
    assert calc.ratio(0, 0) is None


# --- planned distribution curves --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("curve", "half", "quarter"),
    [
        (Curve.LINEAR, 0.5, 0.25),
        (Curve.FRONT_LOADED, 0.75, 0.4375),
        (Curve.BACK_LOADED, 0.25, 0.0625),
        (Curve.S_CURVE, 0.5, 0.15625),
    ],
)
def test_curve_fractions(curve: Curve, half: float, quarter: float):
    assert calc.curve_fraction(curve, 0) == 0
    assert calc.curve_fraction(curve, 1) == 1
    assert calc.curve_fraction(curve, 0.5) == pytest.approx(half)
    assert calc.curve_fraction(curve, 0.25) == pytest.approx(quarter)


@pytest.mark.parametrize("curve", list(Curve))
def test_curves_rise_steadily_and_stay_in_range(curve: Curve):
    values = [calc.curve_fraction(curve, i / 100) for i in range(101)]
    assert values == sorted(values)
    assert calc.curve_fraction(curve, -1) == 0
    assert calc.curve_fraction(curve, 2) == 1


def test_s_curve_is_symmetric():
    for t in (0.1, 0.3, 0.45):
        assert calc.curve_fraction(Curve.S_CURVE, t) + calc.curve_fraction(Curve.S_CURVE, 1 - t) == pytest.approx(1)


def test_planned_value_over_a_ten_day_package():
    start, finish = date(2026, 1, 1), date(2026, 1, 10)
    assert calc.planned_to_date(100, start, finish, Curve.LINEAR, date(2025, 12, 31)) == 0
    assert calc.planned_to_date(100, start, finish, Curve.LINEAR, date(2026, 1, 1)) == pytest.approx(10)
    assert calc.planned_to_date(100, start, finish, Curve.LINEAR, date(2026, 1, 5)) == pytest.approx(50)
    assert calc.planned_to_date(100, start, finish, Curve.FRONT_LOADED, date(2026, 1, 5)) == pytest.approx(75)
    assert calc.planned_to_date(100, start, finish, Curve.BACK_LOADED, date(2026, 1, 5)) == pytest.approx(25)
    assert calc.planned_to_date(100, start, finish, Curve.S_CURVE, date(2026, 1, 5)) == pytest.approx(50)
    assert calc.planned_to_date(100, start, finish, Curve.LINEAR, date(2026, 1, 10)) == 100
    assert calc.planned_to_date(100, start, finish, Curve.LINEAR, date(2027, 1, 1)) == 100


def test_planned_value_edge_cases():
    day = date(2026, 3, 2)
    assert calc.planned_to_date(40, day, day, Curve.S_CURVE, day) == 40
    assert calc.planned_to_date(40, None, day, Curve.LINEAR, day) == 0
    assert calc.planned_to_date(40, day, None, Curve.LINEAR, day) == 0
    assert calc.planned_to_date(0, day, day, Curve.LINEAR, day) == 0
    # a finish before the start is a one-day package
    assert calc.planned_to_date(40, day, date(2026, 3, 1), Curve.LINEAR, day) == 40


# --- periods and the forecast finish ----------------------------------------------------------------


def test_weekly_periods_run_monday_to_sunday():
    weeks = calc.periods(date(2026, 1, 7), date(2026, 1, 20), Interval.WEEK)
    assert weeks == [
        (date(2026, 1, 5), date(2026, 1, 11)),
        (date(2026, 1, 12), date(2026, 1, 18)),
        (date(2026, 1, 19), date(2026, 1, 25)),
    ]


def test_monthly_periods_cross_the_year():
    months = calc.periods(date(2025, 11, 15), date(2026, 2, 1), Interval.MONTH)
    assert months == [
        (date(2025, 11, 1), date(2025, 11, 30)),
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
    ]


def test_periods_are_capped():
    assert len(calc.periods(date(2000, 1, 1), date(2100, 1, 1), Interval.WEEK, limit=10)) == 10


def test_forecast_finish_stretches_by_spi():
    start, finish = date(2026, 1, 1), date(2026, 1, 10)
    assert calc.forecast_finish(start, finish, date(2026, 1, 5), 0.5) == date(2026, 1, 20)
    assert calc.forecast_finish(start, finish, date(2026, 1, 5), 1.0) == finish
    assert calc.forecast_finish(start, finish, date(2026, 1, 5), 2.0) == date(2026, 1, 5)
    assert calc.forecast_finish(start, finish, date(2026, 1, 5), None) == finish
    assert calc.forecast_finish(start, finish, date(2026, 2, 1), None) == date(2026, 2, 1)

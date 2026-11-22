"""Dew point, the 3 °C surface margin, and DFT statistics under 80/20, 90/10 and min/max."""

from datetime import date

import pytest

from src.modules.coatings.calc import dew_point, dft_stats, environment_check
from src.modules.scaffolds.service import hire_days

SET = [60, 70, 80, 90, 100, 55, 58, 62, 75, 85]


@pytest.mark.parametrize(
    ("air", "rh", "expected"),
    [(20.0, 50.0, 9.3), (25.0, 80.0, 21.3), (10.0, 100.0, 10.0), (30.0, 40.0, 14.9)],
)
def test_dew_point_by_magnus(air: float, rh: float, expected: float):
    assert dew_point(air, rh) == pytest.approx(expected, abs=0.1)


def test_dew_point_needs_a_real_humidity():
    with pytest.raises(ValueError):
        dew_point(20, 0)


def test_the_surface_must_be_three_degrees_above_the_dew_point():
    assert environment_check(12.2, air_temp_c=20, rh_pct=50).passed is False
    ok = environment_check(12.3, air_temp_c=20, rh_pct=50)
    assert (ok.dew_point_c, ok.margin_c, ok.passed) == (9.3, 3.0, True)
    assert environment_check(10.0, dew_point_c=8.0).passed is False
    assert environment_check(10.0, dew_point_c=8.0, required_margin_c=2.0).passed is True
    with pytest.raises(ValueError):
        environment_check(10.0, air_temp_c=20)


def test_dft_statistics():
    stats = dft_stats(SET, 60, 120, "80/20")
    assert (stats.count, stats.mean, stats.minimum, stats.maximum) == (10, 73.5, 55, 100)
    assert (stats.pct_within, stats.pct_below_min) == (80.0, 20.0)
    assert stats.passed


def test_ninety_ten_is_stricter_than_eighty_twenty():
    stats = dft_stats(SET, 60, 120, "90/10")
    assert not stats.passed
    assert stats.failures == ("2 of 10 readings below the minimum (allowed 10%)",)


def test_no_reading_below_the_floor_or_above_the_maximum():
    low = dft_stats([*SET[:-1], 45], 60, 120, "80/20")
    assert not low.passed
    assert any("below 80% of the minimum" in f for f in low.failures)
    high = dft_stats([70, 80, 130], 60, 120, "80/20")
    assert high.failures == ("highest reading 130 µm is above the maximum 120 µm",)
    assert dft_stats([60, 61, 120], 60, 120, "min_max").passed
    assert not dft_stats([59, 70, 80], 60, 120, "min_max").passed


def test_the_mean_must_reach_the_minimum():
    stats = dft_stats([50, 50, 62, 62, 62, 62, 62, 62, 62, 62], 63, None, "80/20")
    assert any(f.startswith("mean") for f in stats.failures)


def test_hire_days_count_both_ends_and_clip_to_the_period():
    assert hire_days(None, None, None, date(2026, 1, 31)) == 0
    assert hire_days(date(2026, 1, 1), None, None, date(2026, 1, 10)) == 10
    assert hire_days(date(2026, 1, 1), date(2026, 1, 5), None, date(2026, 1, 10)) == 5
    assert hire_days(date(2026, 1, 1), None, date(2026, 1, 8), date(2026, 1, 10)) == 3
    assert hire_days(date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 8), date(2026, 1, 10)) == 0

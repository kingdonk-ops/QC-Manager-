"""Splitting a total duration across weighted sections."""

from decimal import Decimal

from src.modules.schedule.service import split_duration, wbs_key


def test_durations_are_proportional_and_add_up():
    assert split_duration([Decimal(10), Decimal(60), Decimal(30)], 20) == [2, 12, 6]
    assert sum(split_duration([1, 2, 3, 4, 5, 6, 7], 50)) == 50


def test_every_section_keeps_a_day_when_there_are_enough():
    assert split_duration([1000, 1, 1], 5) == [3, 1, 1]


def test_zero_weights_share_equally():
    assert split_duration([0, 0], 4) == [2, 2]
    assert split_duration([], 10) == []


def test_wbs_codes_sort_naturally():
    codes = ["1.10", "1.2", "2", "1", "1.2.1", "A.1"]
    assert sorted(codes, key=wbs_key) == ["1", "1.2", "1.2.1", "1.10", "2", "A.1"]

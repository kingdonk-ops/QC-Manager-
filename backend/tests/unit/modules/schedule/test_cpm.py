"""The critical path engine and its working-day calendar, worked by hand on a Monday 5 January 2026 start."""

from datetime import date

import pytest

from src.modules.schedule.calendar import Calendar
from src.modules.schedule.cpm import Activity, CycleError, Link, calculate

MON = date(2026, 1, 5)


def d(day: int) -> date:
    return date(2026, 1, day)


def cal(**kw) -> Calendar:
    return Calendar(MON, **kw)


def run(acts, links=(), calendar=None, data_date=None):
    return calculate(acts, list(links), calendar or cal(), data_date).activities


# --- calendar --------------------------------------------------------------------------------------


def test_calendar_skips_weekends_and_holidays():
    c = cal(holidays=[d(9)])
    assert [c.date_of(i) for i in range(5)] == [d(5), d(6), d(7), d(8), d(12)]
    assert c.index_of(d(10)) == c.index_of(d(12)) == 4  # a Saturday start rolls to Monday
    assert c.date_of(-1) == date(2026, 1, 2)
    assert c.index_of(date(2026, 1, 1)) == -2  # Thursday 1st, back past the weekend
    assert c.working_days_between(d(5), d(12)) == 5
    assert c.add_working_days(d(8), 2) == d(13)


def test_calendar_origin_on_a_weekend_starts_on_monday():
    c = Calendar(date(2026, 1, 3))
    assert c.date_of(0) == d(5)


def test_six_day_week():
    c = cal(working_days=[0, 1, 2, 3, 4, 5])
    r = run([Activity(1, 6)], calendar=c)
    assert r[1].early_finish == d(10)


# --- the four link types with lags -------------------------------------------------------------------


def test_finish_to_start_chain():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2)])
    assert (r[1].early_start, r[1].early_finish) == (d(5), d(7))
    assert (r[2].early_start, r[2].early_finish) == (d(8), d(9))
    assert r[1].critical and r[2].critical and r[2].total_float == 0


def test_finish_to_start_with_lag_crosses_the_weekend():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "FS", 2)])
    assert (r[2].early_start, r[2].early_finish) == (d(12), d(13))


def test_negative_lag_is_a_lead():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "FS", -1)])
    assert (r[2].early_start, r[2].early_finish) == (d(7), d(8))


def test_start_to_start_with_lag():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "SS", 1)])
    assert (r[2].early_start, r[2].early_finish) == (d(6), d(7))
    assert r[1].total_float == r[2].total_float == 0


def test_finish_to_finish_with_lag():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "FF", 2)])
    assert (r[2].early_start, r[2].early_finish) == (d(8), d(9))


def test_start_to_finish_with_lag():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "SF", 4)])
    assert (r[2].early_start, r[2].early_finish) == (d(7), d(8))


def test_negative_start_to_start_lag_cannot_start_before_the_project():
    r = run([Activity(1, 3), Activity(2, 2)], [Link(1, 2, "SS", -2)])
    assert r[2].early_start == d(5)


# --- float, critical path, driving predecessors -------------------------------------------------------


def test_total_and_free_float():
    # A(5) -> C(1); B(1) -> D(1) -> C. B and D share three days of float; only D has it free.
    acts = [Activity(1, 5), Activity(2, 1), Activity(3, 1), Activity(4, 1)]
    links = [Link(1, 3), Link(2, 4), Link(4, 3)]
    schedule = calculate(acts, links, cal())
    r = schedule.activities
    assert (r[2].total_float, r[2].free_float) == (3, 0)
    assert (r[4].total_float, r[4].free_float) == (3, 3)
    assert r[1].critical and r[3].critical and not r[2].critical and not r[4].critical
    assert schedule.critical_path == [1, 3]
    assert r[3].driving == [1]
    assert (r[2].late_start, r[2].late_finish) == (d(8), d(8))
    assert schedule.finish == d(12)


def test_open_ended_activity_float_runs_to_project_finish():
    r = run([Activity(1, 5), Activity(2, 2)])
    assert r[2].total_float == r[2].free_float == 3


def test_milestone_has_no_duration():
    r = run([Activity(1, 3), Activity(2, 0)], [Link(1, 2)])
    assert r[2].early_start == r[2].early_finish == d(8)
    assert r[2].duration == 0


# --- constraints -------------------------------------------------------------------------------------


def test_start_no_earlier_than():
    r = run([Activity(1, 1), Activity(2, 2, constraint="snet", constraint_date=d(7))], [Link(1, 2)])
    assert r[2].early_start == d(7)
    assert r[1].total_float == 1


def test_start_no_earlier_than_on_a_weekend_rolls_forward():
    r = run([Activity(1, 3, constraint="snet", constraint_date=d(10))])
    assert (r[1].early_start, r[1].early_finish) == (d(12), d(14))


def test_must_start_on_overrides_the_logic_and_shows_negative_float():
    r = run([Activity(1, 5), Activity(2, 1, constraint="mso", constraint_date=d(7))], [Link(1, 2)])
    assert r[2].early_start == d(7)
    assert r[1].total_float == -3
    assert r[1].critical


def test_must_start_on_later_than_logic():
    r = run([Activity(1, 1), Activity(2, 1, constraint="mso", constraint_date=d(12))], [Link(1, 2)])
    assert r[2].early_start == d(12)


def test_finish_no_later_than_gives_negative_float():
    r = run([Activity(1, 5, constraint="fnlt", constraint_date=d(8))])
    assert r[1].early_finish == d(9)
    assert r[1].total_float == -1
    assert r[1].late_finish == d(8)


def test_finish_no_later_than_with_room():
    r = run([Activity(1, 2, constraint="fnlt", constraint_date=d(9)), Activity(2, 5)])
    assert r[1].total_float == 3


# --- calendars with holidays ------------------------------------------------------------------------


def test_holiday_extends_an_activity():
    r = run([Activity(1, 5)], calendar=cal(holidays=[d(9)]))
    assert r[1].early_finish == d(12)


def test_lag_skips_holidays():
    r = run([Activity(1, 1), Activity(2, 1)], [Link(1, 2, "FS", 1)], calendar=cal(holidays=[d(7)]))
    assert r[2].early_start == d(8)


# --- progress ----------------------------------------------------------------------------------------


def test_actual_dates_drive_successors():
    acts = [Activity(1, 3, actual_start=d(5), actual_finish=d(8)), Activity(2, 2)]
    r = run(acts, [Link(1, 2)])
    assert r[2].early_start == d(9)
    assert not r[1].critical and r[1].percent_complete == 100


def test_in_progress_work_remaining_from_the_data_date():
    acts = [Activity(1, 4, actual_start=d(5), percent_complete=50), Activity(2, 1)]
    r = run(acts, [Link(1, 2)], data_date=d(7))
    assert r[1].early_finish == d(8)  # two days remaining from Wednesday
    assert r[2].early_start == d(9)


def test_unstarted_work_waits_for_the_data_date():
    r = run([Activity(1, 2)], data_date=d(12))
    assert r[1].early_start == d(12)


# --- summaries ---------------------------------------------------------------------------------------


def test_summary_rolls_up_dates_and_progress():
    acts = [
        Activity(10, summary=True),
        Activity(1, 3, parent_id=10, actual_start=d(5), actual_finish=d(7)),
        Activity(2, 2, parent_id=10),
        Activity(20, parent_id=None),  # a parent by virtue of its child
        Activity(3, 1, parent_id=20),
    ]
    r = run(acts, [Link(1, 2), Link(2, 3)])
    assert (r[10].early_start, r[10].early_finish, r[10].duration) == (d(5), d(9), 5)
    assert r[10].percent_complete == 60
    assert r[20].early_start == r[3].early_start == d(12)


def test_links_to_summaries_are_ignored():
    r = run([Activity(10, summary=True), Activity(1, 2, parent_id=10), Activity(2, 1)], [Link(10, 2)])
    assert r[2].early_start == d(5)


# --- cycles ------------------------------------------------------------------------------------------


def test_cycle_is_reported_with_its_members():
    acts = [Activity(1, 1), Activity(2, 1), Activity(3, 1), Activity(4, 1)]
    with pytest.raises(CycleError) as err:
        calculate(acts, [Link(4, 1), Link(1, 2), Link(2, 3), Link(3, 1)], cal())
    loop = err.value.cycle
    assert loop[0] == loop[-1]
    assert set(loop) == {1, 2, 3}


def test_self_link_is_a_cycle():
    with pytest.raises(CycleError):
        calculate([Activity(1, 1)], [Link(1, 1)], cal())


def test_empty_schedule():
    schedule = calculate([], [], cal())
    assert schedule.activities == {} and schedule.finish == d(5)


def test_summary_progress_weighs_by_hours_only_when_every_child_has_them():
    done = {"actual_start": d(5), "actual_finish": d(7)}
    by_hours = run([Activity(10, summary=True), Activity(1, 3, 10, weight=30, **done), Activity(2, 2, 10, weight=10)])
    mixed = run([Activity(10, summary=True), Activity(1, 3, 10, weight=30, **done), Activity(2, 2, 10)])
    assert by_hours[10].percent_complete == 75
    assert mixed[10].percent_complete == 60

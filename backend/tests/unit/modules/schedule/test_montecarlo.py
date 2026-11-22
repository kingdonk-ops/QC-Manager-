"""Monte Carlo: reproducible with a seed, ordered percentiles, sensible criticality."""

import time
from datetime import date

from src.modules.schedule.calendar import Calendar
from src.modules.schedule.cpm import Activity, Link
from src.modules.schedule.montecarlo import Estimate, simulate, three_point

CAL = Calendar(date(2026, 1, 5))


def chain():
    return [Activity(1, 10), Activity(2, 5), Activity(3, 1)], [Link(1, 2), Link(2, 3)]


def test_same_seed_same_answer():
    acts, links = chain()
    first = simulate(acts, links, CAL, {}, iterations=500, seed=42)
    again = simulate(acts, links, CAL, {}, iterations=500, seed=42)
    other = simulate(acts, links, CAL, {}, iterations=500, seed=7)
    assert first == again
    assert first["histogram"] != other["histogram"] or first["std_dev_days"] != other["std_dev_days"]


def test_percentiles_are_ordered_and_bracket_the_plan():
    acts, links = chain()
    r = simulate(acts, links, CAL, {}, iterations=2000, seed=1)
    assert r["earliest"] <= r["p50"] <= r["p80"] <= r["p90"] <= r["latest"]
    # Defaults are -10% / +25%: the plan is optimistic, so it is met less than half the time.
    assert r["planned_finish"] == date(2026, 1, 26)
    assert 0 < r["probability_on_time"] < 0.5
    assert r["p50"] >= r["planned_finish"]
    assert sum(b["count"] for b in r["histogram"]) == 2000
    assert r["histogram"][-1]["cumulative"] == 1.0


def test_a_single_chain_is_always_critical():
    acts, links = chain()
    r = simulate(acts, links, CAL, {}, iterations=200, seed=3)
    assert {c["criticality_index"] for c in r["criticality"]} == {1.0}


def test_criticality_index_splits_between_parallel_paths():
    acts = [Activity(1, 10), Activity(2, 10), Activity(3, 1), Activity(4, 1)]
    links = [Link(1, 3), Link(2, 3)]
    estimates = {4: Estimate(1, 1, 1)}
    r = simulate(acts, links, CAL, estimates, iterations=1000, seed=5)
    index = {c["activity_id"]: c["criticality_index"] for c in r["criticality"]}
    assert index[3] == 1.0
    assert 0.3 < index[1] < 0.7 and abs(index[1] + index[2] - 1.0) < 0.05
    assert index[4] == 0.0


def test_fixed_estimates_reproduce_the_plan():
    acts, links = chain()
    estimates = {a.id: Estimate(a.duration, a.duration, a.duration) for a in acts}
    r = simulate(acts, links, CAL, estimates, iterations=50, seed=0)
    assert r["p50"] == r["p90"] == r["planned_finish"]
    assert r["probability_on_time"] == 1.0


def test_pert_distribution_and_finished_work():
    acts = [Activity(1, 5, actual_start=date(2026, 1, 5), actual_finish=date(2026, 1, 9)), Activity(2, 5)]
    r = simulate(acts, [Link(1, 2)], CAL, {}, iterations=300, seed=9, distribution="pert")
    assert r["earliest"] >= date(2026, 1, 15)
    assert r["distribution"] == "pert"


def test_three_point_defaults_and_ordering():
    assert three_point(10, None) == (9.0, 10, 12.5)
    assert three_point(10, Estimate(12, 10, 8)) == (8, 10, 12)


def test_twenty_thousand_runs_of_a_hundred_activities_are_quick():
    acts = [Activity(i, 1 + i % 7) for i in range(1, 101)]
    links = [Link(i, i + 1) for i in range(1, 100, 2)] + [Link(i, i + 3) for i in range(1, 97, 3)]
    started = time.perf_counter()
    r = simulate(acts, links, CAL, {}, iterations=20_000, seed=11)
    assert r["iterations"] == 20_000
    assert time.perf_counter() - started < 30

"""Monte Carlo schedule risk: sample every activity's duration and rerun the passes many times.

Durations come from three-point estimates (optimistic / most likely / pessimistic), defaulting to
-10% / as planned / +25% of the planned duration. Each run samples a triangular or PERT-beta
duration for every activity that isn't finished, runs the forward and backward pass from ``cpm``,
and records the finish and which activities were critical. Pure Python; 20 000 runs of a few hundred
activities take seconds.
"""

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil, sqrt

from .calendar import Calendar
from .cpm import EPSILON, Activity, Link, backward, forward, prepare

DEFAULT_ITERATIONS = 1000
MAX_ITERATIONS = 20_000
OPTIMISTIC, PESSIMISTIC = 0.9, 1.25


@dataclass
class Estimate:
    """Three-point estimate of an activity, in working days."""

    optimistic: float | None = None
    most_likely: float | None = None
    pessimistic: float | None = None


def three_point(duration: float, est: Estimate | None) -> tuple[float, float, float]:
    """(low, mode, high), filling gaps from the defaults and putting them in order."""
    est = est or Estimate()
    mode = est.most_likely if est.most_likely is not None else duration
    low = est.optimistic if est.optimistic is not None else mode * OPTIMISTIC
    high = est.pessimistic if est.pessimistic is not None else mode * PESSIMISTIC
    low, high = min(low, mode, high), max(low, mode, high)
    return max(low, 0.0), max(mode, 0.0), max(high, 0.0)


def _sampler(rng: random.Random, distribution: str, low: float, mode: float, high: float) -> Callable[[], float]:
    if high - low < EPSILON:
        return lambda: mode
    if distribution == "pert":
        span = high - low
        alpha = 1 + 4 * (mode - low) / span
        beta = 1 + 4 * (high - mode) / span
        return lambda: low + rng.betavariate(alpha, beta) * span
    return lambda: rng.triangular(low, high, mode)


def simulate(
    activities: Sequence[Activity],
    links: Sequence[Link],
    calendar: Calendar,
    estimates: dict[int, Estimate],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int | None = None,
    distribution: str = "triangular",
    data_date: date | None = None,
    target: date | None = None,
    bins: int = 30,
) -> dict:
    """Run the simulation. ``activities`` are the task activities (summaries excluded)."""
    iterations = max(1, min(iterations, MAX_ITERATIONS))
    rng = random.Random(seed)
    prep = prepare(activities, links, calendar, data_date)
    net = prep.net
    by_id = {a.id: a for a in activities}
    n = len(net.ids)

    deterministic = list(prep.durations)
    samplers: list[tuple[Callable[[], float], float, float] | None] = []
    for i, aid in enumerate(net.ids):
        a = by_id[aid]
        base = deterministic[i]
        if a.actual_finish is not None or a.duration <= 0:
            samplers.append(None)
            continue
        low, mode, high = three_point(float(a.duration), estimates.get(aid))
        draw = _sampler(rng, distribution, low, mode, high)
        if a.actual_start is not None:
            # Only the remaining part is uncertain; it scales with the sampled/likely ratio.
            remaining = a.duration * (1 - min(max(a.percent_complete, 0.0), 100.0) / 100)
            fixed = base - ceil(remaining - EPSILON) if data_date is not None else 0.0
            scale = remaining if data_date is not None else float(a.duration)
            if mode <= 0:
                samplers.append(None)
                continue
            samplers.append((draw, fixed, scale / mode))
        else:
            samplers.append((draw, 0.0, 1.0))

    es0, ef0 = forward(net, deterministic, prep.floor, prep.fixed)
    planned_finish = max(ef0, default=0.0)

    finishes: list[float] = []
    critical_counts = [0] * n
    durations = list(deterministic)
    for _ in range(iterations):
        for i in range(n):
            s = samplers[i]
            if s is not None:
                draw, fixed, factor = s
                durations[i] = fixed + draw() * factor
        es, ef = forward(net, durations, prep.floor, prep.fixed)
        finish = max(ef, default=0.0)
        ls, _ = backward(net, durations, finish, prep.ceiling)
        for i in range(n):
            if ls[i] - es[i] <= EPSILON:
                critical_counts[i] += 1
        finishes.append(finish)

    def to_date(f: float) -> date:
        # Exclusive finish: the work ends on the day before the next whole working-day index.
        whole = ceil(f - EPSILON)
        return calendar.date_of(whole - 1 if whole > 0 else 0)

    finishes.sort()
    dates = [to_date(f) for f in finishes]

    def percentile(p: float) -> date:
        return dates[min(len(dates) - 1, max(0, ceil(p / 100 * len(dates)) - 1))]

    planned_date = to_date(planned_finish)
    target_date = target or planned_date
    on_time = sum(1 for d in dates if d <= target_date) / len(dates)
    mean = sum(finishes) / len(finishes)
    std = sqrt(sum((f - mean) ** 2 for f in finishes) / len(finishes))

    return {
        "iterations": iterations,
        "distribution": distribution,
        "seed": seed,
        "planned_finish": planned_date,
        "target_date": target_date,
        "probability_on_time": round(on_time, 4),
        "p50": percentile(50),
        "p80": percentile(80),
        "p90": percentile(90),
        "earliest": dates[0],
        "latest": dates[-1],
        "mean_duration_days": round(mean - min(es0, default=0.0), 2),
        "std_dev_days": round(std, 2),
        "histogram": _histogram(dates, bins),
        "criticality": sorted(
            (
                {"activity_id": aid, "criticality_index": round(critical_counts[i] / iterations, 4)}
                for i, aid in enumerate(net.ids)
            ),
            key=lambda c: -float(c["criticality_index"]),
        ),
    }


def _histogram(dates: list[date], bins: int) -> list[dict]:
    """Runs finishing on each date (or in each group of dates), with the cumulative share."""
    counts = sorted(Counter(dates).items())
    if len(counts) > bins:
        first, last = counts[0][0].toordinal(), counts[-1][0].toordinal()
        width = max(1, ceil((last - first + 1) / bins))
        grouped: dict[int, int] = {}
        ends: dict[int, date] = {}
        for d, c in counts:
            b = (d.toordinal() - first) // width
            grouped[b] = grouped.get(b, 0) + c
            ends[b] = max(ends.get(b, d), d)
        counts = [(ends[b], grouped[b]) for b in sorted(grouped)]
    total = len(dates)
    running = 0
    out = []
    for d, c in counts:
        running += c
        out.append({"date": d, "count": c, "cumulative": round(running / total, 4)})
    return out

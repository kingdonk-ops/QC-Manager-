"""Earned value arithmetic. Pure functions, no database: everything here is unit-tested on its own.

The basis is whatever the caller sums: labour hours by default, or cost. Every ratio whose
denominator is zero answers ``None`` rather than raising, so a package with no progress yet, or
no actuals booked, simply shows no index.
"""

import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from .constants import Curve, EacMethod, Interval


def ratio(numerator: float, denominator: float) -> float | None:
    """``numerator / denominator``, or ``None`` when the denominator is zero."""
    if denominator == 0 or math.isclose(denominator, 0.0, abs_tol=1e-12):
        return None
    return numerator / denominator


# --- planned distribution ----------------------------------------------------------------------------


def curve_fraction(curve: Curve | str, t: float) -> float:
    """Share of the budget planned to be spent after a fraction ``t`` (0..1) of the duration.

    linear       t                 even spend
    front_loaded 1 - (1 - t)^2     spend falls away: half the budget by ~29% of the time
    back_loaded  t^2               spend builds up: half the budget by ~71% of the time
    s_curve      3t^2 - 2t^3       slow start, peak in the middle, slow finish (half at the midpoint)
    """
    t = min(1.0, max(0.0, t))
    match Curve(curve):
        case Curve.LINEAR:
            return t
        case Curve.FRONT_LOADED:
            return 1 - (1 - t) ** 2
        case Curve.BACK_LOADED:
            return t * t
        case Curve.S_CURVE:
            return t * t * (3 - 2 * t)


def elapsed_fraction(start: date, finish: date, on: date) -> float:
    """How much of the planned duration has passed by the end of day ``on``.

    Both planned dates are working days of the package, so a package from the 1st to the 10th is
    10 days long and is half planned by the end of the 5th. A finish before the start counts as a
    one-day package on the start date.
    """
    if on < start:
        return 0.0
    days = max((finish - start).days, 0) + 1
    return min(1.0, ((on - start).days + 1) / days)


def planned_to_date(budget: float, start: date | None, finish: date | None, curve: Curve | str, on: date) -> float:
    """Planned value (PV) of one package at the end of ``on``. Unscheduled packages plan nothing."""
    if start is None or finish is None or budget == 0:
        return 0.0
    return budget * curve_fraction(curve, elapsed_fraction(start, finish, on))


# --- indices -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Metrics:
    bac: float
    pv: float
    ev: float
    ac: float
    sv: float
    cv: float
    spi: float | None
    cpi: float | None
    eac: float | None
    etc: float | None
    vac: float | None
    tcpi: float | None
    """Efficiency needed on the remaining work to finish on budget: (BAC - EV) / (BAC - AC)."""
    tcpi_eac: float | None
    """Efficiency needed to finish at the EAC: (BAC - EV) / (EAC - AC)."""
    percent_planned: float | None
    percent_complete: float | None
    productivity: float | None
    """Earned hours per actual hour."""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_at_completion(
    bac: float, ev: float, ac: float, cpi: float | None, spi: float | None, method: EacMethod
) -> float | None:
    match method:
        case EacMethod.CPI:
            return ratio(bac, cpi) if cpi is not None else None
        case EacMethod.BUDGET_RATE:
            return ac + (bac - ev)
        case EacMethod.CPI_SPI:
            if cpi is None or spi is None:
                return None
            remaining = ratio(bac - ev, cpi * spi)
            return None if remaining is None else ac + remaining


def compute(
    bac: float,
    pv: float,
    ev: float,
    ac: float,
    method: EacMethod = EacMethod.CPI,
    *,
    earned_hours: float | None = None,
    actual_hours: float | None = None,
) -> Metrics:
    """Every earned value figure for one set of totals.

    ``earned_hours``/``actual_hours`` give the productivity; on the hours basis they default to EV/AC.
    """
    spi = ratio(ev, pv)
    cpi = ratio(ev, ac)
    eac = estimate_at_completion(bac, ev, ac, cpi, spi, method)
    earned = ev if earned_hours is None else earned_hours
    spent = ac if actual_hours is None else actual_hours
    return Metrics(
        bac=bac,
        pv=pv,
        ev=ev,
        ac=ac,
        sv=ev - pv,
        cv=ev - ac,
        spi=spi,
        cpi=cpi,
        eac=eac,
        etc=None if eac is None else eac - ac,
        vac=None if eac is None else bac - eac,
        tcpi=ratio(bac - ev, bac - ac),
        tcpi_eac=None if eac is None else ratio(bac - ev, eac - ac),
        percent_planned=None if (p := ratio(pv, bac)) is None else p * 100,
        percent_complete=None if (c := ratio(ev, bac)) is None else c * 100,
        productivity=ratio(earned, spent),
    )


# --- time ---------------------------------------------------------------------------------------------


def period_start(on: date, interval: Interval) -> date:
    if interval == Interval.WEEK:
        return on - timedelta(days=on.weekday())
    return on.replace(day=1)


def next_period(start: date, interval: Interval) -> date:
    if interval == Interval.WEEK:
        return start + timedelta(days=7)
    return date(start.year + start.month // 12, start.month % 12 + 1, 1)


def periods(first: date, last: date, interval: Interval, limit: int = 600) -> list[tuple[date, date]]:
    """``(start, end)`` of each Monday-to-Sunday week or calendar month covering ``first``..``last``."""
    out: list[tuple[date, date]] = []
    start = period_start(first, interval)
    while start <= last and len(out) < limit:
        following = next_period(start, interval)
        out.append((start, following - timedelta(days=1)))
        start = following
    return out


def forecast_finish(start: date, finish: date, data_date: date, spi: float | None) -> date:
    """Planned duration stretched by the schedule performance: start + duration / SPI.

    Never before the data date; with no SPI (nothing planned yet) or SPI of zero, the planned finish.
    """
    if not spi:
        return max(finish, data_date)
    days = max((finish - start).days, 0) + 1
    stretched = start + timedelta(days=math.ceil(days / spi) - 1)
    return max(stretched, data_date)

"""The coating acceptance arithmetic: dew point, the surface-temperature margin, and DFT statistics.

Pure functions, mirrored in the frontend (``modules/coatings/calc.ts``) for live feedback; the server's
result is the one stored.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

DEFAULT_DEW_POINT_MARGIN_C = 3.0
"""Coating is held while the surface is less than this much warmer than the dew point."""


class DftRule(StrEnum):
    EIGHTY_TWENTY = "80/20"
    """Up to 20 % of readings may be below the minimum (nominal) DFT, none below 80 % of it."""
    NINETY_TEN = "90/10"
    """Up to 10 % of readings may be below the minimum DFT, none below 90 % of it."""
    MIN_MAX = "min_max"
    """Every reading within the specified minimum and maximum."""


RULE_LIMITS: dict[str, tuple[float, float]] = {
    DftRule.EIGHTY_TWENTY: (0.20, 0.80),
    DftRule.NINETY_TEN: (0.10, 0.90),
    DftRule.MIN_MAX: (0.0, 1.0),
}
"""rule -> (share of readings allowed below the minimum, lowest reading as a fraction of the minimum)."""


def dew_point(air_temp_c: float, rh_pct: float) -> float:
    """Dew point by the Magnus formula (Sonntag constants), as in ISO 8502-4. RH in percent, 0 < RH <= 100."""
    if not 0 < rh_pct <= 100:
        raise ValueError("Relative humidity must be above 0 and at most 100 %")
    b, c = 17.62, 243.12
    gamma = math.log(rh_pct / 100.0) + b * air_temp_c / (c + air_temp_c)
    return round(c * gamma / (b - gamma), 1)


@dataclass(frozen=True)
class EnvironmentCheck:
    dew_point_c: float
    margin_c: float
    """Surface temperature minus dew point."""
    required_margin_c: float
    passed: bool


def environment_check(
    surface_temp_c: float,
    *,
    air_temp_c: float | None = None,
    rh_pct: float | None = None,
    dew_point_c: float | None = None,
    required_margin_c: float = DEFAULT_DEW_POINT_MARGIN_C,
) -> EnvironmentCheck:
    """Surface temperature must be at least ``required_margin_c`` above the dew point.

    The dew point is calculated from air temperature and RH unless measured (``dew_point_c``).
    """
    if dew_point_c is None:
        if air_temp_c is None or rh_pct is None:
            raise ValueError("Give the dew point, or the air temperature and relative humidity")
        dew_point_c = dew_point(air_temp_c, rh_pct)
    margin = round(surface_temp_c - dew_point_c, 1)
    return EnvironmentCheck(dew_point_c, margin, required_margin_c, margin >= required_margin_c)


@dataclass(frozen=True)
class DftStats:
    count: int
    mean: float
    minimum: float
    maximum: float
    pct_within: float
    """Share of readings within [min, max], percent."""
    pct_below_min: float
    passed: bool
    failures: tuple[str, ...]


def dft_stats(readings: list[float], dft_min: float, dft_max: float | None, rule: str) -> DftStats:
    """Statistics for one set of spot readings (µm) against the coat's specified minimum (nominal) and maximum DFT.

    Passes when the mean reaches the minimum, the share of readings below the minimum is within the rule's
    allowance, no reading falls below the rule's floor (a fraction of the minimum), and none exceeds the maximum.
    """
    if not readings:
        raise ValueError("A DFT set needs at least one reading")
    allowance, floor = RULE_LIMITS[rule]
    n = len(readings)
    mean = sum(readings) / n
    low, high = min(readings), max(readings)
    below = sum(1 for r in readings if r < dft_min)
    within = sum(1 for r in readings if r >= dft_min and (dft_max is None or r <= dft_max))
    failures = []
    if mean < dft_min:
        failures.append(f"mean {mean:.1f} µm is below the minimum {dft_min:g} µm")
    if below / n > allowance + 1e-9:
        failures.append(f"{below} of {n} readings below the minimum (allowed {allowance:.0%})")
    if low < floor * dft_min - 1e-9:
        failures.append(f"lowest reading {low:g} µm is below {floor:.0%} of the minimum")
    if dft_max is not None and high > dft_max + 1e-9:
        failures.append(f"highest reading {high:g} µm is above the maximum {dft_max:g} µm")
    return DftStats(
        count=n,
        mean=round(mean, 1),
        minimum=low,
        maximum=high,
        pct_within=round(100.0 * within / n, 1),
        pct_below_min=round(100.0 * below / n, 1),
        passed=not failures,
        failures=tuple(failures),
    )

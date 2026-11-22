"""Markup geometry and the measurement maths. Pure functions; the frontend mirrors them in ``geometry.ts``.

Points are ``[x, y]`` in PDF units of the displayed page at scale 1, y pointing down.
A page's calibration is ``meters_per_unit``: the real length, in metres, of one PDF unit.
"""

import math
from collections.abc import Sequence
from typing import Any

Point = tuple[float, float]

UNIT_METERS: dict[str, float] = {"m": 1.0, "mm": 0.001, "cm": 0.01, "km": 1000.0, "ft": 0.3048, "in": 0.0254}

BOX_TYPES = {"rect", "ellipse", "cloud", "highlight", "stamp", "text"}
TWO_POINT_TYPES = {"line", "arrow", "measure_length"}
PATH_TYPES = {"polyline", "freehand", "measure_polyline"}
AREA_TYPES = {"measure_area"}
MEASURE_TYPES = {"measure_length", "measure_polyline", "measure_area"}
ALL_TYPES = BOX_TYPES | TWO_POINT_TYPES | PATH_TYPES | AREA_TYPES | {"callout"}
MAX_POINTS = 5000
LIMIT = 1_000_000.0


class GeometryError(ValueError):
    pass


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polyline_length(points: Sequence[Sequence[float]]) -> float:
    return sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    """The shoelace formula; the polygon closes itself."""
    n = len(points)
    if n < 3:
        return 0.0
    twice = sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))
    return abs(twice) / 2


def scale_factor(p1: Sequence[float], p2: Sequence[float], real_distance: float, unit: str) -> float:
    """Metres per PDF unit, from two picked points and the real distance between them."""
    if unit not in UNIT_METERS:
        raise GeometryError(f"Unknown unit {unit!r}")
    if real_distance <= 0:
        raise GeometryError("The real distance must be more than zero.")
    picked = distance(p1, p2)
    if picked <= 0:
        raise GeometryError("Pick two different points.")
    return real_distance * UNIT_METERS[unit] / picked


def measure(kind: str, points: Sequence[Sequence[float]], meters_per_unit: float) -> dict[str, Any]:
    """Length in metres for the length tools, area in square metres for the area tool."""
    if kind == "measure_area":
        return {"value": polygon_area(points) * meters_per_unit**2, "unit": "m2", "meters_per_unit": meters_per_unit}
    return {"value": polyline_length(points) * meters_per_unit, "unit": "m", "meters_per_unit": meters_per_unit}


def format_measurement(measurement: dict[str, Any] | None) -> str:
    if not measurement:
        return ""
    value = float(measurement["value"])
    if measurement["unit"] == "m2":
        return f"{value:,.2f} m²"
    return f"{value:,.3f} m" if value < 10 else f"{value:,.2f} m"


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GeometryError(f"{name} must be a number")
    if abs(value) > LIMIT:
        raise GeometryError(f"{name} is out of range")
    return float(value)


def _points(value: Any, least: int, most: int = MAX_POINTS) -> list[list[float]]:
    if not isinstance(value, list) or not least <= len(value) <= most:
        raise GeometryError(f"points must be a list of {least} to {most} [x, y] pairs")
    out = []
    for p in value:
        if not isinstance(p, list) or len(p) != 2:
            raise GeometryError("Each point is [x, y]")
        out.append([_number(p[0], "x"), _number(p[1], "y")])
    return out


def _box(geometry: dict[str, Any]) -> dict[str, float]:
    x, y = _number(geometry.get("x"), "x"), _number(geometry.get("y"), "y")
    w, h = _number(geometry.get("w"), "w"), _number(geometry.get("h"), "h")
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    return {"x": x, "y": y, "w": w, "h": h}


def normalise(kind: str, geometry: dict[str, Any]) -> dict[str, Any]:
    """The geometry checked and reduced to what the type needs, or ``GeometryError``."""
    if kind in BOX_TYPES:
        return _box(geometry)
    if kind == "callout":
        anchor = _points([geometry.get("anchor")], 1, 1)[0]
        return {**_box(geometry), "anchor": anchor}
    if kind in TWO_POINT_TYPES:
        return {"points": _points(geometry.get("points"), 2, 2)}
    if kind in PATH_TYPES:
        return {"points": _points(geometry.get("points"), 2)}
    if kind in AREA_TYPES:
        return {"points": _points(geometry.get("points"), 3)}
    raise GeometryError(f"Unknown markup type {kind!r}")


def cloud_points(x: float, y: float, w: float, h: float, steps: int = 8) -> list[Point]:
    """A revision cloud round a box: semicircular bumps bulging outwards, clockwise from the top-left."""
    size = max(6.0, min(24.0, min(w, h) / 4 if min(w, h) > 0 else 6.0))
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    out: list[Point] = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        length = distance(a, b)
        if length == 0:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = uy, -ux
        bumps = max(1, round(length / size))
        step = length / bumps
        r = step / 2
        for k in range(bumps):
            cx, cy = a[0] + ux * (k * step + r), a[1] + uy * (k * step + r)
            for s in range(steps + 1):
                t = math.pi * s / steps
                out.append((cx - r * math.cos(t) * ux + r * math.sin(t) * nx, cy - r * math.cos(t) * uy + r * math.sin(t) * ny))
    return out

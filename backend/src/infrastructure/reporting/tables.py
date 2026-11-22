"""Filtering, aggregating and pivoting dataset rows, in memory.

Filters are JSON: ``{"status": "open"}`` (equals), ``{"status": ["todo", "review"]}`` (any of), or an
operator object ``{"due_date": {"gte": "2026-01-01", "lt": "2026-02-01"}}``. Operators: ``eq``, ``ne``,
``in``, ``gt``, ``gte``, ``lt``, ``lte``, ``contains``, ``empty`` (true/false). Text compares without case.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from .registry import Column, Dataset

Agg = Literal["sum", "avg", "count", "min", "max"]
AGGREGATIONS: tuple[str, ...] = ("sum", "avg", "count", "min", "max")
MAX_PIVOT_ROWS = 5_000
MAX_PIVOT_COLUMNS = 200


class FilterError(ValueError):
    pass


def number(value: Any) -> float | None:
    """A float from a number, Decimal or text like ``"$1,250.50"`` / ``"(300)"``; None if it isn't one."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    for symbol in ("$", "€", "£", "AUD", "USD", "EUR", "GBP", "AED"):
        text = text.replace(symbol, "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if not text:
        return None
    try:
        result = float(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
    return -result if negative else result


def _comparable(value: Any, column: Column | None) -> Any:
    if value is None:
        return None
    kind = column.type if column else "text"
    if kind in ("number", "money"):
        return number(value)
    if kind == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)[:10]
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "y")
        return bool(value)
    return str(value).lower()


def _matches(value: Any, condition: Any, column: Column | None) -> bool:
    if not isinstance(condition, dict):
        condition = {"in": condition} if isinstance(condition, list) else {"eq": condition}
    v = _comparable(value, column)
    for op, raw in condition.items():
        if op == "empty":
            if bool(raw) != (v is None or v == ""):
                return False
            continue
        if op == "in":
            if not isinstance(raw, list):
                raise FilterError("'in' takes a list")
            if v not in {_comparable(x, column) for x in raw}:
                return False
            continue
        target = _comparable(raw, column)
        if op == "eq":
            ok = v == target
        elif op == "ne":
            ok = v != target
        elif op == "contains":
            ok = v is not None and str(target) in str(v)
        elif op in ("gt", "gte", "lt", "lte"):
            if v is None or target is None:
                return False
            try:
                ok = {"gt": v > target, "gte": v >= target, "lt": v < target, "lte": v <= target}[op]
            except TypeError:
                return False
        else:
            raise FilterError(f"Unknown filter operator {op!r}")
        if not ok:
            return False
    return True


def apply_filters(dataset: Dataset, rows: Iterable[dict[str, Any]], filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not filters:
        return list(rows)
    unknown = [k for k in filters if dataset.column(k) is None]
    if unknown:
        raise FilterError(f"Not columns of {dataset.name}: {', '.join(unknown)}")
    columns = {k: dataset.column(k) for k in filters}
    return [row for row in rows if all(_matches(row.get(k), c, columns[k]) for k, c in filters.items())]


def pick_columns(dataset: Dataset, keys: Sequence[str] | None) -> list[Column]:
    if not keys:
        return list(dataset.columns)
    picked = []
    for key in keys:
        column = dataset.column(key)
        if column is None:
            raise FilterError(f"{dataset.name} has no column {key!r}")
        picked.append(column)
    return picked


def aggregate(values: Iterable[Any], agg: str) -> float | None:
    if agg == "count":
        return float(sum(1 for v in values if v is not None and v != ""))
    numbers = [n for n in (number(v) for v in values) if n is not None]
    if not numbers:
        return None
    if agg == "sum":
        return round(sum(numbers), 6)
    if agg == "avg":
        return round(sum(numbers) / len(numbers), 6)
    if agg == "min":
        return min(numbers)
    if agg == "max":
        return max(numbers)
    raise FilterError(f"Unknown aggregation {agg!r}")


def _key(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, dict)):
        return str(value)
    return value


def _sort_key(key: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(
        (v is None, 0, float(v), "")
        if isinstance(v, (int, float))
        else (v is None, 1, 0.0, "" if v is None else str(v).lower())
        for v in key
    )


def pivot(
    rows: Sequence[dict[str, Any]],
    row_fields: Sequence[str],
    column_fields: Sequence[str],
    values: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    """Group ``rows`` by ``row_fields`` down and ``column_fields`` across, aggregating ``values``
    (``(field, agg)`` pairs) in each cell, with row, column and grand totals computed from the raw values."""
    if not values:
        values = [("*", "count")]
    cells: dict[tuple[Any, ...], dict[tuple[Any, ...], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    by_row: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    by_col: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        r = tuple(_key(row.get(f)) for f in row_fields)
        c = tuple(_key(row.get(f)) for f in column_fields)
        cells[r][c].append(row)
        by_row[r].append(row)
        by_col[c].append(row)

    def agg_rows(group: list[dict[str, Any]]) -> list[float | None]:
        out: list[float | None] = []
        for field, how in values:
            if field == "*":
                out.append(float(len(group)))
            else:
                out.append(aggregate((g.get(field) for g in group), how))
        return out

    row_keys = sorted(by_row, key=_sort_key)
    column_keys = sorted(by_col, key=_sort_key)
    truncated = len(row_keys) > MAX_PIVOT_ROWS or len(column_keys) > MAX_PIVOT_COLUMNS
    row_keys, column_keys = row_keys[:MAX_PIVOT_ROWS], column_keys[:MAX_PIVOT_COLUMNS]
    return {
        "row_fields": list(row_fields),
        "column_fields": list(column_fields),
        "values": [{"field": f, "agg": a} for f, a in values],
        "row_keys": [list(k) for k in row_keys],
        "column_keys": [list(k) for k in column_keys],
        "cells": [[agg_rows(cells[r][c]) if c in cells[r] else [None] * len(values) for c in column_keys] for r in row_keys],
        "row_totals": [agg_rows(by_row[r]) for r in row_keys],
        "column_totals": [agg_rows(by_col[c]) for c in column_keys],
        "grand_total": agg_rows(list(rows)),
        "source_rows": len(rows),
        "truncated": truncated,
    }


def pivot_table(result: dict[str, Any], labels: dict[str, str]) -> tuple[list[str], list[list[Any]]]:
    """A pivot as a flat table (headers, rows) for Excel, PDF and email."""
    values = result["values"]
    value_names = [f"{labels.get(v['field'], 'Rows' if v['field'] == '*' else v['field'])} ({v['agg']})" for v in values]
    headers = [labels.get(f, f) for f in result["row_fields"]] or [""]
    for ck in result["column_keys"]:
        prefix = " / ".join("" if v is None else str(v) for v in ck)
        headers += [f"{prefix} · {n}" if prefix else n for n in value_names]
    if result["column_fields"]:
        headers += [f"Total · {n}" for n in value_names]
    table: list[list[Any]] = []
    for i, rk in enumerate(result["row_keys"]):
        line: list[Any] = ["" if v is None else v for v in rk] or ["All"]
        for cell in result["cells"][i]:
            line += cell
        if result["column_fields"]:
            line += result["row_totals"][i]
        table.append(line)
    total: list[Any] = ["Total"] + [""] * (max(1, len(result["row_fields"])) - 1)
    for col in result["column_totals"]:
        total += col
    if result["column_fields"]:
        total += result["grand_total"]
    table.append(total)
    return headers, table

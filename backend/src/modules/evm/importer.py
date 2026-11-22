"""Progress from a spreadsheet: one row per package with its code, percent complete and actual hours.

Headers are matched loosely (``Code``, ``WP``, ``% Complete``, ``Percent``, ``Actual Hours``, ``Hours``...).
Percentages are 0-100; a file whose percentages are all between 0 and 1 is read as fractions (an
Excel column formatted as %). ``45%`` as text works too.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

FIELDS: dict[str, tuple[str, ...]] = {
    "code": ("code", "wp", "wp_code", "package", "work_package", "work_package_code", "package_code"),
    "percent": ("percent", "percent_complete", "pct", "pct_complete", "complete", "progress", "progress_pct"),
    "earned_hours": ("earned_hours", "earned", "ev_hours"),
    "actual_hours": ("actual_hours", "hours", "actual", "ac_hours", "hours_to_date", "actual_hours_to_date"),
    "actual_cost": ("actual_cost", "cost", "cost_to_date"),
    "comment": ("comment", "comments", "note", "notes", "remarks"),
}


def _norm(header: str) -> str:
    if "%" in header:
        return "percent"
    return re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")


def mapping(columns: list[str]) -> dict[str, str]:
    """``{field: column}`` for every field a header matches."""
    found: dict[str, str] = {}
    for column in columns:
        key = _norm(column)
        for field, aliases in FIELDS.items():
            if key in aliases and field not in found:
                found[field] = column
    return found


def _number(value: Any) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip().replace(",", "").rstrip("%").strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' isn't a number") from exc


def parse(columns: list[str], rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[int, str]]]:
    """Rows as ``{code, percent_complete, earned_hours, actual_hours, actual_cost, comment}`` plus ``(row, problem)``.

    Row numbers count the header as row 1, like the spreadsheet.
    """
    cols = mapping(columns)
    if "code" not in cols:
        return [], [(1, "No 'code' column.")]
    if not {"percent", "earned_hours", "actual_hours", "actual_cost"} & set(cols):
        return [], [(1, "No 'percent' or 'actual hours' column.")]
    parsed: list[dict[str, Any]] = []
    issues: list[tuple[int, str]] = []
    texts_with_pct = False
    for i, row in enumerate(rows, start=2):
        code = str(row.get(cols["code"]) or "").strip()
        if not code:
            continue
        try:
            raw_pct = row.get(cols["percent"]) if "percent" in cols else None
            texts_with_pct |= isinstance(raw_pct, str) and raw_pct.strip().endswith("%")
            entry = {
                "row": i,
                "code": code,
                "percent_complete": _number(raw_pct),
                "earned_hours": _number(row.get(cols["earned_hours"])) if "earned_hours" in cols else None,
                "actual_hours": _number(row.get(cols["actual_hours"])) if "actual_hours" in cols else None,
                "actual_cost": _number(row.get(cols["actual_cost"])) if "actual_cost" in cols else None,
                "comment": (str(row.get(cols["comment"])).strip() or None)
                if "comment" in cols and row.get(cols["comment"]) is not None
                else None,
            }
        except ValueError as exc:
            issues.append((i, f"{code}: {exc}"))
            continue
        parsed.append(entry)
    percents = [e["percent_complete"] for e in parsed if e["percent_complete"] is not None]
    if not texts_with_pct and percents and all(0 <= p <= 1 for p in percents) and any(p > 0 for p in percents):
        for e in parsed:
            if e["percent_complete"] is not None:
                e["percent_complete"] *= 100
    valid = []
    for e in parsed:
        problems = []
        if e["percent_complete"] is not None and not 0 <= e["percent_complete"] <= 100:
            problems.append("percent must be between 0 and 100")
        if e["percent_complete"] is not None and e["earned_hours"] is not None:
            problems.append("give percent or earned hours, not both")
        for key in ("earned_hours", "actual_hours", "actual_cost"):
            if e[key] is not None and e[key] < 0:
                problems.append(f"{key.replace('_', ' ')} can't be negative")
        if problems:
            issues.append((e["row"], f"{e['code']}: {'; '.join(problems)}"))
        else:
            e["percent_complete"] = None if e["percent_complete"] is None else e["percent_complete"].quantize(Decimal("0.001"))
            for key in ("earned_hours", "actual_hours", "actual_cost"):
                if e[key] is not None:
                    e[key] = e[key].quantize(Decimal("0.01"))
            valid.append(e)
    return valid, issues

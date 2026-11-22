"""Reading and writing tables: CSV and Excel, for every module's import and export.

columns, rows = read_table(data, "contacts.xlsx")          # rows are dicts keyed by header
body, media_type, ext = write_table(columns, rows, "xlsx")  # or "csv"
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

MAX_ROWS = 50_000


class TableError(ValueError):
    pass


def read_table(data: bytes, filename: str) -> tuple[list[str], list[dict[str, Any]]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _read_xlsx(data)
    if name.endswith((".csv", ".txt", ".tsv")):
        return _read_csv(data)
    raise TableError("Upload a .csv or .xlsx file.")


def _read_csv(data: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = [c.strip() for c in reader.fieldnames or []]
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise TableError(f"More than {MAX_ROWS} rows.")
        rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
    return columns, rows


def _read_xlsx(data: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    except Exception as exc:
        raise TableError("That isn't a readable Excel file.") from exc
    if sheet is None:
        raise TableError("The workbook has no sheet.")
    rows_iter = sheet.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if not header:
        return [], []
    columns = [str(c).strip() if c is not None else f"Column {i + 1}" for i, c in enumerate(header)]
    rows = []
    for i, values in enumerate(rows_iter):
        if i >= MAX_ROWS:
            raise TableError(f"More than {MAX_ROWS} rows.")
        if values is None or all(v is None or v == "" for v in values):
            continue
        rows.append({col: (v.strip() if isinstance(v, str) else v) for col, v in zip(columns, values, strict=False)})
    return columns, rows


def _cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def write_table(
    columns: Sequence[tuple[str, str]], rows: Iterable[dict[str, Any]], fmt: str, *, title: str = "Export"
) -> tuple[bytes, str, str]:
    """``columns`` are ``(key, header)`` pairs. Returns (bytes, media type, file extension)."""
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([h for _, h in columns])
        for row in rows:
            writer.writerow([_cell(row.get(k)) for k, _ in columns])
        return out.getvalue().encode("utf-8-sig"), "text/csv", "csv"

    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = title[:31]
    sheet.append([h for _, h in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    widths = [len(h) for _, h in columns]
    for row in rows:
        values = [_cell(row.get(k)) for k, _ in columns]
        sheet.append(values)
        widths = [max(w, min(60, len(str(v)) if v is not None else 0)) for w, v in zip(widths, values, strict=False)]
    for i, w in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = w + 2
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"

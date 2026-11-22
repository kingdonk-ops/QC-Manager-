"""Getting bills in and out: spreadsheet import with column mapping, Excel/CSV export, GAEB DA XML.

Spreadsheet import builds the hierarchy from a level column (1 = top) when one is mapped, else
from the ordinal's dotted depth (``1.2.3`` is three deep), else everything is top level. A row
with no quantity, unit or rate is a section heading unless a ``kind`` column says otherwise.

GAEB export writes DA XML 3.3: ``BoQCtgy`` for every row with children (or a section), an
``Itemlist`` of ``Item``s (``Qty``, ``QU``, ``OutlineText`` short text, ``DetailTxt`` long text)
for the rest. Phase 83 (tender request) carries no prices; phase 84 adds ``UP`` and ``IT``.
Import reads the same elements back from 81-86 files, ignoring the namespace version.
"""

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

FIELDS = ("ordinal", "level", "code", "short_text", "long_text", "unit", "quantity", "rate", "classification", "kind")

ALIASES: dict[str, tuple[str, ...]] = {
    "ordinal": ("ordinal", "oz", "pos", "pos no", "position", "item", "item no", "no", "nr", "number", "ref"),
    "level": ("level", "indent", "depth", "outline", "ebene"),
    "code": ("code", "item code", "position code", "id"),
    "short_text": ("short text", "description", "text", "kurztext", "title", "name"),
    "long_text": ("long text", "specification", "langtext", "spec", "details"),
    "unit": ("unit", "uom", "einheit", "me", "qu"),
    "quantity": ("quantity", "qty", "menge", "amount"),
    "rate": ("rate", "unit rate", "unit price", "price", "ep", "einheitspreis", "up"),
    "classification": ("classification", "cost group", "kg", "element", "nrm", "masterformat", "section"),
    "kind": ("kind", "type", "row type"),
}

GAEB_NS = "http://www.gaeb.de/GAEB_DA_XML/DA{phase}/3.3"
MAX_GAEB_BYTES = 20 * 1024 * 1024


class ImportError_(ValueError):
    """The file can't be read as a bill; the message says why."""


@dataclass
class ImportRow:
    depth: int
    kind: str
    fields: dict[str, Any]
    parent: int | None = None
    """Index of the parent row in the list."""
    children: list[int] = field(default_factory=list)


def _norm(header: str) -> str:
    return re.sub(r"[^a-z]+", " ", header.lower()).strip()


def auto_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for fld, aliases in ALIASES.items():
        known = {_norm(a) for a in aliases} | {fld.replace("_", " ")}
        for column in columns:
            if column not in taken and _norm(column) in known:
                mapping[fld] = column
                taken.add(column)
                break
    return mapping


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> Decimal | None:
    text = _text(value).replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:  # 1.234,56 or 1,234.56
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def link(rows: list[ImportRow]) -> list[ImportRow]:
    """Set each row's parent from the depths, and turn sections under positions into positions."""
    stack: list[int] = []
    for i, row in enumerate(rows):
        while stack and rows[stack[-1]].depth >= row.depth:
            stack.pop()
        row.parent = stack[-1] if stack else None
        if row.parent is not None:
            rows[row.parent].children.append(i)
        stack.append(i)
    for row in rows:
        if row.kind == "section" and row.parent is not None and rows[row.parent].kind != "section":
            row.kind = "position"
    return rows


def rows_from_table(rows: list[dict[str, Any]], mapping: dict[str, str]) -> tuple[list[ImportRow], list[str]]:
    """Turn spreadsheet rows into a linked hierarchy. Returns the rows and per-row problems."""
    out: list[ImportRow] = []
    errors: list[str] = []
    for line, raw in enumerate(rows, start=2):
        value = {f: raw.get(column) for f, column in mapping.items()}
        text = _text(value.get("short_text"))
        ordinal = _text(value.get("ordinal")).strip(".")
        if not text and not ordinal and not _text(value.get("code")):
            continue
        level = _number(value.get("level"))
        if level is not None:
            depth = max(0, int(level) - 1)
        elif ordinal:
            depth = len([p for p in re.split(r"[.\s]+", ordinal) if p]) - 1
        else:
            depth = 0
        quantity, rate = _number(value.get("quantity")), _number(value.get("rate"))
        if _text(value.get("quantity")) and quantity is None:
            errors.append(f"Row {line}: '{_text(value.get('quantity'))}' isn't a quantity")
        if _text(value.get("rate")) and rate is None:
            errors.append(f"Row {line}: '{_text(value.get('rate'))}' isn't a rate")
        unit = _text(value.get("unit"))[:20]
        kind_text = _text(value.get("kind")).lower()
        if kind_text in ("section", "s", "heading", "title", "group", "lv", "ctgy", "category"):
            kind = "section"
        elif kind_text in ("position", "p", "item", "pos"):
            kind = "position"
        else:
            kind = "section" if quantity is None and rate is None and not unit else "position"
        out.append(
            ImportRow(
                depth=depth,
                kind=kind,
                fields={
                    "code": (_text(value.get("code")) or None) and _text(value.get("code"))[:40],
                    "short_text": (text or ordinal)[:500],
                    "long_text": _text(value.get("long_text")) or None,
                    "unit": unit or None,
                    "quantity": quantity if kind == "position" else None,
                    "unit_rate": rate if kind == "position" else None,
                    "classification": _text(value.get("classification"))[:30] or None,
                },
            )
        )
    return link(out), errors


# --- export ---------------------------------------------------------------------------------------------

COLUMNS = (
    ("ordinal", "Ordinal"),
    ("code", "Code"),
    ("classification", "Classification"),
    ("short_text", "Short text"),
    ("unit", "Unit"),
    ("quantity", "Quantity"),
    ("unit_rate", "Unit rate"),
    ("total", "Total"),
)


def to_xlsx(bill: dict[str, Any]) -> bytes:
    """A workbook with outline levels per depth, ``quantity × rate`` formulas and SUBTOTAL roll-ups."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "BOQ"
    sheet.append([bill["name"]])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([f"Currency: {bill['currency']}", f"Status: {bill['status']}"])
    sheet.append([])
    sheet.append([h for _, h in COLUMNS])
    header = sheet.max_row
    for cell in sheet[header]:
        cell.font = Font(bold=True)
    sheet.sheet_properties.outlinePr.summaryBelow = False
    positions = bill["positions"]
    first = header + 1
    rows = {p["id"]: first + i for i, p in enumerate(positions)}
    last_descendant: dict[int, int] = {}
    for i in range(len(positions) - 1, -1, -1):  # the last row of each subtree
        p = positions[i]
        end = rows[p["id"]]
        for q in positions[i + 1 :]:
            if q["depth"] <= p["depth"]:
                break
            end = rows[q["id"]]
        last_descendant[p["id"]] = end
    group_fill = PatternFill("solid", fgColor="EEF2F7")
    for p in positions:
        r = rows[p["id"]]
        group = p["has_children"] or p["kind"] == "section"
        values: list[Any] = [
            p["ordinal"],
            p["code"],
            p["classification"],
            ("    " * p["depth"]) + (p["short_text"] or ""),
            p["unit"],
            None if group else (float(p["quantity"]) if p["quantity"] is not None else None),
            None if group else (float(p["unit_rate"]) if p["unit_rate"] is not None else None),
        ]
        if group:
            end = last_descendant[p["id"]]
            values.append(f"=SUBTOTAL(9,H{r + 1}:H{end})" if end > r else 0)
        else:
            values.append(f"=ROUND(F{r}*G{r},2)")
        for c, v in enumerate(values, start=1):
            sheet.cell(row=r, column=c, value=v)
        if p["depth"]:
            sheet.row_dimensions[r].outline_level = min(7, p["depth"])
        if group:
            for c in range(1, len(COLUMNS) + 1):
                sheet.cell(row=r, column=c).font = Font(bold=True)
                sheet.cell(row=r, column=c).fill = group_fill
    last = first + len(positions) - 1
    r = last + 2
    net_row = r
    sheet.cell(row=r, column=4, value="Net total").font = Font(bold=True)
    sheet.cell(row=r, column=8, value=f"=SUBTOTAL(9,H{first}:H{max(first, last)})" if positions else 0)
    t = bill
    markup_rows = (
        ("Overhead", t["overhead_pct"], f"=ROUND(H{net_row}*G{{r}}/100,2)"),
        ("Profit", t["profit_pct"], f"=ROUND((H{net_row}+H{net_row + 1})*G{{r}}/100,2)"),
        ("Contingency", t["contingency_pct"], f"=ROUND(H{net_row}*G{{r}}/100,2)"),
    )
    for label, pct, formula in markup_rows:
        r += 1
        sheet.cell(row=r, column=4, value=f"{label} %")
        sheet.cell(row=r, column=7, value=float(pct))
        sheet.cell(row=r, column=8, value=formula.format(r=r))
    r += 1
    sub_row = r
    sheet.cell(row=r, column=4, value="Subtotal").font = Font(bold=True)
    sheet.cell(row=r, column=8, value=f"=SUM(H{net_row}:H{r - 1})")
    r += 1
    sheet.cell(row=r, column=4, value="Tax %")
    sheet.cell(row=r, column=7, value=float(t["tax_pct"]))
    sheet.cell(row=r, column=8, value=f"=ROUND(H{sub_row}*G{r}/100,2)")
    r += 1
    sheet.cell(row=r, column=4, value="Grand total").font = Font(bold=True)
    sheet.cell(row=r, column=8, value=f"=H{sub_row}+H{r - 1}").font = Font(bold=True)
    money = '#,##0.00 "' + bill["currency"] + '"'
    for row in sheet.iter_rows(min_row=first, max_row=r, min_col=6, max_col=8):
        for cell in row:
            if cell.column == 6:
                cell.number_format = "#,##0.000"
            elif cell.column == 8 or (cell.column == 7 and cell.row <= last):
                cell.number_format = money
    for i, width in enumerate((10, 14, 14, 60, 8, 12, 14, 16), start=1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = sheet.cell(row=first, column=1)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def table_rows(bill: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**p, "level": p["depth"] + 1} for p in bill["positions"]]


CSV_COLUMNS = (("level", "Level"), *COLUMNS[:6], ("unit_rate", "Unit rate"), ("total", "Total"), ("long_text", "Long text"))


# --- GAEB -------------------------------------------------------------------------------------------------


def _paragraphs(parent: ET.Element, tag: str, text: str) -> None:
    el = ET.SubElement(parent, tag)
    for line in (text or "").splitlines() or [""]:
        p = ET.SubElement(el, "p")
        ET.SubElement(p, "span").text = line


def to_gaeb(bill: dict[str, Any], project_name: str, phase: int = 83) -> bytes:
    priced = phase >= 84
    root = ET.Element("GAEB", {"xmlns": GAEB_NS.format(phase=phase)})
    info = ET.SubElement(root, "GAEBInfo")
    ET.SubElement(info, "Version").text = "3.3"
    ET.SubElement(info, "ProgSystem").text = "QC Manager"
    prj = ET.SubElement(root, "PrjInfo")
    ET.SubElement(prj, "NamePrj").text = project_name
    ET.SubElement(prj, "Cur").text = bill["currency"]
    award = ET.SubElement(root, "Award")
    ET.SubElement(award, "DP").text = str(phase)
    ET.SubElement(award, "Cur").text = bill["currency"]
    boq = ET.SubElement(award, "BoQ", {"ID": f"BOQ{bill['id']}"})
    boq_info = ET.SubElement(boq, "BoQInfo")
    ET.SubElement(boq_info, "Name").text = bill["name"]
    positions = bill["positions"]
    kids: dict[int | None, list[dict[str, Any]]] = {}
    for p in positions:
        kids.setdefault(p["parent_id"], []).append(p)
    depth = max((p["depth"] for p in positions if p["has_children"] or p["kind"] == "section"), default=-1) + 1
    for _ in range(depth):
        bkdn = ET.SubElement(boq_info, "BoQBkdn")
        ET.SubElement(bkdn, "Type").text = "BoQLevel"
        ET.SubElement(bkdn, "Length").text = "2"
    bkdn = ET.SubElement(boq_info, "BoQBkdn")
    ET.SubElement(bkdn, "Type").text = "Item"
    ET.SubElement(bkdn, "Length").text = "4"

    def emit(body: ET.Element, children: list[dict[str, Any]]) -> None:
        items: ET.Element | None = None
        for index, p in enumerate(children, start=1):
            if p["has_children"] or p["kind"] == "section":
                ctgy = ET.SubElement(body, "BoQCtgy", {"ID": f"C{p['id']}", "RNoPart": f"{index:02d}"})
                _paragraphs(ctgy, "LblTx", p["short_text"])
                emit(ET.SubElement(ctgy, "BoQBody"), kids.get(p["id"], []))
                continue
            if items is None:
                items = ET.SubElement(body, "Itemlist")
            item = ET.SubElement(items, "Item", {"ID": f"I{p['id']}", "RNoPart": f"{index:04d}"})
            if p["quantity"] is not None:
                ET.SubElement(item, "Qty").text = f"{Decimal(p['quantity']):.3f}"
            ET.SubElement(item, "QU").text = p["unit"] or ""
            if priced and p["unit_rate"] is not None:
                ET.SubElement(item, "UP").text = f"{Decimal(p['unit_rate']):.2f}"
                ET.SubElement(item, "IT").text = f"{Decimal(p['total']):.2f}"
            complete = ET.SubElement(ET.SubElement(item, "Description"), "CompleteText")
            if p["long_text"]:
                _paragraphs(ET.SubElement(complete, "DetailTxt"), "Text", p["long_text"])
            outline = ET.SubElement(ET.SubElement(complete, "OutlineText"), "OutlTxt")
            _paragraphs(outline, "TextOutlTxt", p["short_text"])

    emit(ET.SubElement(boq, "BoQBody"), kids.get(None, []))
    ET.indent(root)
    body: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return body


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _local(c.tag) == name), None)


def _all_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    lines = []
    for p in el.iter():
        if _local(p.tag) == "p":
            lines.append("".join(p.itertext()).strip())
    return "\n".join(lines).strip() or "".join(el.itertext()).strip()


def rows_from_gaeb(data: bytes) -> list[ImportRow]:
    if len(data) > MAX_GAEB_BYTES:
        raise ImportError_("GAEB files are limited to 20 MB.")
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise ImportError_("GAEB files with a DOCTYPE or entities aren't accepted.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportError_(f"That isn't readable GAEB XML: {exc}") from exc
    boq = next((el for el in root.iter() if _local(el.tag) == "BoQ"), None)
    body = _child(boq, "BoQBody") if boq is not None else None
    if body is None:
        raise ImportError_("No BoQ/BoQBody in the file.")
    rows: list[ImportRow] = []

    def walk(body: ET.Element, depth: int) -> None:
        for el in body:
            name = _local(el.tag)
            if name == "BoQCtgy":
                rows.append(
                    ImportRow(depth, "section", {"code": None, "short_text": _all_text(_child(el, "LblTx"))[:500] or "-"})
                )
                inner = _child(el, "BoQBody")
                if inner is not None:
                    walk(inner, depth + 1)
            elif name == "Itemlist":
                for item in el:
                    if _local(item.tag) != "Item":
                        continue
                    complete = next((c for c in item.iter() if _local(c.tag) == "CompleteText"), None)
                    outline = (
                        next((c for c in complete.iter() if _local(c.tag) == "OutlineText"), None)
                        if complete is not None
                        else None
                    )
                    detail = (
                        next((c for c in complete.iter() if _local(c.tag) == "DetailTxt"), None)
                        if complete is not None
                        else None
                    )
                    short = _all_text(outline)
                    long = _all_text(detail)
                    qty, qu, up = _child(item, "Qty"), _child(item, "QU"), _child(item, "UP")
                    rows.append(
                        ImportRow(
                            depth,
                            "position",
                            {
                                "code": None,
                                "short_text": (short or long.split("\n")[0])[:500],
                                "long_text": long or None,
                                "unit": (qu.text or "").strip()[:20] or None if qu is not None else None,
                                "quantity": _number(qty.text) if qty is not None else None,
                                "unit_rate": _number(up.text) if up is not None else None,
                                "classification": None,
                            },
                        )
                    )

    walk(body, 0)
    return link(rows)

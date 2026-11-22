"""Turning a template into a PDF or a workbook.

Each section is first resolved into a ``Block`` (headers and rows, a chart's series, KPI values or
text) with the viewer's access; a section that can't be built (module off, no permission, no
project) becomes a note in the report instead of failing it. The blocks are then rendered.
"""

import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import AreaChart, BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.reporting.export import NUMBER_FORMATS, display
from ...infrastructure.reporting.tables import aggregate, pivot, pivot_table
from ..common.exceptions import DomainError
from ..files.models import StoredFile
from ..files.storage import storage
from ..projects.models import Project
from .schemas import (
    Branding,
    ChartSection,
    KpiSection,
    KpiValue,
    PivotSection,
    Section,
    TableSection,
    TextSection,
)
from .service import BadFilterError, ReportInputError, Viewer, dataset_for, kpi_values, rows_for

logger = get_logger()

PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#64748b", "#ea580c"]
MAX_CATEGORIES = 40
STATUS_TEXT = {"good": "On target", "warning": "Watch", "bad": "Off target", "neutral": ""}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class Block:
    kind: str
    """``kpis``, ``table``, ``chart``, ``text`` or ``note``."""
    title: str
    headers: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    text: str = ""
    chart: dict[str, Any] | None = None
    statuses: list[str] = field(default_factory=list)


def kpi_display(value: float | None, unit: str) -> str:
    if value is None:
        return "–"
    if unit == "money":
        return f"{value:,.0f}"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "count":
        return f"{value:,.0f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".") + (f" {unit}" if unit else "")


def _labels(dataset: Any) -> dict[str, str]:
    return {c.key: c.label for c in dataset.columns}


async def _kpis(db: AsyncSession, viewer: Viewer, s: KpiSection, project: Project | None) -> Block:
    if project is None:
        return Block("note", s.title, text="Key figures need a project.")
    values: list[KpiValue] = await kpi_values(db, project.id, viewer.held, s.keys or None)
    return Block(
        "kpis",
        s.title,
        headers=["Measure", "Value", "Status"],
        types=["text", "text", "text"],
        rows=[[v.label, kpi_display(v.value, v.unit), STATUS_TEXT[v.status]] for v in values],
        statuses=[v.status for v in values],
    )


def _sort_value(v: Any) -> tuple[int, Any]:
    if v is None or v == "":
        return (1, "")
    if isinstance(v, (int, float)):
        return (0, v)
    return (0, str(v).lower())


async def _table(db: AsyncSession, viewer: Viewer, s: TableSection, project: Project | None) -> Block:
    pid = project.id if project else None
    dataset = await dataset_for(db, viewer, s.dataset, pid)
    rows = await rows_for(db, viewer, dataset, pid, s.filters)
    columns = [dataset.column(k) for k in s.columns] if s.columns else list(dataset.columns)
    if any(c is None for c in columns):
        raise ReportInputError(f"{dataset.title} has no column {', '.join(k for k in s.columns if dataset.column(k) is None)}")
    picked = [c for c in columns if c is not None]
    title = s.title or dataset.title
    if s.group_by:
        group = dataset.column(s.group_by)
        if group is None:
            raise ReportInputError(f"{dataset.title} has no column {s.group_by}")
        sums = [c for c in picked if c.summable and c.key != group.key]
        buckets: dict[Any, list[dict[str, Any]]] = {}
        for r in rows:
            buckets.setdefault(r.get(group.key), []).append(r)
        table = [
            [key, len(items), *(aggregate((i.get(c.key) for i in items), "sum") for c in sums)]
            for key, items in sorted(buckets.items(), key=lambda kv: _sort_value(kv[0]))
        ]
        return Block(
            "table",
            title,
            headers=[group.label, "Rows", *(c.label for c in sums)],
            types=[group.type, "number", *(c.type for c in sums)],
            rows=table,
        )
    if s.sort_by:
        rows = sorted(rows, key=lambda r: _sort_value(r.get(s.sort_by or "")), reverse=s.descending)
    return Block(
        "table",
        title,
        headers=[c.label for c in picked],
        types=[c.type for c in picked],
        rows=[[r.get(c.key) for c in picked] for r in rows[: s.limit]],
    )


async def _chart(db: AsyncSession, viewer: Viewer, s: ChartSection, project: Project | None) -> Block:
    pid = project.id if project else None
    dataset = await dataset_for(db, viewer, s.dataset, pid)
    labels = _labels(dataset)
    for key in (s.x, *s.y, *([s.group_by] if s.group_by else [])):
        if key != "*" and key not in labels:
            raise ReportInputError(f"{dataset.title} has no column {key}")
    rows = await rows_for(db, viewer, dataset, pid, s.filters)
    result = pivot(rows, [s.x], [s.group_by] if s.group_by else [], [(y, s.agg) for y in s.y])
    categories = ["" if k[0] is None else str(k[0]) for k in result["row_keys"]][:MAX_CATEGORIES]
    series: list[dict[str, Any]] = []
    if s.group_by:
        for j, ck in enumerate(result["column_keys"]):
            name = "(blank)" if ck[0] is None else str(ck[0])
            series.append({"name": name, "values": [result["cells"][i][j][0] or 0 for i in range(len(categories))]})
    else:
        for v, y in enumerate(s.y):
            name = labels.get(y, "Rows") + ("" if s.agg == "sum" else f" ({s.agg})")
            series.append({"name": name, "values": [result["cells"][i][0][v] or 0 for i in range(len(categories))]})
    headers = [labels.get(s.x, s.x), *(se["name"] for se in series)]
    table = [[c, *(se["values"][i] for se in series)] for i, c in enumerate(categories)]
    return Block(
        "chart",
        s.title or dataset.title,
        headers=headers,
        types=["text", *(["number"] * len(series))],
        rows=table,
        chart={"type": s.chart, "categories": categories, "series": series},
    )


async def _pivot(db: AsyncSession, viewer: Viewer, s: PivotSection, project: Project | None) -> Block:
    pid = project.id if project else None
    dataset = await dataset_for(db, viewer, s.dataset, pid)
    labels = _labels(dataset)
    unknown = [k for k in (*s.rows, *s.columns, *(v.field for v in s.values)) if k != "*" and k not in labels]
    if unknown:
        raise ReportInputError(f"{dataset.title} has no column {', '.join(unknown)}")
    rows = await rows_for(db, viewer, dataset, pid, s.filters)
    result = pivot(rows, s.rows, s.columns, [(v.field, v.agg) for v in s.values])
    headers, table = pivot_table(result, labels)
    keys = max(1, len(s.rows))
    return Block(
        "table",
        s.title or dataset.title,
        headers=headers,
        types=["text"] * keys + ["number"] * (len(headers) - keys),
        rows=table,
    )


async def resolve(db: AsyncSession, viewer: Viewer, sections: list[Section], project: Project | None) -> list[Block]:
    blocks: list[Block] = []
    for s in sections:
        try:
            if isinstance(s, KpiSection):
                blocks.append(await _kpis(db, viewer, s, project))
            elif isinstance(s, TableSection):
                blocks.append(await _table(db, viewer, s, project))
            elif isinstance(s, ChartSection):
                blocks.append(await _chart(db, viewer, s, project))
            elif isinstance(s, PivotSection):
                blocks.append(await _pivot(db, viewer, s, project))
            elif isinstance(s, TextSection):
                blocks.append(Block("text", s.title, text=s.body))
        except DomainError as exc:
            message = str(exc) if isinstance(exc, ReportInputError | BadFilterError) else exc.public_detail or str(exc)
            blocks.append(Block("note", s.title or getattr(s, "dataset", ""), text=f"Not available: {message}"))
    return blocks


# --- PDF -----------------------------------------------------------------------------------------------


def _drawing(chart: dict[str, Any], width: float) -> Drawing:
    height = 70 * mm
    drawing = Drawing(width, height)
    series, categories = chart["series"], chart["categories"]
    if not categories or not series:
        return drawing
    names = [str(se["name"]) for se in series]
    if chart["type"] == "pie":
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 10, 10, height - 20, height - 20
        pie.data = [max(0.0, float(v)) for v in series[0]["values"]] or [1]
        pie.labels = None
        for i in range(len(pie.data)):
            pie.slices[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
            pie.slices[i].strokeColor = colors.white
        drawing.add(pie)
        legend_names, legend_count = categories, len(categories)
    else:
        if chart["type"] in ("line", "area"):
            plot: Any = HorizontalLineChart()
            for i in range(len(series)):
                plot.lines[i].strokeColor = colors.HexColor(PALETTE[i % len(PALETTE)])
                plot.lines[i].strokeWidth = 1.5
        else:
            plot = VerticalBarChart()
            plot.barSpacing = 1
            for i in range(len(series)):
                plot.bars[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
                plot.bars[i].strokeColor = None
            if chart["type"] == "stacked":
                plot.categoryAxis.style = "stacked"
        plot.x, plot.y = 40, 30
        plot.width, plot.height = width - 170, height - 45
        plot.data = [tuple(float(v or 0) for v in se["values"]) for se in series]
        plot.categoryAxis.categoryNames = [c[:12] for c in categories]
        plot.categoryAxis.labels.fontSize = 6
        plot.categoryAxis.labels.angle = 30 if len(categories) > 8 else 0
        plot.categoryAxis.labels.boxAnchor = "ne" if len(categories) > 8 else "n"
        plot.valueAxis.labels.fontSize = 6
        plot.valueAxis.forceZero = True
        plot.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}"
        drawing.add(plot)
        legend_names, legend_count = names, len(series)
    legend = Legend()
    legend.x, legend.y = width - 120, height - 10
    legend.fontSize = 6
    legend.alignment = "right"
    legend.columnMaximum = 12
    legend.colorNamePairs = [
        (colors.HexColor(PALETTE[i % len(PALETTE)]), str(legend_names[i])[:24]) for i in range(min(legend_count, 12))
    ]
    drawing.add(legend)
    return drawing


async def _logo(db: AsyncSession, branding: Branding, project: Project | None) -> Image | None:
    if not branding.logo_file_id:
        return None
    f = await db.get(StoredFile, branding.logo_file_id)
    if f is None or f.content_type not in ("image/png", "image/jpeg") or (f.project_id not in (None, project and project.id)):
        return None
    try:
        image = Image(str(storage().path(f.storage_key)), width=40 * mm, height=15 * mm, kind="proportional")
        image.hAlign = "LEFT"
        return image
    except Exception:
        logger.warning("Report logo could not be read", extra={"file_id": f.id})
        return None


def _subtitle(project: Project | None, branding: Branding, when: datetime) -> str:
    parts = [f"{project.code} — {project.name}" if project else "All projects", when.strftime("%d %b %Y")]
    if branding.company_name:
        parts.insert(0, branding.company_name)
    return " · ".join(parts)


async def render_pdf_report(
    db: AsyncSession, name: str, blocks: list[Block], project: Project | None, branding: Branding, wide: bool
) -> bytes:
    when = datetime.now(UTC)
    doc = Document(
        title=name,
        subtitle=_subtitle(project, branding, when),
        landscape=wide,
        footer=" · ".join(x for x in (branding.company_name, name) if x),
    )
    logo = await _logo(db, branding, project)
    if logo is not None:
        doc.flow.append(logo)
    width = (landscape(A4)[0] if wide else A4[0]) - 30 * mm
    for b in blocks:
        if b.title:
            doc.heading(b.title)
        if b.kind in ("text", "note"):
            doc.paragraph(b.text)
            continue
        if b.kind == "chart" and b.chart:
            doc.flow.append(_drawing(b.chart, width))
        numeric = {i for i, t in enumerate(b.types) if t in ("money", "number")}
        if b.rows:
            doc.table(
                b.headers, [[display(v, t) for v, t in zip(row, b.types, strict=False)] for row in b.rows], numeric=numeric
            )
        elif b.kind != "chart":
            doc.paragraph("Nothing to show.")
    return render_pdf(doc)


# --- Excel ---------------------------------------------------------------------------------------------


def _sheet_name(title: str, taken: set[str]) -> str:
    base = re.sub(r"[\[\]\*\?/\\:]", " ", title).strip()[:28] or "Sheet"
    name, n = base, 2
    while name.lower() in taken:
        name, n = f"{base[:25]} ({n})", n + 1
    taken.add(name.lower())
    return name


def _xl(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return str(value)
    return value


def _excel_chart(kind: str) -> Any:
    if kind == "pie":
        return PieChart()
    if kind == "line":
        return LineChart()
    if kind == "area":
        return AreaChart()
    chart = BarChart()
    chart.type = "col"
    if kind == "stacked":
        chart.grouping = "stacked"
        chart.overlap = 100
    return chart


def render_xlsx_report(name: str, blocks: list[Block], project: Project | None, branding: Branding) -> bytes:
    when = datetime.now(UTC)
    book = Workbook()
    summary = book.active
    assert summary is not None
    summary.title = "Summary"
    taken = {"summary"}
    summary.append([name])
    summary["A1"].font = Font(bold=True, size=14)
    summary.append([_subtitle(project, branding, when)])
    summary.append([])
    summary.column_dimensions["A"].width = 36
    summary.column_dimensions["B"].width = 20
    summary.column_dimensions["C"].width = 14
    for b in blocks:
        if b.kind in ("kpis", "text", "note"):
            summary.append([b.title])
            summary.cell(summary.max_row, 1).font = Font(bold=True)
            if b.kind == "kpis":
                for row in b.rows:
                    summary.append(row)
            else:
                for line in b.text.splitlines() or [""]:
                    summary.append([line])
            summary.append([])
            continue
        sheet = book.create_sheet(_sheet_name(b.title, taken))
        sheet.append(b.headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in b.rows:
            sheet.append([_xl(v) for v in row])
        for i, t in enumerate(b.types, start=1):
            letter = get_column_letter(i)
            sheet.column_dimensions[letter].width = max(12, min(48, len(str(b.headers[i - 1])) + 4))
            pattern = NUMBER_FORMATS.get(t)
            if pattern:
                for (cell,) in sheet.iter_rows(min_row=2, min_col=i, max_col=i):
                    cell.number_format = pattern
        sheet.freeze_panes = "A2"
        if b.kind == "chart" and b.chart and b.rows:
            chart = _excel_chart(b.chart["type"])
            chart.title = b.title
            n = len(b.rows)
            last_col = 2 if b.chart["type"] == "pie" else len(b.headers)
            chart.add_data(Reference(sheet, min_col=2, max_col=last_col, min_row=1, max_row=n + 1), titles_from_data=True)
            chart.set_categories(Reference(sheet, min_col=1, min_row=2, max_row=n + 1))
            chart.width, chart.height = 22, 10
            sheet.add_chart(chart, f"{get_column_letter(len(b.headers) + 2)}2")
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def build_report(
    db: AsyncSession,
    viewer: Viewer,
    *,
    name: str,
    sections: list[Section],
    branding: Branding,
    wide: bool,
    project: Project | None,
    fmt: str,
) -> tuple[bytes, str, str]:
    """``(bytes, media type, file name)``."""
    blocks = await resolve(db, viewer, sections, project)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", f"{name} {project.code if project else ''}").strip("-").lower() or "report"
    stem += "-" + datetime.now(UTC).strftime("%Y%m%d")
    if fmt == "xlsx":
        return render_xlsx_report(name, blocks, project, branding), XLSX, f"{stem}.xlsx"
    return await render_pdf_report(db, name, blocks, project, branding, wide), "application/pdf", f"{stem}.pdf"

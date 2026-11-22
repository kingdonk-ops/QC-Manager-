"""Server-side PDFs for every module: registers, cover sheets, minutes, reports.

from ...infrastructure.pdf import Document, render_pdf
doc = Document(title="Transmittal TR-004", subtitle="LNG Train 3 · P-24017")
doc.fields([("To", "Northwind Energy"), ("Purpose", "For construction")])
doc.heading("Documents")
doc.table(["No.", "Title", "Rev"], rows, widths=[0.2, 0.65, 0.15])
doc.paragraph("Please acknowledge receipt.")
pdf_bytes = render_pdf(doc)
"""

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=_styles["Title"], fontSize=16, leading=20, alignment=0, spaceAfter=2)
SUBTITLE = ParagraphStyle("s", parent=_styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"), spaceAfter=10)
HEADING = ParagraphStyle("h", parent=_styles["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("b", parent=_styles["Normal"], fontSize=9, leading=12)
CELL = ParagraphStyle("c", parent=BODY, fontSize=8, leading=10)
HEAD_CELL = ParagraphStyle("hc", parent=CELL, fontName="Helvetica-Bold")


def _p(value: Any, style: ParagraphStyle = CELL) -> Paragraph:
    return Paragraph(escape("" if value is None else str(value)).replace("\n", "<br/>"), style)


@dataclass
class Document:
    title: str
    subtitle: str = ""
    landscape: bool = False
    footer: str = ""
    flow: list[Any] = field(default_factory=list)

    def heading(self, text: str) -> "Document":
        self.flow.append(_p(text, HEADING))
        return self

    def paragraph(self, text: str) -> "Document":
        self.flow.append(_p(text, BODY))
        self.flow.append(Spacer(1, 4))
        return self

    def fields(self, pairs: list[tuple[str, Any]]) -> "Document":
        """Label/value pairs in two columns, like a form header."""
        data = [[_p(k, HEAD_CELL), _p(v)] for k, v in pairs]
        table = Table(data, colWidths=[40 * mm, None], hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        self.flow.append(table)
        self.flow.append(Spacer(1, 6))
        return self

    def table(
        self, headers: list[str], rows: list[list[Any]], widths: list[float] | None = None, numeric: set[int] | None = None
    ) -> "Document":
        """A ruled table. ``widths`` are fractions of the page width; ``numeric`` column indexes align right."""
        page_width = (landscape(A4)[0] if self.landscape else A4[0]) - 30 * mm
        col_widths = [w * page_width for w in widths] if widths else None
        data = [[_p(h, HEAD_CELL) for h in headers]] + [[_p(v) for v in row] for row in rows]
        table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#94a3b8")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i in numeric or set():
            style.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
        table.setStyle(TableStyle(style))
        self.flow.append(table)
        self.flow.append(Spacer(1, 6))
        return self

    def page_break(self) -> "Document":
        self.flow.append(PageBreak())
        return self


def render_pdf(doc: Document) -> bytes:
    buffer = io.BytesIO()
    size = landscape(A4) if doc.landscape else A4
    printed = datetime.now().strftime("%d %b %Y %H:%M")

    def on_page(canvas: Any, template: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 8 * mm, f"{doc.footer or doc.title} · printed {printed}")
        canvas.drawRightString(size[0] - 15 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    template = SimpleDocTemplate(
        buffer, pagesize=size, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title=doc.title
    )
    story = [_p(doc.title, TITLE)]
    if doc.subtitle:
        story.append(_p(doc.subtitle, SUBTITLE))
    template.build(story + doc.flow, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()

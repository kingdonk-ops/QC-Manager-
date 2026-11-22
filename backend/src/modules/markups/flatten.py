"""Print markups onto the PDF: each marked-up page gets a ReportLab overlay merged on top with pypdf.

Pages with a /Rotate have the rotation moved into their content first, so the page's box matches what
the viewer showed and the markup coordinates (top-left origin, y down) map straight onto it.
"""

import io
import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas

from .geometry import cloud_points, format_measurement

DEFAULT_COLOR = "#dc2626"


def _color(value: Any, fallback: str = DEFAULT_COLOR) -> colors.Color:
    try:
        return colors.HexColor(str(value or fallback)[:7])
    except (ValueError, TypeError):
        return colors.HexColor(fallback)


class _Page:
    """Draws on one overlay page, taking top-left, y-down coordinates."""

    def __init__(self, canvas: Canvas, height: float) -> None:
        self.c = canvas
        self.h = height

    def y(self, value: float) -> float:
        return self.h - value

    def path(self, points: Sequence[Sequence[float]], *, close: bool = False, fill: bool = False) -> None:
        p = self.c.beginPath()
        p.moveTo(points[0][0], self.y(points[0][1]))
        for x, y in points[1:]:
            p.lineTo(x, self.y(y))
        if close:
            p.close()
        self.c.drawPath(p, stroke=1, fill=1 if fill else 0)

    def arrow_head(self, a: Sequence[float], b: Sequence[float], size: float) -> None:
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        left = (b[0] - size * math.cos(angle - math.pi / 7), b[1] - size * math.sin(angle - math.pi / 7))
        right = (b[0] - size * math.cos(angle + math.pi / 7), b[1] - size * math.sin(angle + math.pi / 7))
        self.path([b, left, right], close=True, fill=True)

    def text(self, x: float, y: float, text: str, size: float, *, bold: bool = False, center: bool = False) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        for i, line in enumerate(text.splitlines() or [""]):
            baseline = self.y(y + size * (i + 1))
            if center:
                self.c.drawCentredString(x, baseline, line)
            else:
                self.c.drawString(x, baseline, line)

    def label(self, at: Sequence[float], text: str, size: float, color: colors.Color) -> None:
        """A measurement label on a white tab, so it reads over the drawing."""
        width = self.c.stringWidth(text, "Helvetica-Bold", size) + 4
        self.c.saveState()
        self.c.setFillColor(colors.white)
        self.c.setStrokeColor(color)
        self.c.setLineWidth(0.5)
        self.c.rect(at[0], self.y(at[1]) - 2, width, size + 3, stroke=1, fill=1)
        self.c.setFillColor(color)
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(at[0] + 2, self.y(at[1]) + 0.5, text)
        self.c.restoreState()


def _draw(page: _Page, m: dict[str, Any]) -> None:
    c = page.c
    kind, g, style = m["type"], m["geometry"], m.get("style") or {}
    color = _color(style.get("color"))
    width = float(style.get("width") or 1.5)
    size = float(style.get("font_size") or 12)
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    c.setLineJoin(1)
    c.setLineCap(1)
    if "opacity" in style:
        c.setStrokeAlpha(float(style["opacity"]))
        c.setFillAlpha(float(style["opacity"]))
    text = m.get("text") or ""
    if kind in ("rect", "ellipse", "cloud", "highlight", "stamp", "text", "callout"):
        x, y, w, h = g["x"], g["y"], g["w"], g["h"]
        if kind == "rect":
            c.rect(x, page.y(y + h), w, h, stroke=1, fill=0)
        elif kind == "ellipse":
            c.ellipse(x, page.y(y + h), x + w, page.y(y), stroke=1, fill=0)
        elif kind == "cloud":
            page.path(cloud_points(x, y, w, h), close=True)
        elif kind == "highlight":
            c.setFillColor(_color(style.get("color"), "#facc15"))
            c.setFillAlpha(float(style.get("opacity", 0.35)))
            c.rect(x, page.y(y + h), w, h, stroke=0, fill=1)
        elif kind == "stamp":
            c.setLineWidth(max(width, 2))
            c.roundRect(x, page.y(y + h), w, h, min(6, h / 4), stroke=1, fill=0)
            lines = text.splitlines() or [""]
            head = min(size * 1.5, h / (len(lines) + 0.6))
            page.text(x + w / 2, y + head * 0.25, lines[0].upper(), head, bold=True, center=True)
            if len(lines) > 1:
                page.text(x + w / 2, y + head * 1.25, "\n".join(lines[1:]), head * 0.55, center=True)
        elif kind == "text":
            page.text(x + 2, y, text, size)
        else:
            ax, ay = g["anchor"]
            cx = min(max(ax, x), x + w)
            cy = min(max(ay, y), y + h)
            c.line(ax, page.y(ay), cx, page.y(cy))
            page.arrow_head((cx, cy), (ax, ay), max(6, width * 4))
            c.setFillColor(colors.white)
            c.rect(x, page.y(y + h), w, h, stroke=1, fill=1)
            c.setFillColor(color)
            page.text(x + 3, y + 2, text, size)
    else:
        points = g["points"]
        if kind == "measure_area":
            c.setFillAlpha(0.15)
            page.path(points, close=True, fill=True)
            c.setFillAlpha(1)
        else:
            page.path(points)
        if kind == "arrow":
            page.arrow_head(points[-2], points[-1], max(8, width * 4))
        if kind.startswith("measure"):
            for x, y in (points[0], points[-1]) if kind != "measure_area" else points:
                c.circle(x, page.y(y), max(1.5, width), stroke=0, fill=1)
            label = format_measurement(m.get("measurement")) or "not calibrated"
            if kind == "measure_area":
                at = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
            else:
                at = (points[-1][0] + 4, points[-1][1] - 4)
            page.label(at, label, max(7, size * 0.8), color)
    c.restoreState()


def flatten(pdf: bytes, markups: list[dict[str, Any]]) -> bytes:
    """``markups`` are dicts with ``page`` (1-based), ``type``, ``geometry``, ``style``, ``text``, ``measurement``."""
    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for m in markups:
        by_page[int(m["page"])].append(m)
    for number, page in enumerate(writer.pages, start=1):
        if not by_page.get(number):
            continue
        if page.rotation:
            page.transfer_rotation_to_content()
        box = page.cropbox
        width, height = float(box.width), float(box.height)
        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=(width, height))
        drawer = _Page(canvas, height)
        for m in by_page[number]:
            _draw(drawer, m)
        canvas.showPage()
        canvas.save()
        overlay = PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
        page.merge_transformed_page(overlay, Transformation().translate(float(box.left), float(box.bottom)))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

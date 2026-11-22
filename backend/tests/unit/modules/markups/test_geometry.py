"""Calibration and measurement maths, and printing markups onto a PDF."""

import io
import math

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

from src.modules.markups import geometry
from src.modules.markups.flatten import flatten


def test_scale_factor_from_two_points_and_a_real_distance():
    # 200 PDF units on the page are 5 m on site.
    factor = geometry.scale_factor([100, 100], [300, 100], 5, "m")
    assert factor == pytest.approx(0.025)
    # The same in millimetres and feet.
    assert geometry.scale_factor([0, 0], [0, 200], 5000, "mm") == pytest.approx(0.025)
    assert geometry.scale_factor([0, 0], [120, 160], 10, "ft") == pytest.approx(10 * 0.3048 / 200)


def test_scale_factor_refuses_nonsense():
    with pytest.raises(geometry.GeometryError):
        geometry.scale_factor([1, 1], [1, 1], 5, "m")
    with pytest.raises(geometry.GeometryError):
        geometry.scale_factor([0, 0], [10, 0], 0, "m")
    with pytest.raises(geometry.GeometryError):
        geometry.scale_factor([0, 0], [10, 0], 1, "furlong")


def test_length_and_polyline_length_scale_linearly():
    factor = 0.025  # metres per PDF unit
    line = geometry.measure("measure_length", [[0, 0], [300, 400]], factor)
    assert line == {"value": pytest.approx(12.5), "unit": "m", "meters_per_unit": factor}
    path = geometry.measure("measure_polyline", [[0, 0], [100, 0], [100, 100], [0, 100]], factor)
    assert path["value"] == pytest.approx(7.5)


def test_area_scales_with_the_square_of_the_factor():
    square = [[0, 0], [200, 0], [200, 200], [0, 200]]
    area = geometry.measure("measure_area", square, 0.025)
    assert area["unit"] == "m2"
    assert area["value"] == pytest.approx(25.0)  # 5 m x 5 m
    # Winding doesn't matter, and an L-shape is the sum of its parts.
    assert geometry.polygon_area(list(reversed(square))) == pytest.approx(40_000)
    ell = [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]]
    assert geometry.polygon_area(ell) == pytest.approx(300)


def test_format_measurement():
    assert geometry.format_measurement({"value": 2.5, "unit": "m"}) == "2.500 m"
    assert geometry.format_measurement({"value": 1234.567, "unit": "m"}) == "1,234.57 m"
    assert geometry.format_measurement({"value": 25, "unit": "m2"}) == "25.00 m²"
    assert geometry.format_measurement(None) == ""


def test_normalise_checks_geometry_per_type():
    assert geometry.normalise("rect", {"x": 50, "y": 60, "w": -20, "h": 10, "extra": 1}) == {
        "x": 30.0,
        "y": 60.0,
        "w": 20.0,
        "h": 10.0,
    }
    assert geometry.normalise("callout", {"x": 0, "y": 0, "w": 10, "h": 10, "anchor": [50, 50]})["anchor"] == [50.0, 50.0]
    assert geometry.normalise("arrow", {"points": [[0, 0], [1, 1]]}) == {"points": [[0.0, 0.0], [1.0, 1.0]]}
    for kind, bad in (
        ("rect", {"x": 1, "y": 2, "w": "wide", "h": 4}),
        ("line", {"points": [[0, 0]]}),
        ("measure_area", {"points": [[0, 0], [1, 1]]}),
        ("polyline", {"points": [[0, 0], [1, math.inf]]}),
        ("polyline", {"points": [[0, 0], [1, True]]}),
        ("teleport", {}),
    ):
        with pytest.raises(geometry.GeometryError):
            geometry.normalise(kind, bad)


def test_cloud_points_bulge_outside_the_box():
    points = geometry.cloud_points(100, 100, 200, 100)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    assert min(xs) < 100 and max(xs) > 300 and min(ys) < 100 and max(ys) > 200
    assert points[0] == pytest.approx((100, 100))


def _pdf(pages: int = 2, size: tuple[float, float] = (595, 842)) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=size)
    for i in range(pages):
        canvas.drawString(72, 72, f"Drawing sheet {i + 1}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_flatten_prints_every_kind_of_markup_on_its_page():
    style = {"color": "#dc2626", "width": 2, "opacity": 1, "font_size": 12}
    box = {"x": 100, "y": 100, "w": 120, "h": 60}
    kinds = ["rect", "ellipse", "cloud", "highlight", "stamp", "text"]
    markups = [{"page": 2, "type": k, "geometry": box, "style": style, "text": "APPROVED\nJo, 22 Nov"} for k in kinds]
    markups += [
        {"page": 2, "type": "callout", "geometry": {**box, "anchor": [400, 500]}, "style": style, "text": "Check"},
        {"page": 2, "type": "arrow", "geometry": {"points": [[10, 10], [200, 300]]}, "style": style},
        {"page": 2, "type": "freehand", "geometry": {"points": [[10, 10], [20, 30], [40, 35]]}, "style": style},
        {
            "page": 2,
            "type": "measure_area",
            "geometry": {"points": [[0, 0], [200, 0], [200, 200]]},
            "style": style,
            "measurement": {"value": 12.5, "unit": "m2"},
        },
        {"page": 2, "type": "measure_length", "geometry": {"points": [[0, 0], [200, 0]]}, "style": style},
    ]
    out = PdfReader(io.BytesIO(flatten(_pdf(), markups)))
    assert len(out.pages) == 2
    untouched, marked = out.pages[0].extract_text(), out.pages[1].extract_text()
    assert "APPROVED" not in untouched
    assert "Drawing sheet 2" in marked
    assert "APPROVED" in marked and "12.50 m²" in marked and "not calibrated" in marked


def test_flatten_handles_rotated_pages():
    reader = PdfReader(io.BytesIO(_pdf(pages=1)))
    writer = PdfWriter()
    page = reader.pages[0]
    page.rotate(90)
    writer.add_page(page)
    rotated = io.BytesIO()
    writer.write(rotated)
    note = {"page": 1, "type": "text", "geometry": {"x": 20, "y": 20, "w": 100, "h": 20}, "style": {}, "text": "Hello"}
    out = PdfReader(io.BytesIO(flatten(rotated.getvalue(), [note])))
    page = out.pages[0]
    assert page.rotation == 0
    assert float(page.cropbox.width) == pytest.approx(842)
    assert "Hello" in page.extract_text()

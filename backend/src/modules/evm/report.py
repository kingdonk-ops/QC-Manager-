"""The PDF summary and the spreadsheet export."""

from typing import Any

from ...infrastructure.pdf import Document, render_pdf
from ..projects.models import Project
from .constants import Basis

EXPORT_COLUMNS = [
    ("code", "code"),
    ("name", "name"),
    ("control_account", "control account"),
    ("discipline", "discipline"),
    ("bac", "BAC"),
    ("percent_complete", "percent"),
    ("actual_hours", "actual hours"),
    ("pv", "PV"),
    ("ev", "EV"),
    ("ac", "AC"),
    ("sv", "SV"),
    ("cv", "CV"),
    ("spi", "SPI"),
    ("cpi", "CPI"),
    ("eac", "EAC"),
    ("etc", "ETC"),
    ("vac", "VAC"),
    ("tcpi", "TCPI"),
    ("productivity", "productivity"),
]
"""``code``, ``percent`` and ``actual hours`` are the import's columns, so an export can be filled in and sent back."""


def _n(value: float | None, digits: int = 0) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def _i(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def pdf(project: Project, report: dict[str, Any], accounts: list[dict[str, Any]], curve: dict[str, Any]) -> bytes:
    basis = report["basis"]
    unit = "h" if basis == Basis.HOURS else project.currency
    total = report["total"]
    doc = Document(
        title="Earned Value Report",
        subtitle=f"{project.code} · {project.name} · data date {report['data_date']:%d %b %Y} · {basis} basis",
        footer=f"Earned value · {project.code}",
    )
    doc.fields(
        [
            (f"Budget at completion ({unit})", _n(total["bac"])),
            (f"Planned value ({unit})", _n(total["pv"])),
            (f"Earned value ({unit})", _n(total["ev"])),
            (f"Actual ({unit})", _n(total["ac"])),
            ("Schedule variance / SPI", f"{_n(total['sv'])} / {_i(total['spi'])}"),
            ("Cost variance / CPI", f"{_n(total['cv'])} / {_i(total['cpi'])}"),
            (f"EAC ({report['eac_method']})", _n(total["eac"])),
            ("ETC / VAC", f"{_n(total['etc'])} / {_n(total['vac'])}"),
            ("TCPI (to BAC / to EAC)", f"{_i(total['tcpi'])} / {_i(total['tcpi_eac'])}"),
            ("% planned / % complete", f"{_n(total['percent_planned'], 1)} / {_n(total['percent_complete'], 1)}"),
            ("Productivity (earned h per actual h)", _i(total["productivity"])),
        ]
    )
    headers = ["Group", "BAC", "PV", "EV", "AC", "SPI", "CPI", "EAC", "VAC"]

    def table_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
        return [
            [
                r["label"],
                _n(r["bac"]),
                _n(r["pv"]),
                _n(r["ev"]),
                _n(r["ac"]),
                _i(r["spi"]),
                _i(r["cpi"]),
                _n(r["eac"]),
                _n(r["vac"]),
            ]
            for r in rows
        ]

    widths = [0.28, 0.09, 0.09, 0.09, 0.09, 0.07, 0.07, 0.11, 0.11]
    numeric = set(range(1, 9))
    doc.heading("By control account")
    doc.table(headers, table_rows(accounts), widths=widths, numeric=numeric)
    doc.heading("By work package")
    doc.table(["Package", *headers[1:]], table_rows(report["rows"]), widths=widths, numeric=numeric)
    if curve["points"]:
        doc.heading("S-curve (cumulative, monthly)")
        doc.table(
            ["Month", "PV", "EV", "AC", "Forecast"],
            [[p["label"], _n(p["pv"]), _n(p["ev"]), _n(p["ac"]), _n(p["forecast"])] for p in curve["points"]],
            widths=[0.2, 0.2, 0.2, 0.2, 0.2],
            numeric={1, 2, 3, 4},
        )
    return render_pdf(doc)

"""Turning collected sections into one dossier PDF: cover, index with page numbers, section dividers with
registers, rendered records, merged attachments and deduplicated certificate appendices, then page stamps.

Pure functions over bytes (no database), run in a worker thread. Order of the final steps:
merge -> stamp (this module) -> sign (``signing.py``) -> SHA-256 of the final bytes (the caller).
"""

import io
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ...infrastructure.dossier import CERTIFICATE_SECTIONS, MdrRecord
from ...infrastructure.pdf import Document, render_pdf

MAX_LAYOUT_PASSES = 4


@dataclass
class Blob:
    """A stored file the dossier may append."""

    id: int
    name: str
    sha256: str
    content_type: str
    data: bytes | None


@dataclass
class SectionIn:
    key: str
    number: int
    title: str
    records: list[MdrRecord]
    note: str | None = None
    """Printed under the title, e.g. "Not available: no module provides this section"."""


@dataclass
class Cover:
    title: str
    project: str
    code: str
    revision: str | None
    purpose: str
    scope: str
    date: str
    draft: bool
    findings: list[str] = field(default_factory=list)


@dataclass
class Result:
    pdf: bytes
    page_count: int
    manifest: dict[str, Any]


@dataclass
class _Appendix:
    label: str
    blob: Blob
    section: int
    refs: list[str] = field(default_factory=list)
    page: int | None = None


def _pdf_pages(data: bytes | None) -> list[Any] | None:
    if not data:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return None
        return list(reader.pages)
    except (PdfReadError, ValueError, OSError, KeyError, TypeError):
        return None


def _render(doc: Document) -> list[Any]:
    pages = _pdf_pages(render_pdf(doc))
    assert pages is not None
    return pages


@dataclass
class _Part:
    """A run of pages: generated (re-rendered each layout pass) or fixed (record PDFs, attachments)."""

    kind: str
    pages: list[Any]
    section: int | None = None
    title: str | None = None


def _divider(section: SectionIn, label: str, appendix: list[_Appendix], record_pages: dict[str, int | None]) -> Document:
    doc = Document(title=f"Section {section.number}: {section.title}", subtitle=label, footer=label)
    if section.note:
        doc.paragraph(section.note)
    if not section.records:
        doc.paragraph("No records in this section for the dossier's scope.")
        return doc
    certificate = section.key in CERTIFICATE_SECTIONS
    rows = []
    for rec in section.records:
        attached = (
            ", ".join(a.label for a in appendix if rec.reference in a.refs)
            if certificate
            else (str(record_pages.get(rec.reference) or "") or "-")
        )
        rows.append([rec.reference, rec.title, rec.status or "", rec.date or "", rec.location or "", rec.notes or "", attached])
    last = "Appendix item" if certificate else "Page"
    doc.heading("Register")
    doc.table(
        ["Ref.", "Title", "Status", "Date", "Location", "Notes", last],
        rows,
        widths=[0.13, 0.25, 0.1, 0.1, 0.12, 0.18, 0.12],
    )
    mine = [a for a in appendix if a.section == section.number]
    if mine:
        doc.heading("Appendix index")
        doc.table(
            ["Item", "Certificate", "SHA-256", "Page", "Referred to by"],
            [[a.label, a.blob.name, a.blob.sha256[:16] + "…", a.page or "-", ", ".join(a.refs)] for a in mine],
            widths=[0.08, 0.3, 0.2, 0.07, 0.35],
        )
    return doc


def _record_doc(rec: MdrRecord, label: str) -> Document:
    doc = Document(title=f"{rec.reference}: {rec.title}", subtitle=label, footer=label)
    doc.fields([(str(k), "" if v is None else str(v)) for k, v in rec.fields])
    return doc


def _cover(cover: Cover) -> Document:
    doc = Document(title=cover.title, subtitle=cover.project, footer=cover.code)
    doc.fields(
        [
            ("Dossier", cover.code),
            ("Revision", cover.revision or "Draft"),
            ("Purpose", cover.purpose),
            ("Scope", cover.scope),
            ("Compiled", cover.date),
        ]
    )
    if cover.draft:
        doc.heading("DRAFT – not for issue")
        if cover.findings:
            doc.paragraph("Open readiness findings at compile time:")
            doc.table(["Finding"], [[f] for f in cover.findings])
        else:
            doc.paragraph("No open readiness findings at compile time.")
    return doc


def _index(sections: list[SectionIn], starts: dict[int, int], appendix: list[_Appendix], label: str) -> Document:
    doc = Document(title="Index", subtitle=label, footer=label)
    rows: list[list[Any]] = []
    for s in sections:
        rows.append([s.number, s.title, len(s.records), starts.get(s.number, "")])
        rows.extend(["", f"    {a.label} {a.blob.name}", "", a.page or ""] for a in appendix if a.section == s.number)
    doc.table(["No.", "Section", "Records", "Page"], rows, widths=[0.08, 0.7, 0.1, 0.12], numeric={2, 3})
    return doc


def compile_pdf(cover: Cover, sections: list[SectionIn], blobs: dict[int, Blob], label: str) -> Result:
    """Lay the dossier out, merge it and stamp every page with ``label`` and "Page n of N"."""
    # Deduplicate certificates across the dossier by the stored file's SHA-256.
    appendix: list[_Appendix] = []
    by_hash: dict[str, _Appendix] = {}
    unreadable: list[str] = []
    for s in sections:
        if s.key not in CERTIFICATE_SECTIONS:
            continue
        for rec in s.records:
            for fid in rec.file_ids:
                blob = blobs.get(fid)
                if blob is None:
                    continue
                entry = by_hash.get(blob.sha256)
                if entry is None:
                    entry = _Appendix(f"{s.number}.{sum(1 for a in appendix if a.section == s.number) + 1}", blob, s.number)
                    by_hash[blob.sha256] = entry
                    appendix.append(entry)
                if rec.reference not in entry.refs:
                    entry.refs.append(rec.reference)

    # Fixed parts: record PDFs and their attachments, then the certificate appendix.
    fixed: dict[int, list[tuple[str, str, list[Any]]]] = {}
    for s in sections:
        items: list[tuple[str, str, list[Any]]] = []
        for rec in s.records:
            pages: list[Any] = []
            if rec.pdf:
                pages += _pdf_pages(rec.pdf) or []
            elif rec.fields:
                pages += _render(_record_doc(rec, label))
            if s.key not in CERTIFICATE_SECTIONS:
                for fid in rec.file_ids:
                    blob = blobs.get(fid)
                    attached = _pdf_pages(blob.data) if blob else None
                    if attached:
                        pages += attached
                    elif blob:
                        unreadable.append(f"{rec.reference}: {blob.name}")
            if pages:
                items.append((f"record:{rec.reference}", rec.reference, pages))
        for a in appendix:
            if a.section == s.number:
                pages = _pdf_pages(a.blob.data) or []
                if not pages:
                    unreadable.append(f"{a.label}: {a.blob.name}")
                    continue
                items.append((f"appendix:{a.label}", f"{a.label} {a.blob.name}", pages))
        fixed[s.number] = items

    starts: dict[int, int] = {}
    record_pages: dict[str, int | None] = {}
    total = 0
    parts: list[_Part] = []
    for _ in range(MAX_LAYOUT_PASSES):
        parts = [_Part("cover", _render(_cover(cover))), _Part("index", _render(_index(sections, starts, appendix, label)))]
        for s in sections:
            parts.append(_Part("divider", _render(_divider(s, label, appendix, record_pages)), s.number, s.title))
            parts += [_Part(key, pages, s.number, title) for key, title, pages in fixed[s.number]]
        page = 1
        new_starts: dict[int, int] = {}
        new_records: dict[str, int | None] = {}
        for part in parts:
            if part.kind == "divider" and part.section is not None:
                new_starts[part.section] = page
            elif part.kind.startswith("record:"):
                new_records.setdefault(part.kind.removeprefix("record:"), page)
            elif part.kind.startswith("appendix:"):
                label_of = part.kind.removeprefix("appendix:")
                for a in appendix:
                    if a.label == label_of:
                        a.page = page
            page += len(part.pages)
        total = page - 1
        stable = new_starts == starts and new_records == record_pages
        starts, record_pages = new_starts, new_records
        if stable:
            break

    writer = PdfWriter()
    page_index = 0
    for part in parts:
        for p in part.pages:
            writer.add_page(p)
        if part.kind in ("index", "divider") or part.kind.startswith("appendix:"):
            title = "Index" if part.kind == "index" else (part.title or "")
            if part.kind == "divider":
                title = f"{part.section}. {part.title}"
            writer.add_outline_item(title=title, page_number=page_index)
        page_index += len(part.pages)
    _stamp(writer, label, draft=cover.draft)
    writer.add_metadata({"/Title": f"{cover.title} ({label})", "/Subject": cover.project, "/Creator": "QC Manager MDR"})
    out = io.BytesIO()
    writer.write(out)
    manifest = {
        "sections": [
            {
                "number": s.number,
                "key": s.key,
                "title": s.title,
                "records": len(s.records),
                "page": starts.get(s.number),
                "note": s.note,
            }
            for s in sections
        ],
        "appendix": [
            {
                "label": a.label,
                "file_id": a.blob.id,
                "name": a.blob.name,
                "sha256": a.blob.sha256,
                "page": a.page,
                "refs": a.refs,
            }
            for a in appendix
        ],
        "not_merged": unreadable,
    }
    return Result(out.getvalue(), total, manifest)


def _overlay(width: float, height: float, text: str, draft: bool) -> Any:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawRightString(width - 12 * mm, height - 8 * mm, text)
    if draft:
        c.saveState()
        c.setFillColor(colors.Color(0.86, 0.15, 0.15, alpha=0.18))
        c.setFont("Helvetica-Bold", 46)
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, "DRAFT – not for issue")
        c.restoreState()
    c.save()
    return PdfReader(io.BytesIO(buffer.getvalue())).pages[0]


def _stamp(writer: PdfWriter, label: str, *, draft: bool) -> None:
    total = len(writer.pages)
    for n, page in enumerate(writer.pages, start=1):
        box = page.mediabox
        page.merge_page(_overlay(float(box.width), float(box.height), f"{label} · Page {n} of {total}", draft))


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)

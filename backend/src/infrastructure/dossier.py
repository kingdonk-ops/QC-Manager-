"""What modules contribute to a turnover dossier (MDR): records per section, and gate checks.

A module registers from an ``mdr.py`` in its package (imported at startup with the models)::

    # src/modules/welding/mdr.py
    from ...infrastructure.dossier import MdrRecord, register_mdr_provider

    async def nde_reports(db, ctx):
        rows = ...  # the scope's NDE reports: ctx.project_id, ctx.node_ids (None = whole project)
        return [MdrRecord(reference=r.code, title=r.title, status=r.result, file_ids=[r.file_id]) for r in rows]

    register_mdr_provider("nde_reports", nde_reports, module="welding")

See "MDR providers and gate checks" in docs/modules.md.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

SECTIONS: Final[dict[str, str]] = {
    "index": "Index",
    "itp": "Inspection and test plans",
    "inspections": "Inspection records",
    "ncr_register": "NCR / concession register",
    "material_certs": "Material certificates",
    "nde_reports": "NDE reports",
    "calibration_certs": "Calibration certificates",
    "as_built": "As-built drawings",
    "custom": "Other documents",
}
"""The sections a dossier can hold, in their default order. ``index`` is generated, never provided."""

CERTIFICATE_SECTIONS: Final = frozenset({"material_certs", "calibration_certs"})
"""Sections whose files are certificates: each is attached once per dossier, identified by its SHA-256."""


@dataclass
class MdrContext:
    project_id: int
    project_code: str
    project_name: str
    dossier_id: int
    node_ids: list[int] | None
    """The dossier scope's asset nodes with their subtrees (and lineage); ``None`` for the whole project."""

    def in_scope(self, node_id: int | None) -> bool:
        """Whether a record anchored at ``node_id`` belongs to the dossier (unanchored records do, project-wide)."""
        return self.node_ids is None or node_id is None or node_id in self.node_ids


@dataclass
class MdrRecord:
    """One entry of a section's register, and what the dossier prints for it."""

    reference: str
    title: str
    status: str | None = None
    date: str | None = None
    location: str | None = None
    notes: str | None = None
    """A short remark for the register row (disposition, concession reference, result)."""
    pdf: bytes | None = None
    """The record rendered as a PDF (``render_pdf``), printed after the section's register."""
    fields: list[tuple[str, Any]] = field(default_factory=list)
    """Printed as a one-record page when there is no ``pdf``; leave both empty for a register-only row."""
    file_ids: list[int] = field(default_factory=list)
    """Stored files to append (PDFs are merged; anything else is listed). In a certificate section they go to the
    section's appendix once per dossier, however many records refer to them."""


ProviderFn = Callable[[AsyncSession, MdrContext], Awaitable[list[MdrRecord]]]


@dataclass(frozen=True)
class MdrProvider:
    section: str
    module: str
    fn: ProviderFn


@dataclass
class Finding:
    message: str
    reference: str | None = None
    link: str | None = None
    """An app path that opens the blocking record (``/ncr?project=3&id=9``)."""


class CheckUnavailable(Exception):  # noqa: N818 - reads as a state, like StopIteration
    """Raised by a check whose facts can't be read (the module is absent or switched off): reported, not failed."""


CheckFn = Callable[[AsyncSession, MdrContext], Awaitable[list[Finding]]]


@dataclass(frozen=True)
class MdrCheck:
    key: str
    title: str
    module: str
    fn: CheckFn
    blocking: bool = True
    final_only: bool = False
    """Only for a final issue (Rev 0 and later)."""


_providers: list[MdrProvider] = []
_checks: dict[str, MdrCheck] = {}


def register_mdr_provider(section: str, fn: ProviderFn, *, module: str) -> None:
    if section not in SECTIONS or section == "index":
        raise ValueError(f"Unknown MDR section {section!r}")
    _providers[:] = [
        p for p in _providers if not (p.section == section and p.module == module and p.fn.__name__ == fn.__name__)
    ]
    _providers.append(MdrProvider(section, module, fn))


def register_mdr_check(check: MdrCheck) -> None:
    _checks[check.key] = check


def providers_for(section: str) -> list[MdrProvider]:
    return [p for p in _providers if p.section == section]


def all_providers() -> list[MdrProvider]:
    return list(_providers)


def all_checks() -> list[MdrCheck]:
    return list(_checks.values())


def unregister(module: str) -> None:
    """Drop a module's providers and checks (tests)."""
    _providers[:] = [p for p in _providers if p.module != module]
    for key in [k for k, c in _checks.items() if c.module == module]:
        del _checks[key]

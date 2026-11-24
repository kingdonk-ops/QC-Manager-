"""The register views, computed at read time from the stored rows for an as-of day.

``summarise`` is plain computation over item and permit attributes (so unit tests feed it stand-ins and a pinned day);
``load_summary`` fetches a project's items and permits in two queries, groups them in memory and calls it. Results are
never cached or stored. The compliant flag depends only on the breach list; warnings are a separate list."""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ..scaffolds import breach as scaffold_breach
from . import rules
from .constants import site_today
from .models import TemporaryWorksItem, TemporaryWorksPermit
from .rules import Breach

ScaffoldRead = tuple[str | None, bool | None]
"""A linked scaffold as the register sees it: its effective tag and whether its inspection is overdue (None: unknown)."""


@dataclass(frozen=True)
class ItemGate:
    item: Any
    load_open: bool
    strike_open: bool


@dataclass(frozen=True)
class ItemWarning:
    item: Any
    rule: str
    message: str


@dataclass(frozen=True)
class Summary:
    day: date
    total: int
    status_counts: dict[str, int]
    category_counts: dict[str, int]
    clearance: Decimal | None
    breaches: list[Breach]
    overdue_load: list[Any]
    overdue_strike: list[Any]
    gates: list[ItemGate]
    warnings: list[ItemWarning]

    @property
    def compliant(self) -> bool:
        return rules.is_compliant(self.breaches)


def summarise(
    items: Sequence[Any],
    permits_by_item: Mapping[Any, Sequence[Any]],
    day: date,
    scaffold_reads: Mapping[Any, ScaffoldRead] | None = None,
) -> Summary:
    """Every register figure for ``day``. ``scaffold_reads`` is ``None`` when the scaffolds module is off (no scaffold
    advice at all); otherwise a linked scaffold missing from it reads as unknown, which is advised on."""
    gates: list[ItemGate] = []
    warnings: list[ItemWarning] = []
    for item in items:
        permits = permits_by_item.get(getattr(item, "id", None), ())
        gates.append(ItemGate(item, rules.load_gate_open(permits, day), rules.strike_gate_open(permits, day)))
        found = [rules.bearing_load_warning(item, list(permits), day), *rules.lapsing_warnings(item, permits, day)]
        linked = getattr(item, "scaffold_id", None)
        if scaffold_reads is not None and linked is not None:
            tag, overdue = scaffold_reads.get(linked, (None, None))
            found.append(rules.scaffold_state_warning(item, tag, overdue))
        warnings.extend(ItemWarning(item, f.rule, f.message) for f in found if f is not None)
    return Summary(
        day=day,
        total=len(items),
        status_counts=rules.status_counts(getattr(i, "status", None) for i in items),
        category_counts=rules.category_counts(getattr(i, "design_check_category", None) for i in items),
        clearance=rules.design_clearance(getattr(i, "status", None) for i in items),
        breaches=rules.find_breaches(items, permits_by_item, day),
        overdue_load=[i for i in items if rules.overdue_to_load(i, day)],
        overdue_strike=[i for i in items if rules.overdue_to_strike(i, day)],
        gates=gates,
        warnings=warnings,
    )


async def project_rows(
    db: AsyncSession, project_id: int
) -> tuple[list[TemporaryWorksItem], dict[int, list[TemporaryWorksPermit]]]:
    """A project's items and their permits (deleted ones left out) in two queries, the permits grouped by item."""
    items = list(
        (
            await db.execute(
                select(TemporaryWorksItem)
                .where(TemporaryWorksItem.project_id == project_id, TemporaryWorksItem.deleted_at.is_(None))
                .order_by(TemporaryWorksItem.sort_order, TemporaryWorksItem.created_at, TemporaryWorksItem.id)
            )
        ).scalars()
    )
    grouped: dict[int, list[TemporaryWorksPermit]] = defaultdict(list)
    permits = (
        await db.execute(
            select(TemporaryWorksPermit)
            .where(TemporaryWorksPermit.project_id == project_id, TemporaryWorksPermit.deleted_at.is_(None))
            .order_by(TemporaryWorksPermit.id)
        )
    ).scalars()
    for permit in permits:
        grouped[permit.item_id].append(permit)
    return items, grouped


async def _scaffold_reads(
    db: AsyncSession, project_id: int, items: Iterable[TemporaryWorksItem], day: date
) -> dict[Any, ScaffoldRead] | None:
    """The linked scaffolds' tag and inspection state, or ``None`` when the scaffolds module is off for the project."""
    linked = {i.scaffold_id for i in items if i.scaffold_id is not None}
    if not linked or not await is_enabled(db, "scaffolds", project_id):
        return None
    at = None if day == site_today() else day  # today is read as of now; another day as of the end of that day
    reads: dict[Any, ScaffoldRead] = {}
    for scaffold_id in linked:
        state = await scaffold_breach.scaffold_state(db, scaffold_id, project_id, at)
        reads[scaffold_id] = (state.effective_tag, state.inspection_overdue) if state else (None, None)
    return reads


async def load_summary(db: AsyncSession, project_id: int, day: date | None = None) -> Summary:
    """The register of a project for ``day`` (default: today at the site)."""
    day = day or site_today()
    items, permits = await project_rows(db, project_id)
    return summarise(items, permits, day, await _scaffold_reads(db, project_id, items, day))


# --- response bodies ----------------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def _ref(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "reference": item.reference,
        "title": item.title,
        "family": item.family,
        "status": item.status,
        "required_load_on": _text(item.required_load_on),
        "required_strike_on": _text(item.required_strike_on),
    }


def load_status_body(summary: Summary) -> dict[str, Any]:
    return {
        "as_of": summary.day,
        "total": summary.total,
        "compliant": summary.compliant,
        "gates": [
            {
                "item_id": g.item.id,
                "reference": g.item.reference,
                "status": g.item.status,
                "load_gate_open": g.load_open,
                "strike_gate_open": g.strike_open,
            }
            for g in summary.gates
        ],
        "breaches": [b._asdict() for b in summary.breaches],
    }


def rollup_body(summary: Summary) -> dict[str, Any]:
    return {
        **load_status_body(summary),
        "status_counts": summary.status_counts,
        "category_counts": summary.category_counts,
        "design_clearance": None if summary.clearance is None else format(summary.clearance, "f"),
        "overdue_to_load": [_ref(i) for i in summary.overdue_load],
        "overdue_to_strike": [_ref(i) for i in summary.overdue_strike],
        "warnings": [
            {"item_id": w.item.id, "reference": w.item.reference, "rule": w.rule, "message": w.message}
            for w in summary.warnings
        ],
    }

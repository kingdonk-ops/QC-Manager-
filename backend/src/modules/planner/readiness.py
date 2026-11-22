"""Readiness and actuals registries other modules plug into, so the planner never reads their tables.

Readiness — "can this work pack start?"::

    from ..planner.readiness import Finding, ReadinessContext, register_readiness

    async def materials_ready(db, ctx: ReadinessContext) -> list[Finding]:
        short = await my_service.shortages(db, ctx.project_id, ctx.anchor_ids, ctx.start)
        return [Finding("materials", "materials", "warning", f"{s.code} short {s.qty}", s.anchor_id) for s in short]

    register_readiness("materials.shortages", "materials", materials_ready)

Call ``register_readiness`` when your module is imported (its ``service.py`` or ``events.py``). A provider runs
only while its module is switched on for the project; one that raises is logged and skipped, so a broken
provider never stops planning. Findings are ``warning`` (shown as a badge) or ``blocker`` (a pack can't
move to ``ready`` without ``force``).

Actuals — "what was done against each work anchor?" (plan vs actual)::

    register_actuals("workface_log", provider)   # provider(db, project_id, anchor_ids, start, end) -> {anchor_id: Actual}
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from ...infrastructure.modules.state import is_enabled

logger = get_logger()


@dataclass(frozen=True)
class ReadinessContext:
    project_id: int
    pack_id: int
    anchor_ids: tuple[int, ...]
    start: date | None
    end: date | None
    plan_id: int | None = None
    crew_id: int | None = None
    schedule_activity_id: int | None = None


@dataclass(frozen=True)
class Finding:
    source: str
    """The provider's key area, e.g. ``prerequisites``, ``materials``, ``crew``."""
    kind: str
    severity: str
    """``warning`` or ``blocker``."""
    message: str
    anchor_id: int | None = None


@dataclass
class Actual:
    hours: Decimal = field(default_factory=Decimal)
    qty: Decimal = field(default_factory=Decimal)


ReadinessProvider = Callable[[AsyncSession, ReadinessContext], Awaitable[list[Finding]]]
ActualsProvider = Callable[[AsyncSession, int, Sequence[int], date | None, date | None], Awaitable[dict[int, Actual]]]

_readiness: dict[str, tuple[str, ReadinessProvider]] = {}
_actuals: dict[str, ActualsProvider] = {}


def register_readiness(key: str, module: str, provider: ReadinessProvider) -> None:
    """Add (or replace, by ``key``) a readiness provider owned by ``module``."""
    _readiness[key] = (module, provider)


def register_actuals(module: str, provider: ActualsProvider) -> None:
    _actuals[module] = provider


def readiness_providers() -> list[tuple[str, str]]:
    return sorted((key, module) for key, (module, _) in _readiness.items())


async def evaluate(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    findings: list[Finding] = []
    for key, (module, provider) in sorted(_readiness.items()):
        if not await is_enabled(db, module, ctx.project_id):
            continue
        try:
            findings += await provider(db, ctx)
        except Exception:
            logger.exception("Readiness provider failed", extra={"provider": key})
    return findings


async def actuals(
    db: AsyncSession, project_id: int, anchor_ids: Sequence[int], start: date | None, end: date | None
) -> dict[int, Actual]:
    total: dict[int, Actual] = {}
    for module, provider in sorted(_actuals.items()):
        if not await is_enabled(db, module, project_id):
            continue
        try:
            got = await provider(db, project_id, anchor_ids, start, end)
        except Exception:
            logger.exception("Actuals provider failed", extra={"module": module})
            continue
        for anchor_id, a in got.items():
            t = total.setdefault(anchor_id, Actual())
            t.hours += a.hours
            t.qty += a.qty
    return total

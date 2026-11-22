"""Verified progress on the asset breakdown: only verified completion counts (KERP TD-563).

A progress-unit node (a level with the ``progress_unit`` role) carries ``budget_qty`` / ``budget_hours`` and a
self-reported ``earned_qty``. Its **verified** quantity is that of its latest counting
``ProgressVerification``: one backed by an inspection that is completed or closed with no failed item, or
one recorded without an inspection by a holder of ``schedule.review``. A verification whose inspection was
reopened, or failed, stops counting until it passes again.

How other modules read it:

* **P6 actuals export** (``p6_service.progress_rows``): percent complete of a linked activity is
  ``verified_fraction`` of its node(s); actual start is the first counting verification, actual finish the
  date the last unit was verified complete.
* **Claims**: a work line's verified-to-date quantity is ``node_quantities(...)[node].verified_qty``
  summed over the progress units under the claimed node.
* **EVM**: earned value must use ``earned_value(db, project_id)``: for each progress unit,
  ``EV = budget × verified fraction`` (budget hours, or budget quantity when no hours are set), with
  ``reported`` alongside so the gap between self-reported and verified progress stays visible. Planned
  value and actual cost stay with ``evm``; money is a mirror, never authored here.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..asset_tree.constants import Role
from ..asset_tree.models import AssetLevel, AssetNode
from ..inspections.models import Inspection
from .p6_models import ProgressVerification

ZERO = Decimal(0)
PASSED = ("completed", "closed")


@dataclass
class NodeProgress:
    node_id: int
    code: str
    display_path: str
    uom: str | None
    budget_qty: Decimal | None
    budget_hours: Decimal | None
    reported_qty: Decimal
    verified_qty: Decimal
    first_verified: date | None
    completed_on: date | None

    @property
    def weight(self) -> Decimal:
        return self.budget_hours or self.budget_qty or Decimal(1)

    def _fraction(self, qty: Decimal) -> Decimal:
        if self.budget_qty:
            return min(max(qty / self.budget_qty, ZERO), Decimal(1))
        return Decimal(1) if qty > 0 else ZERO

    @property
    def verified_fraction(self) -> Decimal:
        return self._fraction(self.verified_qty)

    @property
    def reported_fraction(self) -> Decimal:
        return self._fraction(self.reported_qty)


async def progress_units(db: AsyncSession, project_id: int, node_ids: set[int] | None = None) -> list[AssetNode]:
    """Progress-unit nodes of the project (in ``node_ids`` when given), active only."""
    levels = (await db.execute(select(AssetLevel.id, AssetLevel.roles).where(AssetLevel.project_id == project_id))).all()
    level_ids = [lid for lid, roles in levels if Role.PROGRESS_UNIT.value in (roles or [])]
    if not level_ids:
        return []
    q = select(AssetNode).where(
        AssetNode.project_id == project_id, AssetNode.level_id.in_(level_ids), AssetNode.status == "active"
    )
    if node_ids is not None:
        if not node_ids:
            return []
        q = q.where(AssetNode.id.in_(node_ids))
    return list((await db.execute(q.order_by(AssetNode.display_path))).scalars())


async def under(db: AsyncSession, project_id: int, node_ids: set[int]) -> dict[int, set[int]]:
    """For each node: the progress units at or below it."""
    nodes = {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(node_ids)))).scalars()}
    units = await progress_units(db, project_id)
    return {nid: {u.id for u in units if u.path.startswith(n.path)} for nid, n in nodes.items()}


async def node_quantities(db: AsyncSession, project_id: int, node_ids: set[int] | None = None) -> dict[int, NodeProgress]:
    units = await progress_units(db, project_id, node_ids)
    if not units:
        return {}
    rows = (
        await db.execute(
            select(ProgressVerification, Inspection.status, Inspection.failed)
            .outerjoin(Inspection, Inspection.id == ProgressVerification.inspection_id)
            .where(ProgressVerification.node_id.in_([u.id for u in units]))
            .order_by(ProgressVerification.verified_on, ProgressVerification.id)
        )
    ).all()
    counting: dict[int, list[ProgressVerification]] = {}
    for v, status, failed in rows:
        if v.inspection_id is not None and (status not in PASSED or (failed or 0) > 0):
            continue
        counting.setdefault(v.node_id, []).append(v)
    out: dict[int, NodeProgress] = {}
    for u in units:
        mine = counting.get(u.id, [])
        latest = Decimal(mine[-1].verified_qty) if mine else ZERO
        if u.budget_qty is not None:
            latest = min(latest, Decimal(u.budget_qty))
        p = NodeProgress(
            node_id=u.id,
            code=u.code,
            display_path=u.display_path,
            uom=u.uom,
            budget_qty=Decimal(u.budget_qty) if u.budget_qty is not None else None,
            budget_hours=Decimal(u.budget_hours) if u.budget_hours is not None else None,
            reported_qty=Decimal(u.earned_qty or 0),
            verified_qty=latest,
            first_verified=next((v.verified_on for v in mine if v.verified_qty > 0), None),
            completed_on=None,
        )
        if p.verified_fraction >= 1:
            p.completed_on = next(
                (v.verified_on for v in mine if p._fraction(Decimal(v.verified_qty)) >= 1), mine[-1].verified_on
            )
        out[u.id] = p
    return out


@dataclass
class Rollup:
    units: int
    verified_percent: float | None
    reported_percent: float | None
    actual_start: date | None
    actual_finish: date | None
    verified_qty: Decimal
    budget_qty: Decimal


def rollup(progress: list[NodeProgress]) -> Rollup:
    """Weighted percent complete of a set of progress units; ``None`` when there are none."""
    if not progress:
        return Rollup(0, None, None, None, None, ZERO, ZERO)
    total = sum((p.weight for p in progress), ZERO)
    verified = sum((p.weight * p.verified_fraction for p in progress), ZERO)
    reported = sum((p.weight * p.reported_fraction for p in progress), ZERO)
    starts = [p.first_verified for p in progress if p.first_verified]
    done = all(p.completed_on for p in progress)
    return Rollup(
        units=len(progress),
        verified_percent=round(float(verified / total * 100), 1) if total else 0.0,
        reported_percent=round(float(reported / total * 100), 1) if total else 0.0,
        actual_start=min(starts) if starts else None,
        actual_finish=max(p.completed_on for p in progress if p.completed_on) if done else None,
        verified_qty=sum((p.verified_qty for p in progress), ZERO),
        budget_qty=sum((p.budget_qty or ZERO for p in progress), ZERO),
    )


async def earned_value(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    """Per progress unit: budget, reported and verified fractions and earned budget. EVM reads this."""
    out = []
    for p in (await node_quantities(db, project_id)).values():
        out.append(
            {
                "node_id": p.node_id,
                "code": p.code,
                "display_path": p.display_path,
                "budget": p.weight,
                "budget_basis": "hours" if p.budget_hours else "quantity" if p.budget_qty else "count",
                "reported_fraction": p.reported_fraction,
                "verified_fraction": p.verified_fraction,
                "earned": p.weight * p.verified_fraction,
            }
        )
    return out

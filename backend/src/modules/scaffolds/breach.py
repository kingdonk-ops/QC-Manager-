"""What the temporary works module needs from a scaffold: its current state for a day, and the red-tag write-back for a
linked item that is bearing load without a valid permit to load.

This file may import the scaffolds service; the service never imports this file, and the scaffolds module never
imports the temporary works module. Nothing here commits: the caller owns the unit of work and commits once.

The red-tag write-back is one setting away from off (``RED_TAG_WRITE_BACK``): with it off the helper writes nothing and
the breach is only reported by the temporary works views."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import record_transition
from ..notifications.constants import Category
from ..notifications.service import notify
from .constants import STANDING, Tag
from .models import Scaffold
from .service import ENTITY, effective_tag, inspection_overdue, link_of

RED_TAG_WRITE_BACK = True
"""Switches the red-tag write-back for breaches off (False) or on (True)."""

TAG_ENTITY = "scaffold_tag"
"""The status-history entity the hourly overdue job also writes tag changes under."""


@dataclass(frozen=True)
class ScaffoldState:
    """A scaffold as the temporary works register needs to see it on one day."""

    scaffold_id: int
    code: str
    status: str
    standing: bool
    effective_tag: str
    inspection_overdue: bool
    next_inspection_due: datetime | None


def _moment(day: date | None) -> datetime:
    """The instant a state is read at: now, or the end of the named day (the planner's reading of an overdue inspection
    'by then')."""
    if day is None:
        return datetime.now(UTC)
    return datetime.combine(day, time.max, tzinfo=UTC)


async def scaffold_state(
    db: AsyncSession, scaffold_id: int, project_id: int | None = None, day: date | None = None
) -> ScaffoldState | None:
    """The scaffold's status, effective tag, whether its inspection is overdue and when the next one is due, worked out
    from the scaffold's own interval. ``None`` when there is no such scaffold (or it belongs to another project)."""
    s = await db.get(Scaffold, scaffold_id)
    if s is None or (project_id is not None and s.project_id != project_id):
        return None
    at = _moment(day)
    return ScaffoldState(
        scaffold_id=s.id,
        code=s.code,
        status=s.status,
        standing=s.status in STANDING,
        effective_tag=effective_tag(s, at),
        inspection_overdue=inspection_overdue(s, at),
        next_inspection_due=s.next_inspection_due,
    )


async def mark_breach_red(
    db: AsyncSession,
    scaffold_id: int,
    *,
    project_id: int | None = None,
    item_reference: str | None = None,
    actor_id: int | None = None,
) -> bool:
    """Write the red tag on a standing scaffold whose linked temporary works item is bearing load without a valid
    permit to load: a tag history entry (the scaffold status is untouched) and one notice to its custodian and
    requester. Does nothing, and returns False, when the write-back is off, the scaffold is missing, in another project,
    not standing or already red, so a second call adds no history entry and no notice. Does not commit."""
    if not RED_TAG_WRITE_BACK:
        return False
    row = await db.execute(
        select(Scaffold).where(Scaffold.id == scaffold_id).with_for_update().execution_options(populate_existing=True)
    )
    s: Scaffold | None = row.scalar_one_or_none()
    if s is None or (project_id is not None and s.project_id != project_id):
        return False
    if s.status not in STANDING or s.tag_status == Tag.RED:
        return False
    before = s.tag_status
    s.tag_status = Tag.RED.value
    source = f"temporary works item {item_reference}" if item_reference else "a linked temporary works item"
    reason = f"{source} is bearing load without a valid permit to load"
    await record_transition(db, TAG_ENTITY, s.id, before, Tag.RED.value, actor_id, reason[:1].upper() + reason[1:])
    watchers = sorted({u for u in (s.custodian_id, s.requested_by_id) if u})
    await notify(
        db,
        watchers,
        Category.DUE,
        f"{s.code}: tag is red, {reason}",
        body="Do not use the scaffold until the permit to load is recorded and it has been inspected and re-tagged.",
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=actor_id,
    )
    await db.flush()
    return True

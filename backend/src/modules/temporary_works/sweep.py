"""The hourly sweep: permit expiry, expiring-soon notices and breach handling.

Three things happen, each with a dedupe marker so a second run repeats nothing:

1. an issued or active permit whose valid-to day is before the site day moves to expired, with a status history entry, an
   audit entry and a notice to the item's coordinator (reads keep judging validity by date window, so they stay
   authoritative until the sweep catches up);
2. a live permit lapsing within the warning window gets one expiring-soon notice;
3. an item bearing load with no valid permit to load is announced once per breach: the coordinator and the holders of the
   issue permission are notified, a task due today goes to the coordinator, an audit entry is written and, for an item
   linked to a standing scaffold, the scaffold's red tag is written. Clearing the breach resets the marker.

The sweep never changes an item's status and never blocks an edit. It commits once, at the end, and rolls the whole run
back before raising if anything fails."""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import record_transition
from ..notifications.constants import Category
from ..notifications.service import notify
from ..role.models import RolePermission, UserRole
from ..scaffolds import breach as scaffold_breach
from ..tasks.service import create_task
from ..user.models import User
from . import rules
from .constants import BEARING_LOAD, ITEM_ENTITY, LIVE_PERMIT_STATUSES, PERMIT_ENTITY, PermitStatus, site_today
from .models import TemporaryWorksItem, TemporaryWorksPermit
from .permissions import TemporaryWorksPermissionName as P
from .service import link_of
from .transitions import permit_move

EXPIRED = PermitStatus.EXPIRED.value
ProjectOn = Callable[[int], Awaitable[bool]]


@dataclass
class SweepResult:
    expired: int = 0
    expiring_soon: int = 0
    breaches: int = 0
    markers_reset: int = 0
    red_tagged: int = 0

    @property
    def total(self) -> int:
        return self.expired + self.expiring_soon + self.breaches + self.markers_reset + self.red_tagged


async def holders(db: AsyncSession, permission: str) -> list[int]:
    """Active users holding ``permission`` through a role, or superusers."""
    by_role = select(UserRole.user_id).join(RolePermission, RolePermission.role_id == UserRole.role_id)
    rows = await db.execute(
        select(User.id, User.is_superuser).where(
            User.is_deleted.is_(False),
            or_(User.is_superuser.is_(True), User.id.in_(by_role.where(RolePermission.permission_name == permission))),
        )
    )
    return [uid for uid, su in rows.all() if permission in await load_permissions(db, uid, is_superuser=su)]


async def _items(db: AsyncSession, ids: set[int]) -> dict[int, TemporaryWorksItem]:
    if not ids:
        return {}
    rows = await db.execute(select(TemporaryWorksItem).where(TemporaryWorksItem.id.in_(ids)))
    return {i.id: i for i in rows.scalars()}


async def _tell_coordinator(
    db: AsyncSession, item: TemporaryWorksItem | None, permit: TemporaryWorksPermit, title: str
) -> None:
    if item is None or item.coordinator_user_id is None:
        return
    await notify(
        db,
        [item.coordinator_user_id],
        Category.DUE,
        f"{item.reference}: {title}",
        body=f"The {permit.kind} permit {permit.number} is valid until {permit.valid_to}.",
        link=link_of(item),
        entity=(PERMIT_ENTITY, permit.id),
    )


async def _live_permits(db: AsyncSession, *where: Any) -> list[TemporaryWorksPermit]:
    rows = await db.execute(
        select(TemporaryWorksPermit)
        .where(
            TemporaryWorksPermit.status.in_(sorted(LIVE_PERMIT_STATUSES)),
            TemporaryWorksPermit.valid_to.is_not(None),
            TemporaryWorksPermit.deleted_at.is_(None),
            *where,
        )
        .order_by(TemporaryWorksPermit.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


async def _expire(db: AsyncSession, today: date, result: SweepResult, on: ProjectOn) -> None:
    permits = [p for p in await _live_permits(db, TemporaryWorksPermit.valid_to < today) if await on(p.project_id)]
    items = await _items(db, {p.item_id for p in permits})
    for permit in permits:
        before = permit.status
        if permit_move(before, EXPIRED, sweep=True) is not None:
            continue
        permit.status = EXPIRED
        await record_transition(db, PERMIT_ENTITY, permit.id, before, EXPIRED, None, "The valid-to day has passed")
        await record_audit(
            db,
            "temporary_works.permit.expired",
            PERMIT_ENTITY,
            permit.id,
            project_id=permit.project_id,
            summary=f"{permit.number}: expired on {permit.valid_to}",
            before={"status": before},
            after={"status": EXPIRED},
        )
        await _tell_coordinator(db, items.get(permit.item_id), permit, f"permit {permit.number} has expired")
        result.expired += 1


async def _expiring_soon(db: AsyncSession, today: date, result: SweepResult, on: ProjectOn) -> None:
    permits = await _live_permits(db, TemporaryWorksPermit.expiry_notified_on.is_(None))
    soon = [p for p in permits if rules.lapses_within(p, today) and await on(p.project_id)]
    items = await _items(db, {p.item_id for p in soon})
    for permit in soon:
        permit.expiry_notified_on = today
        await _tell_coordinator(db, items.get(permit.item_id), permit, f"permit {permit.number} is expiring soon")
        result.expiring_soon += 1


async def _announce(db: AsyncSession, item: TemporaryWorksItem, today: date, issuers: list[int], result: SweepResult) -> None:
    """The once-per-breach actions for one item."""
    reason = rules.breach_reason(item.status, today)
    await notify(
        db,
        {*issuers, *([item.coordinator_user_id] if item.coordinator_user_id else [])},
        Category.DUE,
        f"{item.reference}: bearing load with no valid permit to load",
        body=reason,
        link=link_of(item),
        entity=(ITEM_ENTITY, item.id),
    )
    await create_task(
        db,
        project_id=item.project_id,
        title=f"Breach: {item.reference} has no valid permit to load",
        created_by_id=None,
        entity=(ITEM_ENTITY, item.id),
        commit=False,
        description=reason,
        assignee_id=item.coordinator_user_id,
        due_date=today,
    )
    await record_audit(
        db,
        "temporary_works.item.breach",
        ITEM_ENTITY,
        item.id,
        project_id=item.project_id,
        summary=f"{item.reference}: {reason}",
        after={"status": item.status, "breach_on": today.isoformat()},
    )
    item.breach_notified_on = today
    result.breaches += 1
    if item.scaffold_id is not None and await is_enabled(db, "scaffolds", item.project_id):
        written = await scaffold_breach.mark_breach_red(
            db, item.scaffold_id, project_id=item.project_id, item_reference=item.reference
        )
        result.red_tagged += int(written)


async def _breaches(db: AsyncSession, today: date, result: SweepResult, on: ProjectOn) -> None:
    bearing = list(
        (
            await db.execute(
                select(TemporaryWorksItem)
                .where(TemporaryWorksItem.status.in_(sorted(BEARING_LOAD)), TemporaryWorksItem.deleted_at.is_(None))
                .order_by(TemporaryWorksItem.id)
            )
        ).scalars()
    )
    by_item: dict[int, list[TemporaryWorksPermit]] = defaultdict(list)
    if bearing:
        found = await db.execute(
            select(TemporaryWorksPermit).where(
                TemporaryWorksPermit.item_id.in_([i.id for i in bearing]), TemporaryWorksPermit.deleted_at.is_(None)
            )
        )
        for permit in found.scalars():
            by_item[permit.item_id].append(permit)
    breaching = {i.id for i in bearing if rules.is_breach(i.status, by_item[i.id], today)}
    issuers: list[int] | None = None
    for item in bearing:
        if item.id in breaching and item.breach_notified_on is None and await on(item.project_id):
            issuers = await holders(db, P.ISSUE.value) if issuers is None else issuers
            await _announce(db, item, today, issuers, result)
    still_marked = await db.execute(select(TemporaryWorksItem).where(TemporaryWorksItem.breach_notified_on.is_not(None)))
    for item in still_marked.scalars():
        if item.id not in breaching and await on(item.project_id):
            item.breach_notified_on = None  # the breach has cleared: a later one is announced afresh
            result.markers_reset += 1


async def run_sweep(db: AsyncSession, today: date | None = None) -> SweepResult:
    """Run the three steps for ``today`` (default: the site day) and commit once. Idempotent."""
    today = today or site_today()
    result = SweepResult()
    switched: dict[int, bool] = {}

    async def on(project_id: int) -> bool:
        if project_id not in switched:
            switched[project_id] = await is_enabled(db, "temporary_works", project_id)
        return switched[project_id]

    try:
        await _expire(db, today, result, on)
        await _expiring_soon(db, today, result, on)
        await _breaches(db, today, result, on)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return result

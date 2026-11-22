"""Scaffold lifecycle, tags and inspections, hire days, and the planner's readiness check.

Tags: an inspection hangs a green (safe), yellow (restricted) or red (do not use) tag and sets the next
inspection due ``inspection_interval_days`` later (7 by default). A weather event makes every standing
scaffold in its area due at once. A tag whose inspection is overdue counts as **red** wherever it is read
(``effective_tag``), and the daily ``scaffolds:overdue`` job also writes that red tag back and tells the
custodian, so an overdue scaffold blocks the work it serves until someone re-inspects it.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, record_transition
from ...infrastructure.records.numbering import next_reference
from ..asset_tree import service as tree
from ..asset_tree.models import AssetNode
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..role.models import RolePermission, UserRole
from ..tasks.service import create_task
from ..user.models import User
from .constants import (
    APPROVE_STEPS,
    CLOSED,
    FLOW,
    MOD_FLOW,
    STANDING,
    USABLE_TAGS,
    ModificationStatus,
    ScaffoldStatus,
    Tag,
)
from .models import Scaffold, ScaffoldInspection, ScaffoldLink, ScaffoldModification
from .permissions import ScaffoldPermissionName as P
from .schemas import ScaffoldInspectionRead, ScaffoldRead

ENTITY = "scaffold"


class ScaffoldNotFound(ResourceNotFoundError):
    public_detail = "Scaffold not found."


class NotAllowed(PermissionDeniedError):
    public_detail = "You don't have permission for that scaffold step."


class NotStanding(ValidationError):
    public_detail = "Only a scaffold that is standing on site can be inspected."


class BadModification(ValidationError):
    public_detail = "A modification can only be requested for a scaffold that is erected or in use."


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def inspection_overdue(s: Scaffold, at: datetime | None = None) -> bool:
    """Standing, tagged usable, and the next inspection is past (or was never set)."""
    if s.status not in STANDING or s.tag_status not in USABLE_TAGS:
        return False
    due = _aware(s.next_inspection_due)
    return due is None or due <= (at or utcnow())


def effective_tag(s: Scaffold, at: datetime | None = None) -> str:
    """The tag that applies at ``at``: none unless standing, red when the inspection is overdue."""
    if s.status not in STANDING:
        return Tag.NONE.value
    if inspection_overdue(s, at):
        return Tag.RED.value
    return s.tag_status


def hire_days(erected_on: date | None, dismantled_on: date | None, start: date | None, end: date) -> int:
    """Days on hire within ``[start, end]``, counting the erection and dismantle days."""
    if erected_on is None:
        return 0
    first = max(erected_on, start) if start else erected_on
    last = min(dismantled_on, end) if dismantled_on else end
    return max((last - first).days + 1, 0)


def hire_cost(days: int, rate: Decimal | None) -> Decimal | None:
    return None if rate is None else (Decimal(days) * rate).quantize(Decimal("0.01"))


async def holders(db: AsyncSession, permission: str) -> list[int]:
    rows = await db.execute(
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_name == permission)
        .distinct()
    )
    return list(rows.scalars())


def link_of(s: Scaffold) -> str:
    return f"/scaffolds?project={s.project_id}&id={s.id}"


async def get_scaffold(db: AsyncSession, scaffold_id: int) -> Scaffold:
    s = await db.get(Scaffold, scaffold_id)
    if s is None:
        raise ScaffoldNotFound(str(scaffold_id))
    return s


async def _links(db: AsyncSession, ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {i: [] for i in ids}
    if ids:
        for sid, nid in (
            await db.execute(select(ScaffoldLink.scaffold_id, ScaffoldLink.node_id).where(ScaffoldLink.scaffold_id.in_(ids)))
        ).tuples():
            out[sid].append(nid)
    return out


async def read_scaffolds(db: AsyncSession, rows: list[Scaffold], today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    now = utcnow()
    users = {u for s in rows for u in (s.requested_by_id, s.custodian_id) if u}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(users)))).tuples().all()) if users else {}
    node_ids = {s.node_id for s in rows}
    paths = (
        dict((await db.execute(select(AssetNode.id, AssetNode.display_path).where(AssetNode.id.in_(node_ids)))).tuples().all())
        if node_ids
        else {}
    )
    links = await _links(db, [s.id for s in rows])
    out = []
    for s in rows:
        days = hire_days(s.erected_on, s.dismantled_on, None, today)
        out.append(
            ScaffoldRead.model_validate(s)
            .model_copy(
                update={
                    "node_path": paths.get(s.node_id),
                    "requested_by_name": names.get(s.requested_by_id) if s.requested_by_id else None,
                    "custodian_name": names.get(s.custodian_id) if s.custodian_id else None,
                    "effective_tag": effective_tag(s, now),
                    "inspection_overdue": inspection_overdue(s, now),
                    "days_erected": days,
                    "hire_cost": hire_cost(days, s.hire_rate),
                    "linked_node_ids": sorted(links.get(s.id, [])),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def _check_nodes(db: AsyncSession, project_id: int, node_ids: list[int], item_id: int | None) -> None:
    for nid in node_ids:
        await tree.get_node(db, nid, project_id)
    if item_id is not None:
        await tree.get_item(db, item_id, project_id)


async def _set_links(db: AsyncSession, s: Scaffold, node_ids: list[int]) -> None:
    await db.execute(delete(ScaffoldLink).where(ScaffoldLink.scaffold_id == s.id))
    db.add_all([ScaffoldLink(scaffold_id=s.id, node_id=n) for n in sorted(set(node_ids) - {s.node_id})])


async def create_scaffold(db: AsyncSession, values: dict[str, Any], user: dict[str, Any]) -> Scaffold:
    project_id = values.pop("project_id")
    links = values.pop("linked_node_ids", [])
    await _check_nodes(db, project_id, [values["node_id"], *links], values.get("item_id"))
    s = Scaffold(
        project_id=project_id,
        code=await next_reference(db, "SCF", project_id),
        requested_by_id=user["id"],
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(s)
    await db.flush()
    await _set_links(db, s, links)
    await record_transition(db, ENTITY, s.id, None, s.status, user["id"], "Requested")
    approvers = await holders(db, P.APPROVE.value)
    await notify(
        db,
        [*approvers, *([s.custodian_id] if s.custodian_id else [])],
        Category.APPROVAL,
        f"{s.code}: scaffold requested",
        body=(s.purpose or s.location_text or "")[:500] or None,
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=user["id"],
    )
    await db.commit()
    return s


async def update_scaffold(db: AsyncSession, s: Scaffold, changes: dict[str, Any]) -> None:
    links = changes.pop("linked_node_ids", None)
    nodes = [changes["node_id"]] if changes.get("node_id") else []
    await _check_nodes(db, s.project_id, nodes + (links or []), changes.get("item_id"))
    for key, value in changes.items():
        if key in {"node_id", "scaffold_type", "duty_class", "inspection_interval_days", "dimensions"} and value is None:
            continue
        setattr(s, key, value.value if hasattr(value, "value") else value)
    if "inspection_interval_days" in changes and s.last_inspected_at and s.tag_status in USABLE_TAGS:
        last = _aware(s.last_inspected_at)
        assert last is not None
        s.next_inspection_due = last + timedelta(days=s.inspection_interval_days)
    if links is not None:
        await _set_links(db, s, links)
    await db.commit()


def required_permission(target: str) -> str:
    if target in APPROVE_STEPS:
        return P.APPROVE.value
    if target == ScaffoldStatus.DISMANTLE_REQUESTED:
        return P.CREATE.value
    return P.TRANSITION.value


async def transition(
    db: AsyncSession,
    s: Scaffold,
    target: str,
    user: dict[str, Any],
    held: frozenset[str],
    on: date | None = None,
    note: str | None = None,
) -> None:
    assert_transition(FLOW, s.status, target)
    needed = required_permission(target)
    requester_cancels = target == ScaffoldStatus.CANCELLED and s.requested_by_id == user["id"]
    if not (user.get("is_superuser") or needed in held or requester_cancels):
        raise NotAllowed(needed)
    day = on or date.today()
    before = s.status
    s.status = target
    if target == ScaffoldStatus.APPROVED:
        s.approved_by_id, s.approved_at = user["id"], utcnow()
    elif target == ScaffoldStatus.ERECTED:
        if s.erected_on is None:
            s.erected_on = day
        # Built (or modified): out of use until the handover inspection tags it.
        s.tag_status, s.next_inspection_due = Tag.NONE.value, None
    elif target == ScaffoldStatus.MODIFYING:
        s.tag_status = Tag.RED.value
    elif target == ScaffoldStatus.DISMANTLE_REQUESTED:
        s.dismantle_requested_on = day
    elif target == ScaffoldStatus.DISMANTLING:
        s.tag_status = Tag.RED.value
    elif target == ScaffoldStatus.DISMANTLED:
        s.dismantled_on = day
        s.tag_status, s.next_inspection_due = Tag.NONE.value, None
    elif target in {ScaffoldStatus.IN_USE, ScaffoldStatus.ERECTED} and before == ScaffoldStatus.DISMANTLE_REQUESTED:
        s.dismantle_requested_on = None
    await record_transition(db, ENTITY, s.id, before, target, user["id"], note)
    watchers = {s.requested_by_id, s.custodian_id} - {None}
    if target in {ScaffoldStatus.DISMANTLE_REQUESTED}:
        watchers |= set(await holders(db, P.APPROVE.value))
    await notify(
        db,
        [w for w in watchers if w],
        Category.STATUS,
        f"{s.code} is now {target.replace('_', ' ')}",
        body=note,
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=user["id"],
    )
    await db.commit()


async def inspect(db: AsyncSession, s: Scaffold, values: dict[str, Any], user: dict[str, Any]) -> ScaffoldInspection:
    """Record an inspection and hang its tag. A usable tag on an erected scaffold hands it over (``in_use``)."""
    if s.status not in STANDING:
        raise NotStanding(s.status)
    at = _aware(values.get("inspected_at")) or utcnow()
    tag = str(values["tag"])
    if tag == Tag.NONE:
        raise ValidationError("An inspection hangs a green, yellow or red tag")
    next_due = at + timedelta(days=s.inspection_interval_days) if tag in USABLE_TAGS else None
    row = ScaffoldInspection(
        scaffold_id=s.id,
        kind=str(values["kind"]),
        inspected_at=at,
        inspector_id=user["id"],
        tag=tag,
        tag_no=values.get("tag_no") or s.tag_no,
        restrictions=values.get("restrictions") if tag == Tag.YELLOW else None,
        checklist=[dict(r) for r in values.get("checklist") or []],
        notes=values.get("notes"),
        next_due_at=next_due,
    )
    db.add(row)
    s.tag_status, s.tag_no, s.tag_restrictions = tag, row.tag_no, row.restrictions
    s.last_inspected_at, s.next_inspection_due = at, next_due
    if tag in USABLE_TAGS and s.status == ScaffoldStatus.ERECTED:
        await record_transition(db, ENTITY, s.id, s.status, ScaffoldStatus.IN_USE.value, user["id"], f"Tagged {tag}")
        s.status = ScaffoldStatus.IN_USE.value
    await db.flush()
    await notify(
        db,
        [u for u in {s.custodian_id, s.requested_by_id} if u],
        Category.STATUS,
        f"{s.code} tagged {tag}" + (f" ({row.tag_no})" if row.tag_no else ""),
        body=row.restrictions,
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=user["id"],
    )
    await db.commit()
    return row


async def read_inspections(db: AsyncSession, rows: list[ScaffoldInspection]) -> list[dict[str, Any]]:
    ids = {r.inspector_id for r in rows if r.inspector_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    return [
        ScaffoldInspectionRead.model_validate(r)
        .model_copy(update={"inspector_name": names.get(r.inspector_id) if r.inspector_id else None})
        .model_dump(mode="json")
        for r in rows
    ]


async def request_inspection(db: AsyncSession, s: Scaffold, reason: str, note: str | None, user: dict[str, Any]) -> int:
    """A task for the custodian (who assigns an inspector) due today."""
    task = await create_task(
        db,
        project_id=s.project_id,
        title=f"Inspect scaffold {s.code}" + (f" (tag {s.tag_no})" if s.tag_no else "") + f": {reason.replace('_', ' ')}",
        created_by_id=user["id"],
        entity=(ENTITY, s.id),
        assignee_id=s.custodian_id,
        due_date=date.today(),
        description=note,
        type="construction",
        commit=False,
    )
    await db.commit()
    return task.id


async def weather_event(
    db: AsyncSession, project_id: int, node_id: int | None, description: str, user: dict[str, Any]
) -> list[Scaffold]:
    """Every standing scaffold in the area needs inspecting before use: due now, so its tag reads red until then."""
    where: list[Any] = [Scaffold.project_id == project_id, Scaffold.status.in_([s.value for s in STANDING])]
    if node_id is not None:
        where.append(Scaffold.node_id.in_(await tree.subtree_ids(db, node_id, with_lineage=False)))
    rows = list((await db.execute(select(Scaffold).where(*where).order_by(Scaffold.code))).scalars())
    now = utcnow()
    for s in rows:
        due = _aware(s.next_inspection_due)
        if s.tag_status in USABLE_TAGS and (due is None or due > now):
            s.next_inspection_due = now
        await create_task(
            db,
            project_id=project_id,
            title=f"Inspect scaffold {s.code} after weather event",
            created_by_id=user["id"],
            entity=(ENTITY, s.id),
            assignee_id=s.custodian_id,
            due_date=date.today(),
            description=description,
            type="construction",
            commit=False,
        )
    await db.commit()
    return rows


async def mark_overdue(db: AsyncSession, at: datetime | None = None) -> int:
    """Write the red tag on every standing scaffold whose inspection is overdue, and tell its custodian."""
    at = at or utcnow()
    rows = (
        await db.execute(
            select(Scaffold).where(
                Scaffold.status.in_([s.value for s in STANDING]),
                Scaffold.tag_status.in_(list(USABLE_TAGS)),
            )
        )
    ).scalars()
    count = 0
    for s in rows:
        if not inspection_overdue(s, at):
            continue
        before = s.tag_status
        s.tag_status = Tag.RED.value
        await record_transition(db, "scaffold_tag", s.id, before, Tag.RED.value, None, "Inspection overdue")
        await notify(
            db,
            [u for u in {s.custodian_id} if u],
            Category.DUE,
            f"{s.code}: inspection overdue, tag is red",
            body="Do not use the scaffold until it has been inspected and re-tagged.",
            link=link_of(s),
            entity=(ENTITY, s.id),
        )
        count += 1
    await db.commit()
    return count


# --- modifications ------------------------------------------------------------------------------


async def request_modification(
    db: AsyncSession, s: Scaffold, values: dict[str, Any], user: dict[str, Any]
) -> ScaffoldModification:
    if s.status not in {ScaffoldStatus.ERECTED, ScaffoldStatus.IN_USE}:
        raise BadModification(s.status)
    m = ScaffoldModification(scaffold_id=s.id, requested_by_id=user["id"], **values)
    db.add(m)
    await db.flush()
    await notify(
        db,
        await holders(db, P.APPROVE.value),
        Category.APPROVAL,
        f"{s.code}: modification requested",
        body=m.description[:500],
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=user["id"],
    )
    await db.commit()
    return m


async def decide_modification(
    db: AsyncSession,
    s: Scaffold,
    m: ScaffoldModification,
    target: str,
    note: str | None,
    user: dict[str, Any],
    held: frozenset[str],
) -> None:
    """Approve (the scaffold goes out of use: ``modifying``, red tag), reject, or complete (back to ``erected``)."""
    assert_transition(MOD_FLOW, m.status, target)
    needed = P.TRANSITION.value if target == ModificationStatus.COMPLETED else P.APPROVE.value
    if not (user.get("is_superuser") or needed in held):
        raise NotAllowed(needed)
    m.status, m.note = target, note or m.note
    if target in {ModificationStatus.APPROVED, ModificationStatus.REJECTED}:
        m.decided_by_id, m.decided_at = user["id"], utcnow()
    if target == ModificationStatus.APPROVED and s.status in {ScaffoldStatus.ERECTED, ScaffoldStatus.IN_USE}:
        await record_transition(db, ENTITY, s.id, s.status, ScaffoldStatus.MODIFYING.value, user["id"], "Modification approved")
        s.status, s.tag_status = ScaffoldStatus.MODIFYING.value, Tag.RED.value
    if target == ModificationStatus.COMPLETED:
        m.completed_at = utcnow()
        if s.status == ScaffoldStatus.MODIFYING:
            await record_transition(
                db, ENTITY, s.id, s.status, ScaffoldStatus.ERECTED.value, user["id"], "Modification completed"
            )
            s.status, s.tag_status, s.next_inspection_due = ScaffoldStatus.ERECTED.value, Tag.NONE.value, None
    await notify(
        db,
        [u for u in {m.requested_by_id, s.custodian_id} if u],
        Category.STATUS,
        f"{s.code}: modification {target}",
        body=note,
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=user["id"],
    )
    await db.commit()


# --- hire ---------------------------------------------------------------------------------------


async def hire_lines(db: AsyncSession, project_id: int, start: date | None, end: date) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Scaffold, AssetNode.display_path)
            .join(AssetNode, AssetNode.id == Scaffold.node_id)
            .where(Scaffold.project_id == project_id, Scaffold.erected_on.is_not(None), Scaffold.erected_on <= end)
            .order_by(Scaffold.code)
        )
    ).all()
    out = []
    for s, path in rows:
        days = hire_days(s.erected_on, s.dismantled_on, start, end)
        if days <= 0:
            continue
        out.append(
            {
                "scaffold_id": s.id,
                "code": s.code,
                "tag_no": s.tag_no,
                "status": s.status,
                "node_path": path,
                "erected_on": s.erected_on,
                "dismantled_on": s.dismantled_on,
                "days": days,
                "rate": s.hire_rate,
                "cost": hire_cost(days, s.hire_rate),
            }
        )
    return out


# --- planner readiness --------------------------------------------------------------------------


@dataclass(frozen=True)
class Blocker:
    scaffold_id: int
    code: str
    status: str
    effective_tag: str
    reason: str


async def serving(db: AsyncSession, node_id: int) -> list[Scaffold]:
    """Scaffolds that stand at or are linked to the node or anything beneath it, closed ones left out."""
    ids = await tree.subtree_ids(db, node_id, with_lineage=True)
    linked = select(ScaffoldLink.scaffold_id).where(ScaffoldLink.node_id.in_(ids))
    rows = await db.execute(
        select(Scaffold)
        .where(
            (Scaffold.node_id.in_(ids)) | (Scaffold.id.in_(linked)),
            Scaffold.status.not_in([s.value for s in CLOSED]),
        )
        .order_by(Scaffold.code)
    )
    return list(rows.scalars())


def _blocker(s: Scaffold, on_date: date) -> Blocker | None:
    end_of_day = datetime.combine(on_date, datetime.max.time(), tzinfo=UTC)
    if s.status not in STANDING:
        return Blocker(s.id, s.code, s.status, Tag.NONE.value, "not erected yet")
    if s.status in {ScaffoldStatus.MODIFYING, ScaffoldStatus.DISMANTLING}:
        return Blocker(s.id, s.code, s.status, Tag.RED.value, f"{s.status.replace('_', ' ')}")
    if s.tag_status not in USABLE_TAGS:
        return Blocker(s.id, s.code, s.status, s.tag_status, "not tagged safe" if s.tag_status == Tag.NONE else "red tag")
    due = _aware(s.next_inspection_due)
    if due is None or due < end_of_day:
        return Blocker(s.id, s.code, s.status, Tag.RED.value, "inspection overdue by then")
    return None


async def scaffold_readiness(db: AsyncSession, node_id: int, on_date: date) -> tuple[bool, list[Scaffold], list[Blocker]]:
    rows = await serving(db, node_id)
    blockers = [b for b in (_blocker(s, on_date) for s in rows) if b is not None]
    return not blockers, rows, blockers


async def scaffold_ready(db: AsyncSession, node_id: int, on_date: date) -> bool:
    """For the planner: is the scaffold access for work on ``node_id`` in place on ``on_date``?

    Considers every scaffold standing at, or linked to, the node or any node beneath it (with split/merge
    lineage), except rejected, cancelled and dismantled ones. True when each is erected, carries a green or
    yellow tag, and its next inspection is not due before the end of ``on_date`` (an overdue inspection is a
    red tag). True when no scaffold serves the node: there is nothing to wait for. Use ``scaffold_readiness``
    for the reasons.
    """
    ready, _, _ = await scaffold_readiness(db, node_id, on_date)
    return ready

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..contacts.service import contact_names
from ..user.models import User
from .constants import ENTITY, FLOW, CorrespondenceStatus
from .models import Correspondence
from .schemas import CorrespondenceRead, Party

MAX_THREAD = 500


class CorrespondenceNotFoundError(ResourceNotFoundError):
    public_detail = "Correspondence not found."


class ReplyProjectError(ValidationError):
    public_detail = "A reply must belong to the same project as the item it answers."


async def user_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


def is_overdue(item: Correspondence, today: date | None = None) -> bool:
    return bool(
        item.status == CorrespondenceStatus.RESPONSE_REQUIRED
        and item.response_required_by
        and item.response_required_by < (today or date.today())
    )


def overdue_filter(today: date) -> list[Any]:
    return [
        Correspondence.status == CorrespondenceStatus.RESPONSE_REQUIRED.value,
        Correspondence.response_required_by < today,
    ]


def search_filter(search: str) -> list[Any]:
    """Every word must appear in the reference, subject, body or the other party's reference."""
    text = func.lower(
        Correspondence.reference
        + " "
        + Correspondence.subject
        + " "
        + func.coalesce(Correspondence.body, "")
        + " "
        + func.coalesce(Correspondence.external_reference, "")
    )
    return [text.like(f"%{word}%") for word in search.lower().split()[:8]]


async def read_items(db: AsyncSession, items: list[Correspondence]) -> list[dict[str, Any]]:
    users = await user_names(db, {u for c in items for u in [c.sender_user_id, *c.recipient_user_ids] if isinstance(u, int)})
    contacts = await contact_names(
        db, {i for c in items for i in [c.sender_contact_id, *c.recipient_contact_ids] if isinstance(i, int)}
    )
    ids = [c.id for c in items]
    replies: dict[int, int] = {}
    parents: dict[int, str] = {}
    if ids:
        counted = await db.execute(
            select(Correspondence.in_reply_to_id, func.count())
            .where(Correspondence.in_reply_to_id.in_(ids))
            .group_by(Correspondence.in_reply_to_id)
        )
        replies = {parent: n for parent, n in counted.tuples().all() if parent is not None}
        parent_ids = {c.in_reply_to_id for c in items if c.in_reply_to_id}
        if parent_ids:
            parents = dict(
                (await db.execute(select(Correspondence.id, Correspondence.reference).where(Correspondence.id.in_(parent_ids))))
                .tuples()
                .all()
            )
    today = date.today()
    out = []
    for c in items:
        sender = (
            contacts.get(c.sender_contact_id)
            if c.sender_contact_id
            else (users.get(c.sender_user_id) if c.sender_user_id else None)
        )
        recipients = [Party(kind="contact", id=i, name=contacts.get(i)) for i in c.recipient_contact_ids] + [
            Party(kind="user", id=i, name=users.get(i)) for i in c.recipient_user_ids
        ]
        out.append(
            CorrespondenceRead.model_validate(c)
            .model_copy(
                update={
                    "sender_name": sender,
                    "recipients": recipients,
                    "overdue": is_overdue(c, today),
                    "reply_count": replies.get(c.id, 0),
                    "in_reply_to_reference": parents.get(c.in_reply_to_id) if c.in_reply_to_id else None,
                }
            )
            .model_dump(mode="json")
        )
    return out


async def get_item(db: AsyncSession, item_id: int) -> Correspondence:
    item = await db.get(Correspondence, item_id)
    if item is None:
        raise CorrespondenceNotFoundError("No such correspondence")
    return item


async def create_item(db: AsyncSession, values: dict[str, Any], actor_id: int) -> Correspondence:
    values = {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}
    project_id = values.pop("project_id")
    original = None
    if values.get("in_reply_to_id"):
        original = await get_item(db, values["in_reply_to_id"])
        if original.project_id != project_id:
            raise ReplyProjectError("cross-project reply")
    year = (values.get("date_sent") or values.get("date_received") or date.today()).year
    item = Correspondence(
        project_id=project_id,
        reference=await next_reference(db, f"COR-{year}", project_id),
        subject=values.pop("subject"),
        created_by_id=actor_id,
        **values,
    )
    db.add(item)
    await db.flush()
    await record_transition(db, ENTITY, item.id, None, item.status, actor_id)
    if original is not None and original.status == CorrespondenceStatus.RESPONSE_REQUIRED:
        await record_transition(
            db, ENTITY, original.id, original.status, CorrespondenceStatus.RESPONDED.value, actor_id, f"Reply {item.reference}"
        )
        original.status = CorrespondenceStatus.RESPONDED.value
    await db.commit()
    return item


async def update_item(db: AsyncSession, item: Correspondence, changes: dict[str, Any], actor_id: int) -> None:
    note = changes.pop("status_note", None)
    target = changes.pop("status", None)
    for key, value in changes.items():
        setattr(item, key, value.value if hasattr(value, "value") else value)
    if target is not None and str(target) != item.status:
        assert_transition(FLOW, item.status, str(target))
        await record_transition(db, ENTITY, item.id, item.status, str(target), actor_id, note)
        item.status = str(target)
    await db.commit()


async def thread_of(db: AsyncSession, item: Correspondence) -> list[dict[str, Any]]:
    """The whole exchange the item belongs to, from the first item down, each with its depth."""
    root, seen = item, {item.id}
    while root.in_reply_to_id and len(seen) < MAX_THREAD:
        parent = await db.get(Correspondence, root.in_reply_to_id)
        if parent is None or parent.id in seen:
            break
        seen.add(parent.id)
        root = parent
    members: list[Correspondence] = [root]
    children: dict[int, list[Correspondence]] = defaultdict(list)
    frontier = [root.id]
    while frontier and len(members) < MAX_THREAD:
        rows = list(
            (
                await db.execute(
                    select(Correspondence).where(Correspondence.in_reply_to_id.in_(frontier)).order_by(Correspondence.id)
                )
            ).scalars()
        )
        rows = [r for r in rows if r.id not in {m.id for m in members}]
        for r in rows:
            assert r.in_reply_to_id is not None
            children[r.in_reply_to_id].append(r)
        members += rows
        frontier = [r.id for r in rows]
    read = {r["id"]: r for r in await read_items(db, members)}
    ordered: list[dict[str, Any]] = []

    def walk(node: Correspondence, depth: int) -> None:
        ordered.append({**read[node.id], "depth": depth})
        for child in children[node.id]:
            walk(child, depth + 1)

    walk(root, 0)
    return ordered

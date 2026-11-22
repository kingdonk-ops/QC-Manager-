"""Shift handovers. No FastAPI imports."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.models import AssetNode
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .constants import (
    ESCALATE_AFTER_REMINDERS,
    FLOW,
    ITEM_STATUSES,
    REMIND_AFTER,
    REMIND_EVERY,
    STILL_OPEN,
    HandoverStatus,
    ItemKind,
)
from .models import Handover, HandoverItem
from .schemas import HandoverItemRead, HandoverRead


class HandoverNotFound(ResourceNotFoundError):
    public_detail = "Handover not found."


class HandoverRuleError(ValidationError):
    public_detail = "That change breaks the handover's rules."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class NotAuthor(PermissionDeniedError):
    public_detail = "Only the author can change, hand over or recall this handover."


class NotYours(PermissionDeniedError):
    public_detail = "Only the incoming supervisor named on the handover can acknowledge it."


def link_of(h: Handover) -> str:
    return f"/handover?project={h.project_id}&id={h.id}"


async def get(db: AsyncSession, handover_id: int) -> Handover:
    h = await db.get(Handover, handover_id)
    if h is None:
        raise HandoverNotFound(str(handover_id))
    return h


async def _items(db: AsyncSession, h: Handover, rows: list[dict[str, Any]]) -> list[HandoverItem]:
    out = []
    for seq, r in enumerate(rows, start=1):
        kind = str(r["kind"])
        allowed = ITEM_STATUSES[kind]
        status = r.get("status") or allowed[0]
        if status not in allowed:
            raise HandoverRuleError(f"'{status}' isn't a status for {kind.replace('_', ' ')} (use {', '.join(allowed)}).")
        node_id = r.get("node_id")
        anchor_id = None
        if node_id:
            await tree.get_node(db, node_id, h.project_id)
            anchor_id = (await tree.work_anchor_for(db, node_id)).id
        elif kind == ItemKind.WIP:
            raise tree.NoWorkAnchor()
        out.append(
            HandoverItem(
                handover_id=h.id,
                kind=kind,
                title=r["title"],
                status=status,
                detail=r.get("detail"),
                reference=r.get("reference"),
                anchor_id=anchor_id,
                link_type=r.get("link_type"),
                link_id=r.get("link_id"),
                link_label=r.get("link_label"),
                seq=seq,
            )
        )
    return out


async def _replace_items(db: AsyncSession, h: Handover, rows: list[dict[str, Any]]) -> None:
    items = await _items(db, h, rows)
    await db.execute(delete(HandoverItem).where(HandoverItem.handover_id == h.id))
    db.add_all(items)
    await db.flush()


async def last_in_area(
    db: AsyncSession, project_id: int, area_node_id: int | None, before_id: int | None = None
) -> Handover | None:
    where: list[Any] = [
        Handover.project_id == project_id,
        Handover.status.in_((HandoverStatus.SUBMITTED, HandoverStatus.ACKNOWLEDGED)),
        Handover.area_node_id.is_(None) if area_node_id is None else Handover.area_node_id == area_node_id,
    ]
    if before_id:
        where.append(Handover.id != before_id)
    last: Handover | None = await db.scalar(
        select(Handover).where(*where).order_by(Handover.shift_date.desc(), Handover.submitted_at.desc()).limit(1)
    )
    return last


async def create(db: AsyncSession, values: dict[str, Any], user_id: int) -> Handover:
    project_id = values["project_id"]
    items = values.pop("items", [])
    carry = values.pop("carry_forward", True)
    if values.get("area_node_id"):
        await tree.get_node(db, values["area_node_id"], project_id)
    h = Handover(code=await next_reference(db, "HO", project_id), author_id=user_id, **values)
    db.add(h)
    await db.flush()
    previous = await last_in_area(db, project_id, h.area_node_id, h.id) if carry else None
    carried: list[dict[str, Any]] = []
    if previous is not None:
        h.carried_from_id = previous.id
        for it in (
            await db.execute(select(HandoverItem).where(HandoverItem.handover_id == previous.id).order_by(HandoverItem.seq))
        ).scalars():
            if it.status in STILL_OPEN:
                carried.append(
                    {
                        "kind": it.kind,
                        "title": it.title,
                        "status": it.status,
                        "detail": it.detail,
                        "reference": it.reference,
                        "node_id": it.anchor_id,
                        "link_type": it.link_type,
                        "link_id": it.link_id,
                        "link_label": it.link_label,
                    }
                )
    await _replace_items(db, h, carried + items)
    await record_transition(db, "handover", h.id, None, h.status, user_id)
    return h


async def update(db: AsyncSession, h: Handover, values: dict[str, Any], user_id: int) -> None:
    if h.status != HandoverStatus.DRAFT:
        raise HandoverRuleError(f"{h.code} has been handed over; recall it to change it.")
    if h.author_id != user_id:
        raise NotAuthor()
    items = values.pop("items", None)
    if values.get("area_node_id"):
        await tree.get_node(db, values["area_node_id"], h.project_id)
    for key, value in values.items():
        setattr(h, key, value)
    if items is not None:
        await _replace_items(db, h, items)
    await db.flush()


async def submit(db: AsyncSession, h: Handover, user_id: int) -> None:
    assert_transition(FLOW, h.status, HandoverStatus.SUBMITTED)
    if h.author_id != user_id:
        raise NotAuthor()
    if not h.recipient_id:
        raise HandoverRuleError("Name the incoming supervisor before handing over.")
    if h.recipient_id == user_id:
        raise HandoverRuleError("You can't hand over to yourself.")
    await record_transition(db, "handover", h.id, h.status, HandoverStatus.SUBMITTED, user_id)
    h.status = HandoverStatus.SUBMITTED
    h.submitted_at = datetime.now(UTC)
    h.reminders_sent, h.last_reminded_at = 0, None
    await notify(
        db,
        [h.recipient_id],
        Category.ASSIGNMENT,
        f"Handover {h.code} for your {h.to_shift} shift",
        body=(h.summary or "")[:300] or None,
        link=link_of(h),
        entity=("handover", h.id),
        actor_id=user_id,
    )
    await db.flush()
    await publish(
        "handover.handover.submitted", {"project_id": h.project_id, "handover_id": h.id, "recipient_id": h.recipient_id}
    )


async def recall(db: AsyncSession, h: Handover, user_id: int) -> None:
    assert_transition(FLOW, h.status, HandoverStatus.DRAFT)
    if h.author_id != user_id:
        raise NotAuthor()
    await record_transition(db, "handover", h.id, h.status, HandoverStatus.DRAFT, user_id, "Recalled")
    h.status = HandoverStatus.DRAFT
    h.submitted_at = None
    await db.flush()


async def acknowledge(db: AsyncSession, h: Handover, user_id: int, note: str | None) -> None:
    assert_transition(FLOW, h.status, HandoverStatus.ACKNOWLEDGED)
    if h.recipient_id != user_id:
        raise NotYours()
    await record_transition(db, "handover", h.id, h.status, HandoverStatus.ACKNOWLEDGED, user_id, note)
    h.status = HandoverStatus.ACKNOWLEDGED
    h.acknowledged_at, h.acknowledged_by_id, h.ack_note = datetime.now(UTC), user_id, note
    await notify(
        db,
        [h.author_id or 0],
        Category.STATUS,
        f"Handover {h.code} acknowledged",
        body=note,
        link=link_of(h),
        entity=("handover", h.id),
        actor_id=user_id,
    )
    await db.flush()
    await publish("handover.handover.acknowledged", {"project_id": h.project_id, "handover_id": h.id})


async def remind_unacknowledged(db: AsyncSession, now: datetime | None = None) -> int:
    """Remind incoming supervisors of handovers they haven't acknowledged; tell the author after a few reminders."""
    now = now or datetime.now(UTC)
    rows = (
        await db.execute(
            select(Handover).where(
                Handover.status == HandoverStatus.SUBMITTED,
                Handover.recipient_id.is_not(None),
                Handover.submitted_at <= now - REMIND_AFTER,
            )
        )
    ).scalars()
    sent = 0
    for h in rows:
        if h.last_reminded_at is not None and h.last_reminded_at > now - REMIND_EVERY:
            continue
        assert h.submitted_at is not None and h.recipient_id is not None
        waited = int((now - h.submitted_at).total_seconds() // 3600)
        await notify(
            db,
            [h.recipient_id],
            Category.DUE,
            f"Handover {h.code} is waiting for your acknowledgement",
            body=f"Handed over {waited} h ago.",
            link=link_of(h),
            entity=("handover", h.id),
        )
        h.reminders_sent += 1
        h.last_reminded_at = now
        if h.reminders_sent == ESCALATE_AFTER_REMINDERS and h.author_id:
            await notify(
                db,
                [h.author_id],
                Category.DUE,
                f"Handover {h.code} still not acknowledged",
                body=f"{h.reminders_sent} reminders sent over {waited} h.",
                link=link_of(h),
                entity=("handover", h.id),
            )
        sent += 1
    await db.commit()
    return sent


async def read(db: AsyncSession, rows: list[Handover], *, detail: bool = False) -> list[dict[str, Any]]:
    ids = [h.id for h in rows]
    users = {h.author_id for h in rows} | {h.recipient_id for h in rows}
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_({u for u in users if u})))).tuples().all())
        if any(users)
        else {}
    )
    items: dict[int, list[HandoverItem]] = defaultdict(list)
    for it in (
        (await db.execute(select(HandoverItem).where(HandoverItem.handover_id.in_(ids)).order_by(HandoverItem.seq))).scalars()
        if ids
        else []
    ):
        items[it.handover_id].append(it)
    node_ids = {h.area_node_id for h in rows if h.area_node_id} | {
        i.anchor_id for its in items.values() for i in its if i.anchor_id
    }
    nodes = (
        {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(node_ids)))).scalars()} if node_ids else {}
    )
    now = datetime.now(UTC)
    out = []
    for h in rows:
        its = items.get(h.id, [])
        area = nodes.get(h.area_node_id or 0)
        update: dict[str, Any] = {
            "author_name": names.get(h.author_id or 0),
            "recipient_name": names.get(h.recipient_id or 0),
            "area_name": area.display_path if area else None,
            "item_count": len(its),
            "open_count": sum(1 for i in its if i.status in STILL_OPEN),
            "waiting_hours": round((now - h.submitted_at).total_seconds() / 3600, 1)
            if h.status == HandoverStatus.SUBMITTED and h.submitted_at
            else None,
        }
        if detail:
            update["items"] = [
                HandoverItemRead.model_validate(i).model_copy(
                    update={
                        "anchor_code": (nodes[i.anchor_id].display_code or nodes[i.anchor_id].code)
                        if i.anchor_id in nodes
                        else None,
                        "anchor_path": nodes[i.anchor_id].display_path if i.anchor_id in nodes else None,
                    }
                )
                for i in its
            ]
        out.append(HandoverRead.model_validate(h).model_copy(update=update).model_dump(mode="json"))
    return out


SECTIONS = [
    (ItemKind.SAFETY, "Safety"),
    (ItemKind.PERMIT, "Permits in force"),
    (ItemKind.EQUIPMENT, "Equipment status"),
    (ItemKind.WIP, "Work in progress"),
    (ItemKind.OPEN_ITEM, "Open items"),
    (ItemKind.ISSUE, "Outstanding issues"),
]


async def pdf(db: AsyncSession, h: Handover) -> bytes:
    r = (await read(db, [h], detail=True))[0]
    doc = Document(title=f"Shift handover {h.code}", subtitle=r["area_name"] or "Whole project", footer=h.code)
    doc.fields(
        [
            ("Date", f"{h.shift_date:%a %d %b %Y}"),
            ("Shift", f"{h.from_shift} → {h.to_shift}"),
            ("From", r["author_name"] or "—"),
            ("To", r["recipient_name"] or "—"),
            ("Status", h.status),
            ("Acknowledged", f"{h.acknowledged_at:%d %b %Y %H:%M} UTC" if h.acknowledged_at else "—"),
        ]
    )
    if h.summary:
        doc.heading("Summary")
        doc.paragraph(h.summary)
    if h.safety_notes:
        doc.heading("Safety notes")
        doc.paragraph(h.safety_notes)
    for kind, title in SECTIONS:
        rows = [i for i in r["items"] if i["kind"] == kind]
        if rows:
            doc.heading(title)
            doc.table(
                ["Item", "Where", "Ref / link", "Status", "Detail"],
                [
                    [
                        i["title"],
                        i["anchor_path"] or "",
                        i["reference"] or i["link_label"] or "",
                        i["status"].replace("_", " "),
                        i["detail"] or "",
                    ]
                    for i in rows
                ],
                widths=[0.25, 0.2, 0.15, 0.12, 0.28],
            )
    if h.ack_note:
        doc.heading("Acknowledgement note")
        doc.paragraph(h.ack_note)
    return render_pdf(doc)

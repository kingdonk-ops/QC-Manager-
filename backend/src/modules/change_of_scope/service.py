from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.models import AssetItem, AssetNode
from ..change_orders.constants import CoStatus, Reason
from ..change_orders.models import ChangeOrder, ChangeOrderLine
from ..change_orders.service import ENTITY as CO_ENTITY
from ..change_orders.service import price
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..role.models import RolePermission, UserRole
from ..user.models import User
from .constants import EDITABLE, EXPIRES_AFTER_DAYS, FLOW, REMIND_BEFORE_DAYS, WAITING, CardStatus, Source
from .models import ChangeCard
from .permissions import ChangeOfScopePermissionName as P

ENTITY = "change_card"
CENT = Decimal("0.01")
REASON = {
    Source.SITE_INSTRUCTION: Reason.CLIENT_REQUEST,
    Source.CLIENT_DIRECTION: Reason.CLIENT_REQUEST,
    Source.FIELD_FINDING: Reason.UNFORESEEN_CONDITION,
    Source.OTHER: Reason.OTHER,
}


class CardNotFound(ResourceNotFoundError):
    public_detail = "Change card not found."


class CardError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


def link_of(card: ChangeCard) -> str:
    return f"/change-of-scope?project={card.project_id}&card={card.id}"


def _lines(lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal, Decimal]:
    out, hours, amount = [], Decimal(0), Decimal(0)
    for line in lines:
        qty, rate, hrs = (
            Decimal(str(line.get("quantity") or 0)),
            Decimal(str(line.get("rate") or 0)),
            Decimal(str(line.get("hours") or 0)),
        )
        value = (qty * rate).quantize(CENT, ROUND_HALF_UP)
        out.append(
            {
                "description": line["description"],
                "quantity": str(qty),
                "unit": line.get("unit"),
                "rate": str(rate),
                "hours": str(hrs),
                "amount": str(value),
            }
        )
        hours += hrs
        amount += value
    return out, hours.quantize(CENT), amount


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


async def get_card(db: AsyncSession, card_id: int) -> ChangeCard:
    card = await db.get(ChangeCard, card_id)
    if card is None:
        raise CardNotFound(str(card_id))
    return card


async def _anchor(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    """Check node and item belong to the project; derive the work anchor from the node (or the item's)."""
    node_id = values.get("node_id")
    if values.get("item_id"):
        item = await tree.get_item(db, values["item_id"], project_id)
        node_id = node_id or item.node_id
        values["node_id"] = node_id
    if node_id:
        await tree.get_node(db, node_id, project_id)
        try:
            values["work_anchor_id"] = (await tree.work_anchor_for(db, node_id)).id
        except tree.NoWorkAnchor:
            values["work_anchor_id"] = None
    elif "node_id" in values:
        values["work_anchor_id"] = None


async def create(db: AsyncSession, project: Project, values: dict[str, Any], actor_id: int) -> ChangeCard:
    values = dict(values)
    values.pop("project_id", None)
    await _anchor(db, project.id, values)
    lines, hours, amount = _lines(values.pop("lines", []))
    card = ChangeCard(
        project_id=project.id,
        code=await next_reference(db, "COS", project.id),
        lines=lines,
        estimated_hours=hours,
        estimated_amount=amount,
        created_by_id=actor_id,
        **values,
    )
    db.add(card)
    await db.flush()
    await record_transition(db, ENTITY, card.id, None, card.status, actor_id)
    await db.commit()
    await publish("change_of_scope.card.created", {"project_id": project.id, "card_id": card.id})
    return card


async def update(db: AsyncSession, card: ChangeCard, values: dict[str, Any]) -> ChangeCard:
    if card.status not in EDITABLE:
        raise CardError("Only a draft change card can be edited. Send it back to draft first.")
    if "node_id" in values or "item_id" in values:
        await _anchor(db, card.project_id, values)
    if values.get("lines") is not None:
        card.lines, card.estimated_hours, card.estimated_amount = _lines(values.pop("lines"))
    values.pop("lines", None)
    nullable = {"description", "node_id", "work_anchor_id", "item_id", "client_reference", "instructed_by", "instruction_date"}
    for key, value in values.items():
        if value is None and key not in nullable:
            continue
        setattr(card, key, value)
    await db.commit()
    return card


async def delete(db: AsyncSession, card: ChangeCard) -> None:
    if card.status not in (CardStatus.DRAFT, CardStatus.WITHDRAWN):
        raise CardError("Only a draft or withdrawn change card can be deleted.")
    await db.delete(card)
    await db.commit()


def required_permission(target: str) -> str:
    if target == CardStatus.ACKNOWLEDGED:
        return P.RESPOND.value
    if target in (CardStatus.APPROVED, CardStatus.REJECTED):
        return P.APPROVE.value
    return P.SUBMIT.value


async def transition(
    db: AsyncSession,
    card: ChangeCard,
    target: str,
    actor_id: int,
    note: str | None = None,
    approved_amount: Decimal | None = None,
    now: datetime | None = None,
) -> ChangeCard:
    assert_transition(FLOW, card.status, target)
    now = now or datetime.now(UTC)
    before = card.status
    if target == CardStatus.SUBMITTED and not card.title.strip():
        raise CardError("Give the card a title before submitting.")
    card.status = target
    await record_transition(db, ENTITY, card.id, before, target, actor_id, note)
    if target == CardStatus.SUBMITTED:
        card.submitted_at, card.expires_at, card.reminded_at = now, now + timedelta(days=EXPIRES_AFTER_DAYS), None
        await notify(
            db,
            await holders(db, P.APPROVE.value),
            Category.APPROVAL,
            f"{card.code} waits for the client: {card.title}",
            body=f"Estimate {card.estimated_amount:,.2f}, {card.estimated_hours} h. Expires in {EXPIRES_AFTER_DAYS} days.",
            link=link_of(card),
            entity=(ENTITY, card.id),
            actor_id=actor_id,
        )
    elif target == CardStatus.ACKNOWLEDGED:
        card.acknowledged_at = now
    elif target in (CardStatus.APPROVED, CardStatus.REJECTED):
        card.decided_at, card.decided_by_id, card.decision_note = now, actor_id, note
        card.expires_at = None
        if target == CardStatus.APPROVED:
            card.approved_amount = approved_amount if approved_amount is not None else card.estimated_amount
        await notify(
            db,
            [card.created_by_id] if card.created_by_id else [],
            Category.STATUS,
            f"{card.code} was {target}",
            body=note or card.title,
            link=link_of(card),
            entity=(ENTITY, card.id),
            actor_id=actor_id,
        )
    elif target in (CardStatus.DRAFT, CardStatus.WITHDRAWN):
        card.expires_at = None
        if target == CardStatus.DRAFT:
            card.decided_at, card.decided_by_id, card.decision_note, card.approved_amount = None, None, None, None
    await db.commit()
    await publish(f"change_of_scope.card.{target}", {"project_id": card.project_id, "card_id": card.id, "from": before})
    return card


async def convert(db: AsyncSession, card: ChangeCard, project: Project, actor_id: int) -> ChangeOrder:
    """An approved card becomes an approved change order (lines carried over), linked both ways."""
    if card.status != CardStatus.APPROVED:
        raise CardError("Only an approved change card can be converted.")
    if not await is_enabled(db, "change_orders", project.id):
        raise CardError("Change Orders is switched off for this project, so the card can't be converted.")
    today = date.today()
    co = ChangeOrder(
        project_id=project.id,
        code=await next_reference(db, "CO", project.id),
        title=f"{card.code} {card.title}"[:300],
        reason=REASON.get(Source(card.source), Reason.OTHER).value,
        description="\n".join(
            x
            for x in (
                f"Converted from change card {card.code}.",
                f"Client reference: {card.client_reference}" if card.client_reference else "",
                card.description or "",
            )
            if x
        ),
        requested_by_id=card.created_by_id,
        request_date=card.instruction_date or today,
        status=CoStatus.APPROVED.value,
        approver_id=actor_id,
        decided_on=today,
        decision_comment=f"Approved by the client on change card {card.code}.",
        submitted_at=card.submitted_at,
        created_by_id=actor_id,
    )
    db.add(co)
    await db.flush()
    lines = card.lines or [{"description": card.title, "quantity": "1", "rate": str(card.approved_amount or 0), "unit": "item"}]
    scale = Decimal(1)
    if card.approved_amount is not None and card.estimated_amount and card.approved_amount != card.estimated_amount:
        scale = Decimal(card.approved_amount) / Decimal(card.estimated_amount)
    for n, line in enumerate(lines):
        co_line = ChangeOrderLine(
            change_order_id=co.id,
            description=line["description"][:500],
            sort_order=n,
            unit=line.get("unit"),
            new_quantity=Decimal(str(line.get("quantity") or 0)),
            new_rate=(Decimal(str(line.get("rate") or 0)) * scale).quantize(CENT, ROUND_HALF_UP),
        )
        price(co_line)
        db.add(co_line)
    await record_transition(db, CO_ENTITY, co.id, None, CoStatus.APPROVED.value, actor_id, f"From change card {card.code}")
    card.change_order_id = co.id
    card.status = CardStatus.CONVERTED
    await record_transition(db, ENTITY, card.id, CardStatus.APPROVED, CardStatus.CONVERTED, actor_id, co.code)
    await db.commit()
    await publish("change_of_scope.card.converted", {"project_id": project.id, "card_id": card.id, "change_order_id": co.id})
    return co


async def expire_due(db: AsyncSession, now: datetime | None = None, project_id: int | None = None) -> dict[str, int]:
    """Remind once before, then expire, every card that has waited for the client too long."""
    now = now or datetime.now(UTC)
    where: list[Any] = [ChangeCard.status.in_([s.value for s in WAITING]), ChangeCard.expires_at.is_not(None)]
    if project_id is not None:
        where.append(ChangeCard.project_id == project_id)
    cards = list((await db.execute(select(ChangeCard).where(*where))).scalars())
    approvers = await holders(db, P.APPROVE.value) if cards else []
    expired = reminded = 0
    for card in cards:
        assert card.expires_at is not None
        recipients = [u for u in {card.created_by_id, *approvers} if u]
        if card.expires_at <= now:
            before = card.status
            card.status = CardStatus.EXPIRED
            card.expires_at = None
            await record_transition(
                db, ENTITY, card.id, before, CardStatus.EXPIRED, None, f"No client decision within {EXPIRES_AFTER_DAYS} days"
            )
            await notify(
                db,
                recipients,
                Category.STATUS,
                f"{card.code} expired without a client decision",
                body=f"{card.title}. Resubmit it to start another {EXPIRES_AFTER_DAYS} days.",
                link=link_of(card),
                entity=(ENTITY, card.id),
            )
            expired += 1
        elif card.reminded_at is None and card.expires_at - timedelta(days=REMIND_BEFORE_DAYS) <= now:
            days = max(1, (card.expires_at - now).days + (1 if (card.expires_at - now).seconds else 0))
            card.reminded_at = now
            await notify(
                db,
                recipients,
                Category.DUE,
                f"{card.code} expires in {days} day(s)",
                body=f"{card.title} still waits for the client's decision.",
                link=link_of(card),
                entity=(ENTITY, card.id),
            )
            reminded += 1
    await db.commit()
    return {"expired": expired, "reminded": reminded}


async def read(db: AsyncSession, cards: list[ChangeCard], now: datetime | None = None) -> list[dict[str, Any]]:
    if not cards:
        return []
    now = now or datetime.now(UTC)
    node_ids = {c.node_id for c in cards if c.node_id} | {c.work_anchor_id for c in cards if c.work_anchor_id}
    paths = (
        {n.id: n.display_path for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(node_ids)))).scalars()}
        if node_ids
        else {}
    )
    item_ids = {c.item_id for c in cards if c.item_id}
    tags = (
        {i.id: i.tag for i in (await db.execute(select(AssetItem).where(AssetItem.id.in_(item_ids)))).scalars()}
        if item_ids
        else {}
    )
    co_ids = {c.change_order_id for c in cards if c.change_order_id}
    cos = (
        {c.id: c.code for c in (await db.execute(select(ChangeOrder).where(ChangeOrder.id.in_(co_ids)))).scalars()}
        if co_ids
        else {}
    )
    user_ids = {c.created_by_id for c in cards if c.created_by_id}
    names = {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()} if user_ids else {}
    out = []
    for c in cards:
        out.append(
            {
                **{k: getattr(c, k) for k in ChangeCard.__table__.columns.keys()},  # noqa: SIM118
                "node_path": paths.get(c.node_id or 0),
                "work_anchor_path": paths.get(c.work_anchor_id or 0),
                "item_tag": tags.get(c.item_id or 0),
                "expires_in_days": (c.expires_at - now).days if c.expires_at else None,
                "change_order_code": cos.get(c.change_order_id or 0),
                "created_by_name": names.get(c.created_by_id or 0),
            }
        )
    return out


async def summary(db: AsyncSession, project_id: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cards = list((await db.execute(select(ChangeCard).where(ChangeCard.project_id == project_id))).scalars())
    by: dict[str, dict[str, Any]] = {s.value: {"count": 0, "amount": Decimal(0)} for s in CardStatus}
    for c in cards:
        by[c.status]["count"] += 1
        by[c.status]["amount"] += Decimal(
            c.approved_amount if c.approved_amount is not None and c.status in ("approved", "converted") else c.estimated_amount
        )
    soon = sum(
        1 for c in cards if c.status in WAITING and c.expires_at and c.expires_at - timedelta(days=REMIND_BEFORE_DAYS) <= now
    )
    return {
        "by_status": by,
        "expiring_soon": soon,
        "approved_amount": by["approved"]["amount"] + by["converted"]["amount"],
        "pending_amount": sum((by[s]["amount"] for s in WAITING), Decimal(0)),
    }


EXPORT_COLUMNS = [
    ("code", "No."),
    ("title", "Title"),
    ("status", "Status"),
    ("change_type", "Change type"),
    ("source", "Source"),
    ("node_path", "Location"),
    ("work_anchor_path", "Work anchor"),
    ("client_reference", "Client reference"),
    ("instructed_by", "Instructed by"),
    ("instruction_date", "Instruction date"),
    ("estimated_hours", "Est. hours"),
    ("estimated_amount", "Est. amount"),
    ("approved_amount", "Approved amount"),
    ("submitted_at", "Submitted"),
    ("expires_at", "Expires"),
    ("decided_at", "Decided"),
    ("decision_note", "Decision note"),
    ("change_order_code", "Change order"),
    ("created_by_name", "Raised by"),
]

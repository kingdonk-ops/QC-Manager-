from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..cvr.models import CostHead
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..role.models import RolePermission, UserRole
from ..user.models import User
from .constants import EDITABLE, FLOW, PENDING, CoStatus, CvrApply
from .models import ChangeOrder, ChangeOrderLine
from .permissions import ChangeOrderPermissionName
from .schemas import ChangeLogSummary, ChangeOrderDetail, ChangeOrderRead, CoLineRead, CoStatusTotal

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("99999999999999.99")
ENTITY = "change_order"


class ChangeOrderNotFoundError(ResourceNotFoundError):
    public_detail = "Change order not found."


class LineNotFoundError(ResourceNotFoundError):
    public_detail = "Change order line not found."


class NotEditableError(ValidationError):
    public_detail = "Only a draft change order can be changed. Send a rejected or withdrawn one back to draft first."


class NotDeletableError(ValidationError):
    public_detail = "An approved, submitted or under-review change order can't be deleted."


class CostHeadMismatchError(ValidationError):
    public_detail = "That cost head isn't in this change order's project."


class EmptyChangeOrderError(ValidationError):
    public_detail = "Add at least one line before submitting."


class AmountTooLargeError(ValidationError):
    public_detail = "That quantity and rate give an amount too large to store."


class UnknownUserError(ValidationError):
    public_detail = "The requester must be an existing user."


def link_of(co: ChangeOrder) -> str:
    return f"/change-orders?project={co.project_id}&co={co.id}"


def amount(quantity: Decimal, rate: Decimal) -> Decimal:
    value = (Decimal(quantity) * Decimal(rate)).quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(value) > MAX_AMOUNT:
        raise AmountTooLargeError(str(value))
    return value


def price(line: ChangeOrderLine) -> None:
    """Recompute a line's amounts and delta from its quantities and rates."""
    line.original_amount = amount(line.original_quantity, line.original_rate)
    line.new_amount = amount(line.new_quantity, line.new_rate)
    line.delta = line.new_amount - line.original_amount


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    clean = {i for i in ids if i}
    if not clean:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(clean)))).tuples().all())


async def _totals(db: AsyncSession, ids: list[int]) -> dict[int, tuple[Decimal, Decimal, Decimal, int]]:
    if not ids:
        return {}
    rows = await db.execute(
        select(
            ChangeOrderLine.change_order_id,
            func.coalesce(func.sum(ChangeOrderLine.original_amount), 0),
            func.coalesce(func.sum(ChangeOrderLine.new_amount), 0),
            func.coalesce(func.sum(ChangeOrderLine.delta), 0),
            func.count(),
        )
        .where(ChangeOrderLine.change_order_id.in_(ids))
        .group_by(ChangeOrderLine.change_order_id)
    )
    return {cid: (Decimal(o), Decimal(n), Decimal(d), c) for cid, o, n, d, c in rows.all()}


async def read_orders(db: AsyncSession, orders: list[ChangeOrder], currency: str, mode: str = "json") -> list[dict[str, Any]]:
    totals = await _totals(db, [o.id for o in orders])
    names = await user_names(db, {o.requested_by_id for o in orders} | {o.approver_id for o in orders})
    out = []
    for o in orders:
        orig, new, delta, count = totals.get(o.id, (Decimal(0), Decimal(0), Decimal(0), 0))
        read = ChangeOrderRead.model_validate(o).model_copy(
            update={
                "requested_by_name": names.get(o.requested_by_id) if o.requested_by_id else None,
                "approver_name": names.get(o.approver_id) if o.approver_id else None,
                "currency": currency,
                "original_total": orig,
                "new_total": new,
                "total_delta": delta,
                "line_count": count,
            }
        )
        out.append(read.model_dump(mode=mode))
    return out


async def lines_of(db: AsyncSession, co_id: int) -> list[ChangeOrderLine]:
    return list(
        (
            await db.execute(
                select(ChangeOrderLine)
                .where(ChangeOrderLine.change_order_id == co_id)
                .order_by(ChangeOrderLine.sort_order, ChangeOrderLine.id)
            )
        ).scalars()
    )


async def detail(db: AsyncSession, co: ChangeOrder, currency: str) -> dict[str, Any]:
    head = (await read_orders(db, [co], currency))[0]
    lines = [CoLineRead.model_validate(line).model_dump(mode="json") for line in await lines_of(db, co.id)]
    return ChangeOrderDetail(**head, lines=lines).model_dump(mode="json")


def filters(project_id: int, status: str | None, reason: str | None, search: str | None) -> list[Any]:
    where: list[Any] = [ChangeOrder.project_id == project_id]
    if status == "pending":
        where.append(ChangeOrder.status.in_([s.value for s in PENDING]))
    elif status:
        where.append(ChangeOrder.status == status)
    if reason:
        where.append(ChangeOrder.reason == reason)
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(ChangeOrder.title + " " + ChangeOrder.code).like(like),
                func.lower(func.coalesce(ChangeOrder.description, "")).like(like),
            )
        )
    return where


async def get_order(db: AsyncSession, co_id: int) -> ChangeOrder:
    co = await db.get(ChangeOrder, co_id)
    if co is None:
        raise ChangeOrderNotFoundError(f"Change order {co_id} not found")
    return co


async def get_line(db: AsyncSession, co: ChangeOrder, line_id: int) -> ChangeOrderLine:
    line = await db.get(ChangeOrderLine, line_id)
    if line is None or line.change_order_id != co.id:
        raise LineNotFoundError(f"Line {line_id} not found")
    return line


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}


def assert_editable(co: ChangeOrder) -> None:
    if co.status not in EDITABLE:
        raise NotEditableError(co.status)


async def _check_user(db: AsyncSession, user_id: int | None) -> None:
    if user_id is not None and await db.get(User, user_id) is None:
        raise UnknownUserError(str(user_id))


async def _check_cost_head(db: AsyncSession, project_id: int, head_id: int | None) -> None:
    if head_id is None:
        return
    head = await db.get(CostHead, head_id)
    if head is None or head.project_id != project_id:
        raise CostHeadMismatchError(str(head_id))


async def create(db: AsyncSession, values: dict[str, Any], actor_id: int) -> ChangeOrder:
    values = _plain(values)
    project_id = values.pop("project_id")
    values["requested_by_id"] = values.get("requested_by_id") or actor_id
    values["request_date"] = values.get("request_date") or date.today()
    await _check_user(db, values["requested_by_id"])
    co = ChangeOrder(project_id=project_id, code=await next_reference(db, "CO", project_id), created_by_id=actor_id, **values)
    db.add(co)
    await db.flush()
    await record_transition(db, ENTITY, co.id, None, co.status, actor_id)
    await db.commit()
    await publish("change_orders.change_order.created", {"project_id": project_id, "change_order_id": co.id})
    return co


async def update(db: AsyncSession, co: ChangeOrder, values: dict[str, Any]) -> None:
    assert_editable(co)
    if "requested_by_id" in values:
        await _check_user(db, values["requested_by_id"])
    for key, value in _plain(values).items():
        if value is None and key not in {"description", "requested_by_id", "request_date"}:
            continue
        setattr(co, key, value)
    await db.commit()


async def delete(db: AsyncSession, co: ChangeOrder) -> None:
    if co.status in {CoStatus.APPROVED, *PENDING}:
        raise NotDeletableError(co.status)
    await db.delete(co)
    await db.commit()


async def add_line(db: AsyncSession, co: ChangeOrder, values: dict[str, Any]) -> ChangeOrderLine:
    assert_editable(co)
    await _check_cost_head(db, co.project_id, values.get("cost_head_id"))
    line = ChangeOrderLine(change_order_id=co.id, **values)
    price(line)
    db.add(line)
    await db.commit()
    return line


async def update_line(db: AsyncSession, co: ChangeOrder, line: ChangeOrderLine, values: dict[str, Any]) -> None:
    assert_editable(co)
    if values.get("cost_head_id") is not None:
        await _check_cost_head(db, co.project_id, values["cost_head_id"])
    nullable = {"cost_head_id", "cost_code", "unit"}
    for key, value in values.items():
        if value is None and key not in nullable:
            continue
        setattr(line, key, value)
    price(line)
    await db.commit()


async def delete_line(db: AsyncSession, co: ChangeOrder, line: ChangeOrderLine) -> None:
    assert_editable(co)
    await db.delete(line)
    await db.commit()


async def approvers(db: AsyncSession) -> list[int]:
    """Every active user who holds ``change_orders.approve``, through a role or as a superuser."""
    name = ChangeOrderPermissionName.APPROVE.value
    by_role = select(UserRole.user_id).join(RolePermission, RolePermission.role_id == UserRole.role_id)
    rows = await db.execute(
        select(User.id, User.is_superuser).where(
            User.is_deleted.is_(False),
            or_(User.is_superuser.is_(True), User.id.in_(by_role.where(RolePermission.permission_name == name))),
        )
    )
    held = []
    for uid, superuser in rows.all():
        if name in await load_permissions(db, uid, is_superuser=superuser):
            held.append(uid)
    return held


async def _apply_to_cvr(db: AsyncSession, co: ChangeOrder) -> list[int]:
    """Move the linked cost heads' forecasts by each line's delta. Returns the heads touched."""
    if co.cvr_apply == CvrApply.NONE or co.applied_to_cvr_at is not None:
        return []
    if not await is_enabled(db, "cvr", co.project_id):
        return []
    deltas: dict[int, Decimal] = defaultdict(Decimal)
    for line in await lines_of(db, co.id):
        if line.cost_head_id:
            deltas[line.cost_head_id] += line.delta
    touched = []
    for head_id, delta in deltas.items():
        head = await db.get(CostHead, head_id)
        if head is None or head.project_id != co.project_id:
            continue
        if co.cvr_apply in (CvrApply.VALUE, CvrApply.BOTH):
            head.forecast_value += delta
        if co.cvr_apply in (CvrApply.COST, CvrApply.BOTH):
            head.forecast_cost += delta
        touched.append(head_id)
    co.applied_to_cvr_at = datetime.now(UTC)
    return touched


async def transition(db: AsyncSession, co: ChangeOrder, target: str, actor_id: int, comment: str | None) -> None:
    assert_transition(FLOW, co.status, target)
    if target == CoStatus.SUBMITTED and not await lines_of(db, co.id):
        raise EmptyChangeOrderError(co.code)
    before = co.status
    co.status = target
    await record_transition(db, ENTITY, co.id, before, target, actor_id, comment)
    total = (await _totals(db, [co.id])).get(co.id, (Decimal(0), Decimal(0), Decimal(0), 0))[2]
    touched: list[int] = []

    if target == CoStatus.SUBMITTED:
        co.submitted_at = datetime.now(UTC)
        await notify(
            db,
            await approvers(db),
            Category.APPROVAL,
            f"{co.code} needs approval: {co.title}",
            body=f"Change of {total:,.2f}, {co.time_impact_days} day(s).",
            link=link_of(co),
            entity=(ENTITY, co.id),
            actor_id=actor_id,
        )
    elif target in (CoStatus.APPROVED, CoStatus.REJECTED):
        co.approver_id = actor_id
        co.decided_on = date.today()
        co.decision_comment = comment
        if target == CoStatus.APPROVED:
            touched = await _apply_to_cvr(db, co)
        await notify(
            db,
            [u for u in {co.requested_by_id, co.created_by_id} if u],
            Category.STATUS,
            f"{co.code} was {target}",
            body=comment or co.title,
            link=link_of(co),
            entity=(ENTITY, co.id),
            actor_id=actor_id,
        )
    elif target == CoStatus.DRAFT:
        co.approver_id, co.decided_on, co.decision_comment = None, None, None
    await db.commit()
    await publish(
        f"change_orders.change_order.{target}",
        {
            "project_id": co.project_id,
            "change_order_id": co.id,
            "from": before,
            "total_delta": str(total),
            "cvr_apply": co.cvr_apply,
            "cost_heads_updated": touched,
        },
    )


async def summary(db: AsyncSession, project: Project) -> ChangeLogSummary:
    delta = func.coalesce(func.sum(ChangeOrderLine.delta), 0)
    per_order = (
        select(ChangeOrder.id, ChangeOrder.status, ChangeOrder.reason, ChangeOrder.time_impact_days, delta.label("delta"))
        .outerjoin(ChangeOrderLine, ChangeOrderLine.change_order_id == ChangeOrder.id)
        .where(ChangeOrder.project_id == project.id)
        .group_by(ChangeOrder.id)
    )
    buckets: dict[str, list[tuple[Decimal, int]]] = defaultdict(list)
    reasons: dict[str, list[tuple[Decimal, int]]] = defaultdict(list)
    for _, status, reason, days, d in (await db.execute(per_order)).all():
        bucket = "pending" if status in PENDING else status
        buckets[bucket].append((Decimal(d), days))
        if status == CoStatus.APPROVED:
            reasons[reason].append((Decimal(d), days))

    def total(items: list[tuple[Decimal, int]]) -> CoStatusTotal:
        return CoStatusTotal(
            count=len(items), delta=sum((d for d, _ in items), Decimal(0)), time_impact_days=sum(t for _, t in items)
        )

    return ChangeLogSummary(
        project_id=project.id,
        currency=project.currency,
        approved=total(buckets["approved"]),
        pending=total(buckets["pending"]),
        rejected=total(buckets["rejected"]),
        draft=total(buckets["draft"]),
        withdrawn=total(buckets["withdrawn"]),
        by_reason={r: total(v) for r, v in reasons.items()},
    )


def _money(value: Any) -> str:
    return f"{Decimal(value):,.2f}"


async def pdf(db: AsyncSession, co: ChangeOrder, project: Project) -> bytes:
    data = await detail(db, co, project.currency)
    doc = Document(
        title=f"Change Order {co.code}",
        subtitle=f"{project.name} · {project.code}",
        footer=f"{project.code} {co.code}",
        landscape=True,
    )
    doc.fields(
        [
            ("Title", co.title),
            ("Reason", co.reason.replace("_", " ").capitalize()),
            ("Status", co.status.replace("_", " ").capitalize()),
            ("Requested by", data["requested_by_name"] or ""),
            ("Request date", co.request_date.isoformat() if co.request_date else ""),
            ("Time impact", f"{co.time_impact_days} day(s)"),
            ("Currency", project.currency),
        ]
    )
    if co.description:
        doc.heading("Description")
        doc.paragraph(co.description)
    doc.heading("Lines")
    rows = [
        [
            line["cost_code"] or "",
            line["description"],
            line["unit"] or "",
            line["original_quantity"],
            _money(line["original_rate"]),
            _money(line["original_amount"]),
            line["new_quantity"],
            _money(line["new_rate"]),
            _money(line["new_amount"]),
            _money(line["delta"]),
        ]
        for line in data["lines"]
    ]
    rows.append(
        [
            "",
            "Total",
            "",
            "",
            "",
            _money(data["original_total"]),
            "",
            "",
            _money(data["new_total"]),
            _money(data["total_delta"]),
        ]
    )
    doc.table(
        [
            "Code",
            "Description",
            "Unit",
            "Orig. qty",
            "Orig. rate",
            "Orig. amount",
            "New qty",
            "New rate",
            "New amount",
            "Delta",
        ],
        rows,
        widths=[0.07, 0.25, 0.05, 0.08, 0.09, 0.1, 0.08, 0.09, 0.1, 0.09],
        numeric={3, 4, 5, 6, 7, 8, 9},
    )
    if co.status in (CoStatus.APPROVED, CoStatus.REJECTED):
        doc.heading("Decision")
        doc.fields(
            [
                ("Decision", co.status.capitalize()),
                ("By", data["approver_name"] or ""),
                ("On", co.decided_on.isoformat() if co.decided_on else ""),
                ("Comment", co.decision_comment or ""),
            ]
        )
    return render_pdf(doc)


EXPORT_COLUMNS = [
    ("code", "Code"),
    ("title", "Title"),
    ("reason", "Reason"),
    ("status", "Status"),
    ("requested_by_name", "Requested by"),
    ("request_date", "Request date"),
    ("time_impact_days", "Time impact (days)"),
    ("original_total", "Original total"),
    ("new_total", "New total"),
    ("total_delta", "Delta"),
    ("approver_name", "Approver"),
    ("decided_on", "Decided on"),
    ("decision_comment", "Decision comment"),
]

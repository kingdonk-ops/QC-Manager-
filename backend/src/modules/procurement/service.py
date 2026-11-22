from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.mail import Attachment, Mail, deliver
from ...infrastructure.modules import publish
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..contacts.models import Company, Contact
from ..contacts.service import contact_emails, full_name
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..user.models import User
from .constants import AWAITING, COMMITTED, FLOW, RECEIPT_ENTITY, RECEIVABLE, PoStatus
from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from .schemas import (
    OutstandingDelivery,
    PoLineRead,
    PoSupplier,
    ProcurementSummary,
    PurchaseOrderDetail,
    PurchaseOrderRead,
    ReceiptLineRead,
    ReceiptPhoto,
    ReceiptRead,
)

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("99999999999999.99")
ENTITY = "purchase_order"


class PurchaseOrderNotFoundError(ResourceNotFoundError):
    public_detail = "Purchase order not found."


class LineNotFoundError(ResourceNotFoundError):
    public_detail = "Purchase order line not found."


class NotEditableError(ValidationError):
    public_detail = "Only a draft purchase order can be changed."


class NotDeletableError(ValidationError):
    public_detail = "Only a draft or cancelled purchase order can be deleted."


class UnknownSupplierError(ValidationError):
    public_detail = "The supplier must be a company or contact in the Contacts directory."


class UnknownUserError(ValidationError):
    public_detail = "The person who received the goods must be an existing user."


class NoRecipientError(ValidationError):
    public_detail = "The supplier has no email address. Add one to the contact or company, or enter one."


class NothingToSendError(ValidationError):
    public_detail = "Add at least one line before sending."


class NotSendableError(ValidationError):
    public_detail = "Only a draft, sent or partially received purchase order can be sent."


class NotReceivableError(ValidationError):
    public_detail = "Goods can be received only against a sent purchase order."


class ForeignLineError(ValidationError):
    public_detail = "Every receipt line must be a line of this purchase order."


class ManualStatusError(ValidationError):
    public_detail = "Set closed or cancelled here; sending and goods receipts set the other statuses."


class ApprovalNeededError(PermissionDeniedError):
    public_detail = "This purchase order is over its approval threshold: someone who can approve it must send it."


class AmountTooLargeError(ValidationError):
    public_detail = "That quantity and price give an amount too large to store."


def link_of(po: PurchaseOrder) -> str:
    return f"/procurement?project={po.project_id}&po={po.id}"


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def price(line: PurchaseOrderLine) -> None:
    line.amount = _round(Decimal(line.quantity) * Decimal(line.unit_price))
    line.tax = _round(line.amount * Decimal(line.tax_rate) / 100)
    if line.amount + line.tax > MAX_AMOUNT:
        raise AmountTooLargeError(str(line.amount))


def _qty(value: Decimal) -> str:
    return f"{Decimal(value).normalize():f}"


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}


def is_overdue(po: PurchaseOrder, today: date | None = None) -> bool:
    return bool(po.required_by and po.required_by < (today or date.today()) and po.status in AWAITING)


# --- reading --------------------------------------------------------------------------------------------

OUTSTANDING = func.greatest(PurchaseOrderLine.quantity - PurchaseOrderLine.received_quantity, 0)


async def _totals(db: AsyncSession, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    rows = await db.execute(
        select(
            PurchaseOrderLine.purchase_order_id,
            func.coalesce(func.sum(PurchaseOrderLine.amount), 0),
            func.coalesce(func.sum(PurchaseOrderLine.tax), 0),
            func.coalesce(func.sum(func.round(PurchaseOrderLine.received_quantity * PurchaseOrderLine.unit_price, 2)), 0),
            func.coalesce(func.sum(func.round(OUTSTANDING * PurchaseOrderLine.unit_price, 2)), 0),
            func.count(),
            func.count().filter(OUTSTANDING > 0),
        )
        .where(PurchaseOrderLine.purchase_order_id.in_(ids))
        .group_by(PurchaseOrderLine.purchase_order_id)
    )
    return {
        pid: {
            "net_total": Decimal(net),
            "tax_total": Decimal(tax),
            "gross_total": Decimal(net) + Decimal(tax),
            "received_net": Decimal(received),
            "outstanding_net": Decimal(outstanding),
            "line_count": count,
            "lines_outstanding": open_lines,
        }
        for pid, net, tax, received, outstanding, count, open_lines in rows.all()
    }


async def supplier_names(db: AsyncSession, pos: list[PurchaseOrder]) -> dict[int, str]:
    companies = {p.supplier_company_id for p in pos if p.supplier_company_id}
    contacts = {p.supplier_contact_id for p in pos if p.supplier_contact_id}
    company_names = (
        dict((await db.execute(select(Company.id, Company.name).where(Company.id.in_(companies)))).tuples().all())
        if companies
        else {}
    )
    contact_rows = (
        {c.id: full_name(c) for c in (await db.execute(select(Contact).where(Contact.id.in_(contacts)))).scalars()}
        if contacts
        else {}
    )
    out = {}
    for p in pos:
        name = company_names.get(p.supplier_company_id or 0) or contact_rows.get(p.supplier_contact_id or 0)
        if name:
            out[p.id] = name
    return out


async def read_orders(db: AsyncSession, pos: list[PurchaseOrder], mode: str = "json") -> list[dict[str, Any]]:
    totals = await _totals(db, [p.id for p in pos])
    names = await supplier_names(db, pos)
    today = date.today()
    out = []
    for p in pos:
        t = totals.get(p.id, {})
        net = t.get("net_total", Decimal(0))
        gross = t.get("gross_total", Decimal(0))
        received = t.get("received_net", Decimal(0))
        read = PurchaseOrderRead.model_validate(p).model_copy(
            update={
                "supplier_name": names.get(p.id),
                "net_total": net,
                "tax_total": t.get("tax_total", Decimal(0)),
                "gross_total": gross,
                "received_net": received,
                "outstanding_net": t.get("outstanding_net", Decimal(0)),
                "received_pct": round(float(received / net * 100), 1) if net else 0.0,
                "needs_approval": p.approval_threshold is not None and gross > p.approval_threshold,
                "overdue": is_overdue(p, today),
                "line_count": t.get("line_count", 0),
            }
        )
        out.append(read.model_dump(mode=mode))
    return out


async def lines_of(db: AsyncSession, po_id: int) -> list[PurchaseOrderLine]:
    return list(
        (
            await db.execute(
                select(PurchaseOrderLine)
                .where(PurchaseOrderLine.purchase_order_id == po_id)
                .order_by(PurchaseOrderLine.sort_order, PurchaseOrderLine.id)
            )
        ).scalars()
    )


def read_line(line: PurchaseOrderLine) -> PoLineRead:
    return PoLineRead.model_validate(line).model_copy(
        update={"outstanding_quantity": max(Decimal(line.quantity) - Decimal(line.received_quantity), Decimal(0))}
    )


async def supplier_of(db: AsyncSession, po: PurchaseOrder) -> PoSupplier:
    company = await db.get(Company, po.supplier_company_id) if po.supplier_company_id else None
    contact = await db.get(Contact, po.supplier_contact_id) if po.supplier_contact_id else None
    return PoSupplier(
        company_id=company.id if company else None,
        company_name=company.name if company else None,
        address=company.address if company else None,
        email=company.email if company else None,
        phone=company.phone if company else None,
        tax_id=company.tax_id if company else None,
        banking=dict(company.banking or {}) if company else {},
        contact_id=contact.id if contact else None,
        contact_name=full_name(contact) if contact else None,
        contact_email=contact.email if contact else None,
        contact_phone=(contact.phone or contact.mobile) if contact else None,
    )


async def receipts_of(db: AsyncSession, po: PurchaseOrder) -> list[ReceiptRead]:
    receipts = list(
        (
            await db.execute(
                select(GoodsReceipt)
                .where(GoodsReceipt.purchase_order_id == po.id)
                .order_by(GoodsReceipt.received_date, GoodsReceipt.id)
            )
        ).scalars()
    )
    if not receipts:
        return []
    ids = [r.id for r in receipts]
    lines: dict[int, list[ReceiptLineRead]] = defaultdict(list)
    rows = await db.execute(
        select(
            GoodsReceiptLine.receipt_id,
            GoodsReceiptLine.line_id,
            PurchaseOrderLine.description,
            PurchaseOrderLine.unit,
            GoodsReceiptLine.quantity,
        )
        .join(PurchaseOrderLine, PurchaseOrderLine.id == GoodsReceiptLine.line_id)
        .where(GoodsReceiptLine.receipt_id.in_(ids))
        .order_by(GoodsReceiptLine.id)
    )
    for rid, lid, desc, unit, qty in rows.all():
        lines[rid].append(ReceiptLineRead(line_id=lid, description=desc, unit=unit, quantity=qty))
    photos: dict[int, list[ReceiptPhoto]] = defaultdict(list)
    files = await db.execute(
        select(StoredFile.entity_id, StoredFile.id, StoredFile.name, StoredFile.content_type)
        .where(StoredFile.entity_type == RECEIPT_ENTITY, StoredFile.entity_id.in_(ids), StoredFile.is_latest.is_(True))
        .order_by(StoredFile.id)
    )
    for rid, fid, name, ctype in files.all():
        if rid is not None:
            photos[rid].append(ReceiptPhoto(id=fid, name=name, content_type=ctype))
    users = {r.received_by_id for r in receipts if r.received_by_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(users)))).tuples().all()) if users else {}
    return [
        ReceiptRead(
            id=r.id,
            purchase_order_id=r.purchase_order_id,
            code=r.code,
            received_date=r.received_date,
            received_by_id=r.received_by_id,
            received_by_name=names.get(r.received_by_id) if r.received_by_id else None,
            quality_notes=r.quality_notes,
            lines=lines[r.id],
            photos=photos[r.id],
            created_at=r.created_at,
        )
        for r in receipts
    ]


async def detail(db: AsyncSession, po: PurchaseOrder) -> dict[str, Any]:
    head = (await read_orders(db, [po], mode="python"))[0]
    return PurchaseOrderDetail(
        **head,
        supplier=await supplier_of(db, po),
        lines=[read_line(line) for line in await lines_of(db, po.id)],
        receipts=await receipts_of(db, po),
    ).model_dump(mode="json")


def filters(
    project_id: int, status: str | None, supplier_company_id: int | None, overdue: bool, search: str | None
) -> list[Any]:
    where: list[Any] = [PurchaseOrder.project_id == project_id]
    if status == "open":
        where.append(PurchaseOrder.status.in_([s.value for s in AWAITING]))
    elif status:
        where.append(PurchaseOrder.status == status)
    if supplier_company_id:
        where.append(PurchaseOrder.supplier_company_id == supplier_company_id)
    if overdue:
        where += [PurchaseOrder.required_by < date.today(), PurchaseOrder.status.in_([s.value for s in AWAITING])]
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(PurchaseOrder.code + " " + func.coalesce(PurchaseOrder.title, "")).like(like),
                PurchaseOrder.supplier_company_id.in_(select(Company.id).where(func.lower(Company.name).like(like))),
            )
        )
    return where


# --- writing --------------------------------------------------------------------------------------------


async def get_order(db: AsyncSession, po_id: int) -> PurchaseOrder:
    po = await db.get(PurchaseOrder, po_id)
    if po is None:
        raise PurchaseOrderNotFoundError(f"Purchase order {po_id} not found")
    return po


async def get_line(db: AsyncSession, po: PurchaseOrder, line_id: int) -> PurchaseOrderLine:
    line = await db.get(PurchaseOrderLine, line_id)
    if line is None or line.purchase_order_id != po.id:
        raise LineNotFoundError(f"Line {line_id} not found")
    return line


def assert_editable(po: PurchaseOrder) -> None:
    if po.status != PoStatus.DRAFT:
        raise NotEditableError(po.status)


async def _resolve_supplier(db: AsyncSession, values: dict[str, Any]) -> None:
    """Check the supplier ids, and take the company from the contact when only a contact is given."""
    if values.get("supplier_company_id") and await db.get(Company, values["supplier_company_id"]) is None:
        raise UnknownSupplierError(str(values["supplier_company_id"]))
    if values.get("supplier_contact_id"):
        contact = await db.get(Contact, values["supplier_contact_id"])
        if contact is None:
            raise UnknownSupplierError(str(values["supplier_contact_id"]))
        if not values.get("supplier_company_id") and contact.company_id:
            values["supplier_company_id"] = contact.company_id


async def create(db: AsyncSession, project: Project, values: dict[str, Any], actor_id: int) -> PurchaseOrder:
    values = _plain(values)
    values.pop("project_id")
    await _resolve_supplier(db, values)
    values["currency"] = values.get("currency") or project.currency
    values["order_date"] = values.get("order_date") or date.today()
    po = PurchaseOrder(project_id=project.id, code=await next_reference(db, "PO", project.id), created_by_id=actor_id, **values)
    db.add(po)
    await db.flush()
    await record_transition(db, ENTITY, po.id, None, po.status, actor_id)
    await db.commit()
    await publish("procurement.purchase_order.created", {"project_id": project.id, "purchase_order_id": po.id})
    return po


async def update(db: AsyncSession, po: PurchaseOrder, values: dict[str, Any]) -> None:
    assert_editable(po)
    values = _plain(values)
    if "supplier_contact_id" in values or "supplier_company_id" in values:
        merged = {
            "supplier_company_id": values.get("supplier_company_id", po.supplier_company_id),
            "supplier_contact_id": values.get("supplier_contact_id", po.supplier_contact_id),
        }
        if "supplier_company_id" not in values and "supplier_contact_id" in values:
            merged["supplier_company_id"] = None
        await _resolve_supplier(db, merged)
        if "supplier_company_id" not in values and merged["supplier_company_id"] is None:
            merged["supplier_company_id"] = po.supplier_company_id
        values.update(merged)
    for key, value in values.items():
        if value is None and key in {"currency", "order_date"}:
            continue
        setattr(po, key, value)
    await db.commit()


async def delete(db: AsyncSession, po: PurchaseOrder) -> None:
    if po.status not in (PoStatus.DRAFT, PoStatus.CANCELLED):
        raise NotDeletableError(po.status)
    await db.delete(po)
    await db.commit()


async def add_line(db: AsyncSession, po: PurchaseOrder, values: dict[str, Any]) -> PurchaseOrderLine:
    assert_editable(po)
    line = PurchaseOrderLine(purchase_order_id=po.id, **values)
    price(line)
    db.add(line)
    await db.commit()
    return line


async def update_line(db: AsyncSession, po: PurchaseOrder, line: PurchaseOrderLine, values: dict[str, Any]) -> None:
    assert_editable(po)
    for key, value in values.items():
        if value is None and key not in {"unit", "cost_code", "cost_head_id"}:
            continue
        setattr(line, key, value)
    price(line)
    await db.commit()


async def delete_line(db: AsyncSession, po: PurchaseOrder, line: PurchaseOrderLine) -> None:
    assert_editable(po)
    await db.delete(line)
    await db.commit()


async def _set_status(db: AsyncSession, po: PurchaseOrder, target: str, actor_id: int, note: str | None = None) -> None:
    assert_transition(FLOW, po.status, target)
    before = po.status
    po.status = target
    await record_transition(db, ENTITY, po.id, before, target, actor_id, note)


async def change_status(db: AsyncSession, po: PurchaseOrder, target: str, actor_id: int, note: str | None) -> None:
    if target not in {PoStatus.CLOSED, PoStatus.CANCELLED}:
        raise ManualStatusError(target)
    await _set_status(db, po, target, actor_id, note)
    await db.commit()
    await publish(f"procurement.purchase_order.{target}", {"project_id": po.project_id, "purchase_order_id": po.id})


# --- sending --------------------------------------------------------------------------------------------


def _money(value: Any) -> str:
    return f"{Decimal(value):,.2f}"


async def pdf(db: AsyncSession, po: PurchaseOrder, project: Project) -> bytes:
    data = await detail(db, po)
    supplier = data["supplier"]
    doc = Document(
        title=f"Purchase Order {po.code}", subtitle=f"{project.name} · {project.code}", footer=f"{project.code} {po.code}"
    )
    doc.fields(
        [
            ("PoSupplier", supplier["company_name"] or supplier["contact_name"] or ""),
            ("PoSupplier address", supplier["address"] or ""),
            ("Attention", " · ".join(x for x in (supplier["contact_name"], supplier["contact_email"]) if x)),
            ("Order date", po.order_date.isoformat() if po.order_date else ""),
            ("Required by", po.required_by.isoformat() if po.required_by else ""),
            ("Deliver to", po.delivery_address or project.location or ""),
            ("Currency", po.currency),
        ]
        + ([("Reference", po.title)] if po.title else [])
    )
    doc.heading("Items")
    rows = [
        [
            str(i),
            line["description"] + (f"\n{line['cost_code']}" if line["cost_code"] else ""),
            line["unit"] or "",
            line["quantity"],
            _money(line["unit_price"]),
            f"{Decimal(line['tax_rate']):g}%",
            _money(line["amount"]),
        ]
        for i, line in enumerate(data["lines"], start=1)
    ]
    doc.table(
        ["#", "Description", "Unit", "Qty", "Unit price", "Tax", "Amount"],
        rows,
        widths=[0.05, 0.43, 0.08, 0.1, 0.13, 0.08, 0.13],
        numeric={3, 4, 5, 6},
    )
    doc.fields(
        [
            ("Net", f"{po.currency} {_money(data['net_total'])}"),
            ("Tax", f"{po.currency} {_money(data['tax_total'])}"),
            ("Total", f"{po.currency} {_money(data['gross_total'])}"),
        ]
    )
    if po.terms:
        doc.heading("Terms")
        doc.paragraph(po.terms)
    if po.notes:
        doc.heading("Notes")
        doc.paragraph(po.notes)
    doc.paragraph(f"Please quote {po.code} on all delivery dockets and invoices.")
    return render_pdf(doc)


async def recipients(db: AsyncSession, po: PurchaseOrder, explicit: list[str]) -> list[str]:
    if explicit:
        return list(dict.fromkeys(str(e) for e in explicit))
    if po.supplier_contact_id:
        found = await contact_emails(db, [po.supplier_contact_id])
        if po.supplier_contact_id in found:
            return [found[po.supplier_contact_id]]
    if po.supplier_company_id:
        company = await db.get(Company, po.supplier_company_id)
        if company and company.email:
            return [company.email]
    return []


async def send(
    db: AsyncSession,
    po: PurchaseOrder,
    project: Project,
    to: list[str],
    message: str | None,
    actor: dict[str, Any],
    can_approve: bool,
) -> list[str]:
    """Render the PO, email it to the supplier, and mark it sent. Returns the addresses it went to.

    A PO whose gross total is over its approval threshold goes only from someone who may approve it.
    """
    if po.status not in (PoStatus.DRAFT, *AWAITING):
        raise NotSendableError(po.status)
    if not await lines_of(db, po.id):
        raise NothingToSendError(po.code)
    totals = (await _totals(db, [po.id]))[po.id]
    over_threshold = po.approval_threshold is not None and totals["gross_total"] > po.approval_threshold
    if over_threshold and not can_approve:
        raise ApprovalNeededError(po.code)
    addresses = await recipients(db, po, to)
    if not addresses:
        raise NoRecipientError(po.code)
    body = await pdf(db, po, project)
    text = "\n\n".join(
        part
        for part in (
            message,
            f"Please find attached purchase order {po.code} for {project.name} ({project.code}), "
            f"total {po.currency} {_money(totals['gross_total'])}"
            + (f", required by {po.required_by:%d %b %Y}" if po.required_by else "")
            + ".",
            f"Please quote {po.code} on all delivery dockets and invoices.",
            actor.get("name"),
        )
        if part
    )
    await deliver(
        Mail(
            to=addresses,
            subject=f"Purchase order {po.code} — {project.name}",
            text=text,
            attachments=[Attachment(f"{po.code}.pdf", body, "application/pdf")],
        )
    )
    if po.status == PoStatus.DRAFT:
        await _set_status(db, po, PoStatus.SENT, actor["id"], f"Sent to {', '.join(addresses)}")
    if over_threshold:
        po.approved_by_id = actor["id"]
    po.sent_at = datetime.now(UTC)
    po.sent_to = ", ".join(addresses)[:1000]
    await db.commit()
    await publish("procurement.purchase_order.sent", {"project_id": po.project_id, "purchase_order_id": po.id})
    return addresses


# --- receiving ------------------------------------------------------------------------------------------


async def receive(db: AsyncSession, po: PurchaseOrder, values: dict[str, Any], actor_id: int) -> tuple[GoodsReceipt, list[str]]:
    """Record a delivery against the PO's lines; the PO's status follows. Over-receipt is kept, with a warning."""
    if po.status not in RECEIVABLE:
        raise NotReceivableError(po.status)
    received_by = values.get("received_by_id") or actor_id
    if await db.get(User, received_by) is None:
        raise UnknownUserError(str(received_by))
    lines = {line.id: line for line in await lines_of(db, po.id)}
    wanted: dict[int, Decimal] = defaultdict(Decimal)
    for item in values["lines"]:
        if item["line_id"] not in lines:
            raise ForeignLineError(str(item["line_id"]))
        wanted[item["line_id"]] += Decimal(item["quantity"])

    receipt = GoodsReceipt(
        purchase_order_id=po.id,
        code=await next_reference(db, "GRN", po.project_id),
        received_date=values.get("received_date") or date.today(),
        received_by_id=received_by,
        quality_notes=values.get("quality_notes"),
        created_by_id=actor_id,
    )
    db.add(receipt)
    await db.flush()
    warnings = []
    for line_id, qty in wanted.items():
        line = lines[line_id]
        db.add(GoodsReceiptLine(receipt_id=receipt.id, line_id=line_id, quantity=qty))
        line.received_quantity = Decimal(line.received_quantity) + qty
        if line.received_quantity > line.quantity:
            over = line.received_quantity - Decimal(line.quantity)
            warnings.append(
                f"{line.description}: {_qty(line.received_quantity)} received against {_qty(line.quantity)} ordered "
                f"({_qty(over)} over)"
            )

    complete = all(Decimal(line.received_quantity) >= Decimal(line.quantity) for line in lines.values())
    target = PoStatus.FULLY_RECEIVED if complete else PoStatus.PARTIALLY_RECEIVED
    if po.status != target:
        await _set_status(db, po, target, actor_id, f"Goods receipt {receipt.code}")
    if po.created_by_id:
        await notify(
            db,
            [po.created_by_id],
            Category.STATUS,
            f"{po.code}: goods received ({receipt.code})",
            body=f"Now {target.replace('_', ' ')}." + (f" {len(warnings)} line(s) over-received." if warnings else ""),
            link=link_of(po),
            entity=(ENTITY, po.id),
            actor_id=actor_id,
        )
    await db.commit()
    await publish(
        "procurement.goods_receipt.created",
        {"project_id": po.project_id, "purchase_order_id": po.id, "receipt_id": receipt.id, "status": target},
    )
    return receipt, warnings


# --- reporting ------------------------------------------------------------------------------------------


async def summary(db: AsyncSession, project: Project) -> ProcurementSummary:
    pos = list((await db.execute(select(PurchaseOrder).where(PurchaseOrder.project_id == project.id))).scalars())
    totals = await _totals(db, [p.id for p in pos])
    names = await supplier_names(db, pos)
    today = date.today()
    zero = Decimal(0)
    by_status: dict[str, int] = {s.value: 0 for s in PoStatus}
    committed_net = committed_gross = received = outstanding = draft = zero
    deliveries = []
    for p in pos:
        t = totals.get(p.id, {})
        by_status[p.status] = by_status.get(p.status, 0) + 1
        if p.status in COMMITTED:
            committed_net += t.get("net_total", zero)
            committed_gross += t.get("gross_total", zero)
            received += t.get("received_net", zero)
        if p.status == PoStatus.DRAFT:
            draft += t.get("net_total", zero)
        if p.status in AWAITING:
            outstanding += t.get("outstanding_net", zero)
            late = is_overdue(p, today)
            deliveries.append(
                OutstandingDelivery(
                    purchase_order_id=p.id,
                    code=p.code,
                    title=p.title,
                    supplier_name=names.get(p.id),
                    status=p.status,
                    required_by=p.required_by,
                    overdue=late,
                    days_overdue=(today - p.required_by).days if late and p.required_by else 0,
                    outstanding_net=t.get("outstanding_net", zero),
                    lines_outstanding=t.get("lines_outstanding", 0),
                )
            )
    deliveries.sort(key=lambda d: (d.required_by is None, d.required_by or today, d.code))
    return ProcurementSummary(
        project_id=project.id,
        currency=project.currency,
        committed_net=committed_net,
        committed_gross=committed_gross,
        received_net=received,
        outstanding_net=outstanding,
        draft_net=draft,
        by_status=by_status,
        overdue_count=sum(1 for d in deliveries if d.overdue),
        outstanding=deliveries,
    )


EXPORT_COLUMNS = [
    ("code", "PO"),
    ("title", "Reference"),
    ("supplier_name", "PoSupplier"),
    ("status", "Status"),
    ("order_date", "Order date"),
    ("required_by", "Required by"),
    ("currency", "Currency"),
    ("net_total", "Net"),
    ("tax_total", "Tax"),
    ("gross_total", "Gross"),
    ("received_net", "Received (net)"),
    ("outstanding_net", "Outstanding (net)"),
    ("overdue", "Overdue"),
    ("sent_to", "Sent to"),
]

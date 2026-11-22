"""Receipts, heats and certificates, PMI, issue to work, holds, traceability both ways.

Cross-module services:

- ``certificates_for(db, node_ids)``: the certificate appendix of an MDR for those nodes.
- ``unverified_heats_for_items(db, item_ids)``: heats issued to the items without a verified certificate.
- ``readiness_warnings(db, node_ids)``: client-supplied material late for its work anchor (TD-593).
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.models import AssetItem, AssetNode
from ..calibration.service import assert_calibrated
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..procurement.models import GoodsReceipt, PurchaseOrder
from .constants import (
    CERT_ENTITY,
    HEAT_ENTITY,
    HOLD_ENTITY,
    RECEIPT_ENTITY,
    RECEIPT_FLOW,
    HeatStatus,
    HoldStatus,
    PmiResult,
    SuppliedBy,
    VerificationStatus,
)
from .models import Heat, MaterialHold, MaterialIssue, MaterialReceipt, MillCertificate, PmiTest
from .schemas import HeatRead, MaterialHoldRead, MaterialIssueRead, MillCertificateRead, PmiRead


class NotFound(ResourceNotFoundError):
    public_detail = "Not found."


class DuplicateHeat(ResourceExistsError):
    public_detail = "That heat number and grade are already on this project."


class MaterialsRuleError(ValidationError):
    public_detail = "That breaks a materials rule."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


async def get(db: AsyncSession, model: Any, row_id: int) -> Any:
    row = await db.get(model, row_id)
    if row is None:
        raise NotFound(f"{model.__tablename__} {row_id}")
    return row


async def check_file(db: AsyncSession, file_id: int | None, project_id: int) -> None:
    if file_id is None:
        return
    f = await db.get(StoredFile, file_id)
    if f is None or (f.project_id is not None and f.project_id != project_id):
        raise MaterialsRuleError("That file isn't in this project's files.")


# --- receipts ----------------------------------------------------------------------------------------


async def _check_procurement(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    po_id, gr_id = values.get("purchase_order_id"), values.get("goods_receipt_id")
    if not po_id and not gr_id:
        return
    if not await is_enabled(db, "procurement", project_id):
        raise MaterialsRuleError("Procurement is switched off for this project; leave the PO and goods receipt empty.")
    if po_id:
        po = await db.get(PurchaseOrder, po_id)
        if po is None or po.project_id != project_id:
            raise MaterialsRuleError("That purchase order is not on this project.")
    if gr_id:
        gr = await db.get(GoodsReceipt, gr_id)
        if gr is None:
            raise MaterialsRuleError("That goods receipt doesn't exist.")
        if po_id and gr.purchase_order_id != po_id:
            raise MaterialsRuleError("That goods receipt belongs to another purchase order.")
        if not po_id:
            po = await db.get(PurchaseOrder, gr.purchase_order_id)
            if po is None or po.project_id != project_id:
                raise MaterialsRuleError("That goods receipt is not on this project.")
            values["purchase_order_id"] = po.id


async def create_receipt(db: AsyncSession, values: dict[str, Any], user_id: int) -> MaterialReceipt:
    await _check_procurement(db, values["project_id"], values)
    r = MaterialReceipt(code=await next_reference(db, "MRIR", values["project_id"]), created_by_id=user_id, **values)
    db.add(r)
    await db.flush()
    await record_transition(db, RECEIPT_ENTITY, r.id, None, r.status, user_id, None)
    return r


async def update_receipt(db: AsyncSession, r: MaterialReceipt, changes: dict[str, Any]) -> None:
    merged = {"purchase_order_id": r.purchase_order_id, "goods_receipt_id": r.goods_receipt_id, **changes}
    await _check_procurement(db, r.project_id, merged)
    for k, v in changes.items():
        setattr(r, k, v)
    if "purchase_order_id" in merged:
        r.purchase_order_id = merged["purchase_order_id"]
    await db.flush()


async def change_receipt_status(db: AsyncSession, r: MaterialReceipt, target: str, note: str | None, user_id: int) -> None:
    if target == r.status:
        return
    assert_transition(RECEIPT_FLOW, r.status, target)
    await record_transition(db, RECEIPT_ENTITY, r.id, r.status, target, user_id, note)
    r.status = target
    r.inspected_by_id = user_id
    await db.flush()


# --- heats -------------------------------------------------------------------------------------------


async def _check_anchor(db: AsyncSession, node_id: int | None, project_id: int) -> None:
    if node_id is None:
        return
    node = await tree.get_node(db, node_id, project_id)
    anchor = await tree.work_anchor_for(db, node.id)
    if anchor.id != node.id:
        raise MaterialsRuleError(f"Plan the material for the work anchor {anchor.code}, not {node.code}.")


async def _unique(db: AsyncSession, project_id: int, number: str, grade: str, own_id: int = 0) -> None:
    if await db.scalar(
        select(Heat.id).where(
            Heat.project_id == project_id, Heat.heat_number == number, Heat.material_grade == grade, Heat.id != own_id
        )
    ):
        raise DuplicateHeat(f"{number} {grade}")


async def create_heat(db: AsyncSession, values: dict[str, Any], user_id: int) -> Heat:
    project_id = values["project_id"]
    await _unique(db, project_id, values["heat_number"], values["material_grade"])
    await _check_anchor(db, values.get("planned_node_id"), project_id)
    if values.get("receipt_id"):
        receipt = await get(db, MaterialReceipt, values["receipt_id"])
        if receipt.project_id != project_id:
            raise MaterialsRuleError("That receipt is not on this project.")
        values["received_on"] = values.get("received_on") or receipt.received_on
    values = {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}
    heat = Heat(created_by_id=user_id, **values)
    heat.status = HeatStatus.AVAILABLE if heat.received_on else HeatStatus.EXPECTED
    db.add(heat)
    await db.flush()
    await record_transition(db, HEAT_ENTITY, heat.id, None, heat.status, user_id, None)
    return heat


async def update_heat(db: AsyncSession, heat: Heat, changes: dict[str, Any]) -> None:
    if "heat_number" in changes or "material_grade" in changes:
        await _unique(
            db,
            heat.project_id,
            changes.get("heat_number") or heat.heat_number,
            changes.get("material_grade") or heat.material_grade,
            heat.id,
        )
    if changes.get("planned_node_id"):
        await _check_anchor(db, changes["planned_node_id"], heat.project_id)
    for k, v in changes.items():
        if k in ("heat_number", "material_grade") and not v:
            continue
        setattr(heat, k, v.value if hasattr(v, "value") else v)
    await db.flush()


async def _set_heat_status(db: AsyncSession, heat: Heat, target: str, user_id: int | None, note: str | None = None) -> None:
    if heat.status != target:
        await record_transition(db, HEAT_ENTITY, heat.id, heat.status, target, user_id, note)
        heat.status = target


async def receive(db: AsyncSession, heat: Heat, values: dict[str, Any], user_id: int) -> None:
    if heat.status != HeatStatus.EXPECTED:
        raise MaterialsRuleError(f"Heat {heat.heat_number} has already been received.")
    if values.get("receipt_id"):
        receipt = await get(db, MaterialReceipt, values["receipt_id"])
        if receipt.project_id != heat.project_id:
            raise MaterialsRuleError("That receipt is not on this project.")
        heat.receipt_id = receipt.id
    heat.received_on = values["received_on"]
    if values.get("quantity") is not None:
        heat.quantity = values["quantity"]
    await _set_heat_status(db, heat, HeatStatus.AVAILABLE, user_id, "Received")
    await db.flush()


# --- certificates ------------------------------------------------------------------------------------


async def add_certificate(db: AsyncSession, heat: Heat, values: dict[str, Any], user_id: int) -> MillCertificate:
    await check_file(db, values.get("file_id"), heat.project_id)
    cert = MillCertificate(
        project_id=heat.project_id,
        heat_id=heat.id,
        uploaded_by_id=user_id,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(cert)
    await db.flush()
    await record_transition(db, CERT_ENTITY, cert.id, None, cert.status, user_id, None)
    return cert


async def verify_certificate(db: AsyncSession, cert: MillCertificate, target: str, reason: str | None, user_id: int) -> None:
    """QA verifies (or rejects) a certificate against the heat. Rejecting needs a reason."""
    if target == VerificationStatus.PENDING:
        raise MaterialsRuleError("Verify or reject the certificate.")
    if target == VerificationStatus.REJECTED and not reason:
        raise MaterialsRuleError("Give the reason the certificate is rejected.")
    if target == VerificationStatus.VERIFIED and cert.file_id is None:
        has_attachment = await db.scalar(
            select(StoredFile.id).where(StoredFile.entity_type == CERT_ENTITY, StoredFile.entity_id == cert.id).limit(1)
        )
        if not has_attachment:
            raise MaterialsRuleError("Attach the certificate file before verifying it.")
    await record_transition(db, CERT_ENTITY, cert.id, cert.status, target, user_id, reason)
    cert.status = target
    cert.verified_by_id = user_id
    cert.verified_at = datetime.now(UTC)
    cert.rejection_reason = reason if target == VerificationStatus.REJECTED else None
    await db.flush()


async def certificate_status(db: AsyncSession, heat_ids: Iterable[int]) -> dict[int, str]:
    """The best certificate status per heat: verified beats pending beats rejected; ``none`` without one."""
    rank = {VerificationStatus.VERIFIED.value: 0, VerificationStatus.PENDING.value: 1, VerificationStatus.REJECTED.value: 2}
    ids = list(heat_ids)
    out: dict[int, str] = {i: "none" for i in ids}
    if ids:
        for heat_id, status in (
            (await db.execute(select(MillCertificate.heat_id, MillCertificate.status).where(MillCertificate.heat_id.in_(ids))))
            .tuples()
            .all()
        ):
            if out[heat_id] == "none" or rank.get(status, 9) < rank.get(out[heat_id], 9):
                out[heat_id] = status
    return out


# --- PMI ---------------------------------------------------------------------------------------------


async def record_pmi(db: AsyncSession, heat: Heat, values: dict[str, Any], user_id: int) -> PmiTest:
    if values.get("item_id"):
        await tree.get_item(db, values["item_id"], heat.project_id)
    if values.get("equipment_id") and await is_enabled(db, "calibration", heat.project_id):
        await assert_calibrated(db, [values["equipment_id"]], values["tested_on"], project_id=heat.project_id)
    test = PmiTest(
        heat_id=heat.id, recorded_by_id=user_id, **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}
    )
    db.add(test)
    await db.flush()
    if test.result == PmiResult.REJECTED:
        await open_hold(
            db, heat, {"reason": f"PMI rejected on {test.tested_on.isoformat()} (found {test.grade_found or '?'})"}, user_id
        )
    return test


# --- holds -------------------------------------------------------------------------------------------


async def open_hold(db: AsyncSession, heat: Heat, values: dict[str, Any], user_id: int) -> MaterialHold:
    if heat.status == HeatStatus.REJECTED:
        raise MaterialsRuleError(f"Heat {heat.heat_number} is already rejected.")
    hold = MaterialHold(
        project_id=heat.project_id,
        heat_id=heat.id,
        code=await next_reference(db, "HOLD", heat.project_id),
        reason=values["reason"],
        ncr_id=values.get("ncr_id"),
        raised_on=date.today(),
        raised_by_id=user_id,
    )
    db.add(hold)
    await db.flush()
    await record_transition(db, HOLD_ENTITY, hold.id, None, hold.status, user_id, hold.reason)
    await _set_heat_status(db, heat, HeatStatus.QUARANTINED, user_id, f"{hold.code}: {hold.reason}")
    await db.flush()
    return hold


async def close_hold(db: AsyncSession, hold: MaterialHold, target: str, disposition: str | None, user_id: int) -> None:
    if hold.status != HoldStatus.OPEN:
        raise MaterialsRuleError(f"{hold.code} is already {hold.status}.")
    if target == HoldStatus.OPEN:
        raise MaterialsRuleError("Release or reject the material.")
    heat = await get(db, Heat, hold.heat_id)
    await record_transition(db, HOLD_ENTITY, hold.id, hold.status, target, user_id, disposition)
    hold.status = target
    hold.disposition = disposition
    hold.closed_by_id = user_id
    hold.closed_at = datetime.now(UTC)
    await db.flush()
    if target == HoldStatus.REJECTED:
        await _set_heat_status(db, heat, HeatStatus.REJECTED, user_id, f"{hold.code} rejected")
    else:
        still_open = await db.scalar(
            select(func.count()).where(MaterialHold.heat_id == heat.id, MaterialHold.status == HoldStatus.OPEN.value)
        )
        if not still_open:
            await _set_heat_status(
                db, heat, HeatStatus.AVAILABLE if heat.received_on else HeatStatus.EXPECTED, user_id, f"{hold.code} released"
            )
    await db.flush()


# --- issue to work -----------------------------------------------------------------------------------


async def issued_quantity(db: AsyncSession, heat_ids: Iterable[int]) -> dict[int, Decimal]:
    ids = list(heat_ids)
    if not ids:
        return {}
    rows = await db.execute(
        select(MaterialIssue.heat_id, func.coalesce(func.sum(MaterialIssue.quantity), 0))
        .where(MaterialIssue.heat_id.in_(ids))
        .group_by(MaterialIssue.heat_id)
    )
    return {h: Decimal(q or 0) for h, q in rows.tuples().all()}


async def issue(db: AsyncSession, values: dict[str, Any], user_id: int) -> MaterialIssue:
    """Issue material of a heat to a work anchor (found from the item or node). Quarantined material can't go out."""
    project_id = values["project_id"]
    heat = await get(db, Heat, values["heat_id"])
    if heat.project_id != project_id:
        raise MaterialsRuleError("That heat is not on this project.")
    if heat.status != HeatStatus.AVAILABLE:
        raise MaterialsRuleError(f"Heat {heat.heat_number} is {heat.status}; it can't be issued to work.")
    item_id = values.get("item_id")
    if item_id:
        item = await tree.get_item(db, item_id, project_id)
        anchor_id = item.work_anchor_id or (await tree.work_anchor_for(db, item.node_id)).id
    elif values.get("node_id"):
        anchor_id = (await tree.work_anchor_for(db, values["node_id"])).id
        await tree.get_node(db, anchor_id, project_id)
    else:
        raise MaterialsRuleError("Issue to an item or to a work anchor node.")
    qty = values.get("quantity")
    if qty is not None and heat.quantity is not None:
        already = (await issued_quantity(db, [heat.id])).get(heat.id, Decimal(0))
        if already + Decimal(qty) > heat.quantity:
            raise MaterialsRuleError(
                f"Only {heat.quantity - already} {heat.uom or ''} of heat {heat.heat_number} is left to issue.".replace(
                    "  ", " "
                )
            )
    row = MaterialIssue(
        project_id=project_id,
        heat_id=heat.id,
        node_id=anchor_id,
        item_id=item_id,
        issued_on=values.get("issued_on") or date.today(),
        quantity=qty,
        uom=values.get("uom") or heat.uom,
        notes=values.get("notes"),
        issued_by_id=user_id,
    )
    db.add(row)
    await db.flush()
    return row


# --- reads -------------------------------------------------------------------------------------------


async def read_heats(db: AsyncSession, heats: list[Heat]) -> list[dict[str, Any]]:
    ids = [h.id for h in heats]
    certs = await certificate_status(db, ids)
    issued = await issued_quantity(db, ids)
    holds = dict(
        (
            await db.execute(
                select(MaterialHold.heat_id, func.count())
                .where(MaterialHold.heat_id.in_(ids or [0]), MaterialHold.status == HoldStatus.OPEN.value)
                .group_by(MaterialHold.heat_id)
            )
        )
        .tuples()
        .all()
    )
    receipts = dict(
        (
            await db.execute(
                select(MaterialReceipt.id, MaterialReceipt.code).where(
                    MaterialReceipt.id.in_({h.receipt_id for h in heats if h.receipt_id} or {0})
                )
            )
        )
        .tuples()
        .all()
    )
    return [
        HeatRead.model_validate(h)
        .model_copy(
            update={
                "certificate_status": certs.get(h.id, "none"),
                "issued_quantity": issued.get(h.id, Decimal(0)),
                "open_holds": holds.get(h.id, 0),
                "receipt_code": receipts.get(h.receipt_id) if h.receipt_id else None,
            }
        )
        .model_dump(mode="json")
        for h in heats
    ]


async def read_certificates(db: AsyncSession, certs: list[MillCertificate]) -> list[dict[str, Any]]:
    heats = {h.id: h for h in (await db.execute(select(Heat).where(Heat.id.in_({c.heat_id for c in certs} or {0})))).scalars()}
    return [
        MillCertificateRead.model_validate(c)
        .model_copy(
            update={
                "heat_number": heats[c.heat_id].heat_number if c.heat_id in heats else None,
                "material_grade": heats[c.heat_id].material_grade if c.heat_id in heats else None,
            }
        )
        .model_dump(mode="json")
        for c in certs
    ]


async def read_issues(db: AsyncSession, issues: list[MaterialIssue]) -> list[dict[str, Any]]:
    nodes = dict(
        (
            await db.execute(
                select(AssetNode.id, AssetNode.display_path).where(AssetNode.id.in_({i.node_id for i in issues} or {0}))
            )
        )
        .tuples()
        .all()
    )
    tags = dict(
        (
            await db.execute(
                select(AssetItem.id, AssetItem.tag).where(AssetItem.id.in_({i.item_id for i in issues if i.item_id} or {0}))
            )
        )
        .tuples()
        .all()
    )
    numbers = dict(
        (await db.execute(select(Heat.id, Heat.heat_number).where(Heat.id.in_({i.heat_id for i in issues} or {0}))))
        .tuples()
        .all()
    )
    return [
        MaterialIssueRead.model_validate(i)
        .model_copy(
            update={
                "node_path": nodes.get(i.node_id),
                "item_tag": tags.get(i.item_id) if i.item_id else None,
                "heat_number": numbers.get(i.heat_id),
            }
        )
        .model_dump(mode="json")
        for i in issues
    ]


async def read_holds(db: AsyncSession, holds: list[MaterialHold]) -> list[dict[str, Any]]:
    numbers = dict(
        (await db.execute(select(Heat.id, Heat.heat_number).where(Heat.id.in_({h.heat_id for h in holds} or {0}))))
        .tuples()
        .all()
    )
    return [
        MaterialHoldRead.model_validate(h).model_copy(update={"heat_number": numbers.get(h.heat_id)}).model_dump(mode="json")
        for h in holds
    ]


async def heat_detail(db: AsyncSession, heat: Heat) -> dict[str, Any]:
    certs = list(
        (
            await db.execute(select(MillCertificate).where(MillCertificate.heat_id == heat.id).order_by(MillCertificate.id))
        ).scalars()
    )
    pmi = list(
        (await db.execute(select(PmiTest).where(PmiTest.heat_id == heat.id).order_by(PmiTest.tested_on, PmiTest.id))).scalars()
    )
    holds = list(
        (await db.execute(select(MaterialHold).where(MaterialHold.heat_id == heat.id).order_by(MaterialHold.id))).scalars()
    )
    issues = list(
        (await db.execute(select(MaterialIssue).where(MaterialIssue.heat_id == heat.id).order_by(MaterialIssue.id))).scalars()
    )
    return {
        **(await read_heats(db, [heat]))[0],
        "certificates": await read_certificates(db, certs),
        "pmi": [PmiRead.model_validate(p).model_dump(mode="json") for p in pmi],
        "holds": await read_holds(db, holds),
        "issues": await read_issues(db, issues),
    }


# --- traceability ------------------------------------------------------------------------------------


async def _trace_heats(db: AsyncSession, issues: list[MaterialIssue]) -> list[dict[str, Any]]:
    by_heat: dict[int, list[MaterialIssue]] = defaultdict(list)
    for i in issues:
        by_heat[i.heat_id].append(i)
    heats = list((await db.execute(select(Heat).where(Heat.id.in_(set(by_heat) or {0})).order_by(Heat.heat_number))).scalars())
    reads = {h["id"]: h for h in await read_heats(db, heats)}
    certs: dict[int, list[MillCertificate]] = defaultdict(list)
    pmi: dict[int, list[PmiTest]] = defaultdict(list)
    if heats:
        for c in (
            await db.execute(select(MillCertificate).where(MillCertificate.heat_id.in_(reads)).order_by(MillCertificate.id))
        ).scalars():
            certs[c.heat_id].append(c)
        for p in (await db.execute(select(PmiTest).where(PmiTest.heat_id.in_(reads)).order_by(PmiTest.id))).scalars():
            pmi[p.heat_id].append(p)
    return [
        {
            "heat": reads[h.id],
            "certificates": await read_certificates(db, certs[h.id]),
            "pmi": [PmiRead.model_validate(p).model_dump(mode="json") for p in pmi[h.id]],
            "issues": await read_issues(db, by_heat[h.id]),
        }
        for h in heats
    ]


async def trace_item(db: AsyncSession, item: AssetItem) -> dict[str, Any]:
    """Item → heats → certificates: material issued to the item, and to its work anchor without a named item."""
    anchor_id = item.work_anchor_id
    where = MaterialIssue.item_id == item.id
    stmt = select(MaterialIssue).where(where)
    if anchor_id:
        stmt = select(MaterialIssue).where(where | ((MaterialIssue.node_id == anchor_id) & MaterialIssue.item_id.is_(None)))
    issues = list((await db.execute(stmt.order_by(MaterialIssue.id))).scalars())
    node = await db.get(AssetNode, item.node_id)
    return {
        "item_id": item.id,
        "tag": item.tag,
        "node_path": node.display_path if node else None,
        "heats": await _trace_heats(db, issues),
    }


async def trace_node(db: AsyncSession, node: AssetNode) -> dict[str, Any]:
    """Node (and its subtree) → heats → certificates."""
    ids = await tree.subtree_ids(db, node.id)
    item_ids = select(AssetItem.id).where(AssetItem.node_id.in_(ids))
    issues = list(
        (
            await db.execute(
                select(MaterialIssue)
                .where(MaterialIssue.node_id.in_(ids) | MaterialIssue.item_id.in_(item_ids))
                .order_by(MaterialIssue.id)
            )
        ).scalars()
    )
    return {"node_id": node.id, "node_path": node.display_path, "heats": await _trace_heats(db, issues)}


async def where_used(db: AsyncSession, heat: Heat) -> dict[str, Any]:
    """Heat → where used: every issue to a work anchor or item, with its certificates."""
    issues = list(
        (await db.execute(select(MaterialIssue).where(MaterialIssue.heat_id == heat.id).order_by(MaterialIssue.id))).scalars()
    )
    certs = list((await db.execute(select(MillCertificate).where(MillCertificate.heat_id == heat.id))).scalars())
    return {
        "heat": (await read_heats(db, [heat]))[0],
        "certificates": await read_certificates(db, certs),
        "issues": await read_issues(db, issues),
    }


async def _issues_for_nodes(db: AsyncSession, node_ids: Iterable[int]) -> list[MaterialIssue]:
    ids = list(set(node_ids))
    if not ids:
        return []
    item_ids = select(AssetItem.id).where(AssetItem.node_id.in_(ids))
    return list(
        (
            await db.execute(select(MaterialIssue).where(MaterialIssue.node_id.in_(ids) | MaterialIssue.item_id.in_(item_ids)))
        ).scalars()
    )


async def certificates_for(db: AsyncSession, node_ids: Iterable[int], *, verified_only: bool = False) -> list[dict[str, Any]]:
    """The certificate appendix of a dossier (MDR) for these nodes.

    ``node_ids`` are taken as given (expand a node with ``asset_tree.service.subtree_ids`` first). A
    heat counts when it was issued to one of the nodes or to an item on one of them. Returns one row
    per certificate, ordered by heat number, with ``file_id`` for the PDF and the ``node_ids`` it was
    issued to. Rejected certificates are left out; ``verified_only`` also leaves out pending ones.
    """
    issues = await _issues_for_nodes(db, node_ids)
    if not issues:
        return []
    item_nodes = dict(
        (
            await db.execute(
                select(AssetItem.id, AssetItem.node_id).where(AssetItem.id.in_({i.item_id for i in issues if i.item_id} or {0}))
            )
        )
        .tuples()
        .all()
    )
    nodes_of: dict[int, set[int]] = defaultdict(set)
    for i in issues:
        nodes_of[i.heat_id].add(i.node_id)
        if i.item_id and i.item_id in item_nodes:
            nodes_of[i.heat_id].add(item_nodes[i.item_id])
    wanted = set(node_ids)
    statuses = [VerificationStatus.VERIFIED.value] + ([] if verified_only else [VerificationStatus.PENDING.value])
    rows = await db.execute(
        select(MillCertificate, Heat)
        .join(Heat, Heat.id == MillCertificate.heat_id)
        .where(MillCertificate.heat_id.in_(set(nodes_of)), MillCertificate.status.in_(statuses))
        .order_by(Heat.heat_number, MillCertificate.id)
    )
    return [
        {
            "certificate_id": c.id,
            "certificate_number": c.certificate_number,
            "certificate_type": c.certificate_type,
            "status": c.status,
            "heat_id": h.id,
            "heat_number": h.heat_number,
            "material_grade": h.material_grade,
            "product_form": h.product_form,
            "issuer": c.issuer,
            "issued_on": c.issued_on,
            "file_id": c.file_id,
            "node_ids": sorted(nodes_of[h.id] & wanted),
        }
        for c, h in rows.tuples().all()
    ]


async def unverified_heats_for_items(db: AsyncSession, item_ids: Iterable[int]) -> list[str]:
    """Heat numbers issued to these items that have no verified certificate (blocks weld acceptance)."""
    ids = list(item_ids)
    if not ids:
        return []
    heat_ids = set((await db.execute(select(MaterialIssue.heat_id).where(MaterialIssue.item_id.in_(ids)))).scalars())
    if not heat_ids:
        return []
    status = await certificate_status(db, heat_ids)
    bad = [h for h, s in status.items() if s != VerificationStatus.VERIFIED]
    if not bad:
        return []
    return sorted(set((await db.execute(select(Heat.heat_number).where(Heat.id.in_(bad)))).scalars()))


async def readiness_warnings(db: AsyncSession, project_id: int, node_ids: Iterable[int] | None = None) -> list[dict[str, Any]]:
    """Client-supplied material not yet received and expected after its work anchor's planned start (TD-593).

    A warning, never a block. Material with no expected date is flagged too once the start is set.
    """
    stmt = select(Heat).where(
        Heat.project_id == project_id,
        Heat.supplied_by == SuppliedBy.CLIENT.value,
        Heat.status == HeatStatus.EXPECTED.value,
        Heat.planned_node_id.is_not(None),
    )
    if node_ids is not None:
        stmt = stmt.where(Heat.planned_node_id.in_(list(node_ids) or [0]))
    heats = list((await db.execute(stmt.order_by(Heat.expected_delivery))).scalars())
    nodes = {
        n.id: n
        for n in (
            await db.execute(select(AssetNode).where(AssetNode.id.in_({h.planned_node_id for h in heats} or {0})))
        ).scalars()
    }
    out = []
    for h in heats:
        node = nodes.get(h.planned_node_id or 0)
        if node is None or node.planned_start is None:
            continue
        if h.expected_delivery is not None and h.expected_delivery <= node.planned_start:
            continue
        when = f"expected {h.expected_delivery.isoformat()}" if h.expected_delivery else "has no expected delivery date"
        out.append(
            {
                "kind": "client_material_late",
                "node_id": node.id,
                "node_path": node.display_path,
                "heat_id": h.id,
                "heat_number": h.heat_number,
                "expected_delivery": h.expected_delivery,
                "planned_start": node.planned_start,
                "message": f"Client-supplied {h.material_grade} heat {h.heat_number} {when}, after {node.code} starts on "
                f"{node.planned_start.isoformat()}.",
            }
        )
    return out

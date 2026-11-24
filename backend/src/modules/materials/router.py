"""Mounted at /api/v1/materials."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import Select, func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..asset_tree import service as tree
from ..asset_tree.models import AssetNode
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..procurement.models import PurchaseOrder
from ..projects.service import readable_project
from . import quality, service
from .constants import CERT_ENTITY, HEAT_ENTITY, HeatStatus, HoldStatus, SuppliedBy, VerificationStatus
from .models import Heat, MaterialHold, MaterialIssue, MaterialReceipt, MillCertificate
from .permissions import MaterialsPermissionName as P
from .schemas import (
    CertificateAppendixRow,
    CertificateVerifyIn,
    HeatDetail,
    HeatIn,
    HeatRead,
    HeatReceiveIn,
    HeatUpdate,
    ItemTrace,
    MaterialHistoryEntry,
    MaterialHoldClose,
    MaterialHoldIn,
    MaterialHoldRead,
    MaterialIssueIn,
    MaterialIssueRead,
    MaterialReadinessWarning,
    MaterialReceiptIn,
    MaterialReceiptRead,
    MaterialReceiptStatusIn,
    MaterialReceiptUpdate,
    MillCertificateIn,
    MillCertificateRead,
    NodeTrace,
    PmiIn,
    PmiRead,
    WhereUsed,
)

router = APIRouter(tags=["Materials & traceability"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
OptId = Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)]
Search = Annotated[str | None, Query(max_length=100)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _page(
    db: Any, stmt: Select, page: int, items_per_page: int, read: Callable[[list[Any]], Awaitable[list[dict[str, Any]]]]
) -> Any:
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = list((await db.execute(stmt.offset(compute_offset(page, items_per_page)).limit(items_per_page))).scalars())
    return paginated_response(
        crud_data={"data": await read(rows), "total_count": total or 0}, page=page, items_per_page=items_per_page
    )


async def _owned(db: Any, model: Any, row_id: int, user: dict, held: frozenset[str]) -> Any:
    row = await service.get(db, model, row_id)
    await readable_project(db, row.project_id, user["id"], held)
    return row


# --- receipts ----------------------------------------------------------------------------------------


async def _read_receipts(db: Any, rows: list[MaterialReceipt]) -> list[dict[str, Any]]:
    counts = dict(
        (
            await db.execute(
                select(Heat.receipt_id, func.count())
                .where(Heat.receipt_id.in_([r.id for r in rows] or [0]))
                .group_by(Heat.receipt_id)
            )
        )
        .tuples()
        .all()
    )
    codes: dict[int, str] = {}
    po_ids = {r.purchase_order_id for r in rows if r.purchase_order_id}
    if po_ids:
        codes = dict(
            (await db.execute(select(PurchaseOrder.id, PurchaseOrder.code).where(PurchaseOrder.id.in_(po_ids)))).tuples().all()
        )
    return [
        MaterialReceiptRead.model_validate(r)
        .model_copy(update={"heats": counts.get(r.id, 0), "purchase_order_code": codes.get(r.purchase_order_id or 0)})
        .model_dump(mode="json")
        for r in rows
    ]


@router.get(
    "/receipts/",
    response_model=PaginatedListResponse[MaterialReceiptRead],
    summary="Material Receipts (MRIR)",
    dependencies=perm(P.READ),
)
async def list_receipts(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(MaterialReceipt).where(MaterialReceipt.project_id == project_id).order_by(MaterialReceipt.id.desc())

    async def read(rows: list[MaterialReceipt]) -> list[dict[str, Any]]:
        return await _read_receipts(db, rows)

    return await _page(db, stmt, page, items_per_page, read)


@router.post(
    "/receipts/",
    response_model=MaterialReceiptRead,
    status_code=201,
    summary="Receive Material",
    description="Link the procurement PO and goods receipt when procurement is on.",
    dependencies=perm(P.CREATE),
)
async def create_receipt(
    values: MaterialReceiptIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    r = await service.create_receipt(db, values.model_dump(), user["id"])
    await db.commit()
    return (await _read_receipts(db, [r]))[0]


@router.patch(
    "/receipts/{receipt_id}", response_model=MaterialReceiptRead, summary="Update a Receipt", dependencies=perm(P.UPDATE)
)
async def update_receipt(
    receipt_id: Id, values: MaterialReceiptUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _owned(db, MaterialReceipt, receipt_id, user, held)
    await service.update_receipt(db, r, values.model_dump(exclude_unset=True))
    await db.commit()
    return (await _read_receipts(db, [r]))[0]


@router.post(
    "/receipts/{receipt_id}/status",
    response_model=MaterialReceiptRead,
    summary="Accept or Reject a Receipt",
    dependencies=perm(P.REVIEW),
)
async def receipt_status(
    receipt_id: Id, values: MaterialReceiptStatusIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _owned(db, MaterialReceipt, receipt_id, user, held)
    report = await quality.review_receipt(db, r, values, user["id"])
    await db.commit()
    await quality.announce(report)
    return (await _read_receipts(db, [r]))[0]


# --- heats -------------------------------------------------------------------------------------------


@router.get(
    "/heats/",
    response_model=PaginatedListResponse[HeatRead],
    summary="Heats and Lots",
    description="Filter by status, who supplied it, receipt, certificate status or text.",
    dependencies=perm(P.READ),
)
async def list_heats(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: HeatStatus | None = None,
    supplied_by: SuppliedBy | None = None,
    receipt_id: OptId = None,
    uncertified: bool = Query(False, description="Only heats without a verified certificate"),
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(Heat).where(Heat.project_id == project_id)
    if status:
        stmt = stmt.where(Heat.status == status.value)
    if supplied_by:
        stmt = stmt.where(Heat.supplied_by == supplied_by.value)
    if receipt_id:
        stmt = stmt.where(Heat.receipt_id == receipt_id)
    if uncertified:
        verified = select(MillCertificate.heat_id).where(MillCertificate.status == VerificationStatus.VERIFIED.value)
        stmt = stmt.where(Heat.id.not_in(verified))
    if search:
        text = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Heat.heat_number).like(text),
                func.lower(Heat.material_grade).like(text),
                func.lower(func.coalesce(Heat.description, "")).like(text),
            )
        )

    async def read(rows: list[Heat]) -> list[dict[str, Any]]:
        return await service.read_heats(db, rows)

    return await _page(db, stmt.order_by(Heat.heat_number, Heat.id), page, items_per_page, read)


@router.post("/heats/", response_model=HeatRead, status_code=201, summary="Add a Heat / Lot", dependencies=perm(P.CREATE))
async def create_heat(values: HeatIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    heat = await service.create_heat(db, values.model_dump(), user["id"])
    await db.commit()
    return (await service.read_heats(db, [heat]))[0]


@router.get(
    "/warnings",
    response_model=list[MaterialReadinessWarning],
    summary="Readiness Warnings",
    description="Client-supplied material expected after its work anchor's planned start (a warning, never a block).",
    dependencies=perm(P.READ),
)
async def warnings(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ, node_id: OptId = None
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    ids = None
    if node_id:
        await tree.get_node(db, node_id, project_id)
        ids = await tree.subtree_ids(db, node_id)
    return await service.readiness_warnings(db, project_id, ids)


@router.get(
    "/appendix",
    response_model=list[CertificateAppendixRow],
    summary="Certificate Appendix",
    description="Certificates of the heats issued to the node's subtree (or the whole project), for the MDR.",
    dependencies=perm(P.READ),
)
async def appendix(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    node_id: OptId = None,
    verified_only: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    if node_id:
        await tree.get_node(db, node_id, project_id)
        ids = await tree.subtree_ids(db, node_id)
    else:
        ids = list((await db.execute(select(AssetNode.id).where(AssetNode.project_id == project_id))).scalars())
    return await service.certificates_for(db, ids, verified_only=verified_only)


@router.get(
    "/heats/{heat_id}",
    response_model=HeatDetail,
    summary="Heat with Certificates, PMI, Holds and Issues",
    dependencies=perm(P.READ),
)
async def get_heat(heat_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.heat_detail(db, await _owned(db, Heat, heat_id, user, held))


@router.patch("/heats/{heat_id}", response_model=HeatDetail, summary="Update a Heat", dependencies=perm(P.UPDATE))
async def update_heat(
    heat_id: Id, values: HeatUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    await service.update_heat(db, heat, values.model_dump(exclude_unset=True))
    await db.commit()
    return await service.heat_detail(db, heat)


@router.delete(
    "/heats/{heat_id}", summary="Delete a Heat", description="Only one never issued to work.", dependencies=perm(P.DELETE)
)
async def delete_heat(heat_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    heat = await _owned(db, Heat, heat_id, user, held)
    if await db.scalar(select(MaterialIssue.id).where(MaterialIssue.heat_id == heat.id).limit(1)):
        raise service.MaterialsRuleError("This heat has been issued to work and stays on record.")
    await db.delete(heat)
    await db.commit()
    return {"message": "Heat deleted"}


@router.get(
    "/heats/{heat_id}/history",
    response_model=list[MaterialHistoryEntry],
    summary="Heat Status History",
    dependencies=perm(P.READ),
)
async def heat_history(heat_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    return await history_of(db, HEAT_ENTITY, heat.id)


@router.post(
    "/heats/{heat_id}/receive", response_model=HeatDetail, summary="Receive Expected Material", dependencies=perm(P.UPDATE)
)
async def receive(
    heat_id: Id, values: HeatReceiveIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    await service.receive(db, heat, values.model_dump(), user["id"])
    await db.commit()
    return await service.heat_detail(db, heat)


@router.post(
    "/heats/{heat_id}/certificates",
    response_model=MillCertificateRead,
    status_code=201,
    summary="Add a Mill Certificate",
    description="Pending until QA verifies it.",
    dependencies=perm(P.UPLOAD),
)
async def add_certificate(
    heat_id: Id, values: MillCertificateIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    cert = await service.add_certificate(db, heat, values.model_dump(), user["id"])
    await db.commit()
    return (await service.read_certificates(db, [cert]))[0]


@router.post(
    "/heats/{heat_id}/pmi",
    response_model=PmiRead,
    status_code=201,
    summary="Record PMI",
    description="The analyser must pass the calibration gate; a rejected PMI quarantines the heat.",
    dependencies=perm(P.REVIEW),
)
async def record_pmi(heat_id: Id, values: PmiIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    test = await service.record_pmi(db, heat, await quality.pmi_values(db, heat, values), user["id"])
    report = await quality.record_pmi_outcome(db, heat, test, values, user["id"])
    await db.commit()
    await quality.announce(report)
    return test


@router.post(
    "/heats/{heat_id}/holds",
    response_model=MaterialHoldRead,
    status_code=201,
    summary="Quarantine (Hold) a Heat",
    dependencies=perm(P.REVIEW),
)
async def open_hold(
    heat_id: Id, values: MaterialHoldIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    heat = await _owned(db, Heat, heat_id, user, held)
    hold = await service.open_hold(db, heat, values.model_dump(), user["id"])
    await db.commit()
    return (await service.read_holds(db, [hold]))[0]


# --- certificates ------------------------------------------------------------------------------------


@router.get(
    "/certificates/",
    response_model=PaginatedListResponse[MillCertificateRead],
    summary="Mill Certificates",
    dependencies=perm(P.READ),
)
async def list_certificates(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: VerificationStatus | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(MillCertificate).where(MillCertificate.project_id == project_id)
    if status:
        stmt = stmt.where(MillCertificate.status == status.value)

    async def read(rows: list[MillCertificate]) -> list[dict[str, Any]]:
        return await service.read_certificates(db, rows)

    return await _page(db, stmt.order_by(MillCertificate.id.desc()), page, items_per_page, read)


@router.post(
    "/certificates/{certificate_id}/verify",
    response_model=MillCertificateRead,
    summary="Verify or Reject a Certificate",
    description="QA checks the certificate (attached file needed) against the heat.",
    dependencies=perm(P.APPROVE),
)
async def verify_certificate(
    certificate_id: Id, values: CertificateVerifyIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    cert = await _owned(db, MillCertificate, certificate_id, user, held)
    await service.verify_certificate(db, cert, values.status.value, values.reason, user["id"])
    await db.commit()
    return (await service.read_certificates(db, [cert]))[0]


@router.get(
    "/certificates/{certificate_id}/history",
    response_model=list[MaterialHistoryEntry],
    summary="Certificate History",
    dependencies=perm(P.READ),
)
async def certificate_history(
    certificate_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    cert = await _owned(db, MillCertificate, certificate_id, user, held)
    return await history_of(db, CERT_ENTITY, cert.id)


# --- holds -------------------------------------------------------------------------------------------


@router.get(
    "/holds/", response_model=PaginatedListResponse[MaterialHoldRead], summary="Quarantine Holds", dependencies=perm(P.READ)
)
async def list_holds(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: HoldStatus | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(MaterialHold).where(MaterialHold.project_id == project_id)
    if status:
        stmt = stmt.where(MaterialHold.status == status.value)

    async def read(rows: list[MaterialHold]) -> list[dict[str, Any]]:
        return await service.read_holds(db, rows)

    return await _page(db, stmt.order_by(MaterialHold.id.desc()), page, items_per_page, read)


@router.post(
    "/holds/{hold_id}/close",
    response_model=MaterialHoldRead,
    summary="Release or Reject Held Material",
    description="Released: the heat is available again once no hold is open. Rejected: the heat stays rejected.",
    dependencies=perm(P.APPROVE),
)
async def close_hold(
    hold_id: Id, values: MaterialHoldClose, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    hold = await _owned(db, MaterialHold, hold_id, user, held)
    await service.close_hold(db, hold, values.status.value, values.disposition, user["id"])
    await db.commit()
    return (await service.read_holds(db, [hold]))[0]


# --- issues ------------------------------------------------------------------------------------------


@router.get(
    "/issues/",
    response_model=PaginatedListResponse[MaterialIssueRead],
    summary="Material Issued to Work",
    dependencies=perm(P.READ),
)
async def list_issues(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    heat_id: OptId = None,
    node_id: OptId = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(MaterialIssue).where(MaterialIssue.project_id == project_id)
    if heat_id:
        stmt = stmt.where(MaterialIssue.heat_id == heat_id)
    if node_id:
        stmt = stmt.where(MaterialIssue.node_id == node_id)

    async def read(rows: list[MaterialIssue]) -> list[dict[str, Any]]:
        return await service.read_issues(db, rows)

    return await _page(db, stmt.order_by(MaterialIssue.id.desc()), page, items_per_page, read)


@router.post(
    "/issues/",
    response_model=MaterialIssueRead,
    status_code=201,
    summary="Issue Material to Work",
    description="To an item or a node (its work anchor is recorded). Held, rejected or unreceived material is refused.",
    dependencies=perm(P.CREATE),
)
async def create_issue(values: MaterialIssueIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    row = await service.issue(db, values.model_dump(), user["id"])
    await db.commit()
    return (await service.read_issues(db, [row]))[0]


@router.delete("/issues/{issue_id}", summary="Undo an Issue", dependencies=perm(P.DELETE))
async def delete_issue(issue_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    await db.delete(await _owned(db, MaterialIssue, issue_id, user, held))
    await db.commit()
    return {"message": "Issue removed"}


# --- traceability ------------------------------------------------------------------------------------


@router.get(
    "/trace/items/{item_id}", response_model=ItemTrace, summary="Item → Heats → Certificates", dependencies=perm(P.READ)
)
async def trace_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    item = await tree.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    return await service.trace_item(db, item)


@router.get(
    "/trace/nodes/{node_id}", response_model=NodeTrace, summary="Node Subtree → Heats → Certificates", dependencies=perm(P.READ)
)
async def trace_node(node_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await tree.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    return await service.trace_node(db, node)


@router.get("/trace/heats/{heat_id}", response_model=WhereUsed, summary="Heat → Where Used", dependencies=perm(P.READ))
async def where_used(heat_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.where_used(db, await _owned(db, Heat, heat_id, user, held))

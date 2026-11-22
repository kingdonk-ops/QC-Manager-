"""Mounted at /api/v1/procurement."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.models import Project
from ..projects.service import readable_project
from . import service
from .models import PurchaseOrder
from .permissions import ProcurementPermissionName as P
from .schemas import (
    PoHistoryEntry,
    PoLineCreate,
    PoLineRead,
    PoLineUpdate,
    PoStatusChange,
    ProcurementSummary,
    PurchaseOrderCreate,
    PurchaseOrderDetail,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
    ReceiptCreate,
    ReceiptRead,
    ReceiptResult,
    SendRequest,
)

router = APIRouter(tags=["Procurement"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
PO = "/purchase-orders"


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _order(db: AsyncSession, po_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[PurchaseOrder, Project]:
    po = await service.get_order(db, po_id)
    project = await readable_project(db, po.project_id, user["id"], held)
    return po, project


@router.get(
    f"{PO}/",
    response_model=PaginatedListResponse[PurchaseOrderRead],
    summary="List Purchase Orders",
    description="`status=open` lists those awaiting delivery (sent or partially received).",
    dependencies=perm(P.READ),
)
async def list_purchase_orders(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: Annotated[
        str | None, Query(pattern=r"^(open|draft|sent|partially_received|fully_received|closed|cancelled)$")
    ] = None,
    supplier_company_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    overdue: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = service.filters(project_id, status, supplier_company_id, overdue, search)
    total = await db.scalar(select(func.count()).select_from(PurchaseOrder).where(*where))
    rows = (
        await db.execute(
            select(PurchaseOrder)
            .where(*where)
            .order_by(PurchaseOrder.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_orders(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    f"{PO}/", response_model=PurchaseOrderDetail, status_code=201, summary="Raise a Purchase Order", dependencies=perm(P.CREATE)
)
async def create_purchase_order(
    values: PurchaseOrderCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    po = await service.create(db, project, values.model_dump(), user["id"])
    return await service.detail(db, po)


@router.get(
    "/summary",
    response_model=ProcurementSummary,
    summary="Committed Against Received, and Outstanding Deliveries",
    description="Committed counts sent, received and closed purchase orders. Totals are in the project's currency.",
    dependencies=perm(P.READ),
)
async def summary(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.summary(db, project)


@router.get(f"{PO}/export", summary="Export the Purchase Order Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    rows = (
        await db.execute(select(PurchaseOrder).where(PurchaseOrder.project_id == project_id).order_by(PurchaseOrder.id))
    ).scalars()
    data = await service.read_orders(db, list(rows), mode="python")
    body, media_type, ext = write_table(service.EXPORT_COLUMNS, data, format, title="Purchase orders")
    name = quote(f"{project.code}-purchase-orders.{ext}")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})


@router.get(f"{PO}/{{po_id}}", response_model=PurchaseOrderDetail, summary="Get a Purchase Order", dependencies=perm(P.READ))
async def get_purchase_order(po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    po, _ = await _order(db, po_id, user, held)
    return await service.detail(db, po)


@router.patch(
    f"{PO}/{{po_id}}",
    response_model=PurchaseOrderDetail,
    summary="Update a Purchase Order",
    description="Only while it's a draft.",
    dependencies=perm(P.UPDATE),
)
async def update_purchase_order(
    po_id: Id, values: PurchaseOrderUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    po, _ = await _order(db, po_id, user, held)
    await service.update(db, po, values.model_dump(exclude_unset=True))
    return await service.detail(db, po)


@router.delete(f"{PO}/{{po_id}}", summary="Delete a Purchase Order", dependencies=perm(P.DELETE))
async def delete_purchase_order(
    po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    po, _ = await _order(db, po_id, user, held)
    await service.delete(db, po)
    return {"message": "Purchase order deleted"}


@router.patch(
    f"{PO}/{{po_id}}/status",
    response_model=PurchaseOrderDetail,
    summary="Close or Cancel a Purchase Order",
    dependencies=perm(P.TRANSITION),
)
async def change_status(
    po_id: Id, values: PoStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    po, _ = await _order(db, po_id, user, held)
    await service.change_status(db, po, values.status.value, user["id"], values.note)
    return await service.detail(db, po)


@router.get(
    f"{PO}/{{po_id}}/history",
    response_model=list[PoHistoryEntry],
    summary="A Purchase Order's Status History",
    dependencies=perm(P.READ),
)
async def history(po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    po, _ = await _order(db, po_id, user, held)
    return await history_of(db, service.ENTITY, po.id)


@router.get(f"{PO}/{{po_id}}/pdf", summary="The Purchase Order as a PDF", dependencies=perm(P.READ))
async def purchase_order_pdf(po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    po, project = await _order(db, po_id, user, held)
    body = await service.pdf(db, po, project)
    return Response(
        body,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(f'{po.code}.pdf')}"},
    )


@router.post(
    f"{PO}/{{po_id}}/send",
    response_model=PurchaseOrderDetail,
    summary="Email the Purchase Order to the PoSupplier",
    description="Renders the PDF and emails it to `to`, or else the supplier contact's (or company's) address; "
    "a draft becomes sent. Over its approval threshold, only holders of `procurement.approve` may send it.",
    dependencies=perm(P.SUBMIT),
)
async def send(po_id: Id, values: SendRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    po, project = await _order(db, po_id, user, held)
    await service.send(db, po, project, [str(e) for e in values.to], values.message, user, P.APPROVE.value in held)
    return await service.detail(db, po)


# --- lines ----------------------------------------------------------------------------------------------


@router.get(
    f"{PO}/{{po_id}}/lines", response_model=list[PoLineRead], summary="A Purchase Order's Lines", dependencies=perm(P.READ)
)
async def list_lines(po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    po, _ = await _order(db, po_id, user, held)
    return [service.read_line(line) for line in await service.lines_of(db, po.id)]


@router.post(
    f"{PO}/{{po_id}}/lines", response_model=PoLineRead, status_code=201, summary="Add a Line", dependencies=perm(P.UPDATE)
)
async def add_line(
    po_id: Id, values: PoLineCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    po, _ = await _order(db, po_id, user, held)
    return service.read_line(await service.add_line(db, po, values.model_dump()))


@router.patch(
    f"{PO}/{{po_id}}/lines/{{line_id}}", response_model=PoLineRead, summary="Change a Line", dependencies=perm(P.UPDATE)
)
async def update_line(
    po_id: Id, line_id: Id, values: PoLineUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    po, _ = await _order(db, po_id, user, held)
    line = await service.get_line(db, po, line_id)
    await service.update_line(db, po, line, values.model_dump(exclude_unset=True))
    return service.read_line(line)


@router.delete(f"{PO}/{{po_id}}/lines/{{line_id}}", summary="Delete a Line", dependencies=perm(P.UPDATE))
async def delete_line(
    po_id: Id, line_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    po, _ = await _order(db, po_id, user, held)
    await service.delete_line(db, po, await service.get_line(db, po, line_id))
    return {"message": "Line deleted"}


# --- goods receipts -------------------------------------------------------------------------------------


@router.get(
    f"{PO}/{{po_id}}/receipts",
    response_model=list[ReceiptRead],
    summary="A Purchase Order's Goods Receipts",
    dependencies=perm(P.READ),
)
async def list_receipts(po_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    po, _ = await _order(db, po_id, user, held)
    return await service.receipts_of(db, po)


@router.post(
    f"{PO}/{{po_id}}/receipts",
    response_model=ReceiptResult,
    status_code=201,
    summary="Record a Goods Receipt",
    description="Quantities received per line. The PO becomes partially or fully received on its own; receiving more "
    "than ordered is recorded and reported in `warnings`. Attach photos to files entity `goods_receipt`.",
    dependencies=perm(P.TRANSITION),
)
async def receive(
    po_id: Id, values: ReceiptCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    po, _ = await _order(db, po_id, user, held)
    receipt, warnings = await service.receive(db, po, values.model_dump(), user["id"])
    read = next(r for r in await service.receipts_of(db, po) if r.id == receipt.id)
    return ReceiptResult(receipt=read, status=po.status, warnings=warnings)

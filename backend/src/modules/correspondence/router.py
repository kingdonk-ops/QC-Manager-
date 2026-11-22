"""Mounted at /api/v1/correspondence."""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import ENTITY, CorrespondenceStatus, CorrespondenceType, Direction
from .models import Correspondence
from .permissions import CorrespondencePermissionName as P
from .schemas import CorrespondenceCreate, CorrespondenceRead, CorrespondenceUpdate, ThreadEntry

router = APIRouter(tags=["Correspondence"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
Search = Annotated[str | None, Query(max_length=200)]
ContactFilter = Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID, description="Sender or recipient")]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _filters(
    project_id: int,
    type: CorrespondenceType | None,
    direction: Direction | None,
    status: CorrespondenceStatus | None,
    overdue: bool,
    contact_id: int | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
) -> list[Any]:
    where: list[Any] = [Correspondence.project_id == project_id]
    if type:
        where.append(Correspondence.type == type.value)
    if direction:
        where.append(Correspondence.direction == direction.value)
    if status:
        where.append(Correspondence.status == status.value)
    if overdue:
        where += service.overdue_filter(date.today())
    if contact_id:
        where.append(
            or_(
                Correspondence.sender_contact_id == contact_id,
                cast(Correspondence.recipient_contact_ids, JSONB).contains([contact_id]),
            )
        )
    day = func.coalesce(Correspondence.date_sent, Correspondence.date_received)
    if date_from:
        where.append(day >= date_from)
    if date_to:
        where.append(day <= date_to)
    if search:
        where += service.search_filter(search)
    return where


@router.get(
    "/",
    response_model=PaginatedListResponse[CorrespondenceRead],
    summary="List Correspondence",
    description="A project's register. `search` matches every word in the reference, subject or body.",
    dependencies=perm(P.READ),
)
async def list_items(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    type: CorrespondenceType | None = None,
    direction: Direction | None = None,
    status: CorrespondenceStatus | None = None,
    overdue: bool = False,
    contact_id: ContactFilter = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, type, direction, status, overdue, contact_id, date_from, date_to, search)
    total = await db.scalar(select(func.count()).select_from(Correspondence).where(*where))
    rows = (
        await db.execute(
            select(Correspondence)
            .where(*where)
            .order_by(Correspondence.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_items(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=CorrespondenceRead,
    status_code=201,
    summary="Register Correspondence",
    description="With `in_reply_to_id`, a reply: the item it answers moves from response required to responded.",
    dependencies=perm(P.CREATE),
)
async def create(values: CorrespondenceCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    item = await service.create_item(db, values.model_dump(), user["id"])
    return (await service.read_items(db, [item]))[0]


EXPORT_COLUMNS = [
    ("reference", "Reference"),
    ("direction", "Direction"),
    ("type_name", "Type"),
    ("subject", "Subject"),
    ("sender_name", "From"),
    ("recipient_names", "To"),
    ("date_sent", "Sent"),
    ("date_received", "Received"),
    ("response_required_by", "Response by"),
    ("status", "Status"),
    ("in_reply_to_reference", "In reply to"),
    ("external_reference", "Their reference"),
]


@router.get(
    "/export",
    summary="Export the Correspondence Register",
    description="With the listing's filters, as Excel, CSV or PDF.",
    dependencies=perm(P.EXPORT),
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv", "pdf"] = "xlsx",
    type: CorrespondenceType | None = None,
    direction: Direction | None = None,
    status: CorrespondenceStatus | None = None,
    overdue: bool = False,
    contact_id: ContactFilter = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Search = None,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, type, direction, status, overdue, contact_id, date_from, date_to, search)
    items = list((await db.execute(select(Correspondence).where(*where).order_by(Correspondence.id))).scalars())
    rows = [
        {
            **r,
            "type_name": r["custom_type"] or r["type"].replace("_", " "),
            "recipient_names": ", ".join(p["name"] or "" for p in r["recipients"]),
            "status": r["status"].replace("_", " "),
        }
        for r in await service.read_items(db, items)
    ]
    filename = f"{project.code}-correspondence"
    if format == "pdf":
        doc = Document(title="Correspondence Register", subtitle=f"{project.name} · {project.code}", landscape=True)
        doc.table(
            ["Reference", "In/Out", "Type", "Subject", "From", "To", "Date", "Response by", "Status"],
            [
                [
                    r["reference"],
                    r["direction"],
                    r["type_name"],
                    r["subject"],
                    r["sender_name"] or "",
                    r["recipient_names"],
                    r["date_sent"] or r["date_received"] or "",
                    r["response_required_by"] or "",
                    r["status"],
                ]
                for r in rows
            ],
            widths=[0.1, 0.06, 0.08, 0.26, 0.12, 0.14, 0.08, 0.08, 0.08],
        )
        return Response(
            render_pdf(doc),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    body, media_type, ext = write_table(EXPORT_COLUMNS, rows, format, title="Correspondence")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}.{ext}"'})


async def _readable(db: AsyncSessionDep, item_id: int, user: dict[str, Any], held: frozenset[str]) -> Correspondence:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    return item


@router.get("/{item_id}", response_model=CorrespondenceRead, summary="Get Correspondence", dependencies=perm(P.READ))
async def get(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_items(db, [await _readable(db, item_id, user, held)]))[0]


@router.patch(
    "/{item_id}",
    response_model=CorrespondenceRead,
    summary="Update Correspondence",
    description="A `status` change follows the register's workflow and is kept in its history.",
    dependencies=perm(P.UPDATE),
)
async def update(
    item_id: Id, values: CorrespondenceUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await _readable(db, item_id, user, held)
    await service.update_item(db, item, values.model_dump(exclude_unset=True), user["id"])
    return (await service.read_items(db, [item]))[0]


@router.delete(
    "/{item_id}",
    summary="Delete Correspondence",
    description="Replies to it stay, unlinked.",
    dependencies=perm(P.DELETE),
)
async def delete(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    item = await _readable(db, item_id, user, held)
    await db.delete(item)
    await db.commit()
    return {"message": "Correspondence deleted"}


@router.get(
    "/{item_id}/thread",
    response_model=list[ThreadEntry],
    summary="The Whole Exchange an Item Belongs To",
    description="From the first item down through every reply, in order, each with its depth.",
    dependencies=perm(P.READ),
)
async def thread(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.thread_of(db, await _readable(db, item_id, user, held))


@router.get("/{item_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    item = await _readable(db, item_id, user, held)
    rows = await history_of(db, ENTITY, item.id)
    names = await service.user_names(db, {r["changed_by_id"] for r in rows if r["changed_by_id"]})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"])} for r in rows]

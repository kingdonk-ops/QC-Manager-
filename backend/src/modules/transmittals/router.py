"""Mounted at /api/v1/transmittals."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from ..user.models import User
from . import service
from .constants import ENTITY, TransmittalStatus
from .models import Transmittal, TransmittalDocument, TransmittalRecipient
from .permissions import TransmittalPermissionName as P
from .schemas import (
    Acknowledge,
    DocumentsAdd,
    RecipientsAdd,
    SendRequest,
    TransmittalCreate,
    TransmittalRead,
    TransmittalUpdate,
)

router = APIRouter(tags=["Transmittals"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _readable(db: AsyncSessionDep, transmittal_id: int, user: dict[str, Any], held: frozenset[str]) -> Transmittal:
    t = await service.get_transmittal(db, transmittal_id)
    await readable_project(db, t.project_id, user["id"], held)
    return t


async def _detail(db: AsyncSessionDep, t: Transmittal) -> dict[str, Any]:
    await db.refresh(t)
    return (await service.read_transmittals(db, [t], full=True))[0]


@router.get(
    "/",
    response_model=PaginatedListResponse[TransmittalRead],
    summary="List Transmittals",
    description="A project's register, with each recipient's delivery status.",
    dependencies=perm(P.READ),
)
async def list_transmittals(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: TransmittalStatus | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Transmittal.project_id == project_id]
    if status:
        where.append(Transmittal.status == status.value)
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(Transmittal.code).like(like), func.lower(Transmittal.subject).like(like)))
    total = await db.scalar(select(func.count()).select_from(Transmittal).where(*where))
    rows = (
        await db.execute(
            select(Transmittal)
            .where(*where)
            .order_by(Transmittal.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_transmittals(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=TransmittalRead,
    status_code=201,
    summary="Create a Transmittal",
    description="A draft, optionally with documents and recipients. `warnings` lists superseded revisions.",
    dependencies=perm(P.CREATE),
)
async def create(values: TransmittalCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    t = await service.create(db, values.model_dump(), user["id"])
    return await _detail(db, t)


@router.get("/{transmittal_id}", response_model=TransmittalRead, summary="Get a Transmittal", dependencies=perm(P.READ))
async def get(transmittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _detail(db, await _readable(db, transmittal_id, user, held))


@router.patch(
    "/{transmittal_id}", response_model=TransmittalRead, summary="Update a Draft Transmittal", dependencies=perm(P.UPDATE)
)
async def update(
    transmittal_id: Id, values: TransmittalUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    service.require_draft(t)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(t, key, value.value if hasattr(value, "value") else value)
    await db.commit()
    return await _detail(db, t)


@router.delete("/{transmittal_id}", summary="Delete a Transmittal", dependencies=perm(P.DELETE))
async def delete(transmittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    t = await _readable(db, transmittal_id, user, held)
    await db.delete(t)
    await db.commit()
    return {"message": "Transmittal deleted"}


@router.post(
    "/{transmittal_id}/documents",
    response_model=TransmittalRead,
    summary="Add Documents",
    description="Project files, at their current revision. `warnings` lists any that are superseded.",
    dependencies=perm(P.UPDATE),
)
async def add_documents(
    transmittal_id: Id, values: DocumentsAdd, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    await service.add_documents(db, t, values.file_ids)
    await db.commit()
    return await _detail(db, t)


async def _document(db: AsyncSessionDep, t: Transmittal, document_id: int) -> TransmittalDocument:
    d = await db.get(TransmittalDocument, document_id)
    if d is None or d.transmittal_id != t.id:
        raise service.TransmittalNotFoundError("No such document on this transmittal")
    return d


@router.delete(
    "/{transmittal_id}/documents/{document_id}",
    response_model=TransmittalRead,
    summary="Remove a Document",
    dependencies=perm(P.UPDATE),
)
async def remove_document(
    transmittal_id: Id, document_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    service.require_draft(t)
    await db.delete(await _document(db, t, document_id))
    await db.commit()
    return await _detail(db, t)


@router.post(
    "/{transmittal_id}/documents/{document_id}/latest",
    response_model=TransmittalRead,
    summary="Swap a Document to Its Latest Revision",
    dependencies=perm(P.UPDATE),
)
async def use_latest(
    transmittal_id: Id, document_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    await service.swap_to_latest(db, t, await _document(db, t, document_id))
    await db.commit()
    return await _detail(db, t)


@router.post(
    "/{transmittal_id}/recipients",
    response_model=TransmittalRead,
    summary="Add Recipients",
    description="Contacts; each one's name and email are kept as they are now.",
    dependencies=perm(P.UPDATE),
)
async def add_recipients(
    transmittal_id: Id, values: RecipientsAdd, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    await service.add_recipients(db, t, values.contact_ids)
    await db.commit()
    return await _detail(db, t)


@router.delete(
    "/{transmittal_id}/recipients/{recipient_id}",
    response_model=TransmittalRead,
    summary="Remove a Recipient",
    dependencies=perm(P.UPDATE),
)
async def remove_recipient(
    transmittal_id: Id, recipient_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    service.require_draft(t)
    r = await db.get(TransmittalRecipient, recipient_id)
    if r is None or r.transmittal_id != t.id:
        raise service.RecipientNotFoundError("No such recipient")
    await db.delete(r)
    await db.commit()
    return await _detail(db, t)


@router.post(
    "/{transmittal_id}/send",
    response_model=TransmittalRead,
    summary="Send a Transmittal",
    description="Marks it sent and emails each recipient with an address the cover sheet and document list. "
    "`warnings` lists documents that were superseded when sent.",
    dependencies=perm(P.SUBMIT),
)
async def send(
    transmittal_id: Id, values: SendRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    await service.send(db, t, user, values.message)
    return await _detail(db, t)


@router.patch(
    "/{transmittal_id}/acknowledge",
    response_model=TransmittalRead,
    summary="Record a Recipient's Receipt or Acknowledgement",
    description="The transmittal becomes partially acknowledged, then acknowledged once every recipient has.",
    dependencies=perm(P.UPDATE),
)
async def acknowledge(
    transmittal_id: Id, values: Acknowledge, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _readable(db, transmittal_id, user, held)
    await service.acknowledge(db, t, values.model_dump(exclude_unset=True), user["id"])
    return await _detail(db, t)


@router.get(
    "/{transmittal_id}/cover.pdf",
    summary="The Cover Sheet",
    description="Project, number, date, recipients, purpose, the document list and an acknowledgement block.",
    dependencies=perm(P.READ),
)
async def cover(transmittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    t = await _readable(db, transmittal_id, user, held)
    pdf = await service.cover_sheet(db, t)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{t.code}.pdf"'})


@router.get("/{transmittal_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(
    transmittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    t = await _readable(db, transmittal_id, user, held)
    rows = await history_of(db, ENTITY, t.id)
    ids = {r["changed_by_id"] for r in rows if r["changed_by_id"]}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    return [{**r, "changed_by_name": names.get(r["changed_by_id"])} for r in rows]

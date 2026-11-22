"""Mounted at /api/v1/markups. Every route reads the drawing (and so its project) through ``files`` first."""

from typing import Annotated, Any
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from pypdf.errors import PdfReadError
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..files.storage import storage
from ..projects.service import readable_project
from . import geometry, service
from .flatten import flatten
from .models import Markup, MarkupCalibration, MarkupSet, StampTemplate
from .permissions import MarkupPermissionName as P
from .schemas import (
    MarkupCalibrationRead,
    MarkupCalibrationSet,
    MarkupCreate,
    MarkupRead,
    MarkupSetCreate,
    MarkupSetRead,
    MarkupSetUpdate,
    MarkupStampCreate,
    MarkupStampRead,
    MarkupStampUpdate,
    MarkupUpdate,
)

router = APIRouter(tags=["Markups"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
PageNo = Annotated[int, Path(ge=1, le=100_000)]
FileQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# --- sets -----------------------------------------------------------------------------------------------


@router.get(
    "/sets/",
    response_model=PaginatedListResponse[MarkupSetRead],
    summary="List a Drawing's Markup Sets",
    dependencies=perm(P.READ),
)
async def list_sets(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file_id: FileQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await service.drawing(db, file_id, user, held)
    where = [MarkupSet.file_id == file_id]
    total = await db.scalar(select(func.count()).select_from(MarkupSet).where(*where))
    rows = (
        await db.scalars(
            select(MarkupSet)
            .where(*where)
            .order_by(MarkupSet.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).all()
    data = {"data": await service.read_sets(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/sets/", response_model=MarkupSetRead, status_code=201, summary="Start a Markup Set", dependencies=perm(P.CREATE))
async def create_set(values: MarkupSetCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    f = await service.drawing(db, values.file_id, user, held)
    row = await service.new_set(db, f, values.name, user)
    await db.commit()
    return (await service.read_sets(db, [row]))[0]


@router.patch("/sets/{set_id}", response_model=MarkupSetRead, summary="Rename a Markup Set", dependencies=perm(P.CREATE))
async def update_set(
    set_id: Id, values: MarkupSetUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await service.get_set(db, set_id)
    await service.drawing(db, row.file_id, user, held)
    service.may_change(row.author_id, user, held, P.UPDATE)
    row.name = values.name
    await db.commit()
    return (await service.read_sets(db, [row]))[0]


@router.delete("/sets/{set_id}", summary="Delete a Markup Set and Its Markups", dependencies=perm(P.CREATE))
async def delete_set(set_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    row = await service.get_set(db, set_id)
    await service.drawing(db, row.file_id, user, held)
    service.may_change(row.author_id, user, held, P.DELETE)
    await db.delete(row)
    await db.commit()
    return {"message": "Markup set deleted"}


# --- calibrations ---------------------------------------------------------------------------------------


@router.get(
    "/calibrations/",
    response_model=PaginatedListResponse[MarkupCalibrationRead],
    summary="List a Drawing's Page Scales",
    dependencies=perm(P.READ),
)
async def list_calibrations(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file_id: FileQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await service.drawing(db, file_id, user, held)
    where = [MarkupCalibration.file_id == file_id]
    total = await db.scalar(select(func.count()).select_from(MarkupCalibration).where(*where))
    rows = (
        await db.scalars(
            select(MarkupCalibration)
            .where(*where)
            .order_by(MarkupCalibration.page)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).all()
    data = {"data": [MarkupCalibrationRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.put(
    "/calibrations/{file_id}/{page}",
    response_model=MarkupCalibrationRead,
    summary="Set a Page's Scale",
    description="Two points picked on the page and the real distance between them. "
    "Measurements already on the page are recalculated.",
    dependencies=perm(P.CREATE),
)
async def calibrate(
    file_id: Id,
    page: PageNo,
    values: MarkupCalibrationSet,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await service.drawing(db, file_id, user, held)
    current = await service.calibration(db, file_id, page)
    if current is not None:
        service.may_change(current.set_by_id, user, held, P.UPDATE)
    try:
        factor = geometry.scale_factor(values.points[0], values.points[1], values.real_distance, values.unit)
    except geometry.GeometryError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    fields = {
        "points": values.points,
        "real_distance": values.real_distance,
        "unit": values.unit,
        "meters_per_unit": factor,
        "set_by_id": user["id"],
    }
    if current is None:
        current = MarkupCalibration(file_id=file_id, page=page, **fields)
        db.add(current)
    else:
        for key, value in fields.items():
            setattr(current, key, value)
    await db.flush()
    await service.remeasure_page(db, file_id, page)
    await db.commit()
    await db.refresh(current)
    return MarkupCalibrationRead.model_validate(current)


@router.delete("/calibrations/{file_id}/{page}", summary="Clear a Page's Scale", dependencies=perm(P.CREATE))
async def uncalibrate(
    file_id: Id, page: PageNo, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await service.drawing(db, file_id, user, held)
    current = await service.calibration(db, file_id, page)
    if current is not None:
        service.may_change(current.set_by_id, user, held, P.UPDATE)
        await db.delete(current)
        await db.flush()
        await service.remeasure_page(db, file_id, page)
        await db.commit()
    return {"message": "Scale cleared"}


# --- stamp templates ------------------------------------------------------------------------------------


@router.get(
    "/stamps/",
    response_model=PaginatedListResponse[MarkupStampRead],
    summary="List a Project's Stamps",
    description="A project starts with Approved, Approved as noted, Rejected, Reviewed and For Construction.",
    dependencies=perm(P.READ),
)
async def list_stamps(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.stamps(db, project_id)
    where = [StampTemplate.project_id == project_id]
    total = await db.scalar(select(func.count()).select_from(StampTemplate).where(*where))
    rows = (
        await db.scalars(
            select(StampTemplate)
            .where(*where)
            .order_by(StampTemplate.position, StampTemplate.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).all()
    data = {"data": [MarkupStampRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/stamps/", response_model=MarkupStampRead, status_code=201, summary="Add a Stamp", dependencies=perm(P.UPDATE))
async def create_stamp(
    values: MarkupStampCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    await service.stamps(db, values.project_id)
    row = StampTemplate(**values.model_dump())
    db.add(row)
    await db.commit()
    return MarkupStampRead.model_validate(row)


@router.patch("/stamps/{stamp_id}", response_model=MarkupStampRead, summary="Change a Stamp", dependencies=perm(P.UPDATE))
async def update_stamp(
    stamp_id: Id, values: MarkupStampUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await db.get(StampTemplate, stamp_id)
    if row is None:
        raise service.MarkupNotFoundError("No such stamp")
    await readable_project(db, row.project_id, user["id"], held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return MarkupStampRead.model_validate(row)


@router.delete("/stamps/{stamp_id}", summary="Remove a Stamp", dependencies=perm(P.UPDATE))
async def delete_stamp(stamp_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    row = await db.get(StampTemplate, stamp_id)
    if row is None:
        raise service.MarkupNotFoundError("No such stamp")
    await readable_project(db, row.project_id, user["id"], held)
    await db.delete(row)
    await db.commit()
    return {"message": "Stamp removed"}


# --- markups --------------------------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedListResponse[MarkupRead],
    summary="List a Drawing's Markups",
    description="Filter by page or set.",
    dependencies=perm(P.READ),
)
async def list_markups(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file_id: FileQuery,
    set_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    pdf_page: Annotated[int | None, Query(ge=1, le=100_000, description="Page of the PDF")] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await service.drawing(db, file_id, user, held)
    where: list[Any] = [Markup.file_id == file_id]
    if set_id:
        where.append(Markup.set_id == set_id)
    if pdf_page:
        where.append(Markup.page == pdf_page)
    total = await db.scalar(select(func.count()).select_from(Markup).where(*where))
    rows = (
        await db.scalars(
            select(Markup)
            .where(*where)
            .order_by(Markup.page, Markup.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).all()
    data = {"data": await service.read_markups(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=MarkupRead, status_code=201, summary="Add a Markup", dependencies=perm(P.CREATE))
async def create_markup(values: MarkupCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    f = await service.drawing(db, values.file_id, user, held)
    if values.set_id is not None:
        markup_set = await service.get_set(db, values.set_id)
        if markup_set.file_id != f.id:
            raise UnprocessableEntityException("That set belongs to another file.")
        service.may_change(markup_set.author_id, user, held, P.UPDATE)
    else:
        markup_set = await service.own_set(db, f, user)
    row = Markup(
        set_id=markup_set.id,
        file_id=f.id,
        page=values.page,
        type=values.type,
        geometry=service.checked_geometry(values.type, values.geometry),
        style=values.style.model_dump(),
        text=values.text,
        author_id=user["id"],
    )
    await service.measure(db, row)
    db.add(row)
    await db.commit()
    return (await service.read_markups(db, [row]))[0]


@router.patch("/{markup_id}", response_model=MarkupRead, summary="Change a Markup", dependencies=perm(P.CREATE))
async def update_markup(
    markup_id: Id, values: MarkupUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await service.get_markup(db, markup_id)
    await service.drawing(db, row.file_id, user, held)
    service.may_change(row.author_id, user, held, P.UPDATE)
    changes = values.model_dump(exclude_unset=True)
    if changes.get("page") is not None:
        row.page = changes["page"]
    if changes.get("geometry") is not None:
        row.geometry = service.checked_geometry(row.type, changes["geometry"])
    if changes.get("style") is not None:
        row.style = changes["style"]
    if "text" in changes:
        row.text = changes["text"]
    await service.measure(db, row)
    await db.commit()
    return (await service.read_markups(db, [row]))[0]


@router.delete("/{markup_id}", summary="Delete a Markup", dependencies=perm(P.CREATE))
async def delete_markup(
    markup_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    row = await service.get_markup(db, markup_id)
    await service.drawing(db, row.file_id, user, held)
    service.may_change(row.author_id, user, held, P.DELETE)
    await db.delete(row)
    await db.commit()
    return {"message": "Markup deleted"}


@router.get(
    "/{file_id}/flattened.pdf",
    summary="The Drawing with Its Markups Printed On",
    description="Every set, or only `set_ids`.",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    dependencies=perm(P.EXPORT),
)
async def flattened(
    file_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    set_ids: Annotated[list[int] | None, Query(max_length=100)] = None,
) -> Response:
    f = await service.drawing(db, file_id, user, held)
    query = select(Markup).where(Markup.file_id == file_id).order_by(Markup.id)
    if set_ids:
        query = query.where(Markup.set_id.in_(set_ids))
    rows = (await db.scalars(query)).all()
    markups = [
        {"page": m.page, "type": m.type, "geometry": m.geometry, "style": m.style, "text": m.text, "measurement": m.measurement}
        for m in rows
    ]
    source = await anyio.Path(storage().path(f.storage_key)).read_bytes()
    try:
        body = await anyio.to_thread.run_sync(flatten, source, markups)
    except (PdfReadError, ValueError, KeyError) as exc:
        raise UnprocessableEntityException("This PDF couldn't be read to print the markups on.") from exc
    stem = f.name[:-4] if f.name.lower().endswith(".pdf") else f.name
    return Response(
        body,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(stem + ' (marked up).pdf')}"},
    )

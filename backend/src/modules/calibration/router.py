"""Mounted at /api/v1/calibration."""

from datetime import date
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import Date, and_, cast, func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import ENTITY, DisplayStatus, EquipmentStatus, EquipmentType
from .models import CalibrationCertificate, Equipment
from .permissions import CalibrationPermissionName as P
from .schemas import (
    CalibrationCertificateCreate,
    CalibrationCertificateRead,
    CalibrationGateCheck,
    CalibrationGateResult,
    CalibrationHistoryEntry,
    CalibrationSummary,
    EquipmentCreate,
    EquipmentRead,
    EquipmentStatusChange,
    EquipmentUpdate,
)

router = APIRouter(tags=["Calibration"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]

EXPORT_COLUMNS = [
    ("code", "No."),
    ("name", "Equipment"),
    ("equipment_type", "Type"),
    ("manufacturer", "Manufacturer"),
    ("model", "Model"),
    ("serial_number", "Serial"),
    ("custodian_name", "Custodian"),
    ("location", "Location"),
    ("interval_days", "Interval (days)"),
    ("last_calibrated_on", "Last calibrated"),
    ("due_on", "Due"),
    ("status", "Status"),
]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _status_filter(status: DisplayStatus, today: date) -> Any:
    in_service = Equipment.status == EquipmentStatus.IN_SERVICE.value
    needs = Equipment.requires_calibration.is_(True)
    overdue = and_(in_service, needs, or_(Equipment.due_on.is_(None), Equipment.due_on < today))
    due = and_(in_service, needs, Equipment.due_on >= today, Equipment.due_on <= cast(today, Date) + Equipment.reminder_days)
    if status == DisplayStatus.OVERDUE:
        return overdue
    if status == DisplayStatus.DUE:
        return due
    if status == DisplayStatus.IN_SERVICE:
        return and_(in_service, ~overdue, ~due)
    return Equipment.status == status.value


@router.get(
    "/equipment/",
    response_model=PaginatedListResponse[EquipmentRead],
    summary="List Equipment",
    description="The register, by due date. `status` takes the displayed status (`due` and `overdue` included).",
    dependencies=perm(P.READ),
)
async def list_equipment(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: DisplayStatus | None = None,
    equipment_type: EquipmentType | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Equipment.project_id == project_id]
    if status:
        where.append(_status_filter(status, date.today()))
    if equipment_type:
        where.append(Equipment.equipment_type == equipment_type.value)
    if search:
        text = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Equipment.code).like(text),
                func.lower(Equipment.name).like(text),
                func.lower(func.coalesce(Equipment.serial_number, "")).like(text),
            )
        )
    total = await db.scalar(select(func.count()).select_from(Equipment).where(*where))
    rows = (
        await db.execute(
            select(Equipment)
            .where(*where)
            .order_by(Equipment.due_on.is_(None), Equipment.due_on, Equipment.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_equipment(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/equipment/", response_model=EquipmentRead, status_code=201, summary="Register Equipment", dependencies=perm(P.CREATE)
)
async def create_equipment(
    values: EquipmentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    e = await service.create_equipment(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_equipment(db, [e]))[0]


@router.get("/summary", response_model=CalibrationSummary, summary="Counts by Status", dependencies=perm(P.READ))
async def summary(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ) -> Any:
    await readable_project(db, project_id, user["id"], held)
    rows = (await db.execute(select(Equipment).where(Equipment.project_id == project_id))).scalars()
    counts = {s.value: 0 for s in DisplayStatus}
    total = 0
    today = date.today()
    for e in rows:
        counts[service.display_status(e, today)] += 1
        total += 1
    return {"total": total, **counts}


@router.get(
    "/available",
    response_model=list[EquipmentRead],
    summary="Equipment Usable on a Date",
    description="For pickers on reading forms: in service and (when it needs it) calibrated on `on`.",
    dependencies=perm(P.READ),
)
async def available(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    on: date | None = None,
    equipment_type: EquipmentType | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Equipment.project_id == project_id, Equipment.status == EquipmentStatus.IN_SERVICE.value]
    if equipment_type:
        where.append(Equipment.equipment_type == equipment_type.value)
    day = on or date.today()
    rows = [
        e
        for e in (await db.execute(select(Equipment).where(*where).order_by(Equipment.code))).scalars()
        if service.problem_on(e, day) is None
    ]
    return await service.read_equipment(db, rows)


@router.post(
    "/gate",
    response_model=CalibrationGateResult,
    summary="Check the Calibration Gate",
    description="What `assert_calibrated` would say, without refusing: for a form to warn before it submits.",
    dependencies=perm(P.READ),
)
async def check_gate(
    values: CalibrationGateCheck, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    try:
        await service.assert_calibrated(db, values.equipment_ids, values.on_date, project_id=project_id)
    except service.CalibrationGateError as e:
        return {"ok": False, "problems": e.problems}
    return {"ok": True, "problems": []}


@router.get("/export", summary="Export the Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    rows = list(
        (await db.execute(select(Equipment).where(Equipment.project_id == project_id).order_by(Equipment.code))).scalars()
    )
    body, media_type, ext = write_table(
        EXPORT_COLUMNS, await service.read_equipment(db, rows), format, title="Calibration register"
    )
    name = f"{project.code}-calibration-register.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


async def _equipment(db: Any, equipment_id: int, user: dict, held: frozenset[str]) -> Equipment:
    e = await service.get_equipment(db, equipment_id)
    await readable_project(db, e.project_id, user["id"], held)
    return e


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead, summary="Get Equipment", dependencies=perm(P.READ))
async def get_equipment(equipment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_equipment(db, [await _equipment(db, equipment_id, user, held)]))[0]


@router.patch(
    "/equipment/{equipment_id}", response_model=EquipmentRead, summary="Update Equipment", dependencies=perm(P.UPDATE)
)
async def update_equipment(
    equipment_id: Id, values: EquipmentUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    e = await _equipment(db, equipment_id, user, held)
    await service.update_equipment(db, e, values.model_dump(exclude_unset=True, mode="python"))
    await db.commit()
    return (await service.read_equipment(db, [e]))[0]


@router.delete("/equipment/{equipment_id}", summary="Delete Equipment", dependencies=perm(P.DELETE))
async def delete_equipment(equipment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    e = await _equipment(db, equipment_id, user, held)
    await db.delete(e)
    await db.commit()
    return {"message": "Equipment deleted"}


@router.post(
    "/equipment/{equipment_id}/status",
    response_model=EquipmentRead,
    summary="Change Status",
    description="Back into service needs a current certificate when the equipment requires calibration.",
    dependencies=perm(P.TRANSITION),
)
async def change_status(
    equipment_id: Id, values: EquipmentStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    e = await _equipment(db, equipment_id, user, held)
    await service.change_status(db, e, values.status.value, values.note, user["id"])
    await db.commit()
    return (await service.read_equipment(db, [e]))[0]


@router.get(
    "/equipment/{equipment_id}/history",
    response_model=list[CalibrationHistoryEntry],
    summary="Status History",
    dependencies=perm(P.READ),
)
async def history(equipment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    e = await _equipment(db, equipment_id, user, held)
    return await history_of(db, ENTITY, e.id)


@router.get(
    "/equipment/{equipment_id}/certificates",
    response_model=list[CalibrationCertificateRead],
    summary="Calibration Certificates",
    description="Newest first; the active one is the current calibration.",
    dependencies=perm(P.READ),
)
async def certificates(equipment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    e = await _equipment(db, equipment_id, user, held)
    rows = await db.execute(
        select(CalibrationCertificate)
        .where(CalibrationCertificate.equipment_id == e.id)
        .order_by(CalibrationCertificate.calibrated_on.desc(), CalibrationCertificate.id.desc())
    )
    return list(rows.scalars())


@router.post(
    "/equipment/{equipment_id}/certificates",
    response_model=CalibrationCertificateRead,
    status_code=201,
    summary="Record a Calibration",
    description="Supersedes the active certificate, moves the due date, and returns equipment that was away into service.",
    dependencies=perm(P.UPLOAD),
)
async def add_certificate(
    equipment_id: Id,
    values: CalibrationCertificateCreate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    e = await _equipment(db, equipment_id, user, held)
    cert = await service.add_certificate(db, e, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return cert

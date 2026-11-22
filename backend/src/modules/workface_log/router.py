"""Mounted at /api/v1/workface-log."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..planner.service import nodes_by_id
from ..projects.service import readable_project
from . import service
from .constants import DelayCode, EquipmentStatus, LogStatus, OverheadCode
from .models import DailyLog
from .permissions import WorkfaceLogPermissionName as P
from .schemas import LogCreate, LogNoteIn, LogRead, LogUpdate, WorkfaceAnchorTotal, WorkfaceCodes, WorkfaceDaySummary

router = APIRouter(tags=["Daily Workface Log"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _log(db: Any, log_id: int, user: dict, held: frozenset[str]) -> DailyLog:
    log = await service.get_log(db, log_id)
    await readable_project(db, log.project_id, user["id"], held)
    return log


async def _one(db: Any, log: DailyLog) -> dict[str, Any]:
    return (await service.read_logs(db, [log], detail=True))[0]


@router.get(
    "/codes", response_model=WorkfaceCodes, summary="Delay, Overhead and Equipment WorkfaceCodes", dependencies=perm(P.READ)
)
async def codes(_: CurrentUserDep) -> Any:
    return {
        "delay_codes": [c.value for c in DelayCode],
        "overhead_codes": [c.value for c in OverheadCode],
        "equipment_statuses": [s.value for s in EquipmentStatus],
    }


@router.get("/logs/", response_model=PaginatedListResponse[LogRead], summary="List Daily Logs", dependencies=perm(P.READ))
async def list_logs(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    work_date: date | None = None,
    start: date | None = None,
    end: date | None = None,
    crew_id: Annotated[int | None, Query(ge=1)] = None,
    status: LogStatus | None = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [DailyLog.project_id == project_id]
    if work_date:
        where.append(DailyLog.work_date == work_date)
    if start:
        where.append(DailyLog.work_date >= start)
    if end:
        where.append(DailyLog.work_date <= end)
    if crew_id:
        where.append(DailyLog.crew_id == crew_id)
    if status:
        where.append(DailyLog.status == status.value)
    total = await db.scalar(select(func.count()).select_from(DailyLog).where(*where))
    rows = (
        await db.execute(
            select(DailyLog)
            .where(*where)
            .order_by(DailyLog.work_date.desc(), DailyLog.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_logs(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/logs/",
    response_model=LogRead,
    status_code=201,
    summary="Start a Crew's Log for a Day",
    description="With `prefill`, the crew's members and the planner's daily plan for that crew are filled in.",
    dependencies=perm(P.CREATE),
)
async def create_log(values: LogCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    log = await service.create_log(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return await _one(db, log)


@router.get("/logs/{log_id}", response_model=LogRead, summary="Get a Daily Log", dependencies=perm(P.READ))
async def get_log(log_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _log(db, log_id, user, held))


@router.put(
    "/logs/{log_id}",
    response_model=LogRead,
    summary="Save the Log Form",
    description="Lists given replace what was there. Hours need a node (resolved to its work anchor, else 422 "
    "`NoWorkAnchor`) or a delay/overhead code. Only drafts change.",
    dependencies=perm(P.UPDATE),
)
async def save_log(
    log_id: Id, values: LogUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    log = await _log(db, log_id, user, held)
    changes = values.model_dump(mode="python", exclude_unset=True)
    await service.update_log(db, log, changes)
    await db.commit()
    return await _one(db, log)


@router.post(
    "/logs/{log_id}/copy-previous",
    response_model=LogRead,
    summary="Copy Yesterday",
    description="Replace the people, hours and equipment with the crew's previous log; edit the deviations.",
    dependencies=perm(P.UPDATE),
)
async def copy_previous(log_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    log = await _log(db, log_id, user, held)
    await service.copy_previous(db, log)
    await db.commit()
    return await _one(db, log)


@router.post("/logs/{log_id}/submit", response_model=LogRead, summary="Submit for Sign-Off", dependencies=perm(P.SUBMIT))
async def submit(log_id: Id, values: LogNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    log = await _log(db, log_id, user, held)
    await service.submit(db, log, user["id"], values.note)
    await db.commit()
    return await _one(db, log)


@router.post("/logs/{log_id}/return", response_model=LogRead, summary="Return for Changes", dependencies=perm(P.REVIEW))
async def return_log(
    log_id: Id, values: LogNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    log = await _log(db, log_id, user, held)
    await service.return_log(db, log, user["id"], values.note)
    await db.commit()
    return await _one(db, log)


@router.post(
    "/logs/{log_id}/sign",
    response_model=LogRead,
    summary="Supervisor Sign-Off",
    description="Locks the log, adds its quantities to the nodes' `earned_qty`, and publishes `workface_log.day.signed` "
    "with hours per work anchor (for earned value).",
    dependencies=perm(P.REVIEW),
)
async def sign(log_id: Id, values: LogNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    log = await _log(db, log_id, user, held)
    payload = await service.sign(db, log, user["id"], values.note)
    await db.commit()
    await service.publish_signed(payload)
    return await _one(db, log)


@router.get("/logs/{log_id}/history", summary="A Log's Status History", dependencies=perm(P.READ))
async def history(log_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    log = await _log(db, log_id, user, held)
    return await history_of(db, "workface_log", log.id)


@router.delete("/logs/{log_id}", summary="Delete a Draft Log", dependencies=perm(P.DELETE))
async def delete_log(log_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    log = await _log(db, log_id, user, held)
    if log.status != LogStatus.DRAFT:
        raise service.LogRuleError("Only a draft log can be deleted.")
    await db.delete(log)
    await db.commit()
    return {"message": "Log deleted"}


@router.get(
    "/day-summary",
    response_model=WorkfaceDaySummary,
    summary="The Project's Day",
    description="Every crew that logged or was planned that day, with totals across them.",
    dependencies=perm(P.READ),
)
async def day_summary(
    project_id: ProjectQ, work_date: date, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.day_summary(db, project_id, work_date)


@router.get(
    "/rollup",
    response_model=list[WorkfaceAnchorTotal],
    summary="Hours and Quantities per Work Anchor",
    description="Productive hours and installed quantity per work anchor, from signed logs (or all with `signed_only=false`).",
    dependencies=perm(P.READ),
)
async def rollup(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    start: date | None = None,
    end: date | None = None,
    signed_only: bool = True,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    totals = await service.rollup(db, project_id, start, end, signed_only=signed_only)
    nodes = await nodes_by_id(db, set(totals))
    rows = [
        WorkfaceAnchorTotal(
            anchor_id=anchor_id,
            anchor_code=(nodes[anchor_id].display_code or nodes[anchor_id].code) if anchor_id in nodes else str(anchor_id),
            anchor_path=nodes[anchor_id].display_path if anchor_id in nodes else "",
            hours=a.hours,
            qty=a.qty,
            uom=nodes[anchor_id].uom if anchor_id in nodes else None,
        )
        for anchor_id, a in totals.items()
    ]
    return sorted(rows, key=lambda r: r.anchor_path)

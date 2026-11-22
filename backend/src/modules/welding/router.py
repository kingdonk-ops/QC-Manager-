"""Mounted at /api/v1/welding."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import Select, case, func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of, record_transition
from ..asset_tree.models import AssetItem
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import (
    JOINT_ENTITY,
    NDE_REQUEST_ENTITY,
    WELD_ENTITY,
    WPS_ENTITY,
    BoltedJointStatus,
    NdeMethod,
    NdeReason,
    NdeResultValue,
    WeldStatus,
    WpsStatus,
)
from .models import (
    BoltedJoint,
    ContinuityEntry,
    JointEvent,
    NdeRequest,
    NdeResult,
    Pqr,
    Qualification,
    Weld,
    Welder,
    WeldPass,
    Wps,
)
from .permissions import WeldingPermissionName as P
from .schemas import (
    BoltedJointDetail,
    BoltedJointEventIn,
    BoltedJointEventRead,
    BoltedJointIn,
    BoltedJointRead,
    BoltedJointUpdate,
    ContinuityIn,
    ContinuityRead,
    NdeRequestDetail,
    NdeRequestIn,
    NdeRequestRead,
    NdeRequestStatusIn,
    NdeResultIn,
    NdeResultOutcome,
    NdeResultRead,
    NdeSampling,
    PqrIn,
    PqrRead,
    PqrUpdate,
    QualificationIn,
    QualificationMatrix,
    QualificationRead,
    QualificationUpdate,
    RepairRates,
    WeldDetail,
    WeldDrawingSummary,
    WelderDetail,
    WelderIn,
    WelderRead,
    WelderUpdate,
    WeldIn,
    WeldingHistoryEntry,
    WeldingIn,
    WeldingSettingsIn,
    WeldingSettingsRead,
    WeldNoteIn,
    WeldPwhtIn,
    WeldRead,
    WeldRepairIn,
    WeldUpdate,
    WeldVisualIn,
    WpsIn,
    WpsRead,
    WpsStatusIn,
    WpsUpdate,
)

router = APIRouter(tags=["Welding & NDE"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
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


async def _plain(rows: list[Any]) -> list[Any]:
    return rows


async def _owned(db: Any, model: Any, row_id: int, user: dict, held: frozenset[str]) -> Any:
    row = await service.get(db, model, row_id)
    await readable_project(db, row.project_id, user["id"], held)
    return row


async def _welder_of_qualification(db: Any, q: Qualification, user: dict, held: frozenset[str]) -> Welder:
    welder: Welder = await _owned(db, Welder, q.welder_id, user, held)
    return welder


# --- settings ----------------------------------------------------------------------------------------


def _settings(s: Any) -> dict[str, Any]:
    return {
        "project_id": s.project_id,
        "nde_rates": s.nde_rates,
        "continuity_days": s.continuity_days,
        "max_repairs": s.max_repairs,
        "progressive_count": s.progressive_count,
    }


@router.get(
    "/settings/{project_id}", response_model=WeldingSettingsRead, summary="NDE Rates and Rules", dependencies=perm(P.READ)
)
async def get_settings(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    s = await service.settings_for(db, project_id)
    await db.commit()
    return _settings(s)


@router.put(
    "/settings/{project_id}",
    response_model=WeldingSettingsRead,
    summary="Set NDE Rates and Rules",
    dependencies=perm(P.APPROVE),
)
async def put_settings(
    project_id: Id, values: WeldingSettingsIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    s = await service.settings_for(db, project_id)
    changes = values.model_dump(exclude_unset=True, mode="json")
    for k, v in changes.items():
        if v is not None:
            setattr(s, k, v)
    await db.commit()
    return _settings(s)


# --- PQR ---------------------------------------------------------------------------------------------


@router.get("/pqrs/", response_model=PaginatedListResponse[PqrRead], summary="List PQRs", dependencies=perm(P.READ))
async def list_pqrs(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(Pqr).where(Pqr.project_id == project_id).order_by(Pqr.code, Pqr.id)
    return await _page(db, stmt, page, items_per_page, _plain)


@router.post("/pqrs/", response_model=PqrRead, status_code=201, summary="Add a PQR", dependencies=perm(P.APPROVE))
async def create_pqr(values: PqrIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    if await db.scalar(select(Pqr.id).where(Pqr.project_id == values.project_id, Pqr.code == values.code)):
        raise service.Duplicate(values.code)
    pqr = Pqr(**values.model_dump())
    db.add(pqr)
    await db.commit()
    return pqr


@router.patch("/pqrs/{pqr_id}", response_model=PqrRead, summary="Update a PQR", dependencies=perm(P.APPROVE))
async def update_pqr(
    pqr_id: Id, values: PqrUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    pqr = await _owned(db, Pqr, pqr_id, user, held)
    for k, v in values.model_dump(exclude_unset=True).items():
        setattr(pqr, k, v)
    await db.commit()
    return pqr


@router.delete("/pqrs/{pqr_id}", summary="Delete a PQR", dependencies=perm(P.APPROVE))
async def delete_pqr(pqr_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    await db.delete(await _owned(db, Pqr, pqr_id, user, held))
    await db.commit()
    return {"message": "PQR deleted"}


# --- WPS ---------------------------------------------------------------------------------------------


@router.get("/wps/", response_model=PaginatedListResponse[WpsRead], summary="List WPSs", dependencies=perm(P.READ))
async def list_wps(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: WpsStatus | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(Wps).where(Wps.project_id == project_id)
    if status:
        stmt = stmt.where(Wps.status == status.value)
    return await _page(db, stmt.order_by(Wps.code, Wps.revision), page, items_per_page, _plain)


@router.post("/wps/", response_model=WpsRead, status_code=201, summary="Add a WPS (draft)", dependencies=perm(P.CREATE))
async def create_wps(values: WpsIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    if await db.scalar(
        select(Wps.id).where(Wps.project_id == values.project_id, Wps.code == values.code, Wps.revision == values.revision)
    ):
        raise service.Duplicate(f"{values.code} rev {values.revision}")
    if values.pqr_id:
        pqr = await service.get(db, Pqr, values.pqr_id)
        if pqr.project_id != values.project_id:
            raise service.WeldingRuleError("That PQR is not on this project.")
    wps = Wps(**values.model_dump(mode="json"))
    db.add(wps)
    await db.flush()
    await record_transition(db, WPS_ENTITY, wps.id, None, wps.status, user["id"], None)
    await db.commit()
    return wps


@router.patch("/wps/{wps_id}", response_model=WpsRead, summary="Update a Draft WPS", dependencies=perm(P.UPDATE))
async def update_wps(
    wps_id: Id, values: WpsUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    wps = await _owned(db, Wps, wps_id, user, held)
    changes = values.model_dump(exclude_unset=True, mode="json")
    if wps.status != WpsStatus.DRAFT and set(changes) - {"notes"}:
        raise service.WeldingRuleError(f"WPS {wps.code} is {wps.status}: issue a new revision instead.")
    for k, v in changes.items():
        setattr(wps, k, v)
    await db.commit()
    return wps


@router.post(
    "/wps/{wps_id}/status",
    response_model=WpsRead,
    summary="Approve or Withdraw a WPS",
    description="Welding against a WPS needs it approved.",
    dependencies=perm(P.APPROVE),
)
async def wps_status(
    wps_id: Id, values: WpsStatusIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    wps = await _owned(db, Wps, wps_id, user, held)
    await service.change_wps_status(db, wps, values.status.value, values.note, user["id"])
    await db.commit()
    return wps


@router.get("/wps/{wps_id}/history", response_model=list[WeldingHistoryEntry], summary="WPS History", dependencies=perm(P.READ))
async def wps_history(wps_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    wps = await _owned(db, Wps, wps_id, user, held)
    return await history_of(db, WPS_ENTITY, wps.id)


@router.delete("/wps/{wps_id}", summary="Delete a WPS", dependencies=perm(P.DELETE))
async def delete_wps(wps_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    wps = await _owned(db, Wps, wps_id, user, held)
    if await db.scalar(select(Weld.id).where(Weld.wps_id == wps.id).limit(1)):
        raise service.WeldingRuleError("Welds use this WPS; withdraw it instead.")
    await db.delete(wps)
    await db.commit()
    return {"message": "WPS deleted"}


# --- welders -----------------------------------------------------------------------------------------


@router.get("/welders/", response_model=PaginatedListResponse[WelderRead], summary="List Welders", dependencies=perm(P.READ))
async def list_welders(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(Welder).where(Welder.project_id == project_id)
    if search:
        text = f"%{search.lower()}%"
        stmt = stmt.where(or_(func.lower(Welder.stamp).like(text), func.lower(Welder.name).like(text)))

    async def read(rows: list[Welder]) -> list[dict[str, Any]]:
        return await service.read_welders(db, rows, project_id)

    return await _page(db, stmt.order_by(Welder.stamp), page, items_per_page, read)


@router.post("/welders/", response_model=WelderRead, status_code=201, summary="Add a Welder", dependencies=perm(P.CREATE))
async def create_welder(values: WelderIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    if await db.scalar(select(Welder.id).where(Welder.project_id == values.project_id, Welder.stamp == values.stamp)):
        raise service.Duplicate(values.stamp)
    welder = Welder(**values.model_dump())
    db.add(welder)
    await db.commit()
    return (await service.read_welders(db, [welder], welder.project_id))[0]


@router.get(
    "/qualification-matrix",
    response_model=QualificationMatrix,
    summary="Welder Qualification Matrix",
    description="Welders by process: the best qualification's state today (valid, expiring, lapsed, expired, suspended).",
    dependencies=perm(P.READ),
)
async def qualification_matrix(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    out = await service.matrix(db, project_id)
    await db.commit()
    return out


@router.get(
    "/welders/{welder_id}",
    response_model=WelderDetail,
    summary="Welder, Qualifications and Continuity",
    dependencies=perm(P.READ),
)
async def get_welder(welder_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    welder = await _owned(db, Welder, welder_id, user, held)
    quals = list(
        (
            await db.execute(
                select(Qualification)
                .where(Qualification.welder_id == welder.id)
                .order_by(Qualification.process, Qualification.id)
            )
        ).scalars()
    )
    log = list(
        (
            await db.execute(
                select(ContinuityEntry)
                .where(ContinuityEntry.welder_id == welder.id)
                .order_by(ContinuityEntry.welded_on.desc())
                .limit(200)
            )
        ).scalars()
    )
    base = (await service.read_welders(db, [welder], welder.project_id))[0]
    return {
        **base,
        "qualifications": await service.read_qualifications(db, quals, welder.project_id),
        "continuity": [ContinuityRead.model_validate(c).model_dump(mode="json") for c in log],
    }


@router.patch("/welders/{welder_id}", response_model=WelderRead, summary="Update a Welder", dependencies=perm(P.UPDATE))
async def update_welder(
    welder_id: Id, values: WelderUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    welder = await _owned(db, Welder, welder_id, user, held)
    changes = values.model_dump(exclude_unset=True, mode="json")
    if changes.get("stamp") and changes["stamp"] != welder.stamp:
        if await db.scalar(select(Welder.id).where(Welder.project_id == welder.project_id, Welder.stamp == changes["stamp"])):
            raise service.Duplicate(changes["stamp"])
    for k, v in changes.items():
        setattr(welder, k, v)
    await db.commit()
    return (await service.read_welders(db, [welder], welder.project_id))[0]


@router.delete("/welders/{welder_id}", summary="Delete a Welder", dependencies=perm(P.DELETE))
async def delete_welder(welder_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    welder = await _owned(db, Welder, welder_id, user, held)
    if await db.scalar(select(WeldPass.id).where(WeldPass.welder_id == welder.id).limit(1)):
        raise service.WeldingRuleError("This welder has welds on record; set them inactive instead.")
    await db.delete(welder)
    await db.commit()
    return {"message": "Welder deleted"}


@router.post(
    "/welders/{welder_id}/qualifications",
    response_model=QualificationRead,
    status_code=201,
    summary="Add a Qualification",
    dependencies=perm(P.APPROVE),
)
async def add_qualification(
    welder_id: Id, values: QualificationIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    welder = await _owned(db, Welder, welder_id, user, held)
    if values.wps_id:
        wps = await service.get(db, Wps, values.wps_id)
        if wps.project_id != welder.project_id:
            raise service.WeldingRuleError("That WPS is not on this project.")
    if values.expires_on and values.expires_on < values.qualified_on:
        raise service.WeldingRuleError("The qualification can't expire before it was gained.")
    q = Qualification(welder_id=welder.id, verified_by_id=user["id"], **values.model_dump(mode="json"))
    q.qualified_on, q.expires_on = values.qualified_on, values.expires_on
    db.add(q)
    await db.commit()
    return (await service.read_qualifications(db, [q], welder.project_id))[0]


@router.patch(
    "/qualifications/{qualification_id}",
    response_model=QualificationRead,
    summary="Update, Suspend or Revoke a Qualification",
    dependencies=perm(P.APPROVE),
)
async def update_qualification(
    qualification_id: Id, values: QualificationUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    q = await service.get(db, Qualification, qualification_id)
    welder = await _welder_of_qualification(db, q, user, held)
    changes = values.model_dump(exclude_unset=True, mode="json")
    if "expires_on" in changes:
        changes["expires_on"] = values.expires_on
    for k, v in changes.items():
        setattr(q, k, v)
    await db.commit()
    return (await service.read_qualifications(db, [q], welder.project_id))[0]


@router.delete("/qualifications/{qualification_id}", summary="Delete a Qualification", dependencies=perm(P.APPROVE))
async def delete_qualification(
    qualification_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict:
    q = await service.get(db, Qualification, qualification_id)
    await _welder_of_qualification(db, q, user, held)
    await db.delete(q)
    await db.commit()
    return {"message": "Qualification deleted"}


@router.post(
    "/welders/{welder_id}/continuity",
    response_model=ContinuityRead,
    status_code=201,
    summary="Log Continuity",
    description="Welding with the process outside this project's weld register (keeps the qualification alive).",
    dependencies=perm(P.UPDATE),
)
async def add_continuity(
    welder_id: Id, values: ContinuityIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    welder = await _owned(db, Welder, welder_id, user, held)
    entry = await service.log_continuity(db, welder, values.process, values.welded_on, note=values.note, user_id=user["id"])
    await db.commit()
    return entry


# --- welds -------------------------------------------------------------------------------------------


@router.get(
    "/welds/",
    response_model=PaginatedListResponse[WeldRead],
    summary="Weld Register",
    description="Filter by status, drawing (the weld map), welder, WPS, node subtree or text.",
    dependencies=perm(P.READ),
)
async def list_welds(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: WeldStatus | None = None,
    drawing_ref: Annotated[str | None, Query(max_length=120)] = None,
    welder_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    wps_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(Weld).where(Weld.project_id == project_id)
    if status:
        stmt = stmt.where(Weld.status == status.value)
    if drawing_ref:
        stmt = stmt.where(Weld.drawing_ref == drawing_ref)
    if wps_id:
        stmt = stmt.where(Weld.wps_id == wps_id)
    if welder_id:
        stmt = stmt.where(Weld.id.in_(select(WeldPass.weld_id).where(WeldPass.welder_id == welder_id)))
    if node_id:
        ids = await service.tree.subtree_ids(db, node_id)
        stmt = stmt.where(Weld.item_id.in_(select(AssetItem.id).where(AssetItem.node_id.in_(ids))))
    if search:
        text = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Weld.weld_number).like(text),
                func.lower(func.coalesce(Weld.drawing_ref, "")).like(text),
                func.lower(func.coalesce(Weld.line_ref, "")).like(text),
            )
        )

    async def read(rows: list[Weld]) -> list[dict[str, Any]]:
        return await service.read_welds(db, rows)

    return await _page(db, stmt.order_by(Weld.drawing_ref, Weld.weld_number, Weld.id), page, items_per_page, read)


@router.post(
    "/welds/",
    response_model=WeldRead,
    status_code=201,
    summary="Add a Weld",
    description="Creates the `weld` item on the node (or links an existing one); NDE percentages come from the category.",
    dependencies=perm(P.CREATE),
)
async def create_weld(values: WeldIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    weld = await service.create_weld(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_welds(db, [weld]))[0]


@router.get(
    "/drawings",
    response_model=list[WeldDrawingSummary],
    summary="Weld Maps",
    description="Each isometric / drawing with its weld counts; open one with `GET /welds/?drawing_ref=`.",
    dependencies=perm(P.READ),
)
async def drawings(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ) -> Any:
    await readable_project(db, project_id, user["id"], held)
    ref = func.coalesce(Weld.drawing_ref, "")
    rows = await db.execute(
        select(
            ref,
            func.count(),
            func.sum(case((Weld.status == WeldStatus.ACCEPTED.value, 1), else_=0)),
            func.sum(case((Weld.status == WeldStatus.REJECTED.value, 1), else_=0)),
            func.sum(case((Weld.status.not_in([WeldStatus.ACCEPTED.value, WeldStatus.CUT_OUT.value]), 1), else_=0)),
        )
        .where(Weld.project_id == project_id)
        .group_by(ref)
        .order_by(ref)
    )
    return [
        {"drawing_ref": d, "welds": n, "accepted": a or 0, "rejected": r or 0, "open": o or 0}
        for d, n, a, r, o in rows.tuples().all()
    ]


@router.get(
    "/sampling",
    response_model=NdeSampling,
    summary="NDE Sampling Selection",
    description="Per welder lot: welds, required and selected examinations, and the welds proposed to fill the gap.",
    dependencies=perm(P.READ),
)
async def nde_sampling(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQ, method: NdeMethod
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.sampling(db, project_id, method.value)


@router.get(
    "/repair-rates",
    response_model=RepairRates,
    summary="Repair Rates",
    description="Rejected / examined, per welder and per method.",
    dependencies=perm(P.READ),
)
async def repair_rates(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    method: NdeMethod | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.repair_rates(db, project_id, method.value if method else None)


@router.get(
    "/welds/{weld_id}",
    response_model=WeldDetail,
    summary="Weld Sheet",
    description="With passes, repairs and every NDE result.",
    dependencies=perm(P.READ),
)
async def get_weld(weld_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    return await service.weld_detail(db, weld)


@router.patch("/welds/{weld_id}", response_model=WeldDetail, summary="Update a Weld", dependencies=perm(P.UPDATE))
async def update_weld(
    weld_id: Id, values: WeldUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.update_weld(db, weld, values.model_dump(exclude_unset=True, mode="python"))
    await db.commit()
    return await service.weld_detail(db, weld)


@router.delete(
    "/welds/{weld_id}", summary="Delete a Weld", description="Only before it is welded.", dependencies=perm(P.DELETE)
)
async def delete_weld(weld_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    weld = await _owned(db, Weld, weld_id, user, held)
    if weld.status != WeldStatus.FIT_UP:
        raise service.WeldingRuleError("A welded joint stays on record; cut it out instead.")
    await db.delete(weld)
    await db.commit()
    return {"message": "Weld deleted"}


@router.post(
    "/welds/{weld_id}/weld",
    response_model=WeldDetail,
    summary="Record Welding",
    description="Welders per pass and the date. 422 for an unapproved WPS or a welder not qualified that day.",
    dependencies=perm(P.UPDATE),
)
async def record_welding(
    weld_id: Id, values: WeldingIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.record_welding(db, weld, values.welded_on, [p.model_dump() for p in values.passes], user["id"])
    await db.commit()
    return await service.weld_detail(db, weld)


@router.post(
    "/welds/{weld_id}/visual", response_model=WeldDetail, summary="Record Visual Inspection", dependencies=perm(P.REVIEW)
)
async def visual(
    weld_id: Id, values: WeldVisualIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.record_visual(db, weld, values.result.value, values.inspected_on, values.note, user["id"])
    await db.commit()
    return await service.weld_detail(db, weld)


@router.post("/welds/{weld_id}/pwht", response_model=WeldDetail, summary="Record PWHT", dependencies=perm(P.UPDATE))
async def pwht(weld_id: Id, values: WeldPwhtIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.record_pwht(db, weld, values.done_on)
    await db.commit()
    return await service.weld_detail(db, weld)


@router.post(
    "/welds/{weld_id}/repairs",
    response_model=WeldDetail,
    summary="Record a Repair (R1, R2)",
    description="By the same or new qualified welders; each rejected method is re-examined. Past the limit: cut out.",
    dependencies=perm(P.UPDATE),
)
async def add_repair(
    weld_id: Id, values: WeldRepairIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.repair(db, weld, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return await service.weld_detail(db, weld)


@router.post(
    "/welds/{weld_id}/accept",
    response_model=WeldDetail,
    summary="Accept a Weld",
    description="Needs visual, PWHT when required, every examination of the current repair accepted, certified material.",
    dependencies=perm(P.REVIEW),
)
async def accept(
    weld_id: Id, values: WeldNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.accept(db, weld, user["id"], values.note)
    await db.commit()
    return await service.weld_detail(db, weld)


@router.post("/welds/{weld_id}/cut-out", response_model=WeldDetail, summary="Cut Out a Weld", dependencies=perm(P.REVIEW))
async def cut_out(
    weld_id: Id, values: WeldNoteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    await service.cut_out(db, weld, user["id"], values.note)
    await db.commit()
    return await service.weld_detail(db, weld)


@router.get(
    "/welds/{weld_id}/history", response_model=list[WeldingHistoryEntry], summary="Weld History", dependencies=perm(P.READ)
)
async def weld_history(weld_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    weld = await _owned(db, Weld, weld_id, user, held)
    return await history_of(db, WELD_ENTITY, weld.id)


# --- NDE requests and results ------------------------------------------------------------------------


@router.get(
    "/nde-requests/",
    response_model=PaginatedListResponse[NdeRequestRead],
    summary="List NDE Requests",
    dependencies=perm(P.READ),
)
async def list_requests(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    method: NdeMethod | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(NdeRequest).where(NdeRequest.project_id == project_id)
    if method:
        stmt = stmt.where(NdeRequest.method == method.value)

    async def read(rows: list[NdeRequest]) -> list[dict[str, Any]]:
        return await service.read_requests(db, rows)

    return await _page(db, stmt.order_by(NdeRequest.id.desc()), page, items_per_page, read)


@router.post(
    "/nde-requests/",
    response_model=NdeRequestRead,
    status_code=201,
    summary="Create an NDE Request",
    description="One method: the welds picked (the sampling proposal) plus, by default, pending progressive/repair/100 % ones.",
    dependencies=perm(P.CREATE),
)
async def create_request(values: NdeRequestIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    req = await service.create_request(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_requests(db, [req]))[0]


@router.get(
    "/nde-requests/{request_id}", response_model=NdeRequestDetail, summary="NDE Request with Results", dependencies=perm(P.READ)
)
async def get_request(request_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    req = await _owned(db, NdeRequest, request_id, user, held)
    results = list((await db.execute(select(NdeResult).where(NdeResult.request_id == req.id).order_by(NdeResult.id))).scalars())
    return {**(await service.read_requests(db, [req]))[0], "results": await service.read_results(db, results)}


@router.post(
    "/nde-requests/{request_id}/status",
    response_model=NdeRequestRead,
    summary="Issue, Complete or Cancel",
    dependencies=perm(P.UPDATE),
)
async def request_status(
    request_id: Id, values: NdeRequestStatusIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    req = await _owned(db, NdeRequest, request_id, user, held)
    await service.change_request_status(db, req, values.status.value, values.note, user["id"])
    await db.commit()
    return (await service.read_requests(db, [req]))[0]


@router.get(
    "/nde-requests/{request_id}/history",
    response_model=list[WeldingHistoryEntry],
    summary="NDE Request History",
    dependencies=perm(P.READ),
)
async def request_history(request_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    req = await _owned(db, NdeRequest, request_id, user, held)
    return await history_of(db, NDE_REQUEST_ENTITY, req.id)


@router.get(
    "/nde-results/", response_model=PaginatedListResponse[NdeResultRead], summary="List Examinations", dependencies=perm(P.READ)
)
async def list_results(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    method: NdeMethod | None = None,
    result: NdeResultValue | None = None,
    reason: NdeReason | None = None,
    unrequested: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(NdeResult).where(NdeResult.project_id == project_id)
    if method:
        stmt = stmt.where(NdeResult.method == method.value)
    if result:
        stmt = stmt.where(NdeResult.result == result.value)
    if reason:
        stmt = stmt.where(NdeResult.reason == reason.value)
    if unrequested:
        stmt = stmt.where(NdeResult.request_id.is_(None))

    async def read(rows: list[NdeResult]) -> list[dict[str, Any]]:
        return await service.read_results(db, rows)

    return await _page(db, stmt.order_by(NdeResult.id.desc()), page, items_per_page, read)


@router.post(
    "/nde-results/{result_id}",
    response_model=NdeResultOutcome,
    summary="Record an NDE Result",
    description="A rejected sample adds progressive examinations of the same welder's welds (2, 2 more, then all).",
    dependencies=perm(P.REVIEW),
)
async def record_result(
    result_id: Id, values: NdeResultIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _owned(db, NdeResult, result_id, user, held)
    weld, added, message = await service.record_result(db, r, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return {
        "result": (await service.read_results(db, [r]))[0],
        "weld_status": weld.status,
        "added": await service.read_results(db, added),
        "message": message,
    }


# --- bolted joints -----------------------------------------------------------------------------------


@router.get(
    "/joints/",
    response_model=PaginatedListResponse[BoltedJointRead],
    summary="Bolted Joint Register",
    dependencies=perm(P.READ),
)
async def list_joints(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: BoltedJointStatus | None = None,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    stmt = select(BoltedJoint).where(BoltedJoint.project_id == project_id)
    if status:
        stmt = stmt.where(BoltedJoint.status == status.value)
    if search:
        text = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(BoltedJoint.joint_ref).like(text), func.lower(func.coalesce(BoltedJoint.line_ref, "")).like(text))
        )

    async def read(rows: list[BoltedJoint]) -> list[dict[str, Any]]:
        return await service.read_joints(db, rows)

    return await _page(db, stmt.order_by(BoltedJoint.joint_ref), page, items_per_page, read)


@router.post(
    "/joints/", response_model=BoltedJointRead, status_code=201, summary="Add a Bolted Joint", dependencies=perm(P.CREATE)
)
async def create_joint(values: BoltedJointIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    joint = await service.create_joint(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_joints(db, [joint]))[0]


async def _joint_detail(db: Any, joint: BoltedJoint) -> dict[str, Any]:
    events = list(
        (
            await db.execute(
                select(JointEvent).where(JointEvent.joint_id == joint.id).order_by(JointEvent.performed_on, JointEvent.id)
            )
        ).scalars()
    )
    return {
        **(await service.read_joints(db, [joint]))[0],
        "events": [BoltedJointEventRead.model_validate(e).model_dump(mode="json") for e in events],
    }


@router.get(
    "/joints/{joint_id}",
    response_model=BoltedJointDetail,
    summary="Bolted Joint with Breakouts and Make-ups",
    dependencies=perm(P.READ),
)
async def get_joint(joint_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _joint_detail(db, await _owned(db, BoltedJoint, joint_id, user, held))


@router.patch(
    "/joints/{joint_id}", response_model=BoltedJointDetail, summary="Update a Bolted Joint", dependencies=perm(P.UPDATE)
)
async def update_joint(
    joint_id: Id, values: BoltedJointUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    joint = await _owned(db, BoltedJoint, joint_id, user, held)
    changes = values.model_dump(exclude_unset=True, mode="python")
    if changes.get("joint_ref") and changes["joint_ref"] != joint.joint_ref:
        if await db.scalar(
            select(BoltedJoint.id).where(
                BoltedJoint.project_id == joint.project_id, BoltedJoint.joint_ref == changes["joint_ref"]
            )
        ):
            raise service.Duplicate(changes["joint_ref"])
    for k, v in changes.items():
        setattr(joint, k, v.value if hasattr(v, "value") else v)
    await db.commit()
    return await _joint_detail(db, joint)


@router.delete("/joints/{joint_id}", summary="Delete a Bolted Joint", dependencies=perm(P.DELETE))
async def delete_joint(joint_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict:
    joint = await _owned(db, BoltedJoint, joint_id, user, held)
    if await db.scalar(select(JointEvent.id).where(JointEvent.joint_id == joint.id).limit(1)):
        raise service.WeldingRuleError("This joint has breakout / make-up records and stays on the register.")
    await db.delete(joint)
    await db.commit()
    return {"message": "Joint deleted"}


@router.post(
    "/joints/{joint_id}/events",
    response_model=BoltedJointDetail,
    status_code=201,
    summary="Record a Breakout or Make-up",
    description="A make-up names the calibrated tools (422 when one is overdue) and the applied value within tolerance.",
    dependencies=perm(P.UPDATE),
)
async def joint_event(
    joint_id: Id, values: BoltedJointEventIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    joint = await _owned(db, BoltedJoint, joint_id, user, held)
    await service.record_joint_event(db, joint, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return await _joint_detail(db, joint)


@router.get(
    "/joints/{joint_id}/history", response_model=list[WeldingHistoryEntry], summary="Joint History", dependencies=perm(P.READ)
)
async def joint_history(joint_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    joint = await _owned(db, BoltedJoint, joint_id, user, held)
    return await history_of(db, JOINT_ENTITY, joint.id)

"""Dashboard tiles, project settings, the competency register, delegations and pending co-signs."""

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import ForbiddenException, NotFoundException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from ..user.models import User
from . import eligibility, service, signing
from .models import Competency, Delegation, Inspection, InspectionSignature
from .permissions import InspectionPermissionName as P
from .quality_schemas import (
    CompetencyIn,
    CompetencyRead,
    CompetencyUpdate,
    DelegationIn,
    DelegationRead,
    PendingCosign,
)
from .schemas import InspectionDashboard, InspectionSettingsRead, InspectionSettingsUpdate

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
MANAGE = [require_permissions(P.MANAGE.value)]


@router.get(
    "/dashboard",
    response_model=InspectionDashboard,
    summary="Dashboard Tiles",
    description="Computed on request: open call-outs (and today's), Hold points awaiting release (line accepted, "
    "hold not yet released) and open, records due within 7 days and overdue, awaiting review, and the acceptance rate "
    "(accepted / (accepted + rejected) of completed records). `formal_only` leaves informal records out.",
    dependencies=READ,
)
async def dashboard(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery, formal_only: bool = False
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.dashboard(db, project_id, formal_only)


@router.get("/settings", response_model=InspectionSettingsRead, summary="Project Settings", dependencies=READ)
async def get_settings(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    await readable_project(db, project_id, user["id"], held)
    s = await eligibility.settings_of(db, project_id)
    await db.commit()
    return s


@router.patch(
    "/settings",
    response_model=InspectionSettingsRead,
    summary="Change Project Settings",
    description="Minimum notice for Hold/Witness call-outs, whether short notice blocks, the no-show grace period and "
    "whether a reviewer may approve their own inspection.",
    dependencies=MANAGE,
)
async def update_settings(
    values: InspectionSettingsUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    s = await eligibility.settings_of(db, project_id)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(s, key, value)
    await db.commit()
    return s


# --- competency register -----------------------------------------------------------------------------


def _read_competency(c: Competency, names: dict[int, str]) -> dict[str, Any]:
    today = date.today()
    return (
        CompetencyRead.model_validate(c)
        .model_copy(
            update={
                "user_name": names.get(c.user_id),
                "valid_today": signing.competency_valid(c, today),
                "expires_in_days": (c.expires_on - today).days if c.expires_on else None,
            }
        )
        .model_dump(mode="json")
    )


@router.get(
    "/competencies/",
    response_model=PaginatedListResponse[CompetencyRead],
    summary="Competency Register",
    description="Qualifications people hold, with expiry. Your own are always visible; everyone's needs "
    "`inspections.manage`. `expiring_within` (days) lists those running out soon.",
    dependencies=READ,
)
async def list_competencies(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    user_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    qualification: Annotated[str | None, Query(max_length=120)] = None,
    expiring_within: Annotated[int | None, Query(ge=0, le=3650)] = None,
) -> Any:
    where: list[Any] = []
    if P.MANAGE not in held:
        if user_id not in (None, user["id"]):
            raise ForbiddenException("You see only your own competencies.")
        user_id = user["id"]
    if user_id:
        where.append(Competency.user_id == user_id)
    if qualification:
        where.append(func.lower(Competency.qualification) == qualification.lower())
    if expiring_within is not None:
        where.append(Competency.expires_on <= date.today() + timedelta(days=expiring_within))
    total = await db.scalar(select(func.count()).select_from(Competency).where(*where))
    rows = list(
        (
            await db.execute(
                select(Competency)
                .where(*where)
                .order_by(Competency.expires_on.nulls_last(), Competency.id)
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    names = await service.user_names(db, {c.user_id for c in rows})
    data = {"data": [_read_competency(c, names) for c in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/competencies/", response_model=CompetencyRead, status_code=201, summary="Add a Competency", dependencies=MANAGE)
async def create_competency(values: CompetencyIn, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    if await db.get(User, values.user_id) is None:
        raise NotFoundException("User not found.")
    c = Competency(created_by_id=user["id"], **values.model_dump())
    db.add(c)
    await db.commit()
    return _read_competency(c, await service.user_names(db, {c.user_id}))


async def _competency(db: Any, competency_id: int) -> Competency:
    c: Competency | None = await db.get(Competency, competency_id)
    if c is None:
        raise NotFoundException("Competency not found.")
    return c


@router.patch(
    "/competencies/{competency_id}", response_model=CompetencyRead, summary="Update a Competency", dependencies=MANAGE
)
async def update_competency(competency_id: Id, values: CompetencyUpdate, db: AsyncSessionDep) -> Any:
    c = await _competency(db, competency_id)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(c, key, value)
    await db.commit()
    return _read_competency(c, await service.user_names(db, {c.user_id}))


@router.delete(
    "/competencies/{competency_id}",
    summary="Remove a Competency",
    description="Signatures already made keep their snapshot of it.",
    dependencies=MANAGE,
)
async def delete_competency(competency_id: Id, db: AsyncSessionDep) -> dict[str, str]:
    await db.delete(await _competency(db, competency_id))
    await db.commit()
    return {"message": "Competency removed"}


# --- delegations -------------------------------------------------------------------------------------


async def _read_delegations(db: Any, rows: list[Delegation]) -> list[dict[str, Any]]:
    ids: set[int | None] = {*(d.delegator_id for d in rows), *(d.delegate_id for d in rows)}
    names = await service.user_names(db, ids)
    now = signing.now()
    return [
        DelegationRead.model_validate(d)
        .model_copy(
            update={
                "delegator_name": names.get(d.delegator_id),
                "delegate_name": names.get(d.delegate_id),
                "active": d.revoked_at is None and d.starts_at <= now < d.ends_at,
            }
        )
        .model_dump(mode="json")
        for d in rows
    ]


@router.get(
    "/delegations/",
    response_model=PaginatedListResponse[DelegationRead],
    summary="Delegations",
    description="Yours (as delegator or delegate) on the project; everyone's with `inspections.manage`.",
    dependencies=READ,
)
async def list_delegations(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Delegation.project_id == project_id]
    if P.MANAGE not in held:
        where.append(signing.user_filter(user["id"]))
    total = await db.scalar(select(func.count()).select_from(Delegation).where(*where))
    rows = list(
        (
            await db.execute(
                select(Delegation)
                .where(*where)
                .order_by(Delegation.starts_at.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await _read_delegations(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/delegations/",
    response_model=DelegationRead,
    status_code=201,
    summary="Name an Acting Delegate",
    description="Narrow and time-boxed (at most 90 days), one active per person, project and kind, never to "
    "yourself, never chained. It routes call-outs and lets the delegate sign on your behalf, but confers no "
    "authority: the delegate needs the permission and competency themself. For someone else: `inspections.manage`.",
    dependencies=READ,
)
async def create_delegation(
    values: DelegationIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    body = values.model_dump()
    body["delegator_id"] = body.get("delegator_id") or user["id"]
    if body["delegator_id"] != user["id"] and P.MANAGE not in held:
        raise ForbiddenException("Naming a delegate for someone else needs inspections.manage.")
    if await db.get(User, values.delegate_id) is None:
        raise NotFoundException("User not found.")
    d = await signing.create_delegation(db, values.project_id, body, user["id"])
    await db.commit()
    return (await _read_delegations(db, [d]))[0]


@router.post(
    "/delegations/{delegation_id}/revoke",
    response_model=DelegationRead,
    summary="Revoke a Delegation",
    dependencies=READ,
)
async def revoke_delegation(delegation_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    d = await db.get(Delegation, delegation_id)
    if d is None:
        raise NotFoundException("Delegation not found.")
    await readable_project(db, d.project_id, user["id"], held)
    if user["id"] not in (d.delegator_id, d.delegate_id) and P.MANAGE not in held:
        raise ForbiddenException("Only the people named on it, or inspections.manage, revoke a delegation.")
    if d.revoked_at is None:
        d.revoked_at, d.revoked_by_id = signing.now(), user["id"]
    await db.commit()
    return (await _read_delegations(db, [d]))[0]


# --- co-signs waiting for me -------------------------------------------------------------------------


@router.get(
    "/cosigns/pending",
    response_model=list[PendingCosign],
    summary="Co-signs Waiting for My Confirmation",
    description="Provisional client signatures (drawn on a device, or scanned) recorded in your name.",
    dependencies=[require_permissions(P.RESPOND.value)],
)
async def pending_cosigns(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    sigs: list[InspectionSignature] = await signing.pending_cosigns_for(db, user["id"])
    out = []
    for s in sigs:
        i = await db.get(Inspection, s.inspection_id)
        if i is None:
            continue
        try:
            await readable_project(db, i.project_id, user["id"], held)
        except Exception:  # noqa: BLE001 - a project the caller can no longer see is skipped
            continue
        out.append(
            {
                "signature_id": s.id,
                "inspection_id": i.id,
                "project_id": i.project_id,
                "code": i.code,
                "title": i.title,
                "mode": s.mode,
                "signed_at": s.signed_at,
                "recorded_by_id": s.recorded_by_id,
            }
        )
    return out

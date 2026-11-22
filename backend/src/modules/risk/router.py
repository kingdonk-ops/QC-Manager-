"""Mounted at /api/v1/risks."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import Band, Impact, RiskCategory, RiskStatus
from .models import Risk
from .permissions import RiskPermissionName as P
from .schemas import RiskCreate, RiskHistoryEntry, RiskMatrix, RiskRead, RiskStatusChange, RiskUpdate

router = APIRouter(tags=["Risk Register"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


@router.get(
    "/",
    response_model=PaginatedListResponse[RiskRead],
    summary="List Risks",
    description="Filter by status, category, impact, probability band (the matrix row), owner (`me`), open only, or text.",
    dependencies=perm(P.READ),
)
async def list_risks(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: RiskStatus | None = None,
    category: RiskCategory | None = None,
    impact: Impact | None = None,
    band: Band | None = None,
    owner: Annotated[str | None, Query(pattern=r"^(me|\d{1,10})$")] = None,
    open_only: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["code", "exposure"] = "code",
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = service.filters(
        project_id,
        status=status,
        category=category,
        impact=impact,
        band=band,
        owner_id=(user["id"] if owner == "me" else int(owner)) if owner else None,
        open_only=open_only,
        search=search,
    )
    data = await service.page(db, where, compute_offset(page, items_per_page), items_per_page, sort)
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=RiskRead, status_code=201, summary="Raise a Risk", dependencies=perm(P.CREATE))
async def create_risk(values: RiskCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    risk = await service.create(db, values.model_dump(), user["id"])
    return (await service.read_risks(db, [risk]))[0]


@router.get(
    "/matrix",
    response_model=RiskMatrix,
    summary="Probability × Impact Matrix and Register Totals",
    description="Counts and exposure per probability band × impact cell, totals by category and the top ten by exposure. "
    "Closed risks are left out unless `include_closed`.",
    dependencies=perm(P.READ),
)
async def risk_matrix(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    include_closed: bool = False,
) -> RiskMatrix:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.matrix(db, project, include_closed)


@router.get("/export", summary="Export the Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    risks = (await db.execute(select(Risk).where(Risk.project_id == project_id).order_by(Risk.id))).scalars()
    rows = await service.read_risks(db, list(risks), mode="python")
    body, media_type, ext = write_table(service.EXPORT_COLUMNS, rows, format, title="Risk register")
    name = f"{project.code}-risk-register.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.get("/{risk_id}", response_model=RiskRead, summary="Get a Risk", dependencies=perm(P.READ))
async def get_risk(risk_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    risk = await service.get_risk(db, risk_id)
    await readable_project(db, risk.project_id, user["id"], held)
    return (await service.read_risks(db, [risk]))[0]


@router.patch("/{risk_id}", response_model=RiskRead, summary="Update a Risk", dependencies=perm(P.UPDATE))
async def update_risk(
    risk_id: Id, values: RiskUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    risk = await service.get_risk(db, risk_id)
    await readable_project(db, risk.project_id, user["id"], held)
    await service.update(db, risk, values.model_dump(exclude_unset=True), user["id"])
    return (await service.read_risks(db, [risk]))[0]


@router.patch("/{risk_id}/status", response_model=RiskRead, summary="Change a Risk's Status", dependencies=perm(P.TRANSITION))
async def change_status(
    risk_id: Id, values: RiskStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    risk = await service.get_risk(db, risk_id)
    await readable_project(db, risk.project_id, user["id"], held)
    await service.transition(db, risk, values.status.value, user["id"], values.note)
    return (await service.read_risks(db, [risk]))[0]


@router.get(
    "/{risk_id}/history", response_model=list[RiskHistoryEntry], summary="A Risk's Status History", dependencies=perm(P.READ)
)
async def history(risk_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    risk = await service.get_risk(db, risk_id)
    await readable_project(db, risk.project_id, user["id"], held)
    return await history_of(db, service.ENTITY, risk.id)


@router.delete("/{risk_id}", summary="Delete a Risk", dependencies=perm(P.DELETE))
async def delete_risk(risk_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    risk = await service.get_risk(db, risk_id)
    await readable_project(db, risk.project_id, user["id"], held)
    await db.delete(risk)
    await db.commit()
    return {"message": "Risk deleted"}

"""Mounted at /api/v1/cvr. Every route reads the project through ``projects``' visibility rule first."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID
from ..projects.service import readable_project
from .permissions import CvrPermissionName
from .schemas import CashflowPeriodRead, CashflowSet, CostHeadCreate, CostHeadRead, CostHeadUpdate, CvrSummary
from .service import CvrService

router = APIRouter(tags=["Cost-Value Reconciliation"])

Cvr = Annotated[CvrService, Depends(CvrService)]
ProjectId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
HeadId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(CvrPermissionName.READ.value)]
EDIT = [require_permissions(CvrPermissionName.EDIT.value)]


@router.get(
    "/projects/{project_id}/cost-heads", response_model=list[CostHeadRead], summary="List Cost Heads", dependencies=READ
)
async def list_cost_heads(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, cvr: Cvr
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await cvr.cost_heads(db, project_id)


@router.post(
    "/projects/{project_id}/cost-heads",
    response_model=CostHeadRead,
    status_code=201,
    summary="Add a Cost Head",
    dependencies=EDIT,
)
async def add_cost_head(
    project_id: ProjectId,
    values: CostHeadCreate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    cvr: Cvr,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await cvr.add_cost_head(db, project_id, values.model_dump())


@router.patch(
    "/projects/{project_id}/cost-heads/{head_id}",
    response_model=CostHeadRead,
    summary="Change a Cost Head",
    dependencies=EDIT,
)
async def update_cost_head(
    project_id: ProjectId,
    head_id: HeadId,
    values: CostHeadUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    cvr: Cvr,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await cvr.update_cost_head(db, project_id, head_id, values.model_dump(exclude_unset=True))


@router.delete("/projects/{project_id}/cost-heads/{head_id}", summary="Delete a Cost Head", dependencies=EDIT)
async def delete_cost_head(
    project_id: ProjectId, head_id: HeadId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, cvr: Cvr
) -> dict[str, str]:
    await readable_project(db, project_id, user["id"], held)
    await cvr.delete_cost_head(db, project_id, head_id)
    return {"message": "Cost head deleted"}


@router.get("/projects/{project_id}/summary", response_model=CvrSummary, summary="Totals and Margins", dependencies=READ)
async def summary(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, cvr: Cvr
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await cvr.summary(db, project)


@router.get(
    "/projects/{project_id}/cashflow", response_model=list[CashflowPeriodRead], summary="Monthly Cashflow", dependencies=READ
)
async def cashflow(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, cvr: Cvr
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await cvr.cashflow(db, project_id)


@router.put(
    "/projects/{project_id}/cashflow",
    response_model=list[CashflowPeriodRead],
    summary="Replace the Cashflow",
    dependencies=EDIT,
)
async def set_cashflow(
    project_id: ProjectId,
    values: CashflowSet,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    cvr: Cvr,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await cvr.set_cashflow(db, project_id, values.periods)

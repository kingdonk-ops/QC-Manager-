"""Mounted at /api/v1/temporary-works: the register rollup and the load-status view. Both are read-only, need only the
read permission, check project access first and store nothing."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID
from ..projects.service import readable_project
from . import register
from .permissions import TemporaryWorksPermissionName as P
from .register_schemas import TwLoadStatusRead, TwRegisterRollup

router = APIRouter(tags=["Temporary Works Register"])

ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
AsOf = Annotated[date | None, Query(description="The day to judge on, as YYYY-MM-DD; default: today at the site")]
READ = [require_permissions(P.READ.value)]


@router.get(
    "/register",
    response_model=TwRegisterRollup,
    summary="Register Rollup",
    description="Counts by status and design check category, the design clearance percentage, the overdue-to-load and "
    "overdue-to-strike lists, the breaches (an item loaded or in use with no valid permit to load) with the compliant flag, "
    "per-item gates and separate advisory warnings. Worked out for the as-of day on every request; nothing is stored.",
    dependencies=READ,
)
async def rollup(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery, as_of: AsOf = None
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return register.rollup_body(await register.load_summary(db, project_id, as_of))


@router.get(
    "/load-status",
    response_model=TwLoadStatusRead,
    summary="Load Status",
    description="Whether each item is cleared to load and to strike on the as-of day, and the breaches.",
    dependencies=READ,
)
async def load_status(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery, as_of: AsOf = None
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return register.load_status_body(await register.load_summary(db, project_id, as_of))

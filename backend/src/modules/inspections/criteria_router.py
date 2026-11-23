"""The acceptance-criteria library: list, create, read, update and delete. Included by the main inspections router
before the integer-id routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import criteria
from .criteria_schemas import CriterionCreate, CriterionRead, CriterionUpdate
from .models import AcceptanceCriterion
from .permissions import InspectionPermissionName as P

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
UPDATE = [require_permissions(P.UPDATE.value)]
DELETE = [require_permissions(P.DELETE.value)]


async def _readable(db: Any, criterion_id: int, user: dict[str, Any], held: frozenset[str]) -> AcceptanceCriterion:
    c = await criteria.get_criterion(db, criterion_id)
    await readable_project(db, c.project_id, user["id"], held)
    return c


@router.get(
    "/criteria/",
    response_model=PaginatedListResponse[CriterionRead],
    summary="List Acceptance Criteria",
    description="A project's acceptance-criteria library ordered by code, filterable by category and active flag. "
    "Inactive criteria stay readable.",
    dependencies=READ,
)
async def list_criteria(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    category: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AcceptanceCriterion.project_id == project_id]
    if category:
        where.append(func.lower(AcceptanceCriterion.category) == category.lower())
    if active is not None:
        where.append(AcceptanceCriterion.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(AcceptanceCriterion).where(*where))
    rows = (
        await db.execute(
            select(AcceptanceCriterion)
            .where(*where)
            .order_by(AcceptanceCriterion.code, AcceptanceCriterion.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [CriterionRead.model_validate(c).model_dump(mode="json") for c in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/criteria/",
    response_model=CriterionRead,
    status_code=201,
    summary="Create an Acceptance Criterion",
    description="Limits are stored as text and judged as exact decimals. A range rule whose two limits are numbers "
    "needs the lower one not above the upper one.",
    dependencies=UPDATE,
)
async def create_criterion(
    values: CriterionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    return await criteria.create_criterion(db, values.model_dump(mode="json"), user["id"])


@router.get("/criteria/{criterion_id}", response_model=CriterionRead, summary="Get an Acceptance Criterion", dependencies=READ)
async def get_criterion(criterion_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _readable(db, criterion_id, user, held)


@router.patch(
    "/criteria/{criterion_id}",
    response_model=CriterionRead,
    summary="Update an Acceptance Criterion",
    description="Descriptive fields stay editable. Changing the rule, unit, nominal or a limit is refused with a "
    "conflict once any record has been judged against the criterion.",
    dependencies=UPDATE,
)
async def update_criterion(
    criterion_id: Id, values: CriterionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    c = await _readable(db, criterion_id, user, held)
    await criteria.update_criterion(db, c, values.model_dump(mode="json", exclude_unset=True))
    return c


@router.delete(
    "/criteria/{criterion_id}",
    summary="Delete an Acceptance Criterion",
    description="Refused while any record, gate or template references it; the answer lists each holder kind with its count.",
    dependencies=DELETE,
)
async def delete_criterion(
    criterion_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await criteria.delete_criterion(db, await _readable(db, criterion_id, user, held))
    return {"message": "Criterion deleted"}

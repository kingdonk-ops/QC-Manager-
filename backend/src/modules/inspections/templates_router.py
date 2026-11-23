"""Template routes and the pass-rate trends route, mounted by the main inspections router before the
integer-id routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import ForbiddenException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import Area, GroupBy, Kind
from .dashboard_schemas import InspectionTrends
from .models import ChecklistTemplate, TemplateRevision
from .permissions import InspectionPermissionName as P
from .schemas import (
    ChecklistStarterSeed,
    ChecklistTemplateIn,
    ChecklistTemplateRead,
    ChecklistTemplateUpdate,
    TemplateRevisionRead,
)

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# --- templates ---------------------------------------------------------------------------------------


async def _template(db: Any, template_id: int, user: dict[str, Any], held: frozenset[str]) -> ChecklistTemplate:
    t = await service.get_template(db, template_id)
    await readable_project(db, t.project_id, user["id"], held)
    return t


@router.get(
    "/templates/",
    response_model=PaginatedListResponse[ChecklistTemplateRead],
    summary="List Templates",
    description="A project's inspection and ITP templates, filterable by kind, area, formal and audit. The three "
    "starter checklists are added the first time this is called.",
    dependencies=perm(P.READ),
)
async def list_templates(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    include_inactive: bool = False,
    trade: Annotated[str | None, Query(max_length=100)] = None,
    kind: Kind | None = None,
    area: Area | None = None,
    formal: bool | None = None,
    audit: bool | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.ensure_starters(db, project_id, user["id"])
    where: list[Any] = [ChecklistTemplate.project_id == project_id]
    if not include_inactive:
        where.append(ChecklistTemplate.active.is_(True))
    if trade:
        where.append(func.lower(ChecklistTemplate.trade) == trade.lower())
    if kind:
        where.append(ChecklistTemplate.kind == kind.value)
    if area:
        where.append(ChecklistTemplate.area == area.value)
    if formal is not None:
        where.append(ChecklistTemplate.is_formal.is_(formal))
    if audit is not None:
        where.append(ChecklistTemplate.audit_scope.is_not(None) if audit else ChecklistTemplate.audit_scope.is_(None))
    total = await db.scalar(select(func.count()).select_from(ChecklistTemplate).where(*where))
    rows = (
        await db.execute(
            select(ChecklistTemplate)
            .where(*where)
            .order_by(ChecklistTemplate.name, ChecklistTemplate.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [service.read_template(t) for t in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/templates/",
    response_model=ChecklistTemplateRead,
    status_code=201,
    summary="Create a Template",
    description="`kind=inspection` has sections of checklist items; `kind=itp` has ordered activities with an "
    "intervention point per party (H, W, R, S) and optionally an ITR form (a formal inspection template). ITP "
    "templates are always formal QA/ITP plans.",
    dependencies=perm(P.UPDATE),
)
async def create_template(
    values: ChecklistTemplateIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    t = await service.create_template(db, values.model_dump(mode="json"), user["id"])
    return service.read_template(t)


@router.post(
    "/templates/starter",
    response_model=list[ChecklistTemplateRead],
    status_code=201,
    summary="Add the Starter Templates",
    description="Pipe insulation & cladding, Refractory lining and Protective coating DFT; any the project already has "
    "(by name) are skipped.",
    dependencies=perm(P.UPDATE),
)
async def starter(values: ChecklistStarterSeed, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    return [service.read_template(t) for t in await service.seed_starters(db, values.project_id, user["id"])]


@router.get(
    "/templates/{template_id}", response_model=ChecklistTemplateRead, summary="Get a Template", dependencies=perm(P.READ)
)
async def get_template(template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return service.read_template(await _template(db, template_id, user, held))


@router.get(
    "/templates/{template_id}/revisions",
    response_model=list[TemplateRevisionRead],
    summary="A Template's Revisions",
    description="Every frozen revision, newest first, with the SHA-256 of its content and settings.",
    dependencies=perm(P.READ),
)
async def template_revisions(template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    t = await _template(db, template_id, user, held)
    rows = await db.execute(
        select(TemplateRevision).where(TemplateRevision.template_id == t.id).order_by(TemplateRevision.version.desc())
    )
    return list(rows.scalars())


@router.patch(
    "/templates/{template_id}",
    response_model=ChecklistTemplateRead,
    summary="Update a Template",
    description="A change of content or settings is a new revision; records keep theirs. Changing area, formal or "
    "audit scope needs `inspections.manage`.",
    dependencies=perm(P.UPDATE),
)
async def update_template(
    template_id: Id, values: ChecklistTemplateUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _template(db, template_id, user, held)
    changes = values.model_dump(mode="json", exclude_unset=True)
    locked = [k for k in service.LOCKED_SETTINGS if k in changes and changes[k] != getattr(t, k)]
    if locked and P.MANAGE not in held:
        raise ForbiddenException(f"Changing {', '.join(locked)} needs inspections.manage.")
    await service.update_template(db, t, changes, user["id"])
    return service.read_template(t)


@router.post(
    "/templates/{template_id}/duplicate",
    response_model=ChecklistTemplateRead,
    status_code=201,
    summary="Duplicate a Template",
    description="A client variant: a copy with the same settings (KERP: a copy, never an inheritance overlay).",
    dependencies=perm(P.UPDATE),
)
async def duplicate_template(template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    t = await _template(db, template_id, user, held)
    values = {k: v for k, v in service.template_snapshot(t).items() if k != "name"}
    values["sections"] = [dict(s) for s in t.sections]
    copy = await service.create_template(
        db, {"project_id": t.project_id, "name": f"{t.name} (copy)"[:200], **values}, user["id"]
    )
    return service.read_template(copy)


@router.delete(
    "/templates/{template_id}",
    summary="Delete a Template",
    description="Inspections made from it keep their checklist.",
    dependencies=perm(P.DELETE),
)
async def delete_template(
    template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await db.delete(await _template(db, template_id, user, held))
    await db.commit()
    return {"message": "Template deleted"}


# --- trends ------------------------------------------------------------------------------------------


@router.get(
    "/trends",
    response_model=InspectionTrends,
    summary="Pass-Rate InspectionTrends by Trade or Location",
    description="Completed and closed inspections grouped by `trade` or `location`: each inspection's pass rate "
    "over time, monthly totals, and the group's overall pass rate (passed / (passed + failed), N/A excluded).",
    dependencies=perm(P.READ),
)
async def trends(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    group_by: GroupBy = GroupBy.TRADE,
) -> InspectionTrends:
    await readable_project(db, project_id, user["id"], held)
    groups = await service.trends(db, project_id, group_by.value)
    return InspectionTrends(project_id=project_id, group_by=group_by.value, groups=groups)

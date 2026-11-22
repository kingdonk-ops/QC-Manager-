"""Mounted at /api/v1/inspections. Every route reads the project through ``projects``' visibility rule first."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import GroupBy, InspectionStatus
from .models import ChecklistTemplate, Inspection
from .permissions import InspectionPermissionName as P
from .schemas import (
    ChecklistStarterSeed,
    ChecklistTemplateIn,
    ChecklistTemplateRead,
    ChecklistTemplateUpdate,
    InspectionCompletion,
    InspectionCreate,
    InspectionItemsFill,
    InspectionRead,
    InspectionStatusChange,
    InspectionTrends,
    InspectionUpdate,
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
    summary="List Checklist Templates",
    description="A project's templates. The three starter templates are added the first time this is called.",
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
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.ensure_starters(db, project_id, user["id"])
    where: list[Any] = [ChecklistTemplate.project_id == project_id]
    if not include_inactive:
        where.append(ChecklistTemplate.active.is_(True))
    if trade:
        where.append(func.lower(ChecklistTemplate.trade) == trade.lower())
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
    summary="Create a Checklist Template",
    dependencies=perm(P.UPDATE),
)
async def create_template(
    values: ChecklistTemplateIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    t = ChecklistTemplate(created_by_id=user["id"], **values.model_dump(mode="json"))
    db.add(t)
    await db.commit()
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


@router.patch(
    "/templates/{template_id}", response_model=ChecklistTemplateRead, summary="Update a Template", dependencies=perm(P.UPDATE)
)
async def update_template(
    template_id: Id, values: ChecklistTemplateUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    t = await _template(db, template_id, user, held)
    changes = values.model_dump(mode="json", exclude_unset=True)
    if "sections" in changes and changes["sections"] != t.sections:
        t.version += 1
    for key, value in changes.items():
        setattr(t, key, value)
    await db.commit()
    return service.read_template(t)


@router.post(
    "/templates/{template_id}/duplicate",
    response_model=ChecklistTemplateRead,
    status_code=201,
    summary="Duplicate a Template",
    dependencies=perm(P.UPDATE),
)
async def duplicate_template(template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    t = await _template(db, template_id, user, held)
    copy = ChecklistTemplate(
        project_id=t.project_id,
        name=f"{t.name} (copy)"[:200],
        trade=t.trade,
        activity=t.activity,
        description=t.description,
        sections=[dict(s) for s in t.sections],
        created_by_id=user["id"],
    )
    db.add(copy)
    await db.commit()
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


# --- inspections -------------------------------------------------------------------------------------


async def _readable(db: Any, inspection_id: int, user: dict[str, Any], held: frozenset[str]) -> Inspection:
    i = await service.get_inspection(db, inspection_id)
    await readable_project(db, i.project_id, user["id"], held)
    return i


async def _one(db: Any, inspection: Inspection) -> dict[str, Any]:
    return (await service.read_inspections(db, [inspection], with_items=True))[0]


@router.get(
    "/",
    response_model=PaginatedListResponse[InspectionRead],
    summary="List Inspections",
    description="A project's inspections, newest first, without their items. Filter by status, trade, location, "
    "inspector (`me` for yourself) or search text.",
    dependencies=perm(P.READ),
)
async def list_inspections(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    status: InspectionStatus | None = None,
    trade: Annotated[str | None, Query(max_length=100)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    inspector: Annotated[str | None, Query(pattern=r"^(me|\d+)$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Inspection.project_id == project_id]
    if status:
        where.append(Inspection.status == status.value)
    if trade:
        where.append(func.lower(Inspection.trade) == trade.lower())
    if location:
        where.append(func.lower(Inspection.location) == location.lower())
    if inspector:
        where.append(Inspection.inspector_id == (user["id"] if inspector == "me" else int(inspector)))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Inspection.title + " " + Inspection.code).like(like),
                func.lower(func.coalesce(Inspection.location, "") + " " + func.coalesce(Inspection.area, "")).like(like),
            )
        )
    total = await db.scalar(select(func.count()).select_from(Inspection).where(*where))
    rows = (
        await db.execute(
            select(Inspection)
            .where(*where)
            .order_by(Inspection.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_inspections(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=InspectionRead,
    status_code=201,
    summary="Start an Inspection from a Template",
    description="The template's sections and items are copied onto the inspection, so later template edits don't change it.",
    dependencies=perm(P.CREATE),
)
async def create(values: InspectionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    template = await service.get_template(db, values.template_id)
    if template.project_id != values.project_id:
        raise service.TemplateNotFoundError("Template is on another project")
    fields = values.model_dump(exclude={"project_id", "template_id"}, exclude_none=True)
    inspection = await service.create_inspection(db, template, fields, user["id"])
    return await _one(db, inspection)


@router.get(
    "/{inspection_id}", response_model=InspectionRead, summary="Get an Inspection, with its Items", dependencies=perm(P.READ)
)
async def get(inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _readable(db, inspection_id, user, held))


@router.patch(
    "/{inspection_id}", response_model=InspectionRead, summary="Update an Inspection's Details", dependencies=perm(P.UPDATE)
)
async def update(
    inspection_id: Id, values: InspectionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(inspection, key, value)
    await db.commit()
    return await _one(db, inspection)


@router.patch(
    "/{inspection_id}/items",
    response_model=InspectionRead,
    summary="Record Results",
    description="Results (pass, fail, na), numeric readings and notes for some or all items; the score is recalculated. "
    "A reading outside the item's limits scores as a fail. The first answer moves a planned inspection to in_progress. "
    "Attach photos to an item through `/api/v1/files/` with `entity_type=inspection_item` and the item's id.",
    dependencies=perm(P.UPDATE),
)
async def fill(
    inspection_id: Id, values: InspectionItemsFill, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.fill_items(db, inspection, [a.model_dump(exclude_unset=True) for a in values.items], user["id"])
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/complete",
    response_model=InspectionRead,
    summary="Complete an Inspection",
    description="Scores it (pass rate = passed / (passed + failed), N/A excluded) and raises a follow-up for each "
    "failed item: a task linked to the inspection, or, when `follow_ups` picks `ncr` for the item, an NCR linked back "
    "to the item plus an `inspections.item.ncr_requested` event. Refused while items are unanswered (unless "
    "`allow_unanswered`) or while a failed item that requires a photo has none.",
    dependencies=perm(P.TRANSITION),
)
async def complete(
    inspection_id: Id, values: InspectionCompletion, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    events = await service.complete(db, inspection, values.model_dump(), user)
    await service.publish_completion(inspection, events)
    return await _one(db, inspection)


@router.patch(
    "/{inspection_id}/status",
    response_model=InspectionRead,
    summary="Change an Inspection's Status",
    description="planned ↔ in_progress, completed → closed, completed → in_progress (reopen), closed → completed. "
    "Completing goes through `/complete`.",
    dependencies=perm(P.TRANSITION),
)
async def set_status(
    inspection_id: Id, values: InspectionStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.change_status(db, inspection, values.status.value, values.note, user["id"])
    return await _one(db, inspection)


@router.get("/{inspection_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(
    inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    return await service.history(db, await _readable(db, inspection_id, user, held))


@router.get("/{inspection_id}/report.pdf", summary="Inspection Report (PDF)", dependencies=perm(P.READ))
async def report(inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    inspection = await _readable(db, inspection_id, user, held)
    pdf = await service.report_pdf(db, inspection)
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{inspection.code}.pdf"'}
    )


@router.delete("/{inspection_id}", summary="Delete an Inspection", dependencies=perm(P.DELETE))
async def delete(inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _readable(db, inspection_id, user, held))
    await db.commit()
    return {"message": "Inspection deleted"}

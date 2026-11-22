"""Mounted at /api/v1/reporting."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.reporting import available_datasets, available_kpis
from ...infrastructure.reporting.schemas import DatasetInfo, KpiInfo, dataset_info, kpi_info
from ...infrastructure.reporting.tables import pivot, pivot_table
from ...infrastructure.tabular import write_table
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.constants import ProjectStatus
from ..projects.service import readable_project
from ..user.models import User
from . import service
from .builder import build_report
from .builtins import ensure_builtins
from .models import ReportRun, ReportSchedule, ReportTemplate
from .permissions import ReportingPermissionName as P
from .schedules import run_schedule, schedule_next
from .schemas import (
    DatasetRows,
    GenerateIn,
    KpiValue,
    PivotExportIn,
    PivotIn,
    PivotResult,
    PortfolioRow,
    PortfolioSummary,
    RunRead,
    ScheduleIn,
    ScheduleRead,
    TemplateIn,
    TemplateRead,
)
from .service import BadFilterError, Viewer

router = APIRouter(tags=["Reporting"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)]
Name = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


class TemplateNotFoundError(ResourceNotFoundError):
    public_detail = "Report template not found."


class ScheduleNotFoundError(ResourceNotFoundError):
    public_detail = "Scheduled report not found."


class BuiltinTemplateError(ValidationError):
    public_detail = "The shipped templates can't be changed or deleted. Copy one and change the copy."


def _page(items: list[Any], page: int, items_per_page: int, total: int | None = None) -> dict[str, Any]:
    if total is None:
        skip = compute_offset(page, items_per_page)
        items, total = items[skip : skip + items_per_page], len(items)
    return paginated_response(crud_data={"data": items, "total_count": total}, page=page, items_per_page=items_per_page)


# --- registries ----------------------------------------------------------------------------------------


@router.get(
    "/datasets/",
    response_model=PaginatedListResponse[DatasetInfo],
    summary="Datasets You Can Report On",
    dependencies=perm(P.READ),
)
async def list_datasets(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    items = [dataset_info(d) for d in sorted(await available_datasets(db, held, project_id), key=lambda d: d.title)]
    return _page(items, page, items_per_page)


@router.get(
    "/datasets/{dataset}/rows",
    response_model=DatasetRows,
    summary="A Dataset's Rows",
    description="Up to `limit` rows, filtered (JSON `filters`, as for `/data/export`). For the explorer's raw view.",
    dependencies=perm(P.READ),
)
async def dataset_rows(
    dataset: Name,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery = None,
    filters: Annotated[str | None, Query(max_length=4000)] = None,
    limit: Annotated[int, Query(ge=1, le=50_000)] = 5_000,
) -> Any:
    viewer = await Viewer.of(db, user["id"], held)
    found = await service.dataset_for(db, viewer, dataset, project_id)
    try:
        parsed = json.loads(filters) if filters else None
    except json.JSONDecodeError as exc:
        raise BadFilterError("filters must be JSON") from exc
    rows = await service.rows_for(db, viewer, found, project_id, parsed)
    return DatasetRows(dataset=found.name, total=len(rows), rows=rows[:limit])


@router.get("/kpis/", response_model=PaginatedListResponse[KpiInfo], summary="Registered KPIs", dependencies=perm(P.READ))
async def list_kpis(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    return _page([kpi_info(k) for k in await available_kpis(db, held, project_id)], page, items_per_page)


@router.get(
    "/kpi/{project_id}",
    response_model=list[KpiValue],
    summary="A Project's KPIs",
    description="Every KPI registered by a module that is on for the project and that you may read, with a status colour.",
    dependencies=perm(P.READ),
)
async def project_kpis(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.kpi_values(db, project_id, held)


# --- portfolio -----------------------------------------------------------------------------------------

Region = Annotated[str | None, Query(max_length=10)]
BudgetFilter = Literal["over", "on", "none"] | None
Search = Annotated[str | None, Query(max_length=100)]


@router.get(
    "/portfolio/",
    response_model=PaginatedListResponse[PortfolioRow],
    summary="Portfolio",
    description=(
        "Every project you can see with its budget, value and cost to date, variance (budget less forecast cost, "
        "or cost to date while there is no forecast) and forecast margin, plus the KPIs registered for the portfolio. "
        "`budget=over` keeps the projects forecast over budget."
    ),
    dependencies=perm(P.READ),
)
async def portfolio(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    region: Region = None,
    status: ProjectStatus | None = None,
    budget: BudgetFilter = None,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    rows = await service.portfolio(
        db, user["id"], held, region=region, status=status.value if status else None, budget=budget, search=search
    )
    skip = compute_offset(page, items_per_page)
    shown = await service.with_kpis(db, held, rows[skip : skip + items_per_page])
    return _page(shown, page, items_per_page, total=len(rows))


@router.get(
    "/portfolio/summary",
    response_model=PortfolioSummary,
    summary="Portfolio Totals",
    description="The cards above the portfolio table, for the same filters: totals per currency, counts, mean variance.",
    dependencies=perm(P.READ),
)
async def portfolio_summary(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    region: Region = None,
    status: ProjectStatus | None = None,
    budget: BudgetFilter = None,
    search: Search = None,
) -> Any:
    rows = await service.portfolio(
        db, user["id"], held, region=region, status=status.value if status else None, budget=budget, search=search
    )
    return await service.portfolio_summary(db, held, rows, await service.regions_of(db, user["id"], held))


# --- pivot ---------------------------------------------------------------------------------------------


async def _pivot(db: Any, user: dict[str, Any], held: frozenset[str], values: PivotIn) -> tuple[dict[str, Any], Any]:
    viewer = await Viewer.of(db, user["id"], held)
    found = await service.dataset_for(db, viewer, values.dataset, values.project_id)
    labels = {c.key for c in found.columns}
    unknown = [k for k in (*values.rows, *values.columns, *(v.field for v in values.values)) if k != "*" and k not in labels]
    if unknown:
        raise BadFilterError(f"{found.title} has no column {', '.join(unknown)}")
    rows = await service.rows_for(db, viewer, found, values.project_id, values.filters)
    return pivot(rows, values.rows, values.columns, [(v.field, v.agg) for v in values.values]), found


@router.post(
    "/pivot",
    response_model=PivotResult,
    summary="Pivot a Dataset",
    description=(
        "Groups the dataset's rows by `rows` down and `columns` across and aggregates `values` "
        "(sum, avg, count, min, max; field `*` counts rows) on the server, with row, column and grand totals."
    ),
    dependencies=perm(P.READ),
)
async def run_pivot(values: PivotIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    result, _ = await _pivot(db, user, held, values)
    return result


@router.post(
    "/pivot/export",
    summary="Export a Pivot",
    response_class=Response,
    dependencies=perm(P.EXPORT),
)
async def export_pivot(
    values: PivotExportIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Response:
    result, found = await _pivot(db, user, held, values)
    headers, table = pivot_table(result, {c.key: c.label for c in found.columns})
    keys = [f"c{i}" for i in range(len(headers))]
    rows = [dict(zip(keys, line, strict=False)) for line in table]
    body, media, ext = write_table(list(zip(keys, headers, strict=False)), rows, values.format, title=f"{found.title} pivot")
    name = f"{found.name}-pivot-{datetime.now(UTC).strftime('%Y%m%d')}.{ext}"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- templates -----------------------------------------------------------------------------------------


async def _template(db: Any, template_id: int) -> ReportTemplate:
    template: ReportTemplate | None = await db.get(ReportTemplate, template_id)
    if template is None:
        raise TemplateNotFoundError(str(template_id))
    return template


@router.get(
    "/templates/",
    response_model=PaginatedListResponse[TemplateRead],
    summary="Report Templates",
    dependencies=perm(P.READ),
)
async def list_templates(
    db: AsyncSessionDep, _: CurrentUserDep, page: PageDep = 1, items_per_page: ItemsPerPageDep = 50
) -> Any:
    await ensure_builtins(db)
    total = await db.scalar(select(func.count()).select_from(ReportTemplate))
    rows = (
        await db.execute(
            select(ReportTemplate)
            .order_by(ReportTemplate.builtin_key.is_(None), ReportTemplate.name)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page([TemplateRead.model_validate(t) for t in rows], page, items_per_page, total=total or 0)


@router.post(
    "/templates/", response_model=TemplateRead, status_code=201, summary="Create a Template", dependencies=perm(P.CREATE)
)
async def create_template(values: TemplateIn, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    template = ReportTemplate(**values.model_dump(mode="json"), created_by_id=user["id"])
    db.add(template)
    await db.commit()
    return TemplateRead.model_validate(template)


@router.get("/templates/{template_id}", response_model=TemplateRead, summary="Get a Template", dependencies=perm(P.READ))
async def get_template(template_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    return TemplateRead.model_validate(await _template(db, template_id))


@router.put("/templates/{template_id}", response_model=TemplateRead, summary="Change a Template", dependencies=perm(P.UPDATE))
async def update_template(template_id: Id, values: TemplateIn, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    template = await _template(db, template_id)
    if template.builtin_key:
        raise BuiltinTemplateError(template.builtin_key)
    for key, value in values.model_dump(mode="json").items():
        setattr(template, key, value)
    await db.commit()
    return TemplateRead.model_validate(template)


@router.post(
    "/templates/{template_id}/copy",
    response_model=TemplateRead,
    status_code=201,
    summary="Copy a Template",
    dependencies=perm(P.CREATE),
)
async def copy_template(template_id: Id, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    source = await _template(db, template_id)
    copy = ReportTemplate(
        name=f"{source.name} (copy)"[:200],
        description=source.description,
        sections=list(source.sections),
        branding=dict(source.branding),
        landscape=source.landscape,
        created_by_id=user["id"],
    )
    db.add(copy)
    await db.commit()
    return TemplateRead.model_validate(copy)


@router.delete("/templates/{template_id}", summary="Delete a Template", dependencies=perm(P.DELETE))
async def delete_template(template_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> dict[str, str]:
    template = await _template(db, template_id)
    if template.builtin_key:
        raise BuiltinTemplateError(template.builtin_key)
    await db.delete(template)
    await db.commit()
    return {"message": "Template deleted"}


@router.post(
    "/generate",
    summary="Generate a Report",
    description="Builds the template for the project as a PDF or an Excel workbook and returns the file.",
    response_class=Response,
    dependencies=perm(P.EXPORT),
)
async def generate(values: GenerateIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    project = await readable_project(db, values.project_id, user["id"], held) if values.project_id else None
    template = TemplateRead.model_validate(await _template(db, values.template_id))
    body, media, filename = await build_report(
        db,
        await Viewer.of(db, user["id"], held),
        name=template.name,
        sections=template.sections,
        branding=template.branding,
        wide=template.landscape,
        project=project,
        fmt=values.format,
    )
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --- schedules -----------------------------------------------------------------------------------------


async def _schedule(db: Any, schedule_id: int) -> ReportSchedule:
    schedule: ReportSchedule | None = await db.get(ReportSchedule, schedule_id)
    if schedule is None:
        raise ScheduleNotFoundError(str(schedule_id))
    return schedule


async def _read_schedules(db: Any, schedules: list[ReportSchedule]) -> list[ScheduleRead]:
    ids = [s.id for s in schedules]
    names = dict(
        (
            await db.execute(
                select(ReportTemplate.id, ReportTemplate.name).where(ReportTemplate.id.in_({s.template_id for s in schedules}))
            )
        )
        .tuples()
        .all()
    )
    last: dict[int, str] = {}
    if ids:
        latest = (
            select(ReportRun.schedule_id, func.max(ReportRun.id).label("id"))
            .where(ReportRun.schedule_id.in_(ids))
            .group_by(ReportRun.schedule_id)
            .subquery()
        )
        last = dict(
            (await db.execute(select(ReportRun.schedule_id, ReportRun.status).join(latest, latest.c.id == ReportRun.id)))
            .tuples()
            .all()
        )
    return [
        ScheduleRead.model_validate(s).model_copy(
            update={"template_name": names.get(s.template_id), "last_status": last.get(s.id)}
        )
        for s in schedules
    ]


async def _check_schedule(db: Any, values: ScheduleIn, user: dict[str, Any], held: frozenset[str]) -> None:
    await _template(db, values.template_id)
    for project_id in values.project_ids:
        await readable_project(db, project_id, user["id"], held)
    if values.recipient_user_ids:
        found = set((await db.execute(select(User.id).where(User.id.in_(values.recipient_user_ids)))).scalars())
        missing = sorted(set(values.recipient_user_ids) - found)
        if missing:
            raise ScheduleInputError(f"No users {missing}")
    if not values.recipient_user_ids and not values.recipient_emails:
        raise ScheduleInputError("Add at least one recipient.")


class ScheduleInputError(ValidationError):
    public_detail = "Check the schedule's template, projects and recipients."


@router.get(
    "/schedules/",
    response_model=PaginatedListResponse[ScheduleRead],
    summary="Scheduled Reports",
    dependencies=perm(P.READ),
)
async def list_schedules(
    db: AsyncSessionDep, _: CurrentUserDep, page: PageDep = 1, items_per_page: ItemsPerPageDep = 50
) -> Any:
    total = await db.scalar(select(func.count()).select_from(ReportSchedule))
    rows = list(
        (
            await db.execute(
                select(ReportSchedule)
                .order_by(ReportSchedule.name)
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    return _page(await _read_schedules(db, rows), page, items_per_page, total=total or 0)


@router.post(
    "/schedules/", response_model=ScheduleRead, status_code=201, summary="Schedule a Report", dependencies=perm(P.CREATE)
)
async def create_schedule(values: ScheduleIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await _check_schedule(db, values, user, held)
    schedule = ReportSchedule(**values.model_dump(), created_by_id=user["id"])
    schedule.next_run_at = schedule_next(schedule, datetime.now(UTC)) if schedule.enabled else None
    db.add(schedule)
    await db.commit()
    return (await _read_schedules(db, [schedule]))[0]


@router.get(
    "/schedules/{schedule_id}", response_model=ScheduleRead, summary="Get a Scheduled Report", dependencies=perm(P.READ)
)
async def get_schedule(schedule_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    return (await _read_schedules(db, [await _schedule(db, schedule_id)]))[0]


@router.put(
    "/schedules/{schedule_id}", response_model=ScheduleRead, summary="Change a Scheduled Report", dependencies=perm(P.UPDATE)
)
async def update_schedule(
    schedule_id: Id, values: ScheduleIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    schedule = await _schedule(db, schedule_id)
    await _check_schedule(db, values, user, held)
    for key, value in values.model_dump().items():
        setattr(schedule, key, value)
    schedule.created_by_id = user["id"]
    schedule.next_run_at = schedule_next(schedule, datetime.now(UTC)) if schedule.enabled else None
    await db.commit()
    return (await _read_schedules(db, [schedule]))[0]


@router.delete("/schedules/{schedule_id}", summary="Delete a Scheduled Report", dependencies=perm(P.DELETE))
async def delete_schedule(schedule_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> dict[str, str]:
    await db.delete(await _schedule(db, schedule_id))
    await db.commit()
    return {"message": "Schedule deleted"}


@router.post(
    "/schedules/{schedule_id}/send",
    response_model=list[RunRead],
    summary="Send a Scheduled Report Now",
    description="Generates and emails it straight away, without moving its next scheduled time.",
    dependencies=perm(P.UPDATE),
)
async def send_now(schedule_id: Id, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    schedule = await _schedule(db, schedule_id)
    runs = await run_schedule(db, schedule, trigger="manual", triggered_by_id=user["id"])
    return [RunRead.model_validate(r) for r in runs]


@router.get(
    "/schedules/{schedule_id}/runs/",
    response_model=PaginatedListResponse[RunRead],
    summary="A Scheduled Report's Run History",
    dependencies=perm(P.READ),
)
async def schedule_runs(
    schedule_id: Id, db: AsyncSessionDep, _: CurrentUserDep, page: PageDep = 1, items_per_page: ItemsPerPageDep = 50
) -> Any:
    await _schedule(db, schedule_id)
    where = ReportRun.schedule_id == schedule_id
    total = await db.scalar(select(func.count()).select_from(ReportRun).where(where))
    rows = (
        await db.execute(
            select(ReportRun)
            .where(where)
            .order_by(ReportRun.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return _page([RunRead.model_validate(r) for r in rows], page, items_per_page, total=total or 0)

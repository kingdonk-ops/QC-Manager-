"""Mounted at /api/v1/evm. Every route reads the project through ``projects``' visibility rule first."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.tabular import TableError, read_table, write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import field, importer, report, service
from .constants import Basis, EacMethod, GroupBy, Interval
from .models import BudgetSnapshot, EvmSettings, ProgressRecord, WorkPackage
from .permissions import EvmPermissionName as P
from .schemas import (
    EvmCashflow,
    EvmFieldReport,
    EvmMetricsReport,
    EvmProgressBatch,
    EvmProgressEntry,
    EvmProgressImportReport,
    EvmProgressSaved,
    EvmProgressSheet,
    EvmSCurve,
    EvmSettingsIn,
    EvmSettingsRead,
    EvmSnapshotCompare,
    EvmSnapshotCreate,
    EvmSnapshotRead,
    EvmSnapshotUpdate,
    EvmWorkPackageCreate,
    EvmWorkPackageRead,
    EvmWorkPackageUpdate,
)

router = APIRouter(tags=["Earned Value"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
DataDate = Annotated[date | None, Query(alias="date", description="Data date; default the project's")]
MAX_IMPORT_BYTES = 10 * 1024 * 1024


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# --- work packages ------------------------------------------------------------------------------------


@router.get(
    "/work-packages/",
    response_model=PaginatedListResponse[EvmWorkPackageRead],
    summary="List Work Packages",
    description="A project's packages in sort order. Filter by control account, discipline or a code/name search.",
    dependencies=perm(P.READ),
)
async def list_packages(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    control_account: Annotated[str | None, Query(max_length=60)] = None,
    discipline: Annotated[str | None, Query(max_length=60)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [WorkPackage.project_id == project_id]
    if control_account:
        where.append(WorkPackage.control_account == control_account)
    if discipline:
        where.append(WorkPackage.discipline == discipline)
    if search:
        where.append(func.lower(WorkPackage.code + " " + WorkPackage.name).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(WorkPackage).where(*where))
    rows = await db.execute(
        select(WorkPackage)
        .where(*where)
        .order_by(WorkPackage.sort_order, WorkPackage.code)
        .offset(compute_offset(page, items_per_page))
        .limit(items_per_page)
    )
    data = {"data": [service.read_package(wp) for wp in rows.scalars()], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/work-packages/",
    response_model=EvmWorkPackageRead,
    status_code=201,
    summary="Add a Work Package",
    dependencies=perm(P.CREATE),
)
async def create_package(
    values: EvmWorkPackageCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    return service.read_package(await service.create_package(db, values.model_dump()))


@router.get(
    "/work-packages/{package_id}", response_model=EvmWorkPackageRead, summary="Get a Work Package", dependencies=perm(P.READ)
)
async def get_package(package_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    wp = await service.get_package(db, package_id)
    await readable_project(db, wp.project_id, user["id"], held)
    return service.read_package(wp)


@router.patch(
    "/work-packages/{package_id}",
    response_model=EvmWorkPackageRead,
    summary="Change a Work Package",
    dependencies=perm(P.UPDATE),
)
async def update_package(
    package_id: Id, values: EvmWorkPackageUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    wp = await service.get_package(db, package_id)
    await readable_project(db, wp.project_id, user["id"], held)
    return service.read_package(await service.update_package(db, wp, values.model_dump(exclude_unset=True)))


@router.delete("/work-packages/{package_id}", summary="Delete a Work Package and its progress", dependencies=perm(P.DELETE))
async def delete_package(
    package_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    wp = await service.get_package(db, package_id)
    await readable_project(db, wp.project_id, user["id"], held)
    await db.delete(wp)
    await db.commit()
    return {"message": "Work package deleted"}


# --- settings -----------------------------------------------------------------------------------------


async def _settings_read(db: AsyncSessionDep, project_id: int, currency: str) -> EvmSettingsRead:
    current = await service.settings(db, project_id)
    latest = await db.scalar(select(func.max(ProgressRecord.data_date)).where(ProgressRecord.project_id == project_id))
    has_cost = await db.scalar(
        select(func.count()).select_from(WorkPackage).where(WorkPackage.project_id == project_id, WorkPackage.budget_cost > 0)
    )
    return EvmSettingsRead(
        project_id=project_id,
        data_date=current.data_date,
        eac_method=EacMethod(current.eac_method),
        latest_progress_date=latest,
        cost_available=bool(has_cost),
        currency=currency,
    )


@router.get(
    "/{project_id}/settings", response_model=EvmSettingsRead, summary="Data Date and EAC Method", dependencies=perm(P.READ)
)
async def get_settings(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await _settings_read(db, project_id, project.currency)


@router.put("/{project_id}/settings", response_model=EvmSettingsRead, summary="Set the Data Date", dependencies=perm(P.UPDATE))
async def set_settings(
    project_id: Id, values: EvmSettingsIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    current = await db.get(EvmSettings, project_id)
    if current is None:
        db.add(EvmSettings(project_id=project_id, data_date=values.data_date, eac_method=values.eac_method.value))
    else:
        current.data_date = values.data_date
        current.eac_method = values.eac_method.value
    await db.commit()
    return await _settings_read(db, project_id, project.currency)


# --- progress -----------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/progress",
    response_model=EvmProgressSheet,
    summary="Progress as at a Date",
    description="Every package with its latest progress on or before the date (default: the project's data date).",
    dependencies=perm(P.READ),
)
async def get_progress(
    project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, on: DataDate = None
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    on = await service.data_date(db, project_id, on)
    return {"project_id": project_id, "data_date": on, "rows": await service.progress_sheet(db, project_id, on)}


@router.post(
    "/{project_id}/progress",
    response_model=EvmProgressSaved,
    summary="Record Progress for a Data Date",
    description="Cumulative percent complete (or earned hours), actual hours and cost per package. "
    "Values left out carry forward from the package's previous record.",
    dependencies=perm(P.UPDATE),
)
async def post_progress(
    project_id: Id, values: EvmProgressBatch, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    saved = await service.save_progress(db, project_id, values.data_date, values.entries, user["id"], values.set_data_date)
    return {"data_date": values.data_date, "saved": saved}


@router.post(
    "/{project_id}/progress/from-field",
    response_model=EvmFieldReport,
    summary="Pull Progress from the Field",
    description="Actual hours from signed workface logs and percent complete from verified progress, for each "
    "package matched to the asset breakdown by WBS code or by its linked P6 activity. `dry_run` reports without saving.",
    dependencies=perm(P.UPDATE),
)
async def progress_from_field(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
    dry_run: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    on = await service.data_date(db, project_id, on)
    entries, rows = await field.field_progress(db, project_id, on)
    if entries and not dry_run:
        await service.save_progress(db, project_id, on, entries, user["id"], False)
    return {"data_date": on, "dry_run": dry_run, "saved": 0 if dry_run else len(entries), "rows": rows}


@router.post(
    "/{project_id}/import",
    response_model=EvmProgressImportReport,
    summary="Import Progress from Excel or CSV",
    description="Columns: `code`, `percent` (or `earned hours`), `actual hours`; optional `actual cost`, `comment`. "
    "`dry_run` reports without saving.",
    dependencies=perm(P.IMPORT),
)
async def import_progress(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    data_date: Annotated[date | None, Form()] = None,
    dry_run: Annotated[bool, Form()] = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    on = await service.data_date(db, project_id, data_date)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    try:
        columns, rows = read_table(data, file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    parsed, problems = importer.parse(columns, rows)
    by_code = {wp.code.lower(): wp for wp in await service.packages(db, project_id)}
    entries: list[EvmProgressEntry] = []
    for row in parsed:
        wp = by_code.get(row["code"].lower())
        if wp is None:
            problems.append((row["row"], f"{row['code']}: no work package with that code"))
            continue
        if row["earned_hours"] is not None and not wp.budget_hours:
            problems.append((row["row"], f"{row['code']}: no budget hours to earn against"))
            continue
        fields = {k: row[k] for k in ("percent_complete", "earned_hours", "actual_hours", "actual_cost", "comment")}
        entries.append(EvmProgressEntry(work_package_id=wp.id, **fields))
    if entries and not dry_run:
        await service.save_progress(db, project_id, on, entries, user["id"])
    return {
        "data_date": on,
        "rows": len(rows),
        "saved": 0 if dry_run else len(entries),
        "dry_run": dry_run,
        "issues": [{"row": r, "message": m} for r, m in sorted(problems)],
    }


# --- analysis -----------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/metrics",
    response_model=EvmMetricsReport,
    summary="Earned Value Metrics",
    description="PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC and TCPI as at the data date, on hours (default) or cost, "
    "per package, control account, discipline or for the whole project. Ratios with nothing to divide by are null.",
    dependencies=perm(P.READ),
)
async def get_metrics(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
    basis: Basis = Basis.HOURS,
    group_by: GroupBy = GroupBy.PACKAGE,
    eac_method: EacMethod | None = None,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.metrics_report(db, project, on, basis, group_by, eac_method)


@router.get(
    "/{project_id}/s-curve",
    response_model=EvmSCurve,
    summary="S-Curve",
    description="Cumulative PV, EV and AC per week or month, the forecast from AC to EAC, and the baseline's PV "
    "(the snapshot given, else the active baseline). Period values feed histograms.",
    dependencies=perm(P.READ),
)
async def get_s_curve(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
    interval: Interval = Interval.MONTH,
    basis: Basis = Basis.HOURS,
    snapshot_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.s_curve_report(db, project, on, interval, basis, snapshot_id)


@router.get(
    "/{project_id}/cashflow",
    response_model=EvmCashflow,
    summary="Monthly Cost EvmCashflow",
    description="Planned against actual cost per month from the packages' cost budgets; "
    "the CVR module's cashflow alongside when it's switched on.",
    dependencies=perm(P.READ),
)
async def get_cashflow(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await service.cashflow(db, project)


@router.get("/{project_id}/report.pdf", summary="Earned Value Report (PDF)", dependencies=perm(P.EXPORT))
async def report_pdf(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
    basis: Basis = Basis.HOURS,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    by_package = await service.metrics_report(db, project, on, basis, GroupBy.PACKAGE, None)
    by_account = await service.metrics_report(db, project, by_package["data_date"], basis, GroupBy.ACCOUNT, None)
    curve = await service.s_curve_report(db, project, by_package["data_date"], Interval.MONTH, basis, None)
    body = report.pdf(project, by_package, by_account["rows"], curve)
    name = f"evm-{project.code}-{by_package['data_date']}.pdf"
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get(
    "/{project_id}/export",
    summary="Export Metrics per Package (Excel/CSV)",
    description="One row per package with its metrics; the `code`, `percent` and `actual hours` columns re-import as progress.",
    dependencies=perm(P.EXPORT),
)
async def export(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
    basis: Basis = Basis.HOURS,
    format: Annotated[str, Query(pattern="^(xlsx|csv)$")] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    metrics = await service.metrics_report(db, project, on, basis, GroupBy.PACKAGE, None)
    sheet = {r["work_package_id"]: r for r in await service.progress_sheet(db, project_id, metrics["data_date"])}
    rows = []
    for r in metrics["rows"]:
        progress = sheet.get(r["work_package_id"], {})
        rows.append(
            {
                **r,
                "code": r["key"],
                "name": progress.get("name"),
                "percent_complete": progress.get("percent_complete"),
                "actual_hours": progress.get("actual_hours"),
            }
        )
    body, media_type, ext = write_table(report.EXPORT_COLUMNS, rows, format, title="Earned value")
    name = f"evm-{project.code}-{metrics['data_date']}.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- snapshots ----------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/snapshots/",
    response_model=PaginatedListResponse[EvmSnapshotRead],
    summary="List Budget Snapshots",
    dependencies=perm(P.READ),
)
async def list_snapshots(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = BudgetSnapshot.project_id == project_id
    total = await db.scalar(select(func.count()).select_from(BudgetSnapshot).where(where))
    rows = await db.execute(
        select(BudgetSnapshot)
        .where(where)
        .order_by(BudgetSnapshot.id.desc())
        .offset(compute_offset(page, items_per_page))
        .limit(items_per_page)
    )
    data = {"data": [service.read_snapshot(s) for s in rows.scalars()], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/{project_id}/snapshots/",
    response_model=EvmSnapshotRead,
    status_code=201,
    summary="Freeze the Budget",
    description="Copies every package's budget, dates and curve. `set_as_baseline` re-baselines: "
    "the new snapshot becomes the active baseline.",
    dependencies=perm(P.CREATE),
)
async def create_snapshot(
    project_id: Id, values: EvmSnapshotCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    snap = await service.create_snapshot(db, project_id, values.name, values.note, values.set_as_baseline, user["id"])
    return service.read_snapshot(snap)


@router.patch(
    "/{project_id}/snapshots/{snapshot_id}",
    response_model=EvmSnapshotRead,
    summary="Rename a Snapshot or Make it the Baseline",
    dependencies=perm(P.UPDATE),
)
async def update_snapshot(
    project_id: Id,
    snapshot_id: Id,
    values: EvmSnapshotUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    snap = await service.get_snapshot(db, project_id, snapshot_id)
    return service.read_snapshot(await service.update_snapshot(db, snap, values.model_dump(exclude_unset=True)))


@router.delete("/{project_id}/snapshots/{snapshot_id}", summary="Delete a Snapshot", dependencies=perm(P.DELETE))
async def delete_snapshot(
    project_id: Id, snapshot_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await readable_project(db, project_id, user["id"], held)
    await db.delete(await service.get_snapshot(db, project_id, snapshot_id))
    await db.commit()
    return {"message": "Snapshot deleted"}


@router.get(
    "/{project_id}/snapshots/{snapshot_id}/compare",
    response_model=EvmSnapshotCompare,
    summary="Compare the Current Budget with a Snapshot",
    description="Per package (matched on code): budget hours and cost, planned dates, and planned hours to the data date.",
    dependencies=perm(P.READ),
)
async def compare_snapshot(
    project_id: Id,
    snapshot_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    on: DataDate = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    snap = await service.get_snapshot(db, project_id, snapshot_id)
    on = await service.data_date(db, project_id, on)
    current = [service.Plan.of(wp) for wp in await service.packages(db, project_id)]
    frozen = [service.Plan.thawed(r) for r in snap.packages]
    return {"snapshot": service.read_snapshot(snap), **service.compare(frozen, current, on)}

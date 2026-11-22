"""P6 mirror, linking, schedule facts, verified progress and actuals export. Included by ``router.py``."""

import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastapi.exceptions import HTTPException
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import p6_service as p6
from . import service
from .interchange import ImportFormatError, parse
from .p6_models import P6Change, P6Export, P6Import, P6Link, P6Rule, ProgressVerification
from .p6_schemas import (
    ExportCreate,
    P6ChangeRead,
    P6ChangeUpdate,
    P6ExportRead,
    P6ImportRead,
    P6LinkCreate,
    P6LinkRead,
    P6RuleCreate,
    P6RuleRead,
    P6RuleUpdate,
    P6Settings,
    ProgressRow,
    RuleTest,
    RuleTestResult,
    ScheduleFacts,
    UnmatchedActivity,
    VerificationCreate,
    VerificationRead,
)
from .permissions import SchedulePermissionName as P

router = APIRouter(tags=["4D Schedule: P6 mirror"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
MAX_IMPORT_BYTES = 20 * 1024 * 1024


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _import_read(imp: P6Import, reused: bool = False) -> P6ImportRead:
    return P6ImportRead.model_validate(imp).model_copy(update={"reused": reused})


# --- imports -------------------------------------------------------------------------------------


@router.post(
    "/{project_id}/p6/imports",
    response_model=P6ImportRead,
    status_code=201,
    summary="Upload a P6 Schedule for Preview",
    description="XER or P6 XML (MS Project XML also works). Stages the file, keeps the original, and writes the "
    "change-impact report; nothing changes until the import is committed. The same file twice returns the first "
    "import (`reused`). `create_missing` lets commit create breakdown nodes the names call for, under "
    "`create_under_node_id` when the top level needs a parent.",
    dependencies=perm(P.IMPORT),
)
async def upload(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    create_missing: Annotated[bool, Form()] = False,
    create_under_node_id: Annotated[int | None, Form(ge=1, le=MAX_INTEGER_ID)] = None,
) -> P6ImportRead:
    project = await readable_project(db, project_id, user["id"], held)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=422, detail="Schedule files are limited to 20 MB.")
    try:
        parsed = parse(data)
    except ImportFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if create_under_node_id:
        await p6.tree.get_node(db, create_under_node_id, project.id)
    options = {"create_missing": create_missing, "create_under_node_id": create_under_node_id}
    name = (file.filename or "schedule").replace("/", "_").replace("\\", "_")
    imp, reused = await p6.create_import(db, project, data, name, parsed, options, user["id"])
    return _import_read(imp, reused)


@router.get(
    "/{project_id}/p6/imports/",
    response_model=PaginatedListResponse[P6ImportRead],
    summary="P6 Imports",
    dependencies=perm(P.READ),
)
async def list_imports(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    rows = (
        await db.execute(
            select(P6Import)
            .where(P6Import.project_id == project_id)
            .order_by(P6Import.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [_import_read(r).model_dump() for r in rows], "total_count": await p6.count_imports(db, project_id)}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/{project_id}/p6/imports/{import_id}", response_model=P6ImportRead, summary="A P6 Import", dependencies=perm(P.READ)
)
async def get_import(
    project_id: Id, import_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> P6ImportRead:
    await readable_project(db, project_id, user["id"], held)
    return _import_read(await p6.get_import(db, project_id, import_id))


@router.get("/{project_id}/p6/imports/{import_id}/history", summary="A P6 Import's History", dependencies=perm(P.READ))
async def import_history(
    project_id: Id, import_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    await readable_project(db, project_id, user["id"], held)
    imp = await p6.get_import(db, project_id, import_id)
    return await history_of(db, p6.ENTITY_IMPORT, imp.id)


@router.get(
    "/{project_id}/p6/imports/{import_id}/changes/",
    response_model=PaginatedListResponse[P6ChangeRead],
    summary="The Change-Impact Report",
    description="New, changed, renumbered, removed-in-source and restored activities, with date shifts and the "
    "linked nodes each change touches.",
    dependencies=perm(P.READ),
)
async def list_changes(
    project_id: Id,
    import_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    change_type: Annotated[str | None, Query(max_length=30)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    imp = await p6.get_import(db, project_id, import_id)
    where: list[Any] = [P6Change.import_id == imp.id]
    if change_type:
        where.append(P6Change.change_type == change_type)
    total = await db.scalar(select(func.count()).select_from(P6Change).where(*where))
    rows = (
        await db.execute(
            select(P6Change)
            .where(*where)
            .order_by(P6Change.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [P6ChangeRead.model_validate(r).model_dump() for r in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.patch(
    "/{project_id}/p6/imports/{import_id}/changes/{change_id}",
    response_model=P6ChangeRead,
    summary="Exclude or Include a Change",
    dependencies=perm(P.IMPORT),
)
async def update_change(
    project_id: Id,
    import_id: Id,
    change_id: Id,
    values: P6ChangeUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    imp = await p6.get_import(db, project_id, import_id)
    ch = await p6.get_change(db, imp, change_id)
    return await p6.set_excluded(db, imp, ch, values.excluded)


@router.post(
    "/{project_id}/p6/imports/{import_id}/commit",
    response_model=P6ImportRead,
    summary="Commit a P6 Import",
    description="Applies every change not excluded in one transaction, links activities by the name grammar, "
    "and recalculates. Never deletes: activities missing from the file are marked removed from schedule.",
    dependencies=perm(P.IMPORT),
)
async def commit_import(
    project_id: Id, import_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> P6ImportRead:
    project = await readable_project(db, project_id, user["id"], held)
    imp = await p6.get_import(db, project_id, import_id)
    return _import_read(await p6.commit(db, project, imp, user["id"]))


@router.post(
    "/{project_id}/p6/imports/{import_id}/discard",
    response_model=P6ImportRead,
    summary="Discard a P6 Import",
    dependencies=perm(P.IMPORT),
)
async def discard_import(
    project_id: Id, import_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> P6ImportRead:
    await readable_project(db, project_id, user["id"], held)
    imp = await p6.get_import(db, project_id, import_id)
    await p6.discard(db, imp, user["id"])
    return _import_read(imp)


# --- rules and settings --------------------------------------------------------------------------


@router.get("/{project_id}/p6/rules", response_model=list[P6RuleRead], summary="P6 Mapping Rules", dependencies=perm(P.READ))
async def list_rules(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    rules = await p6.rules_of(db, project)
    await db.commit()
    return rules


@router.post(
    "/{project_id}/p6/rules", response_model=P6RuleRead, status_code=201, summary="Add a P6 Rule", dependencies=perm(P.IMPORT)
)
async def create_rule(
    project_id: Id, values: P6RuleCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await p6.create_rule(db, project, values.model_dump(mode="json"))


@router.patch(
    "/{project_id}/p6/rules/{rule_id}", response_model=P6RuleRead, summary="Change a P6 Rule", dependencies=perm(P.IMPORT)
)
async def update_rule(
    project_id: Id, rule_id: Id, values: P6RuleUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    rule = await p6.get_rule(db, project_id, rule_id)
    return await p6.update_rule(db, rule, values.model_dump(mode="json", exclude_unset=True))


@router.delete("/{project_id}/p6/rules/{rule_id}", status_code=204, summary="Delete a P6 Rule", dependencies=perm(P.IMPORT))
async def delete_rule(
    project_id: Id, rule_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> None:
    await readable_project(db, project_id, user["id"], held)
    rule: P6Rule = await p6.get_rule(db, project_id, rule_id)
    await db.delete(rule)
    await db.commit()


@router.post(
    "/{project_id}/p6/rules/test",
    response_model=list[RuleTestResult],
    summary="Test the Rules Against Sample Names",
    description="Parses each sample with the project's grammars (or `pattern`), applies aliases and eligibility, "
    "and says which node it would link to. Writes nothing.",
    dependencies=perm(P.READ),
)
async def test_rules(
    project_id: Id, values: RuleTest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    out = await p6.test_rules(db, project, values.model_dump(mode="json"))
    await db.commit()
    return out


@router.get("/{project_id}/p6/settings", response_model=P6Settings, summary="P6 Settings", dependencies=perm(P.READ))
async def get_p6_settings(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    s = await p6.settings_of(db, project)
    await db.commit()
    return P6Settings(critical_definition=s.p6_critical_definition, critical_float_hours=s.p6_critical_float_hours)


@router.put("/{project_id}/p6/settings", response_model=P6Settings, summary="Change P6 Settings", dependencies=perm(P.UPDATE))
async def put_p6_settings(
    project_id: Id, values: P6Settings, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    s = await p6.settings_of(db, project)
    s.p6_critical_definition, s.p6_critical_float_hours = values.critical_definition.value, values.critical_float_hours
    await db.commit()
    return values


# --- links ---------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/p6/links/",
    response_model=PaginatedListResponse[P6LinkRead],
    summary="Activity ↔ Node Links",
    dependencies=perm(P.READ),
)
async def list_links(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    activity_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    status: Annotated[str | None, Query(pattern=r"^(confirmed|proposed)$")] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [P6Link.project_id == project_id]
    if activity_id:
        where.append(P6Link.activity_id == activity_id)
    if node_id:
        where.append(P6Link.node_id == node_id)
    if status:
        where.append(P6Link.status == status)
    total = await db.scalar(select(func.count()).select_from(P6Link).where(*where))
    rows = list(
        (
            await db.execute(
                select(P6Link)
                .where(*where)
                .order_by(P6Link.id)
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await p6.read_links(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/{project_id}/p6/unmatched/",
    response_model=PaginatedListResponse[UnmatchedActivity],
    summary="Unmatched Activities",
    description="Eligible, active mirrored activities with no confirmed link, with why the grammar didn't link "
    "them and any proposed links.",
    dependencies=perm(P.READ),
)
async def list_unmatched(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    rows, total = await p6.unmatched(db, project_id, compute_offset(page, items_per_page), items_per_page)
    return paginated_response(crud_data={"data": rows, "total_count": total}, page=page, items_per_page=items_per_page)


@router.post(
    "/{project_id}/p6/activities/{activity_id}/links",
    response_model=P6LinkRead,
    status_code=201,
    summary="Link an Activity to a Node by Hand",
    description="Existing links stay. `remember` links later activities with the same name the same way.",
    dependencies=perm(P.IMPORT),
)
async def link_activity(
    project_id: Id,
    activity_id: Id,
    values: P6LinkCreate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    act = await service.get_activity(db, activity_id)
    link = await p6.link_manually(db, project, act, values.node_id, values.work_window, values.remember, user["id"])
    return (await p6.read_links(db, [link]))[0]


@router.post(
    "/{project_id}/p6/links/{link_id}/confirm",
    response_model=P6LinkRead,
    summary="Confirm a Proposed Link",
    dependencies=perm(P.IMPORT),
)
async def confirm_link(
    project_id: Id, link_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    link = await p6.confirm_link(db, await p6.get_link(db, project_id, link_id))
    return (await p6.read_links(db, [link]))[0]


@router.delete("/{project_id}/p6/links/{link_id}", status_code=204, summary="Remove a Link", dependencies=perm(P.IMPORT))
async def delete_link(
    project_id: Id, link_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> None:
    await readable_project(db, project_id, user["id"], held)
    await db.delete(await p6.get_link(db, project_id, link_id))
    await db.commit()


@router.get(
    "/{project_id}/p6/facts",
    response_model=ScheduleFacts,
    summary="Schedule Facts of a Node",
    description="Total float and critical path of the P6 activities linked to the node (or above or below it), "
    "as of the last committed import. Other modules' rules may read these; they never block by themselves.",
    dependencies=perm(P.READ),
)
async def facts(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    node_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    out = await p6.facts_for_node(db, project, node_id)
    await db.commit()
    return out


# --- verified progress ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/progress/verifications",
    response_model=VerificationRead,
    status_code=201,
    summary="Record Verified Progress",
    description="Verified quantity to date on a progress-unit node. Cite a completed inspection, or attest it "
    "yourself (needs schedule.review). Only verified quantities count as earned.",
    dependencies=perm(P.REVIEW),
)
async def add_verification(
    project_id: Id, values: VerificationCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    v = await p6.add_verification(db, project, values.model_dump(), user["id"])
    return (await p6.read_verifications(db, [v]))[0]


@router.get(
    "/{project_id}/progress/verifications/",
    response_model=PaginatedListResponse[VerificationRead],
    summary="Verified Progress Records",
    dependencies=perm(P.READ),
)
async def list_verifications(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [ProgressVerification.project_id == project_id]
    if node_id:
        where.append(ProgressVerification.node_id == node_id)
    total = await db.scalar(select(func.count()).select_from(ProgressVerification).where(*where))
    rows = list(
        (
            await db.execute(
                select(ProgressVerification)
                .where(*where)
                .order_by(ProgressVerification.verified_on.desc(), ProgressVerification.id.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await p6.read_verifications(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.delete(
    "/{project_id}/progress/verifications/{verification_id}",
    status_code=204,
    summary="Remove a Verification",
    dependencies=perm(P.REVIEW),
)
async def delete_verification(
    project_id: Id, verification_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> None:
    await readable_project(db, project_id, user["id"], held)
    await db.delete(await p6.get_verification(db, project_id, verification_id))
    await db.commit()


# --- actuals export ------------------------------------------------------------------------------


@router.get(
    "/{project_id}/p6/progress",
    response_model=list[ProgressRow],
    summary="Verified Progress per Linked Activity",
    description="What the next export would send: verified percent complete and actual dates per linked P6 "
    "activity, beside P6's own figures and the self-reported percent.",
    dependencies=perm(P.READ),
)
async def progress_rows(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await p6.progress_rows(db, project)


@router.post(
    "/{project_id}/p6/exports",
    response_model=P6ExportRead,
    status_code=201,
    summary="Export Actuals for P6",
    description="Snapshots verified progress as an XER update, P6 XML or CSV for the scheduler to import; "
    "download it from `/exports/{id}/download`.",
    dependencies=perm(P.EXPORT),
)
async def create_export(
    project_id: Id, values: ExportCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    return await p6.create_export(db, project, values.format.value, values.only_changed, user["id"])


@router.get(
    "/{project_id}/p6/exports/",
    response_model=PaginatedListResponse[P6ExportRead],
    summary="Export History",
    dependencies=perm(P.READ),
)
async def list_exports(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    total = await db.scalar(select(func.count()).select_from(P6Export).where(P6Export.project_id == project_id))
    rows = (
        await db.execute(
            select(P6Export)
            .where(P6Export.project_id == project_id)
            .order_by(P6Export.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [P6ExportRead.model_validate(r).model_dump() for r in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/{project_id}/p6/exports/{export_id}/download", summary="Download an Export", dependencies=perm(P.EXPORT))
async def download_export(
    project_id: Id, export_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    exp = await p6.get_export(db, project_id, export_id)
    body, media, ext = p6.render_export(exp, project)
    code = re.sub(r"[^A-Za-z0-9_.-]", "_", project.code)
    stamp = exp.data_date.isoformat() if exp.data_date else date.today().isoformat()
    return Response(
        body, media_type=media, headers={"Content-Disposition": f'attachment; filename="p6-actuals-{code}-{stamp}.{ext}"'}
    )

"""Mounted at /api/v1/issues: the issues engine (punch and NCR), its registers and its templates."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.tabular import write_table
from ..asset_tree.service import get_node
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from . import templates as tpl
from .constants import AnchorKind, IssueType, MdrEffect, NcrStatus, Origin, PunchCategory, Severity, Visibility
from .models import IssueTemplate, IssueTemplateRevision, Ncr
from .permissions import NcrPermissionName as P
from .schemas import (
    CategoryUpsert,
    DefaultTemplateSet,
    FlagOverride,
    FlagOverrideRead,
    IssueCreate,
    IssueUpdate,
    NcrRead,
    RaiseExternal,
    TemplateCreate,
    TemplateDraft,
    Transition,
    Upgrade,
    VoidIssue,
)

issues_router = APIRouter(tags=["Issues"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
OptProjectQ = Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)]
CategoryPath = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _layer_access(
    db: Any, project_id: int | None, user: dict[str, Any], held: frozenset[str], *, write: bool = False
) -> None:
    """Project rows: the project must be readable (and ``ncr.manage`` to write). Library rows: ``ncr.configure``."""
    if project_id is not None:
        await readable_project(db, project_id, user["id"], held)
        if write:
            service.require(held, user, P.MANAGE)
    elif write:
        service.require(held, user, P.CONFIGURE)


# --- register ----------------------------------------------------------------------------------------


@issues_router.get(
    "/",
    response_model=PaginatedListResponse[NcrRead],
    summary="List Issues",
    description=(
        "A project's punch items and NCRs, newest first. `node_id` narrows to an asset node's scope (descendants, "
        "Items and lineage); `linked=node:12` or `item:7` to issues linked to that record. External callers only see "
        "client-visible issues."
    ),
    dependencies=perm(P.READ),
)
async def list_issues(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    issue_type: IssueType | None = None,
    status: NcrStatus | None = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    punch_category: PunchCategory | None = None,
    severity: Severity | None = None,
    origin: Origin | None = None,
    visibility: Visibility | None = None,
    mdr_effect: MdrEffect | None = None,
    node_id: OptProjectQ = None,
    item_id: OptProjectQ = None,
    location_node_id: OptProjectQ = None,
    linked: Annotated[str | None, Query(pattern=r"^(node|item):\d{1,10}$")] = None,
    open_only: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    external = service.is_external(user, held)
    where = await _where(
        db, project_id, external, issue_type, status, category, punch_category, severity, origin, visibility,
        mdr_effect, node_id, item_id, location_node_id, linked, open_only, search,
    )  # fmt: skip
    total = await db.scalar(select(func.count()).select_from(Ncr).where(*where))
    rows = list(
        (
            await db.execute(
                select(Ncr)
                .where(*where)
                .order_by(Ncr.id.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await service.read_ncrs(db, rows, external=external), "total_count": total or 0}
    if external:
        await service.mark_client_seen(db, [r.id for r in rows], "api")
        await db.commit()
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


async def _where(
    db: Any,
    project_id: int,
    external: bool,
    issue_type: IssueType | None,
    status: NcrStatus | None,
    category: str | None,
    punch_category: PunchCategory | None,
    severity: Severity | None,
    origin: Origin | None,
    visibility: Visibility | None,
    mdr_effect: MdrEffect | None,
    node_id: int | None,
    item_id: int | None,
    location_node_id: int | None,
    linked: str | None,
    open_only: bool,
    search: str | None,
) -> list[Any]:
    scope = None
    if node_id:
        await get_node(db, node_id, project_id)
        scope = await service.scope_node_ids(db, [node_id])
    link = None
    if linked:
        kind, target = linked.split(":")
        link = (AnchorKind(kind).value, int(target))
    return service.filters(
        project_id,
        status.value if status else None,
        severity.value if severity else None,
        None,
        None,
        open_only,
        search,
        issue_type=issue_type.value if issue_type else None,
        category=category,
        punch_category=punch_category.value if punch_category else None,
        origin=origin.value if origin else None,
        visibility=visibility.value if visibility else None,
        mdr_effect=mdr_effect.value if mdr_effect else None,
        external=external,
        scope=scope,
        item_id=item_id,
        location_node_id=location_node_id,
        linked=link,
    )


@issues_router.post(
    "/",
    response_model=NcrRead,
    status_code=201,
    summary="Raise an Issue",
    description=(
        "A punch item or an NCR from a template (or the default template of `category` x `issue_type`). "
        "Portal accounts always raise client-origin, client-visible issues."
    ),
    dependencies=perm(P.CREATE),
)
async def create(values: IssueCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    fields = values.model_dump(exclude={"project_id", "title", "issue_type", "template_id", "category", "answers", "links"})
    issue = await service.create_issue(
        db,
        project_id=values.project_id,
        title=values.title,
        raised_by_id=user["id"],
        issue_type=values.issue_type,
        template_id=values.template_id,
        category=values.category,
        external=service.is_external(user, held),
        answers=values.answers,
        links=[link.model_dump(mode="json") for link in values.links],
        **fields,
    )
    return await service.read_one(db, issue, user, held)


@issues_router.get(
    "/summary",
    summary="Register Summary",
    description="Open and closed counts by category, by Cat A/B/C and by area (the anchor's ancestor at `level_key`), "
    "with open Cat A (blocks work completion) and open MDR-blocking counts.",
    dependencies=perm(P.READ),
)
async def summary(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    issue_type: IssueType = IssueType.PUNCH,
    level_key: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    await readable_project(db, project_id, user["id"], held)
    return await service.summary(
        db, project_id, external=service.is_external(user, held), issue_type=issue_type.value, level_key=level_key
    )


@issues_router.get(
    "/blocking",
    summary="Open Issues Blocking the MDR",
    description="The MDR compile gate for a dossier scope (`node_id`, repeatable; none = the whole project): "
    "open issues with `mdr_effect = blocks`. Staff only.",
    dependencies=perm(P.READ),
)
async def blocking(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    node_id: Annotated[list[int] | None, Query(max_length=50)] = None,
) -> list[dict[str, Any]]:
    await readable_project(db, project_id, user["id"], held)
    if service.is_external(user, held):
        raise service.NcrNotFoundError("Not available")
    return await service.blocking_issues(db, project_id, node_id or [])


EXPORT_REGISTERS = {
    "punch": ("Punch list", service.PUNCH_COLUMNS),
    "ncr": ("NCR / concession register", service.NCR_REGISTER_COLUMNS),
}


@issues_router.get(
    "/export",
    summary="Export a Register",
    description="The punch list (`register=punch`) or the NCR / concession register (`register=ncr`) as Excel, CSV or "
    "PDF, with the list's filters.",
    dependencies=perm(P.EXPORT),
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQ,
    register: IssueType = IssueType.PUNCH,
    format: Literal["xlsx", "csv", "pdf"] = "xlsx",
    status: NcrStatus | None = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    punch_category: PunchCategory | None = None,
    mdr_effect: MdrEffect | None = None,
    node_id: OptProjectQ = None,
    open_only: bool = False,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    external = service.is_external(user, held)
    where = await _where(
        db, project_id, external, register, status, category, punch_category, None, None, None, mdr_effect,
        node_id, None, None, None, open_only, None,
    )  # fmt: skip
    rows = await service.export_rows(db, where, external=external)
    await db.commit()
    title, columns = EXPORT_REGISTERS[register.value]
    name = f"{register.value}-register-{project.code}"
    if format == "pdf":
        doc = Document(title=title, subtitle=f"{project.code} {project.name}", landscape=True, footer=title)
        doc.table([h for _, h in columns], [[r.get(k) if r.get(k) is not None else "" for k, _ in columns] for r in rows])
        return Response(
            render_pdf(doc), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'}
        )
    body, media_type, ext = write_table(columns, rows, format, title=title)
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})


# --- categories and defaults -------------------------------------------------------------------------


@issues_router.get(
    "/categories",
    summary="Issue Categories",
    description="The library list with the project's own changes (omit `project_id` for the library alone).",
    dependencies=perm(P.READ),
)
async def categories(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: OptProjectQ = None
) -> list[dict[str, Any]]:
    await _layer_access(db, project_id, user, held)
    result = await tpl.categories_for(db, project_id)
    await db.commit()
    return result


@issues_router.put(
    "/categories/{key}",
    summary="Add or Change a Category",
    description="For the project (`project_id`, needs `ncr.manage`) or the library (needs `ncr.configure`). "
    "Keys are never deleted: deactivate instead.",
    dependencies=perm(P.READ),
)
async def put_category(
    key: CategoryPath,
    values: CategoryUpsert,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: OptProjectQ = None,
) -> list[dict[str, Any]]:
    await _layer_access(db, project_id, user, held, write=True)
    await tpl.upsert_category(db, project_id, key, values.model_dump(exclude_unset=True))
    await db.commit()
    return await tpl.categories_for(db, project_id)


@issues_router.get("/defaults", summary="Default Template per Category and Type", dependencies=perm(P.READ))
async def defaults(
    db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: OptProjectQ = None
) -> list[dict[str, Any]]:
    await _layer_access(db, project_id, user, held)
    result = await tpl.defaults_for(db, project_id)
    await db.commit()
    return result


@issues_router.put("/defaults", summary="Set a Default Template", dependencies=perm(P.READ))
async def put_default(
    values: DefaultTemplateSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    await _layer_access(db, values.project_id, user, held, write=True)
    await tpl.set_default(db, values.project_id, values.category, values.issue_type.value, values.template_id)
    await db.commit()
    return await tpl.defaults_for(db, values.project_id)


# --- templates ---------------------------------------------------------------------------------------


@issues_router.get(
    "/templates/",
    summary="List Issue Templates",
    description="Library templates the project hasn't copied, plus the project's own (omit `project_id` for the library).",
    dependencies=perm(P.READ),
)
async def list_templates(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: OptProjectQ = None,
    issue_type: IssueType | None = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await _layer_access(db, project_id, user, held)
    rows = await tpl.templates_for(db, project_id, issue_type.value if issue_type else None, category)
    await db.commit()
    start = compute_offset(page, items_per_page)
    data = [await tpl.template_read(db, t) for t in rows[start : start + items_per_page]]
    return paginated_response(crud_data={"data": data, "total_count": len(rows)}, page=page, items_per_page=items_per_page)


async def _template(
    db: Any, template_id: int, user: dict[str, Any], held: frozenset[str], *, write: bool = False
) -> IssueTemplate:
    template: IssueTemplate | None = await db.get(IssueTemplate, template_id)
    if template is None:
        raise tpl.TemplateNotFound(str(template_id))
    await _layer_access(db, template.project_id, user, held, write=write)
    return template


@issues_router.post(
    "/templates/",
    status_code=201,
    summary="New Issue Template",
    description="Punch or NCR; starts as draft revision 1 from the type's `general` template unless `fields` are given.",
    dependencies=perm(P.READ),
)
async def create_template(
    values: TemplateCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    await _layer_access(db, values.project_id, user, held, write=True)
    template = await tpl.create_template(
        db,
        project_id=values.project_id,
        name=values.name,
        issue_type=values.issue_type,
        category=values.category,
        user_id=user["id"],
        fields=values.fields,
        flags=values.model_dump(include=set(tpl.FLAG_KEYS), mode="json"),
    )
    await db.commit()
    return await tpl.template_read(db, template, revisions=True)


@issues_router.get("/templates/{template_id}", summary="Get an Issue Template", dependencies=perm(P.READ))
async def get_template(
    template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    return await tpl.template_read(db, await _template(db, template_id, user, held), revisions=True)


@issues_router.put(
    "/templates/{template_id}/draft",
    summary="Edit the Draft Revision",
    description="Fields and flag defaults. Published revisions are frozen: the first edit after a publish starts a new draft.",
    dependencies=perm(P.READ),
)
async def save_draft(
    template_id: Id, values: TemplateDraft, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    template = await _template(db, template_id, user, held, write=True)
    changes = values.model_dump(exclude_unset=True, mode="json")
    if values.fields is not None:
        changes["fields"] = values.fields
    await tpl.save_draft(db, template, changes, user["id"])
    await db.commit()
    return await tpl.template_read(db, template, revisions=True)


@issues_router.post(
    "/templates/{template_id}/publish",
    summary="Publish the Draft",
    description="Freezes the draft as the new published revision; new issues use it, existing ones keep theirs.",
    dependencies=perm(P.READ),
)
async def publish_template(
    template_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    template = await _template(db, template_id, user, held, write=True)
    await tpl.publish(db, template, user["id"])
    await db.commit()
    return await tpl.template_read(db, template, revisions=True)


@issues_router.post(
    "/templates/{template_id}/copy",
    status_code=201,
    summary="Copy a Library Template into the Project",
    description="Made once; the copy replaces the library template in the project's lists and defaults.",
    dependencies=perm(P.MANAGE),
)
async def copy_template(
    template_id: Id, project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    await readable_project(db, project_id, user["id"], held)
    template = await tpl.get_template(db, template_id, project_id)
    copy = await tpl.copy_to_project(db, template, project_id, user["id"])
    await db.commit()
    return await tpl.template_read(db, copy, revisions=True)


@issues_router.get(
    "/template-revisions/{revision_id}",
    summary="Get a Template Revision",
    description="Its fields, flag defaults and the JSON Schema of its answers.",
    dependencies=perm(P.READ),
)
async def get_revision(
    revision_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    revision = await db.get(IssueTemplateRevision, revision_id)
    if revision is None:
        raise tpl.TemplateNotFound(str(revision_id))
    await _template(db, revision.template_id, user, held)
    return tpl.revision_read(revision)


# --- one issue ---------------------------------------------------------------------------------------


@issues_router.get("/{issue_id}", response_model=NcrRead, summary="Get an Issue", dependencies=perm(P.READ))
async def get(issue_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.read_one(db, await service.readable_issue(db, issue_id, user, held), user, held)


@issues_router.patch(
    "/{issue_id}",
    response_model=NcrRead,
    summary="Update an Issue",
    description="Details and template answers (merged). Answers of completed steps are read-only.",
    dependencies=perm(P.UPDATE),
)
async def update(
    issue_id: Id, values: IssueUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    await service.update_issue(db, issue, values.model_dump(exclude_unset=True), user["id"])
    return await service.read_one(db, issue, user, held)


@issues_router.post(
    "/{issue_id}/transition",
    response_model=NcrRead,
    summary="Move an Issue One Step",
    description=(
        "Punch: open → rectified (`ncr.transition`) → verified → closed (`ncr.verify`; closes in the same action unless "
        "the template keeps a separate close; reject = rectified → open with a note). The rectifier can never verify "
        "or close. NCR: open (containment) → disposition → root_cause (`ncr.verify` records the disposition) → "
        "corrective_action → effectiveness → closed (`ncr.verify`, `attest: true`; nobody who recorded the "
        "disposition or completed an action). Required template fields of the completed steps are checked."
    ),
    dependencies=perm(P.READ),
)
async def move(issue_id: Id, values: Transition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    await service.transition(
        db,
        issue,
        values.to.value,
        user,
        held,
        note=values.note,
        attest=values.attest,
        closed_by_inspection_id=values.closed_by_inspection_id,
    )
    return await service.read_one(db, issue, user, held)


@issues_router.post(
    "/{issue_id}/void",
    response_model=NcrRead,
    summary="Void an Issue",
    description="Raised by mistake: the record and its number stay. Needs a reason.",
    dependencies=perm(P.MANAGE),
)
async def void(issue_id: Id, values: VoidIssue, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    await service.void(db, issue, values.reason, user["id"])
    return await service.read_one(db, issue, user, held)


@issues_router.post(
    "/{issue_id}/flags",
    response_model=NcrRead,
    summary="Override a Flag",
    description=(
        "`visibility`, `mdr_effect` or `completion_effect`, with a reason; audited. Client and external-audit origins "
        "are locked (never internal, never excluded); a client-seen issue never becomes internal; internal → client "
        "goes through raise-external. Loosening notifies the QA authority and is counted."
    ),
    dependencies=perm(P.MANAGE),
)
async def override_flag(
    issue_id: Id, values: FlagOverride, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    await service.override_flag(db, issue, values.flag, values.value, values.reason, user["id"])
    return await service.read_one(db, issue, user, held)


@issues_router.get(
    "/{issue_id}/flags", response_model=list[FlagOverrideRead], summary="Flag Override Ledger", dependencies=perm(P.READ)
)
async def flag_overrides(
    issue_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    return await service.overrides_of(db, await service.readable_issue(db, issue_id, user, held))


@issues_router.post(
    "/{issue_id}/upgrade",
    response_model=NcrRead,
    status_code=201,
    summary="Upgrade a Punch Item to an NCR",
    description="A new NCR (answers and photos carried by key, same visibility); the punch closes as `upgraded`.",
    dependencies=perm(P.MANAGE),
)
async def upgrade(issue_id: Id, values: Upgrade, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    ncr = await service.upgrade(db, issue, values.template_id, user["id"], values.note)
    return await service.read_one(db, ncr, user, held)


@issues_router.post(
    "/{issue_id}/raise-external",
    response_model=NcrRead,
    status_code=201,
    summary="Raise an External NCR from an Internal Issue",
    description="A new client-visible NCR carrying only what you pick; the internal issue closes as `escalated`.",
    dependencies=perm(P.MANAGE),
)
async def raise_external(
    issue_id: Id, values: RaiseExternal, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    issue = await service.readable_issue(db, issue_id, user, held)
    ncr = await service.raise_external(
        db,
        issue,
        user["id"],
        template_id=values.template_id,
        title=values.title,
        carry_description=values.carry_description,
        carry_answers=values.carry_answers,
        carry_photos=values.carry_photos,
    )
    return await service.read_one(db, ncr, user, held)


@issues_router.get("/{issue_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(issue_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    return await service.history(db, await service.readable_issue(db, issue_id, user, held))

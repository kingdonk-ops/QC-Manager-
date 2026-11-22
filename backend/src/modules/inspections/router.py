"""Mounted at /api/v1/inspections. Every route reads the project through ``projects``' visibility rule first."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import ForbiddenException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import anchoring, cosign, eligibility, itp, service
from .callouts_router import router as callouts_router
from .constants import Area, GroupBy, InspectionStatus, Kind, LinkKind
from .itp_router import router as itp_router
from .models import ChecklistTemplate, Inspection, InspectionLink, TemplateRevision
from .permissions import InspectionPermissionName as P
from .quality_router import router as quality_router
from .quality_schemas import CosignBody, CosignDecision, HoldReleaseBody, InspectionSign
from .schemas import (
    ChecklistStarterSeed,
    ChecklistTemplateIn,
    ChecklistTemplateRead,
    ChecklistTemplateUpdate,
    InspectionCompletion,
    InspectionCreate,
    InspectionEligibility,
    InspectionItemsFill,
    InspectionRead,
    InspectionReview,
    InspectionStatusChange,
    InspectionSubmit,
    InspectionTrends,
    InspectionUpdate,
    SignatureRead,
    TemplateRevisionRead,
)

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# Fixed paths first: /{inspection_id} would otherwise catch them.
router.include_router(itp_router)
router.include_router(callouts_router)
router.include_router(quality_router)


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
    description="A project's inspection records (QA inspections, project-level checks and ITP lines), newest first, "
    "without their items. Filter by status, kind, area, trade, location, inspector (`me`), an anchor subtree "
    "(`node_id`: records on the node, below it or on its Items), an Item, a link (`linked=node:12`) or search text.",
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
    kind: Kind | None = None,
    category: Area | None = None,
    trade: Annotated[str | None, Query(max_length=100)] = None,
    location: Annotated[str | None, Query(max_length=200)] = None,
    inspector: Annotated[str | None, Query(pattern=r"^(me|\d+)$")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    item_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    linked: Annotated[str | None, Query(pattern=r"^(node|item|equipment):\d{1,9}$")] = None,
    formal: bool | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Inspection.project_id == project_id]
    if status:
        where.append(Inspection.status == status.value)
    if kind:
        where.append(Inspection.kind == kind.value)
    if category:
        where.append(Inspection.category == category.value)
    if formal is not None:
        where.append(Inspection.is_formal.is_(formal))
    if trade:
        where.append(func.lower(Inspection.trade) == trade.lower())
    if location:
        where.append(func.lower(Inspection.location) == location.lower())
    if inspector:
        where.append(Inspection.inspector_id == (user["id"] if inspector == "me" else int(inspector)))
    if node_id:
        await anchoring.tree.get_node(db, node_id, project_id)
        nodes, items = await anchoring.anchored_in(db, node_id)
        where.append(or_(Inspection.node_id.in_(nodes), Inspection.item_id.in_(items or [0])))
    if item_id:
        where.append(Inspection.item_id == item_id)
    if linked:
        kind_s, target = linked.split(":")
        where.append(
            Inspection.id.in_(
                select(InspectionLink.inspection_id).where(
                    InspectionLink.target_kind == LinkKind(kind_s).value, InspectionLink.target_id == int(target)
                )
            )
        )
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
    description="The template's sections and items are copied onto the inspection, so later template edits don't "
    "change it. A `qa_itp` template's record anchors to an inspection-anchor node or an Item (`node_id` / `item_id`); "
    "any other area is project-level with an optional `location_node_id` and `links`.",
    dependencies=perm(P.CREATE),
)
async def create(values: InspectionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    template = await service.get_template(db, values.template_id)
    if template.project_id != values.project_id:
        raise service.TemplateNotFoundError("Template is on another project")
    fields = values.model_dump(mode="json", exclude={"project_id", "template_id"}, exclude_none=True)
    fields["links"] = [link.model_dump(mode="json") for link in values.links]
    if values.scheduled_date:
        fields["scheduled_date"] = values.scheduled_date
    inspection = await service.create_inspection(db, template, fields, user["id"])
    return await _one(db, inspection)


@router.get(
    "/{inspection_id}", response_model=InspectionRead, summary="Get an Inspection, with its Items", dependencies=perm(P.READ)
)
async def get(inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _readable(db, inspection_id, user, held))


@router.patch(
    "/{inspection_id}",
    response_model=InspectionRead,
    summary="Update an Inspection's Details",
    description="Voids every signature over the earlier content.",
    dependencies=perm(P.UPDATE),
)
async def update(
    inspection_id: Id, values: InspectionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.update_details(db, inspection, values.model_dump(exclude_unset=True))
    return await _one(db, inspection)


@router.patch(
    "/{inspection_id}/items",
    response_model=InspectionRead,
    summary="Record Results",
    description="Results (pass, fail, na), numeric readings and notes for some or all items; the score is recalculated. "
    "A reading outside the item's limits scores as a fail. The first answer moves a planned inspection to in_progress. "
    "Refused on an ITP line behind an unreleased Hold point. Any change voids the signatures over the earlier content. "
    "Attach photos to an item through `/api/v1/files/` with `entity_type=inspection_item` and the item's id.",
    dependencies=perm(P.UPDATE),
)
async def fill(
    inspection_id: Id, values: InspectionItemsFill, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.fill_items(db, inspection, [a.model_dump(exclude_unset=True) for a in values.items], user["id"])
    return await _one(db, inspection)


@router.get(
    "/{inspection_id}/eligibility",
    response_model=InspectionEligibility,
    summary="May this Action Happen Now?",
    description="A stateless check returning the reasons an action is blocked: `fill`, `request`, `sign`, `submit`, "
    "`approve`, `hold_release` (Hold points not released, witness requirement, client signature, competency at "
    "signing, self-approval).",
    dependencies=perm(P.READ),
)
async def check_eligibility(
    inspection_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    action: Annotated[str, Query(pattern="^(" + "|".join(eligibility.ACTIONS) + ")$")],
) -> InspectionEligibility:
    inspection = await _readable(db, inspection_id, user, held)
    findings = await eligibility.check(db, inspection, action, user_id=user["id"])
    return InspectionEligibility.model_validate(
        {"action": action, "eligible": not any(f.blocking for f in findings), "findings": [f.dump() for f in findings]}
    )


@router.post(
    "/{inspection_id}/complete",
    response_model=InspectionRead,
    summary="Complete an Informal Inspection",
    description="Scores it (pass rate = passed / (passed + failed), N/A excluded) and raises a follow-up for each "
    "failed item: a task linked to the inspection, or, when `follow_ups` picks `ncr` for the item, an NCR linked back "
    "to the item plus an `inspections.item.ncr_requested` event. Refused while items are unanswered (unless "
    "`allow_unanswered`) or while a failed item that requires a photo has none. A formal record goes through "
    "`/submit` and `/review` instead.",
    dependencies=perm(P.TRANSITION),
)
async def complete(
    inspection_id: Id, values: InspectionCompletion, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    events = await service.complete(db, inspection, values.model_dump(), user)
    await service.publish_completion(inspection, events)
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/sign",
    response_model=SignatureRead,
    status_code=201,
    summary="Sign as the Inspector",
    description="The inspector's formal sign-off over the current content (SHA-256), with a snapshot of the signer "
    "and of their competencies. Refused when the template's required qualification isn't valid today, or behind an "
    "unreleased Hold point. Any later change to the record voids it.",
    dependencies=perm(P.SUBMIT),
)
async def sign(
    inspection_id: Id, values: InspectionSign, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    if not values.accept_intent:
        raise service.UnprocessableEntityException("Accept the signing statement (accept_intent).")
    sig = await service.sign_as_inspector(db, inspection, user["id"], held)
    await db.commit()
    return service.read_signature(sig)


@router.post(
    "/{inspection_id}/cosign",
    response_model=SignatureRead,
    status_code=201,
    summary="Client Co-sign",
    description="After the inspector signed. `portal`: the client signs in their own account (needs "
    "`inspections.respond`). `on_device`: a drawn signature on the inspector's device; `scan`: a scanned paper "
    "signature uploaded to this inspection. Both name the client's account and stay provisional until that client "
    "confirms (`/cosign/{signature_id}`).",
    dependencies=perm(P.READ),
)
async def client_cosign(
    inspection_id: Id, values: CosignBody, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    if values.mode != "portal" and P.SUBMIT not in held and P.UPDATE not in held:
        raise ForbiddenException("Recording a client's signature needs inspections.submit.")
    return service.read_signature(await cosign.cosign(db, inspection, values.model_dump(mode="json"), user, held))


@router.post(
    "/{inspection_id}/cosign/{signature_id}",
    response_model=InspectionRead,
    summary="Confirm or Reject a Provisional Co-sign",
    description="Only the client named on it, in their own account. Rejecting needs a reason and returns a submitted record.",
    dependencies=perm(P.RESPOND),
)
async def decide_cosign(
    inspection_id: Id,
    signature_id: Id,
    values: CosignDecision,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await cosign.decide(db, inspection, signature_id, values.model_dump(), user)
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/submit",
    response_model=InspectionRead,
    summary="Submit a Formal Inspection for Review",
    description="Signs it as the inspector if it isn't signed over the current content (`accept_intent`), then "
    "checks: answers, photos on failures, Hold points before it released, the witness requirement of its external "
    "H/W points (an issued request witnessed, waived, or a no-show on a Witness point after valid notice), the "
    "client co-sign the template requires, and the inspector's competency. Answers are read-only once submitted.",
    dependencies=perm(P.SUBMIT),
)
async def submit(
    inspection_id: Id, values: InspectionSubmit, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.submit(db, inspection, values.model_dump(mode="json"), user, held)
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/review",
    response_model=InspectionRead,
    summary="Approve or Return a Submitted Inspection",
    description="`approve` (with `accept_intent`): the record takes the proposed result, is signed by the reviewer and "
    "its failed items raise follow-ups. Refused for your own inspection unless the project allows self-approval, and "
    "while a required client co-sign is missing or provisional. `return`: needs a reason; comments on single answers "
    "are kept per review round.",
    dependencies=perm(P.REVIEW),
)
async def review(
    inspection_id: Id, values: InspectionReview, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    events = await service.review(db, inspection, values.model_dump(mode="json"), user, held)
    if inspection.status == InspectionStatus.COMPLETED:
        await service.publish_completion(inspection, events)
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/comments/{comment_id}/resolve",
    response_model=InspectionRead,
    summary="Resolve an Answer Comment",
    dependencies=perm(P.UPDATE),
)
async def resolve_comment(
    inspection_id: Id, comment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    await service.resolve_comment(db, inspection, comment_id, user["id"])
    return await _one(db, inspection)


@router.post(
    "/{inspection_id}/hold-release",
    response_model=InspectionRead,
    summary="Release a Hold Point",
    description="The formal, individually signed release of an ITP line's Hold point, once the line is accepted. "
    "Until then every later line of the ITP is blocked. `on_behalf_of_user_id` signs as an active delegate (kind "
    "`hold_point`); the delegate still needs `inspections.approve` and a valid competency.",
    dependencies=perm(P.APPROVE),
)
async def hold_release(
    inspection_id: Id, values: HoldReleaseBody, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    line = await _readable(db, inspection_id, user, held)
    await itp.release_hold(
        db, line, user["id"], held, accept_intent=values.accept_intent, on_behalf_of_user_id=values.on_behalf_of_user_id
    )
    return await _one(db, line)


@router.patch(
    "/{inspection_id}/status",
    response_model=InspectionRead,
    summary="Change an Inspection's Status",
    description="planned ↔ in_progress, completed → closed, completed → in_progress (reopen), closed → completed. "
    "Completing goes through `/complete` or `/review`; requested, submitted and returned have their own actions.",
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


@router.get(
    "/{inspection_id}/report.pdf",
    summary="Inspection Report (PDF)",
    description="Header, anchor, results, photos list, review history and a signatures block (role, signer, mode, "
    "time, content hash).",
    dependencies=perm(P.READ),
)
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

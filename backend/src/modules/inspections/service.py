from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, history_of, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError
from ..files.models import StoredFile
from ..ncr.service import create_ncr
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..role.models import RolePermission, UserRole
from ..tasks.service import create_task
from ..user.models import User
from . import anchoring, eligibility, signing
from .constants import (
    DEDICATED,
    EDITABLE,
    FLOW,
    OPEN_REQUEST,
    Area,
    InspectionStatus,
    Kind,
    ResponseType,
    Result,
    SignatureRole,
    SignatureStatus,
    has_hold,
)
from .models import (
    AnswerComment,
    ChecklistTemplate,
    Inspection,
    InspectionItem,
    InspectionRequest,
    InspectionSettings,
    InspectionSignature,
    RequestLink,
    TemplateRevision,
)
from .schemas import (
    AnswerCommentRead,
    ChecklistTemplateRead,
    InspectionItemRead,
    InspectionRead,
    InspectionTrendGroup,
    InspectionTrendMonth,
    InspectionTrendPoint,
    LinkRead,
    SignatureRead,
)
from .starters import STARTERS

ENTITY = "inspection"
ITEM_ENTITY = "inspection_item"
NCR_REQUESTED = "inspections.item.ncr_requested"
LOCKED_SETTINGS = ("area", "is_formal", "audit_scope")
"""Template settings only ``inspections.manage`` may change (KERP: the QA authority or PER-09)."""
REVISED_FIELDS = (
    "sections",
    "activities",
    "area",
    "is_formal",
    "audit_scope",
    "requires_client_signature",
    "required_qualification",
    "linked_issue_types",
    "issue_category",
)


class TemplateNotFoundError(ResourceNotFoundError):
    public_detail = "Checklist template not found."


class InspectionNotFoundError(ResourceNotFoundError):
    public_detail = "Inspection not found."


def link_of(inspection: Inspection) -> str:
    return f"/inspections/{inspection.id}?project={inspection.project_id}"


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


# --- templates ---------------------------------------------------------------------------------------


def read_template(t: ChecklistTemplate) -> dict[str, Any]:
    count = sum(len(s.get("items", [])) for s in t.sections) if t.kind != Kind.ITP else len(t.activities)
    return ChecklistTemplateRead.model_validate(t).model_copy(update={"item_count": count}).model_dump(mode="json")


async def get_template(db: AsyncSession, template_id: int) -> ChecklistTemplate:
    t = await db.get(ChecklistTemplate, template_id)
    if t is None:
        raise TemplateNotFoundError("No such template")
    return t


def template_snapshot(t: ChecklistTemplate) -> dict[str, Any]:
    keys = {"name", "kind", "trade", "activity", "description", "sections", "activities", "item_type_key", "work_type"}
    keys |= {*REVISED_FIELDS, "client_document_number"}
    return {k: getattr(t, k) for k in sorted(keys)}


async def ensure_revision(db: AsyncSession, t: ChecklistTemplate, user_id: int | None) -> TemplateRevision:
    """The frozen revision for the template's current version, made the first time it's needed."""
    rev = await db.scalar(
        select(TemplateRevision).where(TemplateRevision.template_id == t.id, TemplateRevision.version == t.version)
    )
    if rev is None:
        snapshot = template_snapshot(t)
        rev = TemplateRevision(
            template_id=t.id,
            version=t.version,
            snapshot=snapshot,
            content_sha256=signing.sha256_of(snapshot),
            created_by_id=user_id,
            created_at=datetime.now(UTC),
        )
        db.add(rev)
        await db.flush()
    return rev


async def check_activities(db: AsyncSession, project_id: int, activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in keys and check each ITR form: same project, kind inspection, formal."""
    out, keys = [], set()
    for position, act in enumerate(activities, start=1):
        act = dict(act)
        act["key"] = act.get("key") or str(position)
        if act["key"] in keys:
            raise UnprocessableEntityException(f"Activity key '{act['key']}' is used twice.")
        keys.add(act["key"])
        form_id = act.get("form_template_id")
        if form_id:
            form = await db.get(ChecklistTemplate, form_id)
            if form is None or form.project_id != project_id or form.kind != Kind.INSPECTION:
                raise UnprocessableEntityException(f"Activity '{act['title']}': its form must be an inspection template here.")
            if not form.is_formal:
                raise UnprocessableEntityException(
                    f"Activity '{act['title']}': an ITP line is always formal; its form '{form.name}' is informal."
                )
        out.append(act)
    return out


async def create_template(db: AsyncSession, values: dict[str, Any], user_id: int) -> ChecklistTemplate:
    if values.get("activities"):
        values["activities"] = await check_activities(db, values["project_id"], values["activities"])
    t = ChecklistTemplate(created_by_id=user_id, **values)
    db.add(t)
    await db.flush()
    await ensure_revision(db, t, user_id)
    await db.commit()
    return t


async def update_template(db: AsyncSession, t: ChecklistTemplate, changes: dict[str, Any], user_id: int) -> None:
    if t.kind == Kind.ITP:
        if changes.get("sections"):
            raise UnprocessableEntityException("An ITP template has activities, not sections.")
        if changes.get("area", Area.QA_ITP) != Area.QA_ITP or changes.get("is_formal", True) is not True:
            raise UnprocessableEntityException("An ITP template is always a formal QA/ITP plan.")
        if "activities" in changes and not changes["activities"]:
            raise UnprocessableEntityException("An ITP template needs at least one activity.")
    elif changes.get("activities"):
        raise UnprocessableEntityException("Only an ITP template has activities.")
    if changes.get("activities"):
        changes["activities"] = await check_activities(db, t.project_id, changes["activities"])
    if t.kind == Kind.INSPECTION and changes.get("is_formal") is False:
        used = [a for a in await _itp_templates_using(db, t) if a]
        if used:
            raise UnprocessableEntityException(f"ITP template '{used[0]}' uses this form; an ITP line is always formal.")
    if any(k in changes and changes[k] != getattr(t, k) for k in REVISED_FIELDS):
        t.version += 1
    for key, value in changes.items():
        setattr(t, key, value)
    await db.flush()
    await ensure_revision(db, t, user_id)
    await db.commit()


async def _itp_templates_using(db: AsyncSession, form: ChecklistTemplate) -> list[str]:
    rows = await db.execute(
        select(ChecklistTemplate).where(ChecklistTemplate.project_id == form.project_id, ChecklistTemplate.kind == Kind.ITP)
    )
    return [t.name for t in rows.scalars() if any(a.get("form_template_id") == form.id for a in t.activities)]


async def seed_starters(db: AsyncSession, project_id: int, user_id: int | None) -> list[ChecklistTemplate]:
    """Add the starter templates the project doesn't have (by name). Commits."""
    have = set((await db.execute(select(ChecklistTemplate.name).where(ChecklistTemplate.project_id == project_id))).scalars())
    added = []
    for starter in STARTERS:
        if starter["name"] in have:
            continue
        t = ChecklistTemplate(project_id=project_id, created_by_id=user_id, **starter)
        db.add(t)
        added.append(t)
    settings = await db.get(InspectionSettings, project_id)
    if settings is None:
        db.add(InspectionSettings(project_id=project_id, starters_seeded=True))
    else:
        settings.starters_seeded = True
    await db.commit()
    return added


async def ensure_starters(db: AsyncSession, project_id: int, user_id: int | None) -> None:
    """Seed the starters the first time a project's templates are listed."""
    settings = await db.get(InspectionSettings, project_id)
    if settings is None or not settings.starters_seeded:
        await seed_starters(db, project_id, user_id)


# --- scoring -----------------------------------------------------------------------------------------


def outcome_of(item: InspectionItem) -> str | None:
    """N/A stays N/A. A numeric reading outside its limits fails whatever was chosen; inside them it
    passes unless the inspector failed it. Without a reading the chosen result stands."""
    if item.result == Result.NA:
        return Result.NA.value
    if item.response_type == ResponseType.NUMERIC and item.reading is not None:
        low = item.min_value is not None and item.reading < item.min_value
        high = item.max_value is not None and item.reading > item.max_value
        return Result.FAIL.value if low or high or item.result == Result.FAIL else Result.PASS.value
    return item.result


def pass_rate(passed: int, failed: int) -> float | None:
    """passed / (passed + failed) as a percentage, to one decimal; N/A is left out."""
    scored = passed + failed
    return round(passed * 100.0 / scored, 1) if scored else None


def rescore(inspection: Inspection, items: list[InspectionItem]) -> None:
    counts: dict[str | None, int] = defaultdict(int)
    for item in items:
        item.outcome = outcome_of(item)
        counts[item.outcome] += 1
    inspection.passed = counts[Result.PASS.value]
    inspection.failed = counts[Result.FAIL.value]
    inspection.not_applicable = counts[Result.NA.value]
    inspection.unanswered = counts[None]
    inspection.pass_rate = pass_rate(inspection.passed, inspection.failed)


# --- inspections -------------------------------------------------------------------------------------


async def get_inspection(db: AsyncSession, inspection_id: int) -> Inspection:
    i = await db.get(Inspection, inspection_id)
    if i is None:
        raise InspectionNotFoundError("No such inspection")
    return i


async def items_of(db: AsyncSession, inspection_id: int) -> list[InspectionItem]:
    rows = await db.execute(
        select(InspectionItem).where(InspectionItem.inspection_id == inspection_id).order_by(InspectionItem.position)
    )
    return list(rows.scalars())


async def photo_counts(db: AsyncSession, item_ids: list[int]) -> dict[int, int]:
    if not item_ids:
        return {}
    rows = await db.execute(
        select(StoredFile.entity_id, func.count())
        .where(StoredFile.entity_type == ITEM_ENTITY, StoredFile.entity_id.in_(item_ids), StoredFile.is_latest.is_(True))
        .group_by(StoredFile.entity_id)
    )
    return {eid: n for eid, n in rows.tuples().all() if eid is not None}


def read_signature(sig: InspectionSignature) -> SignatureRead:
    return SignatureRead.model_validate(sig).model_copy(update={"has_image": bool(sig.signature_image)})


async def read_inspections(
    db: AsyncSession, inspections: list[Inspection], *, with_items: bool = False
) -> list[dict[str, Any]]:
    names = await user_names(db, {i.inspector_id for i in inspections})
    anchors = await anchoring.anchor_labels(db, [(i.node_id, i.item_id) for i in inspections])
    links = await anchoring.links_of(db, [i.id for i in inspections])
    out = []
    for i in inspections:
        extra: dict[str, Any] = {}
        if with_items:
            rows = await items_of(db, i.id)
            photos = await photo_counts(db, [r.id for r in rows])
            extra["items"] = [
                InspectionItemRead.model_validate(r).model_copy(update={"photo_count": photos.get(r.id, 0)}) for r in rows
            ]
            extra["signatures"] = [read_signature(s) for s in await signing.signatures_of(db, i.id)]
            extra["comments"] = await comments_of(db, i.id)
            extra["content_sha256"] = signing.sha256_of(signing.canonical(i, rows))
        out.append(
            InspectionRead.model_validate(i)
            .model_copy(
                update={
                    "inspector_name": names.get(i.inspector_id) if i.inspector_id else None,
                    "total": i.passed + i.failed + i.not_applicable + i.unanswered,
                    "anchor_label": anchors.get((i.node_id, i.item_id)),
                    "links": [LinkRead(**link) for link in links.get(i.id, [])],
                    **extra,
                }
            )
            .model_dump(mode="json")
        )
    return out


async def comments_of(db: AsyncSession, inspection_id: int) -> list[AnswerCommentRead]:
    rows = list(
        (
            await db.execute(
                select(AnswerComment).where(AnswerComment.inspection_id == inspection_id).order_by(AnswerComment.id)
            )
        ).scalars()
    )
    names = await user_names(db, {r.author_id for r in rows})
    return [AnswerCommentRead.model_validate(r).model_copy(update={"author_name": names.get(r.author_id or 0)}) for r in rows]


def checklist_items(inspection_id: int, sections: list[dict[str, Any]]) -> list[InspectionItem]:
    position = 0
    items = []
    for section in sections:
        for raw in section.get("items", []):
            position += 1
            items.append(
                InspectionItem(
                    inspection_id=inspection_id,
                    position=position,
                    section=section.get("title", ""),
                    text=raw["text"],
                    response_type=raw.get("response_type", ResponseType.PASS_FAIL.value),
                    unit=raw.get("unit"),
                    min_value=raw.get("min_value"),
                    max_value=raw.get("max_value"),
                    requires_photo_on_fail=bool(raw.get("requires_photo_on_fail")),
                    guidance=raw.get("guidance"),
                )
            )
    return items


async def create_inspection(db: AsyncSession, template: ChecklistTemplate, values: dict[str, Any], user_id: int) -> Inspection:
    if template.kind == Kind.ITP:
        raise UnprocessableEntityException("An ITP template is applied to an anchor through /itp/instances.")
    links = values.pop("links", [])
    await anchoring.check_placement(
        db,
        template.project_id,
        template.area,
        node_id=values.get("node_id"),
        item_id=values.get("item_id"),
        location_node_id=values.get("location_node_id"),
        links=links,
    )
    revision = await ensure_revision(db, template, user_id)
    inspection = Inspection(
        project_id=template.project_id,
        code=await next_reference(db, "INS", template.project_id),
        title=values.pop("title", None) or template.name,
        template_id=template.id,
        template_name=template.name,
        template_version=template.version,
        template_revision_id=revision.id,
        trade=values.pop("trade", None) or template.trade,
        created_by_id=user_id,
        status=InspectionStatus.PLANNED.value,
        kind=Kind.INSPECTION.value,
        category=template.area,
        is_formal=template.is_formal,
        audit_scope=template.audit_scope,
        requires_client_signature=template.requires_client_signature,
        required_qualification=template.required_qualification,
        **values,
    )
    db.add(inspection)
    await db.flush()
    items = checklist_items(inspection.id, template.sections)
    db.add_all(items)
    await anchoring.add_links(db, inspection.id, links)
    rescore(inspection, items)
    await record_transition(db, ENTITY, inspection.id, None, inspection.status, user_id, note=f"From {template.name}")
    await db.commit()
    return inspection


def _editable(inspection: Inspection) -> None:
    if inspection.status not in EDITABLE:
        if inspection.status == InspectionStatus.SUBMITTED:
            raise UnprocessableEntityException("This inspection is submitted for review; its answers are read-only.")
        raise UnprocessableEntityException("This inspection is completed. Reopen it to change the results.")


async def _blocking(db: AsyncSession, inspection: Inspection, action: str, user_id: int | None = None) -> None:
    findings = [f for f in await eligibility.check(db, inspection, action, user_id=user_id) if f.blocking]
    if findings:
        raise UnprocessableEntityException("; ".join(f"{f.code}: {f.message}" for f in findings))


async def update_details(db: AsyncSession, inspection: Inspection, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        setattr(inspection, key, value)
    await db.flush()
    await signing.void_stale(db, inspection)
    await db.commit()


async def fill_items(db: AsyncSession, inspection: Inspection, answers: list[dict[str, Any]], user_id: int) -> None:
    _editable(inspection)
    await _blocking(db, inspection, "fill")
    items = await items_of(db, inspection.id)
    by_id = {i.id: i for i in items}
    unknown = [a["id"] for a in answers if a["id"] not in by_id]
    if unknown:
        raise UnprocessableEntityException(f"Items {unknown} aren't on this inspection.")
    for answer in answers:
        item = by_id[answer["id"]]
        for key in ("result", "reading", "notes"):
            if key in answer:
                value = answer[key]
                setattr(item, key, value.value if hasattr(value, "value") else value)
    rescore(inspection, items)
    if inspection.status == InspectionStatus.PLANNED:
        await record_transition(db, ENTITY, inspection.id, inspection.status, InspectionStatus.IN_PROGRESS, user_id)
        inspection.status = InspectionStatus.IN_PROGRESS.value
    if inspection.inspected_date is None:
        inspection.inspected_date = date.today()
    await db.flush()
    await signing.void_stale(db, inspection)
    await db.commit()


async def change_status(db: AsyncSession, inspection: Inspection, target: str, note: str | None, user_id: int) -> None:
    if target == InspectionStatus.COMPLETED and inspection.status != InspectionStatus.CLOSED:
        raise UnprocessableEntityException("Complete an inspection through /complete, which scores it and raises follow-ups.")
    if target in DEDICATED:
        raise UnprocessableEntityException(f"{target.replace('_', ' ').capitalize()} is reached through its own action.")
    assert_transition(FLOW, inspection.status, target)
    await record_transition(db, ENTITY, inspection.id, inspection.status, target, user_id, note)
    inspection.status = target
    if target == InspectionStatus.IN_PROGRESS:
        inspection.completed_at = None
        inspection.result = None
    await db.commit()


async def complete(
    db: AsyncSession, inspection: Inspection, choice: dict[str, Any], user: dict[str, Any]
) -> list[dict[str, Any]]:
    """Complete an informal record: submit is final (KERP: no review step)."""
    if inspection.is_formal:
        raise UnprocessableEntityException("A formal inspection is submitted for review (/submit), not completed directly.")
    if inspection.status == InspectionStatus.PLANNED:
        raise UnprocessableEntityException("Fill the checklist before completing the inspection.")
    assert_transition(FLOW, inspection.status, InspectionStatus.COMPLETED)
    events = await _finish(db, inspection, choice, user)
    inspection.result = Result.FAIL.value if inspection.failed else Result.PASS.value
    await db.commit()
    return events


async def _finish(
    db: AsyncSession, inspection: Inspection, choice: dict[str, Any], user: dict[str, Any]
) -> list[dict[str, Any]]:
    """Score, then raise a follow-up for every failed item that has none yet: a task by default, or an NCR
    (when that module is on for the project; the ``inspections.item.ncr_requested`` event goes out either way).
    Moves the record to completed; the caller commits. Returns the events to publish once committed."""
    items = await items_of(db, inspection.id)
    rescore(inspection, items)
    if inspection.unanswered and not choice.get("allow_unanswered"):
        raise UnprocessableEntityException(f"{inspection.unanswered} item(s) are unanswered.")
    failed = [i for i in items if i.outcome == Result.FAIL]
    await _photos_for_failures(db, failed)

    choices = {c["item_id"]: c for c in choice.get("follow_ups", [])}
    ncr_on = await is_enabled(db, "ncr", inspection.project_id)
    events: list[dict[str, Any]] = []
    for item in failed:
        if item.task_id or item.ncr_id:
            continue
        picked = choices.get(item.id, {})
        action = str(picked.get("action") or "task")
        assignee = picked.get("assignee_id") or choice.get("default_assignee_id")
        due = picked.get("due_date") or choice.get("default_due_date")
        title = f"{inspection.code} #{item.position}: {item.text}"
        reading = f"Reading {item.reading:g}{' ' + item.unit if item.unit else ''}. " if item.reading is not None else ""
        limits = _limits(item)
        detail = f"{item.section}: {item.text}\n{reading}{limits}{item.notes or ''}".strip()
        item.follow_up = action
        if action == "ncr":
            if ncr_on:
                ncr = await create_ncr(
                    db,
                    project_id=inspection.project_id,
                    title=title,
                    raised_by_id=user["id"],
                    commit=False,
                    description=detail,
                    location=" / ".join(p for p in (inspection.location, inspection.area) if p) or None,
                    trade=inspection.trade,
                    responsible_user_id=assignee,
                    source="inspection",
                    source_reference=f"{inspection.code} item {item.position}",
                    inspection_id=inspection.id,
                    inspection_item_id=item.id,
                    severity=picked.get("severity") or "minor",
                )
                item.ncr_id = ncr.id
            events.append(
                {
                    "project_id": inspection.project_id,
                    "inspection_id": inspection.id,
                    "item_id": item.id,
                    "ncr_id": item.ncr_id,
                    "title": title,
                }
            )
        elif action == "task":
            task = await create_task(
                db,
                project_id=inspection.project_id,
                title=title[:300],
                created_by_id=user["id"],
                entity=(ENTITY, inspection.id),
                commit=False,
                description=detail,
                type="construction",
                priority="high",
                assignee_id=assignee,
                due_date=due,
                type_fields={"location": inspection.location or "", "trade": inspection.trade or ""},
            )
            item.task_id = task.id
    await record_transition(
        db, ENTITY, inspection.id, inspection.status, InspectionStatus.COMPLETED, user["id"], choice.get("note")
    )
    inspection.status = InspectionStatus.COMPLETED.value
    inspection.completed_at = datetime.now(UTC)
    if inspection.inspected_date is None:
        inspection.inspected_date = date.today()
    return events


async def _photos_for_failures(db: AsyncSession, failed: list[InspectionItem]) -> None:
    photos = await photo_counts(db, [i.id for i in failed if i.requires_photo_on_fail])
    missing = [i for i in failed if i.requires_photo_on_fail and not photos.get(i.id)]
    if missing:
        listed = "; ".join(f"{i.position}. {i.text}" for i in missing[:5])
        raise UnprocessableEntityException(f"Failed items need a photo: {listed}")


async def publish_completion(inspection: Inspection, events: list[dict[str, Any]]) -> None:
    for payload in events:
        await publish(NCR_REQUESTED, payload)
    await publish(
        "inspections.inspection.completed",
        {
            "project_id": inspection.project_id,
            "inspection_id": inspection.id,
            "pass_rate": inspection.pass_rate,
            "failed": inspection.failed,
            "result": inspection.result,
            "kind": inspection.kind,
        },
    )


def _limits(item: InspectionItem) -> str:
    if item.response_type != ResponseType.NUMERIC:
        return ""
    unit = f" {item.unit}" if item.unit else ""
    if item.min_value is not None and item.max_value is not None:
        return f"Acceptance {item.min_value:g}-{item.max_value:g}{unit}. "
    if item.min_value is not None:
        return f"Acceptance ≥ {item.min_value:g}{unit}. "
    if item.max_value is not None:
        return f"Acceptance ≤ {item.max_value:g}{unit}. "
    return ""


async def history(db: AsyncSession, inspection: Inspection) -> list[dict[str, Any]]:
    rows = await history_of(db, ENTITY, inspection.id)
    names = await user_names(db, {r["changed_by_id"] for r in rows})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"]) if r["changed_by_id"] else None} for r in rows]


# --- signing, submit and review ----------------------------------------------------------------------


async def sign_as_inspector(
    db: AsyncSession, inspection: Inspection, user_id: int, held: frozenset[str]
) -> InspectionSignature:
    """The inspector's formal sign-off over the current content (competency checked as of today)."""
    _editable(inspection)
    if inspection.status == InspectionStatus.PLANNED and await items_of(db, inspection.id):
        raise UnprocessableEntityException("Fill the record before signing it.")
    await _blocking(db, inspection, "sign", user_id)
    existing = await signing.live_signature(db, inspection, SignatureRole.INSPECTOR)
    if existing is not None:
        return existing
    snapshot, _ = await signing.competency_findings(db, user_id, inspection.required_qualification, date.today())
    if inspection.inspector_id is None:
        inspection.inspector_id = user_id
        await db.flush()
    return await signing.sign(db, inspection, SignatureRole.INSPECTOR, user_id, held=held, competencies=snapshot)


async def submit(
    db: AsyncSession, inspection: Inspection, body: dict[str, Any], user: dict[str, Any], held: frozenset[str]
) -> None:
    if not inspection.is_formal:
        raise UnprocessableEntityException("An informal record has no review: complete it (/complete).")
    _editable(inspection)
    items = await items_of(db, inspection.id)
    if inspection.status == InspectionStatus.PLANNED and items:
        raise UnprocessableEntityException("Fill the record before submitting it.")
    rescore(inspection, items)
    if inspection.unanswered and not body.get("allow_unanswered"):
        raise UnprocessableEntityException(f"{inspection.unanswered} item(s) are unanswered.")
    if body.get("proposed_result") == Result.FAIL or inspection.failed:
        await _photos_for_failures(db, [i for i in items if i.outcome == Result.FAIL])
    await _blocking(db, inspection, "submit", user["id"])
    if inspection.status == InspectionStatus.PLANNED:  # a line without a checklist: started and submitted at once
        await record_transition(db, ENTITY, inspection.id, inspection.status, InspectionStatus.IN_PROGRESS, user["id"])
        inspection.status = InspectionStatus.IN_PROGRESS.value
        if inspection.inspected_date is None:
            inspection.inspected_date = date.today()
            await db.flush()
            await signing.void_stale(db, inspection)
    if await signing.live_signature(db, inspection, SignatureRole.INSPECTOR) is None:
        if not body.get("accept_intent"):
            raise UnprocessableEntityException("Accept the signing statement to submit (accept_intent).")
        await sign_as_inspector(db, inspection, user["id"], held)
    assert_transition(FLOW, inspection.status, InspectionStatus.SUBMITTED)
    await record_transition(
        db, ENTITY, inspection.id, inspection.status, InspectionStatus.SUBMITTED, user["id"], body.get("note")
    )
    inspection.status = InspectionStatus.SUBMITTED.value
    inspection.proposed_result = str(body["proposed_result"])
    inspection.submitted_at = datetime.now(UTC)
    inspection.submitted_by_id = user["id"]
    inspection.review_round += 1
    inspection.return_reason = None
    if inspection.inspected_date is None:
        inspection.inspected_date = date.today()
    await notify(
        db,
        await reviewers_of(db, inspection),
        Category.APPROVAL,
        f"{inspection.code} submitted for review",
        body=f"{inspection.title}: proposed {inspection.proposed_result}.",
        link=link_of(inspection),
        entity=(ENTITY, inspection.id),
        actor_id=user["id"],
    )
    await db.commit()


async def reviewers_of(db: AsyncSession, inspection: Inspection) -> list[int]:
    """Users granted ``inspections.review`` through a role (superusers aren't notified)."""
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_name == "inspections.review")
    )
    return list((await db.execute(select(User.id).where(User.id.in_(holders), User.is_deleted.is_(False)))).scalars())


async def review(
    db: AsyncSession, inspection: Inspection, body: dict[str, Any], user: dict[str, Any], held: frozenset[str]
) -> list[dict[str, Any]]:
    if inspection.status != InspectionStatus.SUBMITTED:
        raise UnprocessableEntityException("Only a submitted inspection can be reviewed.")
    items = {i.id for i in await items_of(db, inspection.id)}
    unknown = [c["item_id"] for c in body.get("comments", []) if c["item_id"] not in items]
    if unknown:
        raise UnprocessableEntityException(f"Items {unknown} aren't on this inspection.")
    now = datetime.now(UTC)
    for c in body.get("comments", []):
        db.add(
            AnswerComment(
                inspection_id=inspection.id,
                item_id=c["item_id"],
                review_round=inspection.review_round,
                body=c["body"],
                author_id=user["id"],
                created_at=now,
            )
        )
    events: list[dict[str, Any]] = []
    if body["decision"] == "return":
        await record_transition(
            db, ENTITY, inspection.id, inspection.status, InspectionStatus.RETURNED, user["id"], body["reason"]
        )
        inspection.status = InspectionStatus.RETURNED.value
        inspection.return_reason = body["reason"]
        title = f"{inspection.code} returned"
    else:
        findings = [f for f in await eligibility.check(db, inspection, "approve", user_id=user["id"]) if f.blocking]
        if findings:
            raise UnprocessableEntityException("; ".join(f"{f.code}: {f.message}" for f in findings))
        if not body.get("accept_intent"):
            raise UnprocessableEntityException("Accept the signing statement to approve (accept_intent).")
        inspection.self_approved = user["id"] in (inspection.inspector_id, inspection.submitted_by_id)
        await signing.sign(db, inspection, SignatureRole.REVIEWER, user["id"], held=held)
        events = await _finish(db, inspection, {**body, "allow_unanswered": True, "note": body.get("reason")}, user)
        inspection.result = inspection.proposed_result
        title = f"{inspection.code} accepted" if inspection.result == Result.PASS else f"{inspection.code} rejected"
    inspection.reviewed_by_id = user["id"]
    inspection.reviewed_at = now
    await notify(
        db,
        [u for u in (inspection.inspector_id, inspection.submitted_by_id) if u],
        Category.STATUS,
        title,
        body=body.get("reason"),
        link=link_of(inspection),
        entity=(ENTITY, inspection.id),
        actor_id=user["id"],
    )
    await db.commit()
    return events


async def resolve_comment(db: AsyncSession, inspection: Inspection, comment_id: int, user_id: int) -> None:
    c = await db.get(AnswerComment, comment_id)
    if c is None or c.inspection_id != inspection.id:
        raise InspectionNotFoundError("No such comment")
    if c.resolved_at is None:
        c.resolved_at = datetime.now(UTC)
        c.resolved_by_id = user_id
    await db.commit()


# --- trends ------------------------------------------------------------------------------------------


async def trends(db: AsyncSession, project_id: int, group_by: str) -> list[InspectionTrendGroup]:
    done = (InspectionStatus.COMPLETED.value, InspectionStatus.CLOSED.value)
    rows = list(
        (
            await db.execute(
                select(Inspection)
                .where(Inspection.project_id == project_id, Inspection.status.in_(done), Inspection.kind == Kind.INSPECTION)
                .order_by(Inspection.inspected_date, Inspection.id)
            )
        ).scalars()
    )
    groups: dict[str, list[Inspection]] = defaultdict(list)
    for i in rows:
        key = (i.trade if group_by == "trade" else i.location) or "Unspecified"
        groups[key].append(i)
    out = []
    for key in sorted(groups):
        members = groups[key]
        months: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        points = []
        for i in members:
            when = i.inspected_date or (i.completed_at.date() if i.completed_at else None)
            points.append(
                InspectionTrendPoint(
                    inspection_id=i.id, code=i.code, date=when, pass_rate=i.pass_rate, passed=i.passed, failed=i.failed
                )
            )
            month = when.strftime("%Y-%m") if when else "unknown"
            months[month][0] += 1
            months[month][1] += i.passed
            months[month][2] += i.failed
        passed, failed = sum(i.passed for i in members), sum(i.failed for i in members)
        out.append(
            InspectionTrendGroup(
                key=key,
                inspections=len(members),
                passed=passed,
                failed=failed,
                pass_rate=pass_rate(passed, failed),
                points=points,
                monthly=[
                    InspectionTrendMonth(month=m, inspections=n, passed=p, failed=f, pass_rate=pass_rate(p, f))
                    for m, (n, p, f) in sorted(months.items())
                ],
            )
        )
    return out


# --- dashboard ---------------------------------------------------------------------------------------


async def dashboard(db: AsyncSession, project_id: int, formal_only: bool) -> dict[str, Any]:
    """Four tiles, computed on request: open call-outs, holds, what's due, and the acceptance rate."""
    today = date.today()
    now = datetime.now(UTC)
    open_requests = await db.scalar(
        select(func.count())
        .select_from(InspectionRequest)
        .where(InspectionRequest.project_id == project_id, InspectionRequest.status.in_(OPEN_REQUEST))
    )
    start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    requests_today = await db.scalar(
        select(func.count())
        .select_from(InspectionRequest)
        .where(
            InspectionRequest.project_id == project_id,
            InspectionRequest.status.in_(OPEN_REQUEST),
            InspectionRequest.scheduled_start >= start,
            InspectionRequest.scheduled_start < start + timedelta(days=1),
        )
    )
    lines = list(
        (
            await db.execute(
                select(Inspection).where(
                    Inspection.project_id == project_id,
                    Inspection.kind == Kind.ITP,
                    Inspection.hold_released_at.is_(None),
                )
            )
        ).scalars()
    )
    holds = [line for line in lines if has_hold(line.points)]
    awaiting = [
        h for h in holds if h.status in (InspectionStatus.COMPLETED, InspectionStatus.CLOSED) and h.result == Result.PASS
    ]
    open_states = (
        InspectionStatus.PLANNED.value,
        InspectionStatus.REQUESTED.value,
        InspectionStatus.IN_PROGRESS.value,
        InspectionStatus.RETURNED.value,
    )
    base = [Inspection.project_id == project_id]
    if formal_only:
        base.append(Inspection.is_formal.is_(True))
    due = await db.scalar(
        select(func.count())
        .select_from(Inspection)
        .where(*base, Inspection.status.in_(open_states), Inspection.scheduled_date <= today + timedelta(days=7))
    )
    overdue = await db.scalar(
        select(func.count())
        .select_from(Inspection)
        .where(*base, Inspection.status.in_(open_states), Inspection.scheduled_date < today)
    )
    awaiting_review = await db.scalar(
        select(func.count()).select_from(Inspection).where(*base, Inspection.status == InspectionStatus.SUBMITTED)
    )
    results = dict(
        (
            await db.execute(
                select(Inspection.result, func.count())
                .where(
                    *base,
                    Inspection.status.in_((InspectionStatus.COMPLETED.value, InspectionStatus.CLOSED.value)),
                    Inspection.result.is_not(None),
                )
                .group_by(Inspection.result)
            )
        )
        .tuples()
        .all()
    )
    passed, failed = results.get("pass", 0), results.get("fail", 0)
    return {
        "project_id": project_id,
        "open_requests": open_requests or 0,
        "requests_today": requests_today or 0,
        "holds_awaiting_release": len(awaiting),
        "holds_open": len(holds),
        "inspections_due": due or 0,
        "overdue": overdue or 0,
        "awaiting_review": awaiting_review or 0,
        "pass_rate": pass_rate(passed, failed),
        "passed": passed,
        "failed": failed,
        "computed_at": now,
    }


async def refs_for_inspection(db: AsyncSession, inspection_id: int) -> list[str]:
    """The numbers of the issued inspection requests that called this record out."""
    rows = await db.execute(
        select(InspectionRequest.code)
        .join(RequestLink, RequestLink.request_id == InspectionRequest.id)
        .where(RequestLink.inspection_id == inspection_id, InspectionRequest.code.is_not(None))
        .order_by(InspectionRequest.id)
    )
    return [c for c in rows.scalars() if c]


# --- report ------------------------------------------------------------------------------------------


async def report_pdf(db: AsyncSession, inspection: Inspection) -> bytes:
    read = (await read_inspections(db, [inspection], with_items=True))[0]
    project = await db.get(Project, inspection.project_id)
    doc = Document(
        title=f"{'ITP line' if inspection.kind == Kind.ITP else 'Inspection'} {inspection.code}: {inspection.title}",
        subtitle=f"{project.code} {project.name}" if project else "",
        footer=f"{inspection.code} · content {read['content_sha256'][:16]}",
    )
    status = inspection.status.replace("_", " ").capitalize()
    if inspection.status == InspectionStatus.SUBMITTED:
        status += " (not approved)"
    if inspection.result:
        status += f" — {'accepted' if inspection.result == Result.PASS else 'rejected'}"
    fields: list[tuple[str, Any]] = [
        ("Template", f"{inspection.template_name or '-'} (v{inspection.template_version or 1})"),
        ("Area", inspection.category.replace("_", " ")),
        ("Formal", "Yes" if inspection.is_formal else "No (record only)"),
    ]
    if read["anchor_label"]:
        fields.append(("Anchor", read["anchor_label"]))
    fields += [
        ("Location / area", " / ".join(p for p in (inspection.location, inspection.area) if p) or "-"),
        ("Trade", inspection.trade or "-"),
        ("Inspector", read["inspector_name"] or "-"),
        ("Inspected", inspection.inspected_date.isoformat() if inspection.inspected_date else "-"),
        ("Status", status),
        (
            "Score",
            f"{inspection.pass_rate if inspection.pass_rate is not None else '-'}% "
            f"({inspection.passed} pass, {inspection.failed} fail, {inspection.not_applicable} N/A)",
        ),
    ]
    refs = await refs_for_inspection(db, inspection.id)
    if refs:
        fields.append(("Inspection requests", ", ".join(refs)))
    if inspection.points:
        fields.append(("Intervention points", ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in inspection.points.items())))
    if inspection.acceptance_criteria:
        fields.append(("Acceptance criteria", inspection.acceptance_criteria))
    if read["links"]:
        fields.append(("Linked", "; ".join(f"{link['kind']}: {link['label'] or link['id']}" for link in read["links"])))
    doc.fields(fields)
    section = None
    rows: list[list[Any]] = []
    for item in read["items"]:
        if item["section"] != section:
            section = item["section"]
            rows.append([f"— {section} —", "", "", "", ""])
        reading = "" if item["reading"] is None else f"{item['reading']:g} {item['unit'] or ''}".strip()
        follow = item["follow_up"] or ""
        rows.append(
            [
                item["position"],
                item["text"],
                reading,
                (item["outcome"] or "-").upper(),
                f"{follow} {item['notes'] or ''}".strip(),
            ]
        )
    if rows:
        doc.heading("Checklist")
        doc.table(["#", "Item", "Reading", "Result", "Notes / follow-up"], rows, widths=[0.06, 0.46, 0.13, 0.1, 0.25])
    photos = await _photo_list(db, [i["id"] for i in read["items"]], {i["id"]: i["position"] for i in read["items"]})
    if photos:
        doc.heading("Photos")
        doc.table(["#", "File", "Uploaded"], photos, widths=[0.08, 0.62, 0.3])
    if inspection.notes:
        doc.heading("Notes")
        doc.paragraph(inspection.notes)
    rounds = await history(db, inspection)
    returns = [r for r in rounds if r["to_status"] == InspectionStatus.RETURNED]
    if returns:
        doc.heading("Review history")
        doc.table(
            ["When", "By", "Returned because"],
            [[str(r["changed_at"])[:16], r["changed_by_name"] or "-", r["note"] or ""] for r in returns],
            widths=[0.2, 0.25, 0.55],
        )
    doc.heading("Signatures")
    sigs = read["signatures"]
    if not sigs:
        doc.paragraph("Not signed.")
    else:
        doc.table(
            ["Role", "Signer", "Mode / state", "Signed (UTC)", "Content SHA-256"],
            [
                [
                    s["role"].replace("_", " "),
                    (s["signer_snapshot"].get("name") or s["signer_name_stated"] or "-")
                    + (f" (on behalf of #{s['on_behalf_of_user_id']})" if s["on_behalf_of_user_id"] else ""),
                    f"{s['mode'] or 'attested'} / {_sig_state(s)}",
                    str(s["signed_at"])[:19].replace("T", " "),
                    s["content_sha256"][:16] + "…",
                ]
                for s in sigs
            ],
            widths=[0.14, 0.26, 0.22, 0.18, 0.2],
        )
        for s in sigs:
            if s["intent_text"] and s["status"] in (SignatureStatus.VALID, SignatureStatus.PROVISIONAL):
                doc.paragraph(f"{s['role'].replace('_', ' ').capitalize()}: “{s['intent_text']}”")
    return render_pdf(doc)


def _sig_state(s: dict[str, Any]) -> str:
    if s["status"] == SignatureStatus.PROVISIONAL:
        return "provisional client signature"
    if s["status"] == SignatureStatus.VALID and s["confirmed_at"]:
        return "confirmed by client"
    return str(s["status"])


async def _photo_list(db: AsyncSession, item_ids: list[int], positions: dict[int, int]) -> list[list[Any]]:
    if not item_ids:
        return []
    rows = await db.execute(
        select(StoredFile)
        .where(StoredFile.entity_type == ITEM_ENTITY, StoredFile.entity_id.in_(item_ids), StoredFile.is_latest.is_(True))
        .order_by(StoredFile.entity_id, StoredFile.id)
    )
    return [
        [positions.get(f.entity_id or 0, ""), getattr(f, "filename", None) or getattr(f, "name", ""), str(f.created_at)[:16]]
        for f in rows.scalars()
    ]

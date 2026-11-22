from collections import defaultdict
from datetime import UTC, date, datetime
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
from ..projects.models import Project
from ..tasks.service import create_task
from ..user.models import User
from .constants import FLOW, InspectionStatus, ResponseType, Result
from .models import ChecklistTemplate, Inspection, InspectionItem, InspectionSettings
from .schemas import (
    ChecklistTemplateRead,
    InspectionItemRead,
    InspectionRead,
    InspectionTrendGroup,
    InspectionTrendMonth,
    InspectionTrendPoint,
)
from .starters import STARTERS

ENTITY = "inspection"
ITEM_ENTITY = "inspection_item"
NCR_REQUESTED = "inspections.item.ncr_requested"


class TemplateNotFoundError(ResourceNotFoundError):
    public_detail = "Checklist template not found."


class InspectionNotFoundError(ResourceNotFoundError):
    public_detail = "Inspection not found."


def link_of(inspection: Inspection) -> str:
    return f"/inspections?project={inspection.project_id}&id={inspection.id}"


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


# --- templates ---------------------------------------------------------------------------------------


def read_template(t: ChecklistTemplate) -> dict[str, Any]:
    count = sum(len(s.get("items", [])) for s in t.sections)
    return ChecklistTemplateRead.model_validate(t).model_copy(update={"item_count": count}).model_dump(mode="json")


async def get_template(db: AsyncSession, template_id: int) -> ChecklistTemplate:
    t = await db.get(ChecklistTemplate, template_id)
    if t is None:
        raise TemplateNotFoundError("No such template")
    return t


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


async def read_inspections(
    db: AsyncSession, inspections: list[Inspection], *, with_items: bool = False
) -> list[dict[str, Any]]:
    names = await user_names(db, {i.inspector_id for i in inspections})
    out = []
    for i in inspections:
        items: list[InspectionItemRead] = []
        if with_items:
            rows = await items_of(db, i.id)
            photos = await photo_counts(db, [r.id for r in rows])
            items = [InspectionItemRead.model_validate(r).model_copy(update={"photo_count": photos.get(r.id, 0)}) for r in rows]
        out.append(
            InspectionRead.model_validate(i)
            .model_copy(
                update={
                    "inspector_name": names.get(i.inspector_id) if i.inspector_id else None,
                    "total": i.passed + i.failed + i.not_applicable + i.unanswered,
                    "items": items,
                }
            )
            .model_dump(mode="json")
        )
    return out


async def create_inspection(db: AsyncSession, template: ChecklistTemplate, values: dict[str, Any], user_id: int) -> Inspection:
    inspection = Inspection(
        project_id=template.project_id,
        code=await next_reference(db, "INS", template.project_id),
        title=values.pop("title", None) or template.name,
        template_id=template.id,
        template_name=template.name,
        template_version=template.version,
        trade=values.pop("trade", None) or template.trade,
        created_by_id=user_id,
        status=InspectionStatus.PLANNED.value,
        **values,
    )
    db.add(inspection)
    await db.flush()
    position = 0
    items = []
    for section in template.sections:
        for raw in section.get("items", []):
            position += 1
            items.append(
                InspectionItem(
                    inspection_id=inspection.id,
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
    db.add_all(items)
    rescore(inspection, items)
    await record_transition(db, ENTITY, inspection.id, None, inspection.status, user_id, note=f"From {template.name}")
    await db.commit()
    return inspection


def _editable(inspection: Inspection) -> None:
    if inspection.status in (InspectionStatus.COMPLETED, InspectionStatus.CLOSED):
        raise UnprocessableEntityException("This inspection is completed. Reopen it to change the results.")


async def fill_items(db: AsyncSession, inspection: Inspection, answers: list[dict[str, Any]], user_id: int) -> None:
    _editable(inspection)
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
    await db.commit()


async def change_status(db: AsyncSession, inspection: Inspection, target: str, note: str | None, user_id: int) -> None:
    if target == InspectionStatus.COMPLETED and inspection.status != InspectionStatus.CLOSED:
        raise UnprocessableEntityException("Complete an inspection through /complete, which scores it and raises follow-ups.")
    assert_transition(FLOW, inspection.status, target)
    await record_transition(db, ENTITY, inspection.id, inspection.status, target, user_id, note)
    inspection.status = target
    if target == InspectionStatus.IN_PROGRESS:
        inspection.completed_at = None
    await db.commit()


async def complete(
    db: AsyncSession, inspection: Inspection, choice: dict[str, Any], user: dict[str, Any]
) -> list[dict[str, Any]]:
    """Score, then raise a follow-up for every failed item that has none yet: a task by default, or an NCR
    (when that module is on for the project; the ``inspections.item.ncr_requested`` event goes out either way).
    Returns the events to publish once committed."""
    if inspection.status == InspectionStatus.PLANNED:
        raise UnprocessableEntityException("Fill the checklist before completing the inspection.")
    assert_transition(FLOW, inspection.status, InspectionStatus.COMPLETED)
    items = await items_of(db, inspection.id)
    rescore(inspection, items)
    if inspection.unanswered and not choice.get("allow_unanswered"):
        raise UnprocessableEntityException(f"{inspection.unanswered} item(s) are unanswered.")
    failed = [i for i in items if i.outcome == Result.FAIL]
    photos = await photo_counts(db, [i.id for i in failed if i.requires_photo_on_fail])
    missing = [i for i in failed if i.requires_photo_on_fail and not photos.get(i.id)]
    if missing:
        listed = "; ".join(f"{i.position}. {i.text}" for i in missing[:5])
        raise UnprocessableEntityException(f"Failed items need a photo: {listed}")

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
    await db.commit()
    return events


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


# --- trends ------------------------------------------------------------------------------------------


async def trends(db: AsyncSession, project_id: int, group_by: str) -> list[InspectionTrendGroup]:
    done = (InspectionStatus.COMPLETED.value, InspectionStatus.CLOSED.value)
    rows = list(
        (
            await db.execute(
                select(Inspection)
                .where(Inspection.project_id == project_id, Inspection.status.in_(done))
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


# --- report ------------------------------------------------------------------------------------------


async def report_pdf(db: AsyncSession, inspection: Inspection) -> bytes:
    read = (await read_inspections(db, [inspection], with_items=True))[0]
    project = await db.get(Project, inspection.project_id)
    doc = Document(
        title=f"Inspection {inspection.code}: {inspection.title}",
        subtitle=f"{project.code} {project.name}" if project else "",
        footer=inspection.code,
    )
    doc.fields(
        [
            ("Checklist", f"{inspection.template_name or '-'} (v{inspection.template_version or 1})"),
            ("Location / area", " / ".join(p for p in (inspection.location, inspection.area) if p) or "-"),
            ("Trade", inspection.trade or "-"),
            ("Inspector", read["inspector_name"] or "-"),
            ("Inspected", inspection.inspected_date.isoformat() if inspection.inspected_date else "-"),
            ("Status", inspection.status.replace("_", " ").capitalize()),
            (
                "Score",
                f"{inspection.pass_rate if inspection.pass_rate is not None else '-'}% "
                f"({inspection.passed} pass, {inspection.failed} fail, {inspection.not_applicable} N/A)",
            ),
        ]
    )
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
    doc.heading("Checklist")
    doc.table(["#", "Item", "Reading", "Result", "Notes / follow-up"], rows, widths=[0.06, 0.46, 0.13, 0.1, 0.25])
    if inspection.notes:
        doc.heading("Notes")
        doc.paragraph(inspection.notes)
    return render_pdf(doc)

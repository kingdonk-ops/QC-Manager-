"""Scoring and completion of an inspection record: item scoring, the informal complete action, the shared
finish step (follow-ups for failed items), the photo-on-fail check and the events published after commit.

This file imports only lower-level helpers; ``service`` imports from it and re-exports the moved names."""

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import assert_transition, record_transition
from ..files.models import StoredFile
from ..ncr.auto import raise_automatic
from ..ncr.models import Ncr
from ..ncr.service import create_ncr
from ..tasks.service import create_task
from . import ncr_text
from .constants import FLOW, InspectionStatus, ResponseType, Result
from .models import AcceptanceCriterion, ChecklistTemplate, Inspection, InspectionItem, InspectionSettings
from .tolerance import criterion_clause

ENTITY = "inspection"
ITEM_ENTITY = "inspection_item"
NCR_REQUESTED = "inspections.item.ncr_requested"


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


# --- completion --------------------------------------------------------------------------------------


async def complete(
    db: AsyncSession, inspection: Inspection, choice: dict[str, Any], user: dict[str, Any]
) -> list[dict[str, Any]]:
    """Complete an informal record: submit is final (KERP: no review step)."""
    if inspection.is_formal:
        raise UnprocessableEntityException("A formal inspection is submitted for review (/submit), not completed directly.")
    if inspection.status == InspectionStatus.PLANNED:
        raise UnprocessableEntityException("Fill the checklist before completing the inspection.")
    assert_transition(FLOW, inspection.status, InspectionStatus.COMPLETED)
    events = await finish(db, inspection, choice, user)
    inspection.result = Result.FAIL.value if inspection.failed else Result.PASS.value
    inspection.conditional = bool(choice.get("conditional"))
    if choice.get("measured_value") is not None:
        inspection.measured_value = choice["measured_value"]
    await raise_record_report(db, inspection, choice, user, events)
    await db.commit()
    return events


async def finish(
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
    await photos_for_failures(db, failed)

    choices = {c["item_id"]: c for c in choice.get("follow_ups", [])}
    ncr_on = await is_enabled(db, "ncr", inspection.project_id)
    events: list[dict[str, Any]] = []
    for item in failed:
        if item.task_id or item.ncr_id:
            continue
        picked = choices.get(item.id, {})
        action = str(picked.get("action") or "task")
        if item.criterion_id and action != "none":
            action = "ncr"  # a failure against a criterion raises its own report instead of the default task
        assignee = picked.get("assignee_id") or choice.get("default_assignee_id")
        due = picked.get("due_date") or choice.get("default_due_date")
        title = f"{inspection.code} #{item.position}: {item.text}"
        reading = f"Reading {item.reading:g}{' ' + item.unit if item.unit else ''}. " if item.reading is not None else ""
        limits = limit_wording(item)
        detail = f"{item.section}: {item.text}\n{reading}{limits}{item.notes or ''}".strip()
        item.follow_up = action
        if action == "ncr":
            if ncr_on:
                if item.criterion_id:
                    ncr = await item_report(db, inspection, item, picked, assignee, user)
                else:
                    ncr = await create_ncr(
                        db,
                        project_id=inspection.project_id,
                        title=title,
                        raised_by_id=user["id"],
                        commit=False,
                        description=detail,
                        location=_location(inspection),
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


async def photos_for_failures(db: AsyncSession, failed: list[InspectionItem]) -> None:
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


def limit_wording(item: InspectionItem) -> str:
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


# --- automatic reports -------------------------------------------------------------------------------


def _location(inspection: Inspection) -> str | None:
    return " / ".join(p for p in (inspection.location, inspection.area) if p) or None


async def _template_category(db: AsyncSession, inspection: Inspection) -> str | None:
    template = await db.get(ChecklistTemplate, inspection.template_id) if inspection.template_id else None
    return template.issue_category if template else None


async def item_report(
    db: AsyncSession, inspection: Inspection, item: InspectionItem, picked: dict[str, Any], assignee: Any, user: dict[str, Any]
) -> Ncr:
    """The automatic report of one failed item that is linked to a criterion: quotes the criterion and the reading.
    Severity defaults to major; an explicit follow-up choice still supplies the assignee and severity."""
    criterion = await db.get(AcceptanceCriterion, item.criterion_id) if item.criterion_id else None
    reading = None if item.reading is None else f"{item.reading:g}"
    number = f"{inspection.code} item {item.position}"
    return await raise_automatic(
        db,
        project_id=inspection.project_id,
        title=ncr_text.event_title("item_failed", f"{inspection.code} #{item.position}", item.text),
        description=ncr_text.description(
            source_label="inspection",
            number=number,
            record_description=f"{item.section}: {item.text}",
            result_notes=item.notes,
            clause=criterion_clause(criterion, reading) if criterion else None,
        ),
        raised_by_id=user["id"],
        severity=picked.get("severity") or ncr_text.default_severity("fail"),
        source="inspection",
        source_reference=number,
        source_data=ncr_text.source_data(
            source_kind="inspection_item",
            record_id=item.id,
            number=number,
            outcome="fail",
            criterion_id=item.criterion_id,
            measured_value=reading,
            inspection_id=inspection.id,
            item_position=item.position,
        ),
        category=await _template_category(db, inspection),
        location=_location(inspection),
        trade=inspection.trade,
        responsible_user_id=assignee,
        inspection_id=inspection.id,
        inspection_item_id=item.id,
    )


async def raise_record_report(
    db: AsyncSession, inspection: Inspection, choice: dict[str, Any], user: dict[str, Any], events: list[dict[str, Any]]
) -> None:
    """After the record's result is set: a failed record raises a report when it carries a record-level criterion or
    the project reports every failure; a conditional acceptance (result pass plus the flag) raises one too. A plain
    pass raises nothing. Same transaction as the result; the identifier is stored before the response. With the
    issues module off the outcome is recorded and only the report-requested event goes out."""
    if inspection.result == Result.FAIL.value:
        outcome = "fail"
    elif inspection.result == Result.PASS.value and inspection.conditional:
        outcome = "conditional"
    else:
        return
    if outcome == "fail" and inspection.criterion_id is None:
        settings = await db.get(InspectionSettings, inspection.project_id)
        if settings is None or not settings.auto_report_on_failure:
            return
    kind = "inspection_failed" if outcome == "fail" else "inspection_conditional"
    title = ncr_text.event_title(kind, inspection.code, inspection.title)
    payload: dict[str, Any] = {
        "project_id": inspection.project_id,
        "inspection_id": inspection.id,
        "item_id": None,
        "ncr_id": None,
        "title": title,
    }
    if await is_enabled(db, "ncr", inspection.project_id):
        criterion = await db.get(AcceptanceCriterion, inspection.criterion_id) if inspection.criterion_id else None
        try:
            ncr = await raise_automatic(
                db,
                project_id=inspection.project_id,
                title=title,
                description=ncr_text.description(
                    source_label="inspection",
                    number=inspection.code,
                    record_description=inspection.notes,
                    result_notes=choice.get("note"),
                    clause=criterion_clause(criterion, inspection.measured_value) if criterion else None,
                ),
                raised_by_id=user["id"],
                severity=choice.get("report_severity") or inspection.proposed_severity or ncr_text.default_severity(outcome),
                source="inspection",
                source_reference=inspection.code,
                source_data=ncr_text.source_data(
                    source_kind="inspection",
                    record_id=inspection.id,
                    number=inspection.code,
                    outcome=outcome,
                    criterion_id=inspection.criterion_id,
                    measured_value=inspection.measured_value,
                    conditional=bool(inspection.conditional),
                ),
                category=await _template_category(db, inspection),
                location=_location(inspection),
                trade=inspection.trade,
                inspection_id=inspection.id,
            )
        except Exception:
            # The outcome, the follow-ups and the report are one unit of work: discard all of it.
            await db.rollback()
            raise
        inspection.report_id = ncr.id
        payload["ncr_id"] = ncr.id
    events.append(payload)

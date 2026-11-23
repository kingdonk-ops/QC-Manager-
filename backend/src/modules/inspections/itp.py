"""Inspection and Test Plans: a template of kind ``itp`` applied to one anchor becomes an instance whose
activities are ``kind=itp`` records (one per line), each carrying its intervention points per party and the
checklist of its ITR form. A Hold point blocks every later line until it is released by a formal sign-off."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.records import next_reference, record_transition
from ..asset_tree import service as tree
from ..common.exceptions import ResourceNotFoundError
from . import anchoring, criteria, eligibility, signing
from .callouts import latest_request_summary
from .constants import Area, DelegationKind, InspectionStatus, Kind, SignatureRole, has_hold
from .models import ChecklistTemplate, Inspection, ItpInstance
from .service import ENTITY, checklist_items, ensure_revision, rescore


class InstanceNotFoundError(ResourceNotFoundError):
    public_detail = "ITP instance not found."


async def get_instance(db: AsyncSession, instance_id: int) -> ItpInstance:
    i = await db.get(ItpInstance, instance_id)
    if i is None:
        raise InstanceNotFoundError("No such ITP instance")
    return i


async def instantiate(
    db: AsyncSession, template: ChecklistTemplate, node_id: int | None, item_id: int | None, user_id: int
) -> ItpInstance:
    if template.kind != Kind.ITP:
        raise UnprocessableEntityException("Only an ITP template can be applied to an anchor.")
    if not template.active:
        raise UnprocessableEntityException("That ITP template is retired.")
    await anchoring.check_anchor(db, template.project_id, node_id, item_id)
    if item_id is not None and template.item_type_key:
        item = await tree.get_item(db, item_id, template.project_id)
        if item.item_type_key != template.item_type_key:
            raise UnprocessableEntityException(
                f"This ITP is written for '{template.item_type_key}' Items; that Item is a '{item.item_type_key}'."
            )
    clash = await db.scalar(
        select(ItpInstance.code).where(
            ItpInstance.template_id == template.id,
            ItpInstance.status == "active",
            ItpInstance.node_id.is_(None) if node_id is None else ItpInstance.node_id == node_id,
            ItpInstance.item_id.is_(None) if item_id is None else ItpInstance.item_id == item_id,
        )
    )
    if clash:
        raise UnprocessableEntityException(f"{clash} already applies this ITP to that anchor.")
    revision = await ensure_revision(db, template, user_id)
    instance = ItpInstance(
        project_id=template.project_id,
        code=await next_reference(db, "ITP", template.project_id),
        template_id=template.id,
        template_name=template.name,
        template_version=template.version,
        node_id=node_id,
        item_id=item_id,
        created_by_id=user_id,
    )
    db.add(instance)
    await db.flush()
    for position, act in enumerate(template.activities, start=1):
        form = await db.get(ChecklistTemplate, act["form_template_id"]) if act.get("form_template_id") else None
        line = Inspection(
            project_id=template.project_id,
            code=f"{instance.code}/{position:02d}",
            title=act["title"][:300],
            template_id=template.id,
            template_name=template.name,
            template_version=template.version,
            template_revision_id=revision.id,
            trade=template.trade,
            created_by_id=user_id,
            status=InspectionStatus.PLANNED.value,
            kind=Kind.ITP.value,
            category=Area.QA_ITP.value,
            is_formal=True,
            requires_client_signature=bool(form and form.requires_client_signature),
            required_qualification=act.get("required_qualification")
            or (form.required_qualification if form else None)
            or template.required_qualification,
            node_id=node_id,
            item_id=item_id,
            itp_instance_id=instance.id,
            itp_position=position,
            points={k: str(v) for k, v in (act.get("points") or {}).items()},
            acceptance_criteria=act.get("acceptance_criteria"),
            criterion_id=act.get("criterion_id"),
            verifying_document=act.get("verifying_document") or (form.name if form else None),
            spec_ref=act.get("spec_ref"),
        )
        db.add(line)
        await db.flush()
        sections = await criteria.snapshot_sections(db, template.project_id, form.sections if form else [])
        items = checklist_items(line.id, sections)
        db.add_all(items)
        rescore(line, items)
        await record_transition(db, ENTITY, line.id, None, line.status, user_id, note=f"{instance.code} line {position}")
    await db.commit()
    return instance


async def lines_of(db: AsyncSession, instance_id: int) -> list[Inspection]:
    rows = await db.execute(
        select(Inspection).where(Inspection.itp_instance_id == instance_id).order_by(Inspection.itp_position)
    )
    return list(rows.scalars())


async def read_instance(db: AsyncSession, instance: ItpInstance, *, with_lines: bool = True) -> dict[str, Any]:
    lines = await lines_of(db, instance.id)
    labels = await anchoring.anchor_labels(db, [(instance.node_id, instance.item_id)])
    done = [line for line in lines if line.status in (InspectionStatus.COMPLETED, InspectionStatus.CLOSED)]
    out: dict[str, Any] = {
        "id": instance.id,
        "project_id": instance.project_id,
        "code": instance.code,
        "template_id": instance.template_id,
        "template_name": instance.template_name,
        "template_version": instance.template_version,
        "node_id": instance.node_id,
        "item_id": instance.item_id,
        "anchor_label": labels.get((instance.node_id, instance.item_id)),
        "status": instance.status,
        "lines_total": len(lines),
        "lines_done": len(done),
        "progress": round(len(done) * 100.0 / len(lines), 1) if lines else 0.0,
        "holds_open": sum(1 for line in lines if has_hold(line.points) and line.hold_released_at is None),
        "created_at": instance.created_at,
        "lines": [],
    }
    if with_lines:
        for line in lines:
            witness, per_party = await eligibility.witness_status(db, line)
            blocked = await eligibility.hold_findings(db, line)
            out["lines"].append(
                {
                    "id": line.id,
                    "code": line.code,
                    "position": line.itp_position,
                    "title": line.title,
                    "status": line.status,
                    "result": line.result,
                    "points": line.points,
                    "acceptance_criteria": line.acceptance_criteria,
                    "verifying_document": line.verifying_document,
                    "spec_ref": line.spec_ref,
                    "required_qualification": line.required_qualification,
                    "criterion_id": line.criterion_id,
                    "item_count": line.passed + line.failed + line.not_applicable + line.unanswered,
                    "has_hold": has_hold(line.points),
                    "hold_released_at": line.hold_released_at,
                    "hold_released_by_id": line.hold_released_by_id,
                    "blocked": bool(blocked),
                    "blocked_by": [f.message for f in blocked],
                    **eligibility.line_gate_state(line, blocked),
                    "witness_status": witness,
                    "witness_by_party": per_party,
                    "request": await latest_request_summary(db, line.id),
                }
            )
    return out


async def release_hold(
    db: AsyncSession,
    line: Inspection,
    user_id: int,
    held: frozenset[str],
    *,
    accept_intent: bool,
    on_behalf_of_user_id: int | None = None,
) -> None:
    """The formal Hold release of one line (always signed individually). Competency checked as of today."""
    if line.kind != Kind.ITP:
        raise UnprocessableEntityException("Only an ITP line has a Hold point to release.")
    findings = [f for f in await eligibility.check(db, line, "hold_release", user_id=user_id) if f.blocking]
    if findings:
        raise UnprocessableEntityException("; ".join(f"{f.code}: {f.message}" for f in findings))
    if not accept_intent:
        raise UnprocessableEntityException("Accept the signing statement to release the hold (accept_intent).")
    delegation = await signing.on_behalf(db, line.project_id, user_id, on_behalf_of_user_id, DelegationKind.HOLD_POINT)
    snapshot, _ = await signing.competency_findings(db, user_id, line.required_qualification, date.today())
    await signing.sign(
        db,
        line,
        SignatureRole.HOLD_RELEASE,
        user_id,
        held=held,
        competencies=snapshot,
        on_behalf_of_user_id=on_behalf_of_user_id if delegation else None,
        delegation_id=delegation.id if delegation else None,
    )
    line.hold_released_at = datetime.now(UTC)
    line.hold_released_by_id = user_id
    await record_transition(db, ENTITY, line.id, line.status, line.status, user_id, note="Hold point released")
    await db.commit()


async def count_instances(db: AsyncSession, where: list[Any]) -> int:
    return await db.scalar(select(func.count()).select_from(ItpInstance).where(*where)) or 0

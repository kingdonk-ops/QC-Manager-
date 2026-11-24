"""Standalone quality gates: create, edit, delete, release, waive and void, the blocking-gate lookups the
can-proceed query and the MDR hook share, and the inspection delete guard.

Only a pending gate changes; released, waived and void gates are permanent evidence. Release, waiver and void are
written to the audit ledger in the same transaction, and the release event is published only after the commit.
Attachment targets are checked through read-only lookups; the dossier table is found by name so this module never
imports the MDR module, and a switched-off module answers not-found."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.database.session import Base
from ...infrastructure.http_exceptions import ConflictException, ForbiddenException, UnprocessableEntityException
from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import NumberingError, link_allocation, next_number
from ..asset_tree import service as tree
from ..asset_tree.models import AssetItem
from ..common.exceptions import ResourceNotFoundError
from ..ncr.models import Ncr
from ..tasks.models import Task
from . import criteria
from .constants import AttachmentKind, GateStatus, InspectionStatus
from .gate_rules import (
    attachment_pair_error,
    authority_satisfies,
    blocks_progress,
    is_waivable,
    release_digest,
    release_snapshot,
)
from .models import Inspection, QualityGate

ENTITY = "quality_gate"
NUMBER_KIND = "quality_gate"
RELEASED_EVENT = "inspections.gate.released"
DONE = (InspectionStatus.COMPLETED.value, InspectionStatus.CLOSED.value)


class GateNotFoundError(ResourceNotFoundError):
    public_detail = "Quality gate not found."


class LinkedRecordNotFoundError(ResourceNotFoundError):
    public_detail = "Linked record not found."


async def get_gate(db: AsyncSession, gate_id: int) -> QualityGate:
    gate = await db.get(QualityGate, gate_id)
    if gate is None:
        raise GateNotFoundError("No such gate")
    return gate


def _pending(gate: QualityGate, action: str) -> None:
    if gate.status != GateStatus.PENDING:
        raise UnprocessableEntityException(f"Gate {gate.number} is {gate.status}; only a pending gate can be {action}.")


# --- references --------------------------------------------------------------------------------------


async def _inspection_of_project(db: AsyncSession, project_id: int, inspection_id: int) -> Inspection:
    """Any record of the single inspection register, ITP lines included; a foreign or missing one is not found."""
    found = await db.get(Inspection, inspection_id)
    if found is None or found.project_id != project_id:
        raise LinkedRecordNotFoundError("No such inspection on this project")
    return found


async def _dossier_exists(db: AsyncSession, project_id: int, dossier_id: int) -> bool:
    table = Base.metadata.tables.get("mdr_dossiers")
    if table is None or not await is_enabled(db, "mdr", project_id):
        return False
    return bool(await db.scalar(select(table.c.id).where(table.c.id == dossier_id, table.c.project_id == project_id)))


async def check_attachment(db: AsyncSession, project_id: int, kind: str, target_id: int) -> None:
    """The attachment target must exist in the project; a module that is switched off answers not-found."""
    if kind == AttachmentKind.NODE:
        await tree.get_node(db, target_id, project_id)
    elif kind == AttachmentKind.ITEM:
        await tree.get_item(db, target_id, project_id)
    elif kind == AttachmentKind.INSPECTION:
        await _inspection_of_project(db, project_id, target_id)
    elif kind == AttachmentKind.TASK:
        task = await db.get(Task, target_id) if await is_enabled(db, "tasks", project_id) else None
        if task is None or task.project_id != project_id:
            raise LinkedRecordNotFoundError("No such task on this project")
    elif kind == AttachmentKind.DOSSIER and not await _dossier_exists(db, project_id, target_id):
        raise LinkedRecordNotFoundError("No such dossier on this project")


async def check_links(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    if values.get("inspection_id") is not None:
        await _inspection_of_project(db, project_id, values["inspection_id"])
    if values.get("criterion_id") is not None:
        await criteria.get_criterion(db, values["criterion_id"], project_id)
    if values.get("attachment_kind") is not None:
        await check_attachment(db, project_id, values["attachment_kind"], values["attachment_id"])


# --- create, edit, delete ----------------------------------------------------------------------------


async def create_gate(db: AsyncSession, values: dict[str, Any], user_id: int) -> QualityGate:
    project_id = values["project_id"]
    await check_links(db, project_id, values)
    values = {**values, "blocks_progress": blocks_progress(values["kind"], values.get("blocks_progress"))}
    try:
        number = await next_number(db, NUMBER_KIND, project_id, fallback_prefix="GATE", user_id=user_id)
        gate = QualityGate(number=number, created_by_id=user_id, **values)
        db.add(gate)
        await db.flush()
        await link_allocation(db, project_id, NUMBER_KIND, number, (ENTITY, gate.id))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if isinstance(exc, NumberingError):
            raise UnprocessableEntityException("; ".join(exc.problems)) from exc
        raise
    return gate


async def update_gate(db: AsyncSession, gate: QualityGate, changes: dict[str, Any]) -> None:
    """Partial update of a pending gate. The attachment pair is checked on the merged values, so a patch that
    sets only one half is refused."""
    _pending(gate, "edited")
    refs = {k: v for k, v in changes.items() if k in ("inspection_id", "criterion_id")}
    if "attachment_kind" in changes or "attachment_id" in changes:
        kind = changes.get("attachment_kind", gate.attachment_kind)
        target = changes.get("attachment_id", gate.attachment_id)
        error = attachment_pair_error(kind, target)
        if error:
            raise UnprocessableEntityException(error)
        refs.update(attachment_kind=kind, attachment_id=target)
    await check_links(db, gate.project_id, refs)
    for key, value in changes.items():
        setattr(gate, key, value)
    await db.commit()


async def delete_gate(db: AsyncSession, gate: QualityGate) -> None:
    if gate.status != GateStatus.PENDING:
        raise ConflictException(
            f"Gate {gate.number} is {gate.status}: a decided gate carries the decision that let work proceed, so it is kept."
        )
    await db.delete(gate)
    await db.commit()


# --- release, waive, void ----------------------------------------------------------------------------


async def _require_passed_inspection(db: AsyncSession, gate: QualityGate) -> None:
    """A linked inspection must have passed: completed or closed with result pass. A missing one fails closed."""
    if gate.inspection_id is None:
        return
    linked = await db.get(Inspection, gate.inspection_id)
    if linked is None:
        raise UnprocessableEntityException(f"The inspection linked to gate {gate.number} could not be found.")
    if linked.status in DONE and linked.result == "pass":
        return
    state = linked.status.replace("_", " ")
    if linked.status in DONE:
        state += f" with result {linked.result or 'none'}"
    raise UnprocessableEntityException(f"Linked inspection {linked.code} is {state}; it has not passed.")


async def release_gate(
    db: AsyncSession,
    gate: QualityGate,
    *,
    user_id: int,
    level: str,
    justification: str | None,
    released_at: datetime | None,
    ip: str | None,
) -> QualityGate:
    """Release needs the asserted level to meet the gate's requirement and a linked inspection to have passed. It
    stores who, at which asserted level, when, why, from where and a digest of the gate's identity."""
    _pending(gate, "released")
    if not authority_satisfies(level, gate.authority):
        raise ForbiddenException(f"Gate {gate.number} needs {gate.authority} authority or higher; you asserted {level}.")
    await _require_passed_inspection(db, gate)
    digest = release_digest(
        release_snapshot(gate.number, gate.kind, gate.inspection_id, gate.attachment_kind, gate.attachment_id, level)
    )
    try:
        gate.status = GateStatus.RELEASED.value
        gate.released_by_id = user_id
        gate.released_level = level
        gate.released_at = released_at or datetime.now(UTC)
        gate.release_justification = justification
        gate.release_ip = ip
        gate.release_digest = digest
        await record_audit(
            db,
            "inspections.gate.released",
            ENTITY,
            gate.id,
            actor_id=user_id,
            project_id=gate.project_id,
            summary=f"{gate.number} released at {level}",
            before={"status": GateStatus.PENDING.value},
            after={"status": GateStatus.RELEASED.value, "level": level, "digest": digest},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await publish(
        RELEASED_EVENT,
        {
            "project_id": gate.project_id,
            "gate_id": gate.id,
            "number": gate.number,
            "kind": gate.kind,
            "level": level,
            "attachment_kind": gate.attachment_kind,
            "attachment_id": gate.attachment_id,
        },
    )
    return gate


async def waive_gate(db: AsyncSession, gate: QualityGate, *, user_id: int, reason: str) -> QualityGate:
    """A waiver is for witness, surveillance and review gates only and compares no authority level."""
    _pending(gate, "waived")
    if not is_waivable(gate.kind):
        raise ConflictException(f"Gate {gate.number} is a {gate.kind} and is never waived; release it at the required level.")
    try:
        gate.status = GateStatus.WAIVED.value
        gate.waived_by_id = user_id
        gate.waiver_reason = reason.strip()
        await record_audit(
            db,
            "inspections.gate.waived",
            ENTITY,
            gate.id,
            actor_id=user_id,
            project_id=gate.project_id,
            summary=f"{gate.number} waived",
            before={"status": GateStatus.PENDING.value},
            after={"status": GateStatus.WAIVED.value, "reason": gate.waiver_reason},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return gate


async def void_gate(db: AsyncSession, gate: QualityGate, *, user_id: int) -> QualityGate:
    _pending(gate, "voided")
    try:
        gate.status = GateStatus.VOID.value
        await record_audit(
            db,
            "inspections.gate.voided",
            ENTITY,
            gate.id,
            actor_id=user_id,
            project_id=gate.project_id,
            summary=f"{gate.number} voided",
            before={"status": GateStatus.PENDING.value},
            after={"status": GateStatus.VOID.value},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return gate


# --- what is still blocking --------------------------------------------------------------------------


def attached_to(kind: str, target_id: int) -> Any:
    return and_(QualityGate.attachment_kind == kind, QualityGate.attachment_id == target_id)


def inspection_gate_match(inspection_id: int) -> Any:
    """A gate belongs to an inspection record when it is attached to it or names it as its linked inspection."""
    return or_(QualityGate.inspection_id == inspection_id, attached_to(AttachmentKind.INSPECTION.value, inspection_id))


async def blocking_gates(db: AsyncSession, project_id: int, kind: str, target_id: int) -> list[QualityGate]:
    """Gates attached to the entity that block progress and are still pending, oldest first. For an inspection, a gate
    that names the record in its linked-inspection field counts the same as one attached to it."""
    rows = await db.execute(
        select(QualityGate)
        .where(
            QualityGate.project_id == project_id,
            inspection_gate_match(target_id) if kind == AttachmentKind.INSPECTION.value else attached_to(kind, target_id),
            QualityGate.blocks_progress.is_(True),
            QualityGate.status == GateStatus.PENDING.value,
        )
        .order_by(QualityGate.id)
    )
    return list(rows.scalars())


async def dossier_scope_where(
    db: AsyncSession, project_id: int, node_ids: list[int] | None = None, dossier_id: int | None = None
) -> list[Any]:
    """The conditions that pick the pending blocking gates of a dossier scope; the hook and the counts share them.

    With scope nodes: gates attached to those nodes and their subtrees, to Items on them, to inspections anchored in
    the scope, or (when the dossier is named) to the dossier itself; gates with no attachment count project-wide
    whatever the scope. Without scope nodes: every pending blocking gate of the project."""
    where: list[Any] = [
        QualityGate.project_id == project_id,
        QualityGate.blocks_progress.is_(True),
        QualityGate.status == GateStatus.PENDING.value,
    ]
    if node_ids:
        scope: set[int] = set()
        for node_id in node_ids:
            scope |= set(await tree.subtree_ids(db, node_id, with_lineage=True))
        items = select(AssetItem.id).where(AssetItem.node_id.in_(scope))
        inspections = select(Inspection.id).where(
            Inspection.project_id == project_id, or_(Inspection.node_id.in_(scope), Inspection.item_id.in_(items))
        )
        reachable = [
            QualityGate.attachment_kind.is_(None),
            and_(QualityGate.attachment_kind == AttachmentKind.NODE.value, QualityGate.attachment_id.in_(scope)),
            and_(QualityGate.attachment_kind == AttachmentKind.ITEM.value, QualityGate.attachment_id.in_(items)),
            and_(QualityGate.attachment_kind == AttachmentKind.INSPECTION.value, QualityGate.attachment_id.in_(inspections)),
        ]
        if dossier_id is not None:
            reachable.append(attached_to(AttachmentKind.DOSSIER.value, dossier_id))
        where.append(or_(*reachable))
    return where


async def pending_blocking_gates(
    db: AsyncSession, project_id: int, node_ids: list[int] | None = None, dossier_id: int | None = None
) -> list[dict[str, Any]]:
    """The MDR gate hook: pending blocking gates in a dossier scope, as findings. Without a dossier identifier the
    answer is the same as it always was; with one, gates attached to that dossier are reported for a scoped dossier
    too."""
    where = await dossier_scope_where(db, project_id, node_ids, dossier_id)
    rows = (await db.execute(select(QualityGate).where(*where).order_by(QualityGate.id))).scalars()
    return [
        {
            "reference": gate.number,
            "message": f"Pending {gate.kind} gate: {gate.title}",
            "link": f"/inspections/gates/{gate.id}",
        }
        for gate in rows
    ]


async def pending_hold_counts(
    db: AsyncSession, project_id: int, node_ids: list[int] | None = None, dossier_id: int | None = None
) -> dict[str, int]:
    """Pending blocking gates of a dossier scope (holds, plus any other kind whose blocking flag was turned on):
    ``plain`` (no override covers them) and ``overridden`` (annotated, still pending). A pending blocking gate with no
    attachment counts whatever the scope."""
    where = await dossier_scope_where(db, project_id, node_ids, dossier_id)
    flag = QualityGate.override_id.is_not(None)
    rows = (await db.execute(select(flag, func.count()).where(*where).group_by(flag))).all()
    counts = {bool(covered): int(n) for covered, n in rows}
    return {"plain": counts.get(False, 0), "overridden": counts.get(True, 0)}


async def annotate_pending(
    db: AsyncSession, project_id: int, numbers: list[str], override_id: int, override_ref: str
) -> list[QualityGate]:
    """Stamp the still-pending, not yet annotated gates with these numbers with the override that covers them.

    Status, blocking flag and release digest are never touched, and a released, waived or void gate is skipped. The rows
    are locked so a concurrent release or void runs before or after, never between. Writes inside the caller's unit
    of work and never commits: the caller commits."""
    if not numbers:
        return []
    rows = await db.execute(
        select(QualityGate)
        .where(
            QualityGate.project_id == project_id,
            QualityGate.number.in_(numbers),
            QualityGate.status == GateStatus.PENDING.value,
            QualityGate.override_id.is_(None),
        )
        .order_by(QualityGate.id)
        .with_for_update()
    )
    annotated = list(rows.scalars())
    for gate in annotated:
        gate.override_id = override_id
        gate.override_ref = override_ref
    await db.flush()
    return annotated


# --- inspection delete guard -------------------------------------------------------------------------


async def check_deletable(db: AsyncSession, inspection: Inspection) -> None:
    """An inspection that carries a result, is closed, or is pointed at by a gate or a report is kept as a record."""
    if inspection.result is not None or inspection.status == InspectionStatus.CLOSED:
        state = inspection.status.replace("_", " ")
        extra = f" with result {inspection.result}" if inspection.result else ""
        raise ConflictException(f"Inspection {inspection.code} is {state}{extra}, so it is kept as a record and not deleted.")
    gates = await db.scalar(select(func.count()).select_from(QualityGate).where(inspection_gate_match(inspection.id)))
    reports = await db.scalar(select(func.count()).select_from(Ncr).where(Ncr.inspection_id == inspection.id))
    held = [f"{n} {label}" for n, label in ((gates, "gate(s)"), (reports, "non-conformance report(s)")) if n]
    if held:
        raise ConflictException(f"Inspection {inspection.code} is referenced by {', '.join(held)}, so it is not deleted.")

"""Temporary works permits: create, edit while draft, issue, activate, close, return to draft and delete.

Only the issue, activate and close actions (and the hourly sweep, to expired) change a permit's status. Every action
runs under a row lock the caller took, is written to the status history and the audit ledger in the same transaction,
and rolls the whole step back before the error is raised. The item's coordinator is notified after the commit. A
permit's expiry is not applied here: reads judge validity by date window."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.http_exceptions import ConflictException
from ...infrastructure.records import record_transition
from ..common.exceptions import ResourceNotFoundError
from ..notifications.constants import Category
from . import deletion, service, validation
from .constants import PERMIT_ENTITY, PermitStatus, site_today
from .models import TemporaryWorksItem, TemporaryWorksPermit
from .rules import Finding
from .transitions import permit_delete_refusal, permit_move, permit_return_to_draft

DRAFT = PermitStatus.DRAFT.value
TAKEN = "A permit with that number already exists in this project."


class PermitNotFoundError(ResourceNotFoundError):
    public_detail = "Temporary works permit not found."


async def get_permit(db: AsyncSession, permit_id: int) -> TemporaryWorksPermit:
    permit = await db.get(TemporaryWorksPermit, permit_id)
    if permit is None or permit.deleted_at is not None:
        raise PermitNotFoundError("No such temporary works permit")
    return permit


async def lock_permit(db: AsyncSession, permit: TemporaryWorksPermit) -> TemporaryWorksPermit:
    """Re-read the permit under a row lock, so two simultaneous actions run in turn and the second sees the new status."""
    await db.refresh(permit, with_for_update=True)
    if permit.deleted_at is not None:
        raise PermitNotFoundError("No such temporary works permit")
    return permit


async def number_taken(db: AsyncSession, project_id: int, number: str, exclude_id: int | None = None) -> bool:
    """Whether the number is in use in the project. A deleted permit still holds its number."""
    query = select(TemporaryWorksPermit.id).where(
        TemporaryWorksPermit.project_id == project_id, TemporaryWorksPermit.number == number
    )
    if exclude_id is not None:
        query = query.where(TemporaryWorksPermit.id != exclude_id)
    return (await db.scalar(query.limit(1))) is not None


async def list_permits(
    db: AsyncSession, project_id: int, *, item_id: int | None, status: str | None, offset: int, limit: int
) -> tuple[int, list[TemporaryWorksPermit]]:
    """A project's permits in creation order, filtered by item and status; deleted permits excluded."""
    where: list[Any] = [TemporaryWorksPermit.project_id == project_id, TemporaryWorksPermit.deleted_at.is_(None)]
    if item_id is not None:
        where.append(TemporaryWorksPermit.item_id == item_id)
    if status is not None:
        where.append(TemporaryWorksPermit.status == status)
    total = await db.scalar(select(func.count()).select_from(TemporaryWorksPermit).where(*where))
    rows = (
        await db.execute(
            select(TemporaryWorksPermit)
            .where(*where)
            .order_by(TemporaryWorksPermit.created_at, TemporaryWorksPermit.id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars()
    return total or 0, list(rows)


async def create_permit(
    db: AsyncSession, item: TemporaryWorksItem, values: dict[str, Any], user_id: int
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    """A draft permit against ``item``; its item and project come from the item, not the body."""
    values = service.plain(values)
    if await number_taken(db, item.project_id, values["number"]):
        raise ConflictException(TAKEN)
    found = validation.validate_permit({**values, "status": DRAFT})
    if found.errors:
        service.refuse(found.errors)
    try:
        permit = TemporaryWorksPermit(
            project_id=item.project_id, item_id=item.id, created_by_id=service.creator_of(user_id), **values
        )
        db.add(permit)
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(TAKEN) from exc
    except Exception:
        await db.rollback()
        raise
    return permit, found.warnings


async def update_permit(
    db: AsyncSession, permit: TemporaryWorksPermit, changes: dict[str, Any]
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    """Edit a draft. Once issued, a permit's fields are no longer edited (conflict); the rules run only when a
    rule-relevant field is supplied."""
    if permit.status != DRAFT:
        raise ConflictException("Only a permit in draft can be edited; send it back to draft first, with a reason.")
    changes = service.plain(changes)
    if changes.get("number") not in (None, permit.number) and await number_taken(
        db, permit.project_id, changes["number"], exclude_id=permit.id
    ):
        raise ConflictException(TAKEN)
    warnings: list[Finding] = []
    if validation.rules_apply(changes, validation.PERMIT_RULE_FIELDS):
        stored = {k: getattr(permit, k) for k in validation.PERMIT_RULE_FIELDS}
        found = validation.validate_permit(validation.merged(stored, changes))
        if found.errors:
            service.refuse(found.errors)
        warnings = found.warnings
    try:
        for key, value in changes.items():
            setattr(permit, key, value)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(TAKEN) from exc
    except Exception:
        await db.rollback()
        raise
    return permit, warnings


async def _step(
    db: AsyncSession, permit: TemporaryWorksPermit, target: str, user_id: int, **fields: Any
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    """One guarded step of the permit: the transition table, then the permit rules on the record as it would be."""
    before = permit.status
    refusal = permit_move(before, target)
    if refusal is not None:
        service.refuse([refusal])
    stored = {k: getattr(permit, k) for k in validation.PERMIT_RULE_FIELDS}
    found = validation.validate_permit(validation.merged(stored, {"status": target, **fields}))
    if found.errors:
        service.refuse(found.errors)
    try:
        permit.status = target
        for key, value in fields.items():
            setattr(permit, key, value)
        await record_transition(db, PERMIT_ENTITY, permit.id, before, target, user_id)
        await record_audit(
            db,
            f"temporary_works.permit.{target}",
            PERMIT_ENTITY,
            permit.id,
            actor_id=user_id,
            project_id=permit.project_id,
            summary=f"{permit.number}: {before} to {target}",
            before={"status": before},
            after={"status": target},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    item = await db.get(TemporaryWorksItem, permit.item_id)
    if item is not None:
        await service.notify_after_commit(
            db,
            [item.coordinator_user_id],
            Category.STATUS,
            f"{item.reference}: permit {permit.number} is {target}",
            body=f"The {permit.kind} permit {permit.number} moved from {before} to {target}.",
            link=service.link_of(item),
            entity=(PERMIT_ENTITY, permit.id),
            actor_id=user_id,
        )
    return permit, found.warnings


async def issue_permit(
    db: AsyncSession, permit: TemporaryWorksPermit, user_id: int
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    """Draft to issued, on today's site day. A permit to load must record both prerequisites: one error per missing
    flag, and it stays a draft."""
    return await _step(db, permit, PermitStatus.ISSUED.value, user_id, issued_on=site_today())


async def activate_permit(
    db: AsyncSession, permit: TemporaryWorksPermit, user_id: int
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    return await _step(db, permit, PermitStatus.ACTIVE.value, user_id)


async def close_permit(
    db: AsyncSession, permit: TemporaryWorksPermit, user_id: int
) -> tuple[TemporaryWorksPermit, list[Finding]]:
    """Issued or active to closed, with the closing user and day."""
    return await _step(db, permit, PermitStatus.CLOSED.value, user_id, closed_on=site_today(), closed_by_id=user_id)


async def return_to_draft(db: AsyncSession, permit: TemporaryWorksPermit, reason: str, user_id: int) -> TemporaryWorksPermit:
    """Send the permit back to draft with a mandatory, audit-logged reason. Its issued and closed days are cleared, so
    issuing it again records the day afresh."""
    refusal = permit_return_to_draft(permit.status, reason)
    if refusal is not None:
        service.refuse([refusal])
    before = permit.status
    try:
        permit.status = DRAFT
        permit.issued_on = permit.closed_on = permit.expiry_notified_on = None
        permit.closed_by_id = None
        await record_transition(db, PERMIT_ENTITY, permit.id, before, DRAFT, user_id, f"Returned to draft: {reason}")
        await record_audit(
            db,
            "temporary_works.permit.returned_to_draft",
            PERMIT_ENTITY,
            permit.id,
            actor_id=user_id,
            project_id=permit.project_id,
            summary=f"{permit.number}: returned to draft from {before}",
            before={"status": before},
            after={"status": DRAFT, "reason": reason},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return permit


async def delete_permit(db: AsyncSession, permit: TemporaryWorksPermit, user_id: int) -> str:
    """Soft-delete a draft permit: the row stays as a tombstone, hidden from lists and counts, in the recycle bin when it
    has no history beyond its creation and otherwise in the hidden Deleted folder. Returns which."""
    refusal = permit_delete_refusal(permit.status)
    if refusal is not None:
        raise ConflictException(f"{refusal.rule}: {refusal.message}")
    try:
        kind = await deletion.move_to_trash(db, permit, user_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return kind

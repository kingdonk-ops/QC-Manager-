"""The actions that change an item's safety state: the guarded transition, return to draft, and delete.

Each runs under the row lock its caller took on the item, is recorded in the status history where the status changes,
and is written to the audit ledger in the same transaction for the statuses that matter (loaded, in use, approved to
strike, struck, removed and on hold) and for every return to draft and delete. A failure part-way rolls the whole step
back before the error is raised. The scaffolds module is reached only through its helper file and only while the
module is switched on for the project."""

from datetime import date
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.http_exceptions import ConflictException
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import record_transition
from ..notifications.constants import Category
from ..scaffolds import breach as scaffold_breach
from . import deletion, rules, service, validation
from .constants import DRAFT_ITEM_STATUS, ITEM_ENTITY, SCAFFOLD_USABLE_TAGS, ItemStatus, label, site_today
from .models import TemporaryWorksItem, TemporaryWorksPermit
from .rules import Finding
from .transitions import EntryFacts, held_from_after, item_delete_refusal, item_return_to_draft, plan_item_move

AUDITED_STATUSES = frozenset(
    {
        ItemStatus.LOADED.value,
        ItemStatus.IN_USE.value,
        ItemStatus.APPROVED_TO_STRIKE.value,
        ItemStatus.STRUCK.value,
        ItemStatus.REMOVED.value,
        ItemStatus.ON_HOLD.value,
    }
)
"""Moves into these statuses are written to the audit ledger as well as the status history."""


async def permits_of(db: AsyncSession, item_id: int) -> list[TemporaryWorksPermit]:
    """The item's permits that have not been deleted, in creation order."""
    rows = await db.execute(
        select(TemporaryWorksPermit)
        .where(TemporaryWorksPermit.item_id == item_id, TemporaryWorksPermit.deleted_at.is_(None))
        .order_by(TemporaryWorksPermit.id)
    )
    return list(rows.scalars())


async def entry_facts(db: AsyncSession, item: TemporaryWorksItem, permits: list[TemporaryWorksPermit], day: date) -> EntryFacts:
    """What the transition rules need to know, judged on ``day``. A linked scaffold that cannot be read counts as not
    usable and not inspected: a missing fact never clears anything."""
    linked = item.scaffold_id is not None and await is_enabled(db, "scaffolds", item.project_id)
    usable, overdue = False, True
    if linked and item.scaffold_id is not None:
        state = await scaffold_breach.scaffold_state(db, item.scaffold_id, item.project_id)  # now, not the end of the day
        if state is not None:
            usable, overdue = state.effective_tag in SCAFFOLD_USABLE_TAGS, state.inspection_overdue
    return EntryFacts(
        category=item.design_check_category,
        coordinator_named=bool((item.coordinator_name or "").strip()) or item.coordinator_user_id is not None,
        load_gate_open=rules.load_gate_open(permits, day),
        load_permit_valid=rules.has_valid_load_permit(permits, day),
        strike_gate_open=rules.strike_gate_open(permits, day),
        scaffold_linked=linked,
        scaffold_tag_usable=usable,
        scaffold_inspection_overdue=overdue,
    )


async def transition_item(
    db: AsyncSession, item: TemporaryWorksItem, target: str | Enum, note: str | None, user_id: int
) -> tuple[TemporaryWorksItem, list[Finding]]:
    """Move the item one guarded step: the transition table first, then the entry preconditions, then the validation
    rules for the status it is entering."""
    wanted = target.value if isinstance(target, Enum) else target
    before = item.status
    permits = await permits_of(db, item.id)
    facts = await entry_facts(db, item, permits, site_today())
    refusal = plan_item_move(before, wanted, item.held_from, note, facts)
    if refusal is not None:
        service.refuse([refusal])
    stored = {k: getattr(item, k) for k in validation.ITEM_RULE_FIELDS}
    found = validation.validate_item(validation.merged(stored, {"status": wanted}))
    if found.errors:
        service.refuse(found.errors)
    try:
        item.held_from = held_from_after(before, wanted)
        item.status = wanted
        await record_transition(db, ITEM_ENTITY, item.id, before, wanted, user_id, note)
        if wanted in AUDITED_STATUSES:
            await record_audit(
                db,
                f"temporary_works.item.{wanted}",
                ITEM_ENTITY,
                item.id,
                actor_id=user_id,
                project_id=item.project_id,
                summary=f"{item.reference}: {label(before)} to {label(wanted)}",
                before={"status": before},
                after={"status": wanted, "note": note} if note else {"status": wanted},
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    if wanted == ItemStatus.APPROVED_TO_LOAD:
        await service.notify_after_commit(
            db,
            [item.coordinator_user_id],
            Category.APPROVAL,
            f"{item.reference}: approved to load",
            body="Temporary works coordinator: the item is approved to load once its permit to load is in place.",
            link=service.link_of(item),
            entity=(ITEM_ENTITY, item.id),
            actor_id=user_id,
        )
    return item, found.warnings


async def return_to_draft(db: AsyncSession, item: TemporaryWorksItem, reason: str, user_id: int) -> TemporaryWorksItem:
    """Send the item back to draft, from any other status, with a mandatory reason that is audit-logged."""
    refusal = item_return_to_draft(item.status, reason)
    if refusal is not None:
        service.refuse([refusal])
    before = item.status
    try:
        item.status = DRAFT_ITEM_STATUS
        item.held_from = None
        await record_transition(db, ITEM_ENTITY, item.id, before, DRAFT_ITEM_STATUS, user_id, f"Returned to draft: {reason}")
        await record_audit(
            db,
            "temporary_works.item.returned_to_draft",
            ITEM_ENTITY,
            item.id,
            actor_id=user_id,
            project_id=item.project_id,
            summary=f"{item.reference}: returned to draft from {label(before)}",
            before={"status": before},
            after={"status": DRAFT_ITEM_STATUS, "reason": reason},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return item


async def delete_item(db: AsyncSession, item: TemporaryWorksItem, user_id: int) -> str:
    """Soft-delete a draft item once each of its permits has been deleted. The row stays as a tombstone: in the recycle
    bin when the item has no history beyond its creation, otherwise in the hidden Deleted folder. Returns which."""
    live = await db.scalar(
        select(func.count())
        .select_from(TemporaryWorksPermit)
        .where(TemporaryWorksPermit.item_id == item.id, TemporaryWorksPermit.deleted_at.is_(None))
    )
    refusal = item_delete_refusal(item.status, live or 0)
    if refusal is not None:
        raise ConflictException(f"{refusal.rule}: {refusal.message}")
    try:
        kind = await deletion.move_to_trash(db, item, user_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return kind

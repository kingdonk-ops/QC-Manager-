"""Deleting, restoring and purging temporary works drafts: the recycle bin and the hidden Deleted folder.

Deleting a draft hides it. If it has no history beyond its creation it goes to the recycle bin (restorable, and removed
by the scheduled purge once the project's retention has passed, leaving a minimal audit entry); otherwise it goes to the
Deleted folder (restorable, never removed). Restore brings either back to draft and leaves its children as they were.
Delete, restore and purge are each written to the audit ledger in the same transaction as the change.

The helpers here do not commit unless they say so: the caller owns the unit of work and rolls it back on failure. The
decisions themselves are in ``deletion_rules``, which imports neither the web framework nor the database layer."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import AuditEntry, record_audit
from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import record_transition
from ...infrastructure.records.models import StatusChange
from . import deletion_rules as rules
from .constants import BIN, DRAFT_ITEM_STATUS, FOLDER, ITEM_ENTITY, PERMIT_ENTITY, SETTINGS_ENTITY, PermitStatus
from .models import TemporaryWorksItem, TemporaryWorksPermit, TemporaryWorksSettings

Record = TemporaryWorksItem | TemporaryWorksPermit


def describe(record: Record) -> tuple[str, str, str]:
    """The record's entity name, its noun in audit actions and its human label (reference or number)."""
    if isinstance(record, TemporaryWorksItem):
        return ITEM_ENTITY, "item", record.reference
    return PERMIT_ENTITY, "permit", record.number


def place(kind: str | None) -> str:
    """The plain-words name of where a deleted record sits. Anything that is not the bin is the Deleted folder."""
    return "recycle bin" if kind == BIN else "Deleted folder"


# --- delete -------------------------------------------------------------------------------------------------------


async def _audit_actions(db: AsyncSession, entity: str, entity_id: int) -> list[str]:
    query = select(AuditEntry.action).where(AuditEntry.entity_type == entity, AuditEntry.entity_id == str(entity_id))
    return list(await db.scalars(query))


async def _status_changes(db: AsyncSession, entity: str, entity_id: int) -> int:
    query = (
        select(func.count())
        .select_from(StatusChange)
        .where(StatusChange.entity_type == entity, StatusChange.entity_id == entity_id)
    )
    return (await db.scalar(query)) or 0


async def _permit_rows(db: AsyncSession, item_id: int) -> int:
    """Every permit the item has ever had, deleted ones included."""
    query = select(func.count()).select_from(TemporaryWorksPermit).where(TemporaryWorksPermit.item_id == item_id)
    return (await db.scalar(query)) or 0


async def record_history(db: AsyncSession, record: Record) -> rules.RecordHistory:
    """What the audit ledger, the status history and the record's own links say about it right now."""
    entity, _, _ = describe(record)
    actions = await _audit_actions(db, entity, record.id)
    changes = await _status_changes(db, entity, record.id)
    if isinstance(record, TemporaryWorksItem):
        links = rules.count_links(record, rules.ITEM_LINK_FIELDS)
        return rules.RecordHistory(actions, changes, await _permit_rows(db, record.id), links)
    return rules.RecordHistory(actions, changes, 0, rules.count_links(record, rules.PERMIT_LINK_FIELDS))


async def move_to_trash(db: AsyncSession, record: Record, user_id: int) -> str:
    """Hide a draft the caller has already checked may be deleted, into the recycle bin or the Deleted folder (returned).
    Writes the audit entry; does not commit."""
    entity, noun, label = describe(record)
    kind = rules.deletion_destination(await record_history(db, record))
    status = record.status
    record.deleted_at = datetime.now(UTC)
    record.deleted_by_id = user_id
    record.deleted_kind = kind
    await record_audit(
        db,
        f"temporary_works.{noun}.deleted",
        entity,
        record.id,
        actor_id=user_id,
        project_id=record.project_id,
        summary=f"{label} deleted to the {place(kind)}",
        before={"status": status, "deleted": False},
        after={"deleted": True, "destination": kind},
    )
    return kind


# --- restore ------------------------------------------------------------------------------------------------------


async def restore(db: AsyncSession, record: Record, user_id: int) -> None:
    """Bring a deleted record back to draft, from the recycle bin or the Deleted folder alike. Its children are left as
    they were: a permit deleted earlier stays deleted until it is restored itself, and a permit cannot be restored while
    its item is deleted. The caller holds the row lock and commits."""
    entity, noun, label = describe(record)
    parent_deleted = False
    if isinstance(record, TemporaryWorksPermit):
        # Lock the item so an item delete (which counts live permits under the same lock) cannot slip in between this
        # check and the commit and leave a live permit under a deleted item.
        locked = select(TemporaryWorksItem).where(TemporaryWorksItem.id == record.item_id).with_for_update()
        parent = await db.scalar(locked.execution_options(populate_existing=True))
        parent_deleted = parent is None or parent.deleted_at is not None
    refusal = rules.restore_refusal(record.deleted_at, parent_deleted)
    if refusal is not None:
        raise ConflictException(f"{refusal.rule}: {refusal.message}")
    origin = BIN if record.deleted_kind == BIN else FOLDER
    before = {"status": record.status, "deleted": True, "destination": origin}
    record.deleted_at = record.deleted_by_id = record.deleted_kind = None
    draft = DRAFT_ITEM_STATUS if isinstance(record, TemporaryWorksItem) else PermitStatus.DRAFT.value
    if record.status != draft:  # only a record deleted by some other route can be anywhere but draft
        await record_transition(db, entity, record.id, record.status, draft, user_id, "Restored to draft")
        record.status = draft
        if isinstance(record, TemporaryWorksItem):
            record.held_from = None
        else:
            record.issued_on = record.closed_on = record.expiry_notified_on = None
            record.closed_by_id = None
    await record_audit(
        db,
        f"temporary_works.{noun}.restored",
        entity,
        record.id,
        actor_id=user_id,
        project_id=record.project_id,
        summary=f"{label} restored to draft from the {place(origin)}",
        before=before,
        after={"status": draft, "deleted": False},
    )


# --- the two views ------------------------------------------------------------------------------------------------


def in_view(model: Any, view: str) -> Any:
    """The condition that picks a view's rows. A deleted row with no kind is in the Deleted folder."""
    marked = model.deleted_at.is_not(None)
    if view == BIN:
        return and_(marked, model.deleted_kind == BIN)
    return and_(marked, or_(model.deleted_kind.is_(None), model.deleted_kind != BIN))


async def list_trash(
    db: AsyncSession, model: Any, project_id: int, view: str, offset: int, limit: int
) -> tuple[int, list[Any]]:
    """A project's deleted records of one kind in one view, most recently deleted first."""
    where = (model.project_id == project_id, in_view(model, view))
    total = await db.scalar(select(func.count()).select_from(model).where(*where))
    query = select(model).where(*where).order_by(model.deleted_at.desc(), model.id).offset(offset).limit(limit)
    return total or 0, list((await db.execute(query)).scalars())


# --- the project's retention --------------------------------------------------------------------------------------


async def retention_of(db: AsyncSession, project_id: int) -> int:
    """Days a deleted draft stays in the recycle bin in this project (the default when it has no setting)."""
    row = await db.get(TemporaryWorksSettings, project_id)
    return rules.retention_days(row.bin_retention_days if row is not None else None)


async def set_retention(db: AsyncSession, project_id: int, days: int, user_id: int) -> int:
    """Save the project's retention (one to sixty days), audit-logged, and commit."""
    refusal = rules.retention_refusal(days)
    if refusal is not None:
        raise UnprocessableEntityException(f"{refusal.rule}: {refusal.message}")
    try:
        row = await db.get(TemporaryWorksSettings, project_id, with_for_update=True)
        before = rules.retention_days(row.bin_retention_days if row is not None else None)
        if row is None:
            db.add(TemporaryWorksSettings(project_id=project_id, bin_retention_days=days, updated_by_id=user_id))
        else:
            row.bin_retention_days = days
            row.updated_by_id = user_id
        await record_audit(
            db,
            "temporary_works.settings.updated",
            SETTINGS_ENTITY,
            project_id,
            actor_id=user_id,
            project_id=project_id,
            summary=f"Recycle bin retention set to {days} days",
            before={"bin_retention_days": before},
            after={"bin_retention_days": days},
        )
        await db.commit()
    except IntegrityError as exc:  # two first-time saves at once: the second one retries
        await db.rollback()
        raise ConflictException("The retention was saved at the same moment by someone else; try again.") from exc
    except Exception:
        await db.rollback()
        raise
    return days


# --- the scheduled purge ------------------------------------------------------------------------------------------


@dataclass
class PurgeResult:
    items: int = 0
    permits: int = 0

    @property
    def total(self) -> int:
        return self.items + self.permits


async def _purge_one(db: AsyncSession, record: Record, now: datetime) -> None:
    """Physically remove one recycle-bin record, leaving a minimal audit entry of what went and when."""
    entity, noun, label = describe(record)
    key = "reference" if isinstance(record, TemporaryWorksItem) else "number"
    await record_audit(
        db,
        f"temporary_works.{noun}.purged",
        entity,
        record.id,
        project_id=record.project_id,
        summary=f"{label} removed from the recycle bin after its retention",
        before={key: label, "deleted_at": record.deleted_at, "deleted_by_id": record.deleted_by_id},
        after={"purged_at": now},
    )
    await db.delete(record)


async def purge_expired(db: AsyncSession, now: datetime | None = None) -> PurgeResult:
    """Remove every recycle-bin record whose project retention has passed, in a project where the module is on, and
    commit once. Only the bin is ever touched: the Deleted folder, a record of unknown kind and any item that still has a
    permit row (deleted or not) are left alone, so nothing the audit chain refers to is removed. Idempotent."""
    moment = now or datetime.now(UTC)
    result = PurgeResult()
    retention: dict[int, int] = {}
    switched: dict[int, bool] = {}

    async def due(record: Record) -> bool:
        pid = record.project_id
        if pid not in switched:
            switched[pid] = await is_enabled(db, "temporary_works", pid)
            retention[pid] = await retention_of(db, pid)
        return switched[pid] and rules.purge_due(record.deleted_kind, record.deleted_at, retention[pid], moment)

    models: tuple[Any, ...] = (TemporaryWorksPermit, TemporaryWorksItem)  # permits first, then items
    try:
        for model in models:
            query = select(model).where(in_view(model, BIN)).order_by(model.id).with_for_update()
            found = await db.execute(query.execution_options(populate_existing=True))
            for record in list(found.scalars()):
                if not await due(record):
                    continue
                if isinstance(record, TemporaryWorksItem):
                    if await _permit_rows(db, record.id):
                        continue
                    result.items += 1
                else:
                    result.permits += 1
                await _purge_one(db, record, moment)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return result

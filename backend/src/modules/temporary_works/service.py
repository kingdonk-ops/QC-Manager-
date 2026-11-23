"""Temporary works items: read, list, create and edit, plus the helpers the transition, return-to-draft and delete actions
(``item_actions``) and the permit actions (``permits``) share.

A change either commits whole or is rolled back whole before the error is raised. Deleted items are tombstones: every
read and list here leaves them out, though their references stay reserved."""

import logging
from collections.abc import Iterable
from enum import Enum
from typing import Any, NoReturn

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import history_of
from ..asset_tree import service as tree
from ..common.exceptions import ResourceNotFoundError
from ..notifications.service import notify
from ..scaffolds import breach as scaffold_breach
from ..user.models import User
from . import validation
from .constants import DRAFT_ITEM_STATUS
from .models import TemporaryWorksItem
from .rules import Finding

LOG = logging.getLogger(__name__)
LINK_FIELDS = ("coordinator_user_id", "asset_node_id", "scaffold_id")


class ItemNotFoundError(ResourceNotFoundError):
    public_detail = "Temporary works item not found."


class LinkNotFoundError(ResourceNotFoundError):
    public_detail = "A linked record was not found."


def plain(values: dict[str, Any]) -> dict[str, Any]:
    """Request values with enumerations as their stored text."""
    return {k: v.value if isinstance(v, Enum) else v for k, v in values.items()}


def refuse(findings: Iterable[Finding]) -> NoReturn:
    """Refuse the request (invalid input), naming every rule that failed."""
    raise UnprocessableEntityException("; ".join(f"{f.rule}: {f.message}" for f in findings))


def warnings_of(findings: Iterable[Finding]) -> list[dict[str, str]]:
    return [{"rule": f.rule, "message": f.message} for f in findings]


def write_body(read: BaseModel, findings: Iterable[Finding]) -> dict[str, Any]:
    """A write response: the record as read, with the non-blocking warnings of the rules that ran."""
    return {**read.model_dump(), "warnings": warnings_of(findings)}


def creator_of(user_id: Any) -> int | None:
    """The creating user, or nothing when the identifier is not a well-formed one."""
    return user_id if isinstance(user_id, int) and not isinstance(user_id, bool) and user_id > 0 else None


def link_of(item: TemporaryWorksItem) -> str:
    return f"/temporary-works?project={item.project_id}&id={item.id}"


async def get_item(db: AsyncSession, item_id: int) -> TemporaryWorksItem:
    item = await db.get(TemporaryWorksItem, item_id)
    if item is None or item.deleted_at is not None:
        raise ItemNotFoundError("No such temporary works item")
    return item


async def lock_item(db: AsyncSession, item: TemporaryWorksItem) -> TemporaryWorksItem:
    """Re-read the item under a row lock, so two concurrent changes to it run in turn and the second sees the first."""
    await db.refresh(item, with_for_update=True)
    if item.deleted_at is not None:
        raise ItemNotFoundError("No such temporary works item")
    return item


async def notify_after_commit(
    db: AsyncSession,
    user_ids: Iterable[int | None],
    category: str,
    title: str,
    *,
    body: str,
    link: str,
    entity: tuple[str, int],
    actor_id: int | None,
) -> None:
    """The change is already committed. A notice that cannot be written is logged and never undoes the change."""
    try:
        await notify(db, [u for u in user_ids if u], category, title, body=body, link=link, entity=entity, actor_id=actor_id)
        await db.commit()
    except Exception:
        await db.rollback()
        LOG.warning("temporary works notice could not be written: %s", title, exc_info=True)


# --- links and uniqueness -----------------------------------------------------------------------------


async def reference_taken(db: AsyncSession, project_id: int, reference: str, exclude_id: int | None = None) -> bool:
    """Whether the reference is in use in the project. A deleted item still holds its reference."""
    query = select(TemporaryWorksItem.id).where(
        TemporaryWorksItem.project_id == project_id, TemporaryWorksItem.reference == reference
    )
    if exclude_id is not None:
        query = query.where(TemporaryWorksItem.id != exclude_id)
    return (await db.scalar(query.limit(1))) is not None


async def check_links(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    """The coordinator user must exist, and the asset node and scaffold must belong to the project (foreign or missing
    ones answer not-found). With the scaffolds module off for the project the scaffold link is left unchecked."""
    if values.get("coordinator_user_id") is not None:
        user = await db.get(User, values["coordinator_user_id"])
        if user is None or user.is_deleted:
            raise UnprocessableEntityException("The coordinator user does not exist.")
    if values.get("asset_node_id") is not None:
        await tree.get_node(db, values["asset_node_id"], project_id)
    if values.get("scaffold_id") is not None and await is_enabled(db, "scaffolds", project_id):
        if await scaffold_breach.scaffold_state(db, values["scaffold_id"], project_id) is None:
            raise LinkNotFoundError("No such scaffold in this project")


# --- list, create, edit -------------------------------------------------------------------------------


async def list_items(
    db: AsyncSession,
    project_id: int,
    *,
    family: str | None,
    status: str | None,
    category: int | None,
    scaffold_id: int | None,
    offset: int,
    limit: int,
) -> tuple[int, list[TemporaryWorksItem]]:
    """A project's items, ascending sort order then creation time, with the optional filters; deleted items excluded."""
    where: list[Any] = [TemporaryWorksItem.project_id == project_id, TemporaryWorksItem.deleted_at.is_(None)]
    for column, value in (
        (TemporaryWorksItem.family, family),
        (TemporaryWorksItem.status, status),
        (TemporaryWorksItem.design_check_category, category),
        (TemporaryWorksItem.scaffold_id, scaffold_id),
    ):
        if value is not None:
            where.append(column == value)
    total = await db.scalar(select(func.count()).select_from(TemporaryWorksItem).where(*where))
    rows = (
        await db.execute(
            select(TemporaryWorksItem)
            .where(*where)
            .order_by(TemporaryWorksItem.sort_order, TemporaryWorksItem.created_at, TemporaryWorksItem.id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars()
    return total or 0, list(rows)


async def create_item(db: AsyncSession, values: dict[str, Any], user_id: int) -> tuple[TemporaryWorksItem, list[Finding]]:
    """Create an item in draft. The reference's uniqueness is checked before the rules, which run on the whole record."""
    values = plain(values)
    project_id = values["project_id"]
    if await reference_taken(db, project_id, values["reference"]):
        raise ConflictException("An item with that reference already exists in this project.")
    found = validation.validate_item({**values, "status": DRAFT_ITEM_STATUS})
    if found.errors:
        refuse(found.errors)
    await check_links(db, project_id, values)
    try:
        item = TemporaryWorksItem(created_by_id=creator_of(user_id), **values)
        db.add(item)
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException("An item with that reference already exists in this project.") from exc
    except Exception:
        await db.rollback()
        raise
    return item, found.warnings


async def update_item(
    db: AsyncSession, item: TemporaryWorksItem, changes: dict[str, Any]
) -> tuple[TemporaryWorksItem, list[Finding]]:
    """A partial edit. The rules run only when a rule-relevant field is supplied, and judge the stored record with the
    change laid over it; an edit of notes alone runs none, whatever state the record is stored in."""
    changes = plain(changes)
    if changes.get("reference") not in (None, item.reference) and await reference_taken(
        db, item.project_id, changes["reference"], exclude_id=item.id
    ):
        raise ConflictException("An item with that reference already exists in this project.")
    warnings: list[Finding] = []
    if validation.rules_apply(changes, validation.ITEM_RULE_FIELDS):
        stored = {k: getattr(item, k) for k in validation.ITEM_RULE_FIELDS}
        found = validation.validate_item(validation.merged(stored, changes))
        if found.errors:
            refuse(found.errors)
        warnings = found.warnings
    await check_links(db, item.project_id, {k: v for k, v in changes.items() if k in LINK_FIELDS})
    try:
        for key, value in changes.items():
            setattr(item, key, value)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException("An item with that reference already exists in this project.") from exc
    except Exception:
        await db.rollback()
        raise
    return item, warnings


async def history_for(db: AsyncSession, entity: str, entity_id: int) -> list[dict[str, Any]]:
    """The status history of an item or a permit, oldest first."""
    return await history_of(db, entity, entity_id)

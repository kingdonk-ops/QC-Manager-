"""Records portal users must not reach through shared services (files, comments).

A module whose records can be internal registers a query for the hidden ids of a project::

    register_internal_records("ncr", lambda project_id: select(Ncr.id).where(
        Ncr.project_id == project_id, Ncr.visibility == "internal"))

Files and comments attached to those records are then left out of lists and answer 404 for portal users
(no ``projects.read``, not a superuser), the same as the record itself.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

HiddenIds = Callable[[int], Select[Any]]
_hidden: dict[str, HiddenIds] = {}


def register_internal_records(entity_type: str, hidden_ids: HiddenIds) -> None:
    _hidden[entity_type] = hidden_ids


def is_portal_user(user: dict[str, Any], held: frozenset[str]) -> bool:
    return not user.get("is_superuser") and "projects.read" not in held


def hidden_from(
    user: dict[str, Any], held: frozenset[str], project_id: int, entity_type: Any, entity_id: Any
) -> list[ColumnElement[bool]]:
    """Filters that drop rows attached to internal records, for a portal user; nothing for staff."""
    if not is_portal_user(user, held):
        return []
    return [not_(and_(entity_type == key, entity_id.in_(query(project_id)))) for key, query in _hidden.items()]


async def is_hidden(
    db: AsyncSession,
    user: dict[str, Any],
    held: frozenset[str],
    project_id: int | None,
    entity_type: str | None,
    entity_id: int | None,
) -> bool:
    query = _hidden.get(entity_type or "")
    if query is None or project_id is None or entity_id is None or not is_portal_user(user, held):
        return False
    ids = query(project_id).subquery()
    return bool(await db.scalar(ids.select().where(ids.c[ids.c.keys()[0]] == entity_id).limit(1)))

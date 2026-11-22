from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.common.exceptions import ValidationError
from .models import StatusChange


class TransitionNotAllowed(ValidationError):
    public_detail = "That status change isn't allowed from the current status."


def assert_transition(flow: Mapping[str, set[str] | frozenset[str]], current: str, target: str) -> None:
    """Raise unless ``flow[current]`` contains ``target``. Answers 422 through the error mapping."""
    if target not in flow.get(current, set()):
        raise TransitionNotAllowed(f"{current} -> {target}")


async def record_transition(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    from_status: str | None,
    to_status: str,
    user_id: int | None,
    note: str | None = None,
) -> None:
    db.add(
        StatusChange(
            entity_type=entity_type,
            entity_id=entity_id,
            from_status=from_status,
            to_status=to_status,
            changed_by_id=user_id,
            note=note,
        )
    )


async def history_of(db: AsyncSession, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(StatusChange)
            .where(StatusChange.entity_type == entity_type, StatusChange.entity_id == entity_id)
            .order_by(StatusChange.changed_at, StatusChange.id)
        )
    ).scalars()

    return [
        {
            "from_status": r.from_status,
            "to_status": r.to_status,
            "changed_by_id": r.changed_by_id,
            "note": r.note,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        }
        for r in rows
    ]

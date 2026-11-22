from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RecordCounter


async def next_reference(db: AsyncSession, prefix: str, project_id: int | None = None, *, width: int = 3) -> str:
    """The next ``PREFIX-NNN`` in the scope, e.g. ``RFI-001`` for a project's first RFI.

    The counter row is locked for the caller's transaction, so two requests never get the same
    number; commit with the record that uses it. A prefix may carry a year (``COR-2026``).
    """
    scope = f"project:{project_id}" if project_id is not None else "global"
    statement = select(RecordCounter).where(RecordCounter.scope == scope, RecordCounter.prefix == prefix)
    counter = await db.scalar(statement.with_for_update())
    if counter is None:
        try:
            async with db.begin_nested():
                db.add(RecordCounter(scope=scope, prefix=prefix, value=0))
        except IntegrityError:
            pass
        counter = await db.scalar(statement.with_for_update())
    assert counter is not None
    counter.value += 1
    await db.flush()

    return f"{prefix}-{counter.value:0{width}d}"

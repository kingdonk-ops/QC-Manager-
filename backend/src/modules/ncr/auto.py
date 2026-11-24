"""Automatic reports: other modules raise an NCR from a recorded outcome inside their own unit of work.

The report is created without committing, so a failure here fails the caller's whole action; the caller stores the
returned identifier and publishes its events once its own commit has gone through. Imports neither the inspections,
the materials nor the as-built module."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Ncr
from .service import create_ncr


async def raise_automatic(
    db: AsyncSession,
    *,
    project_id: int,
    title: str,
    description: str,
    raised_by_id: int | None,
    severity: str,
    source: str,
    source_reference: str,
    source_data: dict[str, Any],
    category: str | None = None,
    location: str | None = None,
    trade: str | None = None,
    responsible_user_id: int | None = None,
    inspection_id: int | None = None,
    inspection_item_id: int | None = None,
    mdr_effect: str | None = None,
    completion_effect: str | None = None,
) -> Ncr:
    """An NCR on the default template of ``category`` (the general one when none is given), initial status open,
    not committed. ``mdr_effect`` / ``completion_effect`` set the report's blocking flags when the caller needs them
    other than the template's (for example ``register_only`` and ``none`` for a report that must never block)."""
    return await create_ncr(
        db,
        project_id=project_id,
        title=title,
        raised_by_id=raised_by_id,
        commit=False,
        category=category,
        description=description,
        severity=severity,
        source=source,
        source_reference=source_reference,
        location=location,
        trade=trade,
        responsible_user_id=responsible_user_id,
        inspection_id=inspection_id,
        inspection_item_id=inspection_item_id,
        mdr_effect=mdr_effect,
        completion_effect=completion_effect,
        source_data=source_data,
    )

"""Raise an issue when an inspection asks for one.

``inspections.item.ncr_requested`` carries ``ncr_id`` when inspections already raised the NCR itself (through
``service.create_ncr``); then there is nothing to do. Without one, the issue is raised here, so inspections can
hand the work over by publishing the event alone. The new issue publishes ``ncr.issue.raised`` with the
inspection and item ids, so the inspection can link back.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.session import local_session
from ...infrastructure.modules import subscribe
from ...infrastructure.modules.state import is_enabled
from .constants import IssueType, Source
from .models import Ncr
from .service import create_issue

REQUESTED = "inspections.item.ncr_requested"


async def raise_requested(db: AsyncSession, payload: dict[str, Any]) -> Ncr | None:
    """The issue for one ``ncr_requested`` payload, or None when it exists already or the module is off."""
    project_id = payload.get("project_id")
    if payload.get("ncr_id") or not project_id or not await is_enabled(db, "ncr", int(project_id)):
        return None
    issue_type = str(payload.get("issue_type") or IssueType.NCR)
    return await create_issue(
        db,
        project_id=int(project_id),
        title=str(payload.get("title") or "Failed inspection item")[:300],
        raised_by_id=payload.get("raised_by_id"),
        issue_type=issue_type,
        template_id=payload.get("template_id"),
        category=payload.get("category"),
        enforce_anchor=False,
        source=Source.INSPECTION,
        inspection_id=payload.get("inspection_id"),
        inspection_item_id=payload.get("item_id"),
        anchor_node_id=payload.get("anchor_node_id"),
        anchor_item_id=payload.get("anchor_item_id"),
        severity=payload.get("severity"),
        punch_category=payload.get("punch_category") or ("A" if issue_type == IssueType.PUNCH else None),
        description=payload.get("description"),
    )


@subscribe(REQUESTED)
async def on_ncr_requested(event: str, payload: dict[str, Any]) -> None:
    async with local_session() as db:
        await raise_requested(db, payload)

"""What issues contribute to a turnover dossier: the NCR / concession register.

The register goes to the client, so it comes from ``mdr_register``: client-visible issues only, never internal,
excluded, void, upgraded or escalated ones. Blocking checks are the MDR gate's ``ncr.service:blocking_issues`` hook.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import MdrContext, MdrRecord, register_mdr_provider
from .service import mdr_register


def _notes(i: dict[str, Any]) -> str:
    closed = i.get("closed_at")
    parts = (
        i.get("issue_type"),
        f"Cat {i['punch_category']}" if i.get("punch_category") else None,
        i.get("severity"),
        f"disposition {str(i['disposition']).replace('_', ' ')}" if i.get("disposition") else None,
        f"concession {i['concession_reference']}" if i.get("concession_reference") else None,
        f"closed {str(closed)[:10]}" if closed else None,
    )
    return "; ".join(str(p) for p in parts if p)


async def ncr_register(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
    rows = await mdr_register(db, ctx.project_id, ctx.node_ids)
    return [
        MdrRecord(
            reference=i["code"],
            title=i["title"],
            status=i.get("status"),
            date=str(i["raised_on"]) if i.get("raised_on") else None,
            location=i.get("location"),
            notes=_notes(i),
        )
        for i in rows
    ]


register_mdr_provider("ncr_register", ncr_register, module="ncr")

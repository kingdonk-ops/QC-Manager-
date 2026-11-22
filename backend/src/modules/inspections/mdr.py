"""What inspections contribute to a turnover dossier: completed inspection reports, and the "all done" check."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import Finding, MdrCheck, MdrContext, MdrRecord, register_mdr_check, register_mdr_provider
from ..files.models import StoredFile
from .constants import InspectionStatus
from .models import Inspection
from .service import link_of, report_pdf

DONE = (InspectionStatus.COMPLETED.value, InspectionStatus.CLOSED.value)


async def _in_scope(db: AsyncSession, ctx: MdrContext, *where: Any) -> list[Inspection]:
    rows = (
        await db.execute(select(Inspection).where(Inspection.project_id == ctx.project_id, *where).order_by(Inspection.code))
    ).scalars()
    # Inspections carry no asset anchor yet; once they do (``asset_node_id``), the dossier scope narrows them.
    return [i for i in rows if ctx.in_scope(getattr(i, "asset_node_id", None))]


async def inspection_records(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
    out = []
    for inspection in await _in_scope(db, ctx, Inspection.status.in_(DONE)):
        files = (
            await db.execute(
                select(StoredFile.id).where(
                    StoredFile.entity_type == "inspection",
                    StoredFile.entity_id == inspection.id,
                    StoredFile.is_latest.is_(True),
                    StoredFile.content_type == "application/pdf",
                )
            )
        ).scalars()
        out.append(
            MdrRecord(
                reference=inspection.code,
                title=inspection.title,
                status=inspection.status,
                date=inspection.inspected_date.isoformat() if inspection.inspected_date else None,
                location=" / ".join(p for p in (inspection.location, inspection.area) if p) or None,
                notes=f"{inspection.pass_rate:g}% pass" if inspection.pass_rate is not None else None,
                pdf=await report_pdf(db, inspection),
                file_ids=list(files),
            )
        )
    return out


async def incomplete_inspections(db: AsyncSession, ctx: MdrContext) -> list[Finding]:
    return [
        Finding(f"{i.code} {i.title} is {i.status.replace('_', ' ')}", reference=i.code, link=link_of(i))
        for i in await _in_scope(db, ctx, Inspection.status.not_in(DONE))
    ]


register_mdr_provider("inspections", inspection_records, module="inspections")
register_mdr_check(
    MdrCheck("inspections_complete", "Every inspection in scope is complete", "inspections", incomplete_inspections)
)

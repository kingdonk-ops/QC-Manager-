"""Published "as constructed" CDE containers (suitability CR) as the dossier's as-built drawings."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import MdrContext, MdrRecord, register_mdr_provider
from .constants import CdeState
from .models import CdeDocument, CdeRevision


async def as_constructed(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
    rows = (
        await db.execute(
            select(CdeDocument, CdeRevision)
            .outerjoin(CdeRevision, CdeRevision.id == CdeDocument.current_revision_id)
            .where(
                CdeDocument.project_id == ctx.project_id,
                CdeDocument.state == CdeState.PUBLISHED.value,
                CdeDocument.suitability == "CR",
            )
            .order_by(CdeDocument.name)
        )
    ).tuples()
    return [
        MdrRecord(
            reference=doc.name,
            title=doc.title,
            status=f"{doc.suitability} rev {doc.revision}",
            file_ids=[rev.file_id] if rev is not None and rev.file_id else [],
        )
        for doc, rev in rows
    ]


register_mdr_provider("as_built", as_constructed, module="cde")

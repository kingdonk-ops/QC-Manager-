"""The dossier's own section: files uploaded to the dossier itself ("Other documents")."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import MdrContext, MdrRecord, register_mdr_provider
from ..files.models import StoredFile
from .constants import ENTITY


async def custom_uploads(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
    rows = (
        await db.execute(
            select(StoredFile)
            .where(StoredFile.entity_type == ENTITY, StoredFile.entity_id == ctx.dossier_id, StoredFile.is_latest.is_(True))
            .order_by(StoredFile.name, StoredFile.id)
        )
    ).scalars()
    return [MdrRecord(reference=f.name, title=f.name, status=f"rev {f.revision}", file_ids=[f.id]) for f in rows]


register_mdr_provider("custom", custom_uploads, module="mdr")

"""Tagged project files as dossier records, until dedicated modules (materials, welding, calibration) provide them.

A file lands in a section by its tags: ``as-built`` (drawings), ``mtr`` / ``material-certificate``, ``nde``,
``calibration``. Files attached to an asset node outside the dossier scope are left out.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import MdrContext, MdrRecord, ProviderFn, register_mdr_provider
from .models import StoredFile

TAGS = {
    "as_built": {"as-built", "as_built", "asbuilt", "as built"},
    "material_certs": {"mtr", "material-certificate", "material_certificate", "mill-certificate"},
    "nde_reports": {"nde", "nde-report", "ndt"},
    "calibration_certs": {"calibration", "calibration-certificate", "cal-cert"},
}


def _section_files(section: str) -> ProviderFn:
    wanted = TAGS[section]

    async def provide(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
        rows = (
            await db.execute(
                select(StoredFile)
                .where(StoredFile.project_id == ctx.project_id, StoredFile.is_latest.is_(True))
                .order_by(StoredFile.name, StoredFile.id)
            )
        ).scalars()
        out = []
        for f in rows:
            if not {str(t).strip().lower() for t in f.tags or []} & wanted:
                continue
            if f.entity_type == "asset_node" and not ctx.in_scope(f.entity_id):
                continue
            out.append(
                MdrRecord(
                    reference=f.name,
                    title=f.name,
                    status=f"rev {f.revision}",
                    date=f.created_at.date().isoformat() if f.created_at else None,
                    file_ids=[f.id],
                )
            )
        return out

    provide.__name__ = f"tagged_{section}"
    return provide


for _section in TAGS:
    register_mdr_provider(_section, _section_files(_section), module="files")

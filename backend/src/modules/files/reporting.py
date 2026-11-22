"""Project documents as a dataset, and a document-count KPI."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from ..user.models import User
from .models import StoredFile


async def document_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(StoredFile, User.name)
        .outerjoin(User, User.id == StoredFile.uploaded_by_id)
        .where(StoredFile.project_id == project_id)
        .order_by(StoredFile.name, StoredFile.revision)
    )
    return [
        {
            "project_id": f.project_id,
            "name": f.name,
            "category": f.category,
            "tags": f.tags,
            "revision": f.revision,
            "latest": f.is_latest,
            "attached_to": f"{f.entity_type} {f.entity_id}" if f.entity_type else None,
            "content_type": f.content_type,
            "size_kb": round(f.size / 1024, 1),
            "uploaded_by": name,
            "uploaded_at": f.created_at.date() if f.created_at else None,
            "documents": 1,
        }
        for f, name in rows.all()
    ]


async def document_count(db: AsyncSession, project_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(StoredFile).where(StoredFile.project_id == project_id, StoredFile.is_latest)
        )
        or 0
    )


register_dataset(
    Dataset(
        name="documents",
        module="files",
        title="Documents",
        description="Project documents and attachments, every revision.",
        permission="files.read",
        columns=[
            Column("name", "Name"),
            Column("category", "Category"),
            Column("tags", "Tags"),
            Column("revision", "Revision", "number", aggregatable=False),
            Column("latest", "Latest", "bool"),
            Column("attached_to", "Attached to"),
            Column("content_type", "Type"),
            Column("size_kb", "Size (KB)", "number"),
            Column("uploaded_by", "Uploaded by"),
            Column("uploaded_at", "Uploaded", "date"),
            Column("documents", "Count", "number"),
        ],
        rows=document_rows,
    )
)

register_kpi(Kpi("files.documents", "files", "Documents", document_count, unit="count", permission="files.read"))

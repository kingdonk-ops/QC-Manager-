from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import hidden_from, is_hidden
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from ..projects.service import readable_project
from ..user.models import User
from .models import StoredFile
from .schemas import FileRead


class FileNotFoundError(ResourceNotFoundError):
    public_detail = "File not found."


class FileAccessError(PermissionDeniedError):
    public_detail = "You can't change this file."


async def readable_file(db: AsyncSession, file_id: int, user: dict[str, Any], held: frozenset[str]) -> StoredFile:
    f = await db.get(StoredFile, file_id)
    if f is None:
        raise FileNotFoundError("No such file")
    if f.project_id is not None:
        await readable_project(db, f.project_id, user["id"], held)
        if await is_hidden(db, user, held, f.project_id, f.entity_type, f.entity_id):
            raise FileNotFoundError("Hidden")
    elif f.uploaded_by_id != user["id"] and not user.get("is_superuser"):
        raise FileNotFoundError("Hidden")
    return f


async def as_read(db: AsyncSession, files: list[StoredFile]) -> list[dict[str, Any]]:
    ids = {f.uploaded_by_id for f in files if f.uploaded_by_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    return [
        FileRead.model_validate(f)
        .model_copy(update={"uploaded_by_name": names.get(f.uploaded_by_id) if f.uploaded_by_id else None})
        .model_dump(mode="json")
        for f in files
    ]


async def page(
    db: AsyncSession,
    *,
    project_id: int | None,
    entity_type: str | None,
    entity_id: int | None,
    category: str | None,
    search: str | None,
    include_superseded: bool,
    user: dict[str, Any],
    held: frozenset[str] = frozenset(),
    skip: int,
    limit: int,
) -> dict[str, Any]:
    filters: list[Any] = []
    if project_id is not None:
        filters.append(StoredFile.project_id == project_id)
        filters += hidden_from(user, held, project_id, StoredFile.entity_type, StoredFile.entity_id)
    else:
        filters.append(StoredFile.project_id.is_(None))
        filters.append(StoredFile.uploaded_by_id == user["id"])
    if entity_type:
        filters.append(StoredFile.entity_type == entity_type)
    if entity_id is not None:
        filters.append(StoredFile.entity_id == entity_id)
    if category:
        filters.append(StoredFile.category == category)
    if not include_superseded:
        filters.append(StoredFile.is_latest.is_(True))
    if search:
        like = f"%{search.lower()}%"
        filters.append(or_(func.lower(StoredFile.name).like(like), func.lower(cast(StoredFile.tags, String)).like(like)))
    total = await db.scalar(select(func.count()).select_from(StoredFile).where(*filters))
    rows = (
        await db.execute(select(StoredFile).where(*filters).order_by(StoredFile.created_at.desc()).offset(skip).limit(limit))
    ).scalars()
    return {"data": await as_read(db, list(rows)), "total_count": total or 0}

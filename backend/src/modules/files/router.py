"""Mounted at /api/v1/files."""

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.config.settings import settings
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from .constants import FileCategory, guess_category
from .models import StoredFile
from .permissions import FilePermissionName
from .schemas import FileRead, FileUpdate
from .service import FileAccessError, as_read, readable_file
from .service import page as page_of_files
from .storage import FileTooLarge, storage

router = APIRouter(tags=["Documents"])

FileId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
INLINE_TYPES = ("image/", "application/pdf", "text/plain")


@router.get(
    "/",
    response_model=PaginatedListResponse[FileRead],
    summary="List Files",
    description="A project's documents, or the files attached to one record (`entity_type` + `entity_id`). "
    "Without `project_id`, the caller's own unfiled uploads.",
    dependencies=[require_permissions(FilePermissionName.READ.value)],
)
async def list_files(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int | None, Query(ge=1)] = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[int | None, Query(ge=1)] = None,
    category: FileCategory | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_superseded: bool = False,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    if project_id is not None:
        await readable_project(db, project_id, user["id"], held)
    data = await page_of_files(
        db,
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        category=category.value if category else None,
        search=search,
        include_superseded=include_superseded,
        user=user,
        held=held,
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
    )
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=FileRead,
    status_code=201,
    summary="Upload a File",
    description="Multipart. `supersedes_id` uploads a new revision of that file.",
    dependencies=[require_permissions(FilePermissionName.UPLOAD.value)],
)
async def upload(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[int | None, Form(ge=1)] = None,
    entity_type: Annotated[str | None, Form(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")] = None,
    entity_id: Annotated[int | None, Form(ge=1)] = None,
    category: Annotated[FileCategory | None, Form()] = None,
    tags: Annotated[str | None, Form(max_length=500, description="Comma separated")] = None,
    supersedes_id: Annotated[int | None, Form(ge=1)] = None,
) -> Any:
    previous = None
    if supersedes_id is not None:
        previous = await readable_file(db, supersedes_id, user, held)
        project_id, entity_type, entity_id = previous.project_id, previous.entity_type, previous.entity_id
    if project_id is not None:
        await readable_project(db, project_id, user["id"], held)
    name = (file.filename or "upload").replace("/", "_").replace("\\", "_")[:300]
    content_type = file.content_type or "application/octet-stream"
    try:
        key, size, digest = await storage().save(file, settings.FILE_MAX_UPLOAD_MB * 1024 * 1024)
    except FileTooLarge as exc:
        raise UnprocessableEntityException(f"Files are limited to {settings.FILE_MAX_UPLOAD_MB} MB.") from exc
    stored = StoredFile(
        name=name,
        content_type=content_type,
        size=size,
        sha256=digest,
        storage_key=key,
        uploaded_by_id=user["id"],
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        category=(category or (FileCategory(previous.category) if previous else guess_category(name, content_type))).value,
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()][:30] or (list(previous.tags) if previous else []),
        revision=previous.revision + 1 if previous else 1,
        supersedes_id=previous.id if previous else None,
    )
    if previous:
        previous.is_latest = False
    db.add(stored)
    await db.commit()
    return (await as_read(db, [stored]))[0]


@router.get(
    "/{file_id}",
    response_model=FileRead,
    summary="File Details",
    dependencies=[require_permissions(FilePermissionName.READ.value)],
)
async def get_file(file_id: FileId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await as_read(db, [await readable_file(db, file_id, user, held)]))[0]


@router.get(
    "/{file_id}/download",
    summary="Download or Preview",
    description="`inline=true` lets the browser show images, PDFs and text in place.",
    dependencies=[require_permissions(FilePermissionName.READ.value)],
)
async def download(
    file_id: FileId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, inline: bool = False
) -> FileResponse:
    f = await readable_file(db, file_id, user, held)
    show = inline and f.content_type.startswith(INLINE_TYPES)
    disposition = "inline" if show else "attachment"
    return FileResponse(
        storage().path(f.storage_key),
        media_type=f.content_type if show else "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(f.name)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.patch(
    "/{file_id}",
    response_model=FileRead,
    summary="Rename, Recategorise or Retag",
    dependencies=[require_permissions(FilePermissionName.UPLOAD.value)],
)
async def update_file(
    file_id: FileId, values: FileUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    f = await readable_file(db, file_id, user, held)
    changes = values.model_dump(exclude_unset=True, exclude_none=True)
    if "category" in changes:
        changes["category"] = changes["category"].value
    for key, value in changes.items():
        setattr(f, key, value)
    await db.commit()
    return (await as_read(db, [f]))[0]


@router.delete("/{file_id}", summary="Delete a File", description="The uploader, or holders of files.delete.")
async def delete_file(
    file_id: FileId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    f = await readable_file(db, file_id, user, held)
    if f.uploaded_by_id != user["id"] and FilePermissionName.DELETE.value not in held and not user.get("is_superuser"):
        raise FileAccessError("Not yours")
    if f.supersedes_id:
        previous = await db.get(StoredFile, f.supersedes_id)
        if previous is not None and f.is_latest:
            previous.is_latest = True
    key = f.storage_key
    await db.delete(f)
    await db.commit()
    await storage().delete(key)
    return {"message": "File deleted"}

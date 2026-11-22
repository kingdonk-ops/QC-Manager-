"""Mounted at /api/v1/cde."""

import json
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.config.settings import settings
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..files.constants import guess_category
from ..files.models import StoredFile
from ..files.storage import FileTooLarge, storage
from ..projects.service import readable_project
from . import naming, service
from .constants import ENTITY, CdeState
from .models import CdeDocument
from .permissions import CdePermissionName as P
from .schemas import (
    CdeDocumentDetail,
    CdeDocumentRead,
    CdeDocumentRegister,
    CdeHistoryRead,
    CdeNamingConventionIn,
    CdeNamingConventionRead,
    CdeStateCounts,
    CdeStatusChange,
)

router = APIRouter(tags=["CDE"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
INLINE_TYPES = ("image/", "application/pdf", "text/plain")


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _naming_failed(errors: list[str]) -> UnprocessableEntityException:
    return UnprocessableEntityException("The name doesn't follow the project's naming convention: " + "; ".join(errors))


async def _store(upload: UploadFile, user: dict[str, Any]) -> StoredFile:
    """Save the bytes; the row is added by the caller. Kept off the project's document list."""
    name = (upload.filename or "upload").replace("/", "_").replace("\\", "_")[:300]
    content_type = upload.content_type or "application/octet-stream"
    try:
        key, size, digest = await storage().save(upload, settings.FILE_MAX_UPLOAD_MB * 1024 * 1024)
    except FileTooLarge as exc:
        raise UnprocessableEntityException(f"Files are limited to {settings.FILE_MAX_UPLOAD_MB} MB.") from exc
    return StoredFile(
        name=name,
        content_type=content_type,
        size=size,
        sha256=digest,
        storage_key=key,
        uploaded_by_id=user["id"],
        entity_type=ENTITY,
        category=guess_category(name, content_type).value,
    )


# --- naming convention --------------------------------------------------------------------------


async def _convention_read(db: AsyncSessionDep, project_id: int) -> CdeNamingConventionRead:
    convention, is_default = await service.convention_of(db, project_id)
    return CdeNamingConventionRead(
        project_id=project_id, is_default=is_default, example=naming.example(convention), **convention
    )


@router.get(
    "/naming/{project_id}",
    response_model=CdeNamingConventionRead,
    summary="The Project's Naming Convention",
    description="The default (ISO 19650 UK annex style) until the project saves its own.",
    dependencies=perm(P.READ),
)
async def get_naming(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await _convention_read(db, project_id)


@router.put(
    "/naming/{project_id}",
    response_model=CdeNamingConventionRead,
    summary="Set the Naming Convention",
    description="Applies to documents registered from now on.",
    dependencies=perm(P.MANAGE),
)
async def set_naming(
    project_id: Id, values: CdeNamingConventionIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    clean = values.model_dump()
    for field in clean["fields"]:
        for code in field["codes"]:
            code["code"] = code["code"].upper()
    await service.save_convention(db, project_id, clean)
    return await _convention_read(db, project_id)


# --- documents ----------------------------------------------------------------------------------


@router.get(
    "/documents/",
    response_model=PaginatedListResponse[CdeDocumentRead],
    summary="List Information Containers",
    description="Only what the caller may see in each state. `code=type:DR` filters by a naming field (repeatable); "
    "`awaiting_me` lists the requests the caller can approve.",
    dependencies=perm(P.READ),
)
async def list_documents(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    state: CdeState | None = None,
    suitability: Annotated[str | None, Query(max_length=4)] = None,
    code: Annotated[list[str] | None, Query(max_length=12, description="`field:CODE`")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    awaiting_me: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = []
    if state:
        where.append(CdeDocument.state == state.value)
    if suitability:
        where.append(CdeDocument.suitability == suitability.upper())
    for item in code or []:
        key, _, value = item.partition(":")
        if not key.isidentifier() or len(key) > 30 or not value or len(value) > 40:
            raise UnprocessableEntityException(f"Filter '{item[:50]}' should look like field:CODE")
        where.append(CdeDocument.fields[key].as_string() == value.upper())
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(CdeDocument.name).like(like), func.lower(CdeDocument.title).like(like)))
    if awaiting_me:
        where.append(service.awaiting(user, held))
    statement = service.scoped(select(CdeDocument), project_id, user, held).where(*where)
    total = await db.scalar(service.scoped(select(func.count()).select_from(CdeDocument), project_id, user, held).where(*where))
    rows = (
        await db.execute(
            statement.order_by(CdeDocument.name).offset(compute_offset(page, items_per_page)).limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_many(db, list(rows), user, held), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/documents/counts",
    response_model=CdeStateCounts,
    summary="How Many Containers in Each State",
    dependencies=perm(P.READ),
)
async def state_counts(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.counts(db, project_id, user, held)


@router.post(
    "/documents/",
    response_model=CdeDocumentDetail,
    status_code=201,
    summary="Register a Container",
    description="Multipart: the file plus `project_id`, `title`, and either `fields` (a JSON object of naming field "
    "codes) or a `name` to check. Starts in WIP at P01, suitability S0. A name that breaks the project's convention "
    "is refused with a message naming each failing field.",
    dependencies=perm(P.UPLOAD),
)
async def register(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[int, Form(ge=1, le=MAX_INTEGER_ID)],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    fields: Annotated[str | None, Form(max_length=2000, description='JSON object, e.g. {"type": "DR"}')] = None,
    name: Annotated[str | None, Form(max_length=200)] = None,
    description: Annotated[str | None, Form(max_length=5000)] = None,
) -> Any:
    try:
        parsed = json.loads(fields) if fields else None
        meta = CdeDocumentRegister.model_validate(
            {"project_id": project_id, "title": title, "description": description, "fields": parsed, "name": name}
        )
    except (ValueError, PydanticValidationError) as exc:
        raise UnprocessableEntityException("`fields` must be a JSON object of field codes, or give a `name`.") from exc
    await readable_project(db, project_id, user["id"], held)
    convention, _ = await service.convention_of(db, project_id)
    if meta.fields:
        full_name, values, errors = naming.compose(convention, meta.fields)
    else:
        full_name, values, errors = naming.parse(convention, meta.name or "")
    if errors:
        raise _naming_failed(errors)
    taken = await db.scalar(select(CdeDocument.id).where(CdeDocument.project_id == project_id, CdeDocument.name == full_name))
    if taken:
        raise ConflictException(f"{full_name} is already registered on this project. Upload a new revision to it.")
    stored = await _store(file, user)
    doc = await service.register(
        db,
        project_id=project_id,
        name=full_name,
        fields=values,
        title=meta.title,
        description=meta.description,
        stored=stored,
        user=user,
    )
    return await service.detail(db, doc, user, held)


@router.get("/documents/{document_id}", response_model=CdeDocumentDetail, summary="Get a Container", dependencies=perm(P.READ))
async def get_document(document_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    doc = await service.readable_document(db, document_id, user, held)
    await readable_project(db, doc.project_id, user["id"], held)
    return await service.detail(db, doc, user, held)


@router.patch(
    "/documents/{document_id}/status",
    response_model=CdeDocumentDetail,
    summary="Change State, or Decide a Request",
    description="`{state, suitability, comment}` moves the container, or asks for approval where a gate applies "
    "(WIP→Shared when the convention requires a check, by a `cde.review` holder; Shared→Published always, by a "
    "`cde.approve` holder). `{decision: approve|reject, comment}` decides the pending request.",
    dependencies=perm(P.READ),
)
async def change_status(
    document_id: Id, values: CdeStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    doc = await service.readable_document(db, document_id, user, held)
    await readable_project(db, doc.project_id, user["id"], held)
    await service.change_status(
        db,
        doc,
        user,
        held,
        state=values.state.value if values.state else None,
        suitability=values.suitability,
        decision=values.decision,
        comment=values.comment,
    )
    return await service.detail(db, doc, user, held)


@router.post(
    "/documents/{document_id}/revisions",
    response_model=CdeDocumentDetail,
    status_code=201,
    summary="Upload a New Revision",
    description="Multipart `file` (+ `comment`). The next P revision, back in WIP at S0; the previous revision is "
    "marked superseded and kept.",
    dependencies=perm(P.UPLOAD),
)
async def add_revision(
    document_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    comment: Annotated[str | None, Form(max_length=5000)] = None,
) -> Any:
    doc = await service.readable_document(db, document_id, user, held)
    await readable_project(db, doc.project_id, user["id"], held)
    if comment and "\x00" in comment:
        raise UnprocessableEntityException("The comment holds a character that can't be stored.")
    service.check_revisable(doc, user, held)
    stored = await _store(file, user)
    stored.entity_id = doc.id
    await service.new_revision(db, doc, stored, user, held, comment)
    return await service.detail(db, doc, user, held)


@router.get(
    "/documents/{document_id}/download",
    summary="Download a Revision's File",
    description="The current revision unless `revision_id` is given. External users get published revisions only.",
    dependencies=perm(P.READ),
)
async def download(
    document_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    revision_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    inline: bool = False,
) -> FileResponse:
    doc = await service.readable_document(db, document_id, user, held)
    await readable_project(db, doc.project_id, user["id"], held)
    f = await service.revision_file(db, doc, revision_id, user, held)
    show = inline and f.content_type.startswith(INLINE_TYPES)
    return FileResponse(
        storage().path(f.storage_key),
        media_type=f.content_type if show else "application/octet-stream",
        headers={
            "Content-Disposition": f"{'inline' if show else 'attachment'}; filename*=UTF-8''{quote(f.name)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.get(
    "/documents/{document_id}/history",
    response_model=list[CdeHistoryRead],
    summary="Transitions and Approvals",
    dependencies=perm(P.READ),
)
async def history(document_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    doc = await service.readable_document(db, document_id, user, held)
    await readable_project(db, doc.project_id, user["id"], held)
    rows = await history_of(db, ENTITY, doc.id)
    if service.is_external(user, held):
        rows = [r for r in rows if r["to_status"] in (CdeState.PUBLISHED, CdeState.ARCHIVED)]
    names = await service.names_of(db, {r["changed_by_id"] for r in rows if r["changed_by_id"]})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"])} for r in rows]

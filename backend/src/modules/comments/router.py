"""Mounted at /api/v1/comments."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID
from ..projects.service import readable_project
from . import service
from .permissions import CommentPermissionName
from .schemas import CommentCreate, CommentEdit, CommentRead, ReplyCreate, ResolveSet

router = APIRouter(tags=["Comments"])

CommentId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
Link = Annotated[str | None, Query(max_length=300, pattern=r"^/[^/].*$", description="App path the notification opens")]


@router.get(
    "/",
    response_model=list[CommentRead],
    summary="The Comment Threads on a Record",
    dependencies=[require_permissions(CommentPermissionName.READ.value)],
)
async def list_comments(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1)],
    entity_type: Annotated[str, Query(max_length=40)],
    entity_id: Annotated[int, Query(ge=1)],
) -> list[CommentRead]:
    await readable_project(db, project_id, user["id"], held)
    threads = await service.thread(db, entity_type, entity_id)
    return [t for t in threads if t.project_id == project_id]


@router.post(
    "/",
    response_model=CommentRead,
    status_code=201,
    summary="Comment on a Record",
    dependencies=[require_permissions(CommentPermissionName.CREATE.value)],
)
async def create(
    values: CommentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, link: Link = None
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    c = await service.add(
        db,
        project_id=values.project_id,
        entity_type=values.entity_type,
        entity_id=values.entity_id,
        body=values.body,
        author=user,
        parent=None,
        attachment_ids=values.attachment_ids,
        link=link,
    )
    return next(t for t in await service.thread(db, c.entity_type, c.entity_id) if t.id == c.id)


@router.post(
    "/{comment_id}/reply",
    response_model=CommentRead,
    status_code=201,
    summary="Reply in a Thread",
    dependencies=[require_permissions(CommentPermissionName.CREATE.value)],
)
async def reply(
    comment_id: CommentId,
    values: ReplyCreate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    link: Link = None,
) -> Any:
    parent = await service.get(db, comment_id)
    await readable_project(db, parent.project_id, user["id"], held)
    if parent.parent_id is not None:
        parent = await service.get(db, parent.parent_id)
    c = await service.add(
        db,
        project_id=parent.project_id,
        entity_type=parent.entity_type,
        entity_id=parent.entity_id,
        body=values.body,
        author=user,
        parent=parent,
        attachment_ids=values.attachment_ids,
        link=link,
    )
    root = next(t for t in await service.thread(db, c.entity_type, c.entity_id) if t.id == parent.id)
    return next(r for r in root.replies if r.id == c.id)


@router.patch("/{comment_id}/resolve", response_model=list[CommentRead], summary="Resolve or Reopen a Thread")
async def resolve(
    comment_id: CommentId, values: ResolveSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    c = await service.get(db, comment_id)
    await readable_project(db, c.project_id, user["id"], held)
    if c.parent_id is not None:
        raise UnprocessableEntityException("Resolve the thread's first comment.")
    if c.author_id != user["id"] and CommentPermissionName.UPDATE.value not in held:
        raise service.NotYourCommentError("Not yours")
    await service.resolve(db, c, values.resolved, user["id"])
    return await service.thread(db, c.entity_type, c.entity_id)


@router.patch("/{comment_id}", response_model=list[CommentRead], summary="Edit a Comment")
async def edit(
    comment_id: CommentId, values: CommentEdit, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    c = await service.get(db, comment_id)
    await readable_project(db, c.project_id, user["id"], held)
    if c.author_id != user["id"] and CommentPermissionName.UPDATE.value not in held:
        raise service.NotYourCommentError("Not yours")
    c.body, c.edited = values.body, True
    await db.commit()
    return await service.thread(db, c.entity_type, c.entity_id)


@router.delete("/{comment_id}", summary="Delete a Comment and Its Replies")
async def delete(
    comment_id: CommentId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    c = await service.get(db, comment_id)
    await readable_project(db, c.project_id, user["id"], held)
    if c.author_id != user["id"] and CommentPermissionName.UPDATE.value not in held:
        raise service.NotYourCommentError("Not yours")
    await db.delete(c)
    await db.commit()
    return {"message": "Comment deleted"}

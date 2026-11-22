import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .models import Comment
from .schemas import CommentRead

MENTION = re.compile(r"(?<![\w@])@([a-z0-9_]{2,32})")


class CommentNotFoundError(ResourceNotFoundError):
    public_detail = "Comment not found."


class NotYourCommentError(PermissionDeniedError):
    public_detail = "Only its author, or holders of comments.update, can change this comment."


async def mentioned_users(db: AsyncSession, body: str) -> list[int]:
    names = set(MENTION.findall(body.lower()))
    if not names:
        return []
    return list((await db.execute(select(User.id).where(User.username.in_(names), User.is_deleted.is_(False)))).scalars())


async def thread(db: AsyncSession, entity_type: str, entity_id: int) -> list[CommentRead]:
    rows = list(
        (
            await db.execute(
                select(Comment)
                .where(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
                .order_by(Comment.created_at, Comment.id)
            )
        ).scalars()
    )
    authors = {c.author_id for c in rows if c.author_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(authors)))).tuples().all()) if authors else {}
    by_id: dict[int, CommentRead] = {}
    roots: list[CommentRead] = []
    for c in rows:
        read = CommentRead(
            id=c.id,
            project_id=c.project_id,
            entity_type=c.entity_type,
            entity_id=c.entity_id,
            parent_id=c.parent_id,
            author_id=c.author_id,
            author_name=names.get(c.author_id) if c.author_id else None,
            body=c.body,
            mentions=list(c.mentions),
            attachment_ids=list(c.attachment_ids),
            resolved=c.resolved,
            resolved_by_id=c.resolved_by_id,
            edited=c.edited,
            created_at=c.created_at,
        )
        by_id[c.id] = read
        parent = by_id.get(c.parent_id) if c.parent_id else None
        (parent.replies if parent else roots).append(read)
    return roots


async def add(
    db: AsyncSession,
    *,
    project_id: int,
    entity_type: str,
    entity_id: int,
    body: str,
    author: dict[str, Any],
    parent: Comment | None,
    attachment_ids: list[int],
    link: str | None,
) -> Comment:
    mentions = await mentioned_users(db, body)
    comment = Comment(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        author_id=author["id"],
        body=body,
        parent_id=parent.id if parent else None,
        mentions=mentions,
        attachment_ids=attachment_ids,
    )
    db.add(comment)
    await db.flush()
    label = f"{entity_type.replace('_', ' ')} #{entity_id}"
    await notify(
        db,
        mentions,
        Category.MENTION,
        f"{author['name']} mentioned you on {label}",
        body=body[:500],
        link=link,
        entity=(entity_type, entity_id),
        actor_id=author["id"],
    )
    if parent is not None:
        root_id = parent.id
        participants = set(
            (
                await db.execute(select(Comment.author_id).where((Comment.id == root_id) | (Comment.parent_id == root_id)))
            ).scalars()
        )
        await notify(
            db,
            [p for p in participants if p and p not in mentions],
            Category.STATUS,
            f"{author['name']} replied on {label}",
            body=body[:500],
            link=link,
            entity=(entity_type, entity_id),
            actor_id=author["id"],
        )
    await db.commit()
    return comment


async def get(db: AsyncSession, comment_id: int) -> Comment:
    c = await db.get(Comment, comment_id)
    if c is None:
        raise CommentNotFoundError("No such comment")
    return c


async def resolve(db: AsyncSession, comment: Comment, resolved: bool, user_id: int) -> None:
    comment.resolved = resolved
    comment.resolved_by_id = user_id if resolved else None
    comment.resolved_at = datetime.now(UTC) if resolved else None
    await db.commit()

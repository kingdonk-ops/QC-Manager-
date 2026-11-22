"""Client plan review: staff share plans with a project's client team; the client decides each document.

Visibility: staff (superusers, holders of ``projects.read`` or ``portal.submit``) see every review of a project
they can read. Anyone else sees a review only once it is shared, and only while they are a member of the
review's client team; otherwise it answers 404, like a project they can't see. Only client-team members
decide documents (no proxy decisions by staff). A review is ``reviewed`` once every document is decided; its
outcome is the worst decision (rejected < approved with comments < approved).
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..projects.permissions import ProjectPermissionName
from ..projects.service import readable_project
from ..team.models import Team, TeamMembership
from ..user.models import User
from .models import PlanReview, PlanReviewComment, PlanReviewDocument
from .permissions import PortalPermissionName as P
from .review_schemas import PlanReviewRead

ENTITY = "plan_review"
DECIDED = ("approved", "approved_with_comments", "rejected")
CLIENT_VISIBLE = ("shared", "reviewed")


class ReviewNotFound(ResourceNotFoundError):
    public_detail = "Plan review not found."


class ReviewStateError(ValidationError):
    public_detail = "That can't be done in the review's current status."


class NoClientTeam(ValidationError):
    public_detail = "The project has no client team to share with. Set one on the project, or choose a team."


class NothingToShare(ValidationError):
    public_detail = "Add at least one document before sharing."


class WrongFile(ValidationError):
    public_detail = "That file isn't one of this project's files."


class CommentRequired(ValidationError):
    public_detail = "Say why: a comment is required unless you approve outright."


class NotReviewer(ResourceNotFoundError):
    public_detail = "Plan review not found."


def utcnow() -> datetime:
    return datetime.now(UTC)


def is_staff(user: dict[str, Any], held: frozenset[str]) -> bool:
    return bool(user.get("is_superuser")) or ProjectPermissionName.READ.value in held or P.SUBMIT.value in held


async def team_members(db: AsyncSession, team_id: int | None) -> list[int]:
    if team_id is None:
        return []
    return list((await db.execute(select(TeamMembership.user_id).where(TeamMembership.team_id == team_id))).scalars())


async def in_team(db: AsyncSession, team_id: int | None, user_id: int) -> bool:
    if team_id is None:
        return False
    found = await db.scalar(
        select(TeamMembership.user_id).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
    )
    return found is not None


async def visible_review(db: AsyncSession, review_id: int, user: dict[str, Any], held: frozenset[str]) -> PlanReview:
    review = await db.get(PlanReview, review_id)
    if review is None:
        raise ReviewNotFound(str(review_id))
    await readable_project(db, review.project_id, user["id"], held)
    if is_staff(user, held):
        return review
    if review.status not in CLIENT_VISIBLE or not await in_team(db, review.client_team_id, user["id"]):
        raise ReviewNotFound(str(review_id))
    return review


def visibility_filter(user: dict[str, Any], held: frozenset[str]) -> list[Any]:
    if is_staff(user, held):
        return []
    teams = select(TeamMembership.team_id).where(TeamMembership.user_id == user["id"])
    return [PlanReview.status.in_(CLIENT_VISIBLE), PlanReview.client_team_id.in_(teams)]


def link_of(review: PlanReview) -> str:
    return f"/plan-reviews?project={review.project_id}&id={review.id}"


async def read_reviews(db: AsyncSession, reviews: list[PlanReview]) -> list[dict[str, Any]]:
    ids = [r.id for r in reviews]
    counts: dict[int, tuple[int, int]] = {}
    if ids:
        rows = await db.execute(
            select(
                PlanReviewDocument.review_id,
                func.count(),
                func.count().filter(PlanReviewDocument.decision != "pending"),
            )
            .where(PlanReviewDocument.review_id.in_(ids))
            .group_by(PlanReviewDocument.review_id)
        )
        counts = {rid: (total, decided) for rid, total, decided in rows.tuples()}
    teams = {r.client_team_id for r in reviews if r.client_team_id}
    names = dict((await db.execute(select(Team.id, Team.name).where(Team.id.in_(teams)))).tuples().all()) if teams else {}
    today = date.today()
    out = []
    for r in reviews:
        total, decided = counts.get(r.id, (0, 0))
        out.append(
            PlanReviewRead(
                id=r.id,
                project_id=r.project_id,
                code=r.code,
                title=r.title,
                kind=r.kind,
                message=r.message,
                client_team_id=r.client_team_id,
                client_team_name=names.get(r.client_team_id) if r.client_team_id else None,
                due_date=r.due_date,
                overdue=bool(r.due_date and r.due_date < today and r.status == "shared"),
                status=r.status,
                outcome=r.outcome,
                documents_total=total,
                documents_decided=decided,
                shared_at=r.shared_at,
                reviewed_at=r.reviewed_at,
                created_at=r.created_at,
            ).model_dump(mode="json")
        )
    return out


async def detail(db: AsyncSession, review: PlanReview, user: dict[str, Any], held: frozenset[str]) -> dict[str, Any]:
    base = (await read_reviews(db, [review]))[0]
    docs = list(
        (
            await db.execute(
                select(PlanReviewDocument, StoredFile)
                .join(StoredFile, StoredFile.id == PlanReviewDocument.file_id)
                .where(PlanReviewDocument.review_id == review.id)
                .order_by(PlanReviewDocument.id)
            )
        ).all()
    )
    comments = list(
        (
            await db.execute(
                select(PlanReviewComment).where(PlanReviewComment.review_id == review.id).order_by(PlanReviewComment.id)
            )
        ).scalars()
    )
    people = {d.decided_by_id for d, _ in docs if d.decided_by_id} | {c.author_id for c in comments if c.author_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(people)))).tuples().all()) if people else {}
    clients = set(await team_members(db, review.client_team_id))
    member = user["id"] in clients
    return {
        **base,
        "documents": [
            {
                "id": d.id,
                "file_id": d.file_id,
                "title": d.title,
                "file_name": f.name,
                "content_type": f.content_type,
                "size": f.size,
                "decision": d.decision,
                "decision_comment": d.decision_comment,
                "decided_by_name": names.get(d.decided_by_id) if d.decided_by_id else None,
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            }
            for d, f in docs
        ],
        "comments": [
            {
                "id": c.id,
                "document_id": c.document_id,
                "author_id": c.author_id,
                "author_name": names.get(c.author_id) if c.author_id else None,
                "from_client": c.author_id in clients,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
        "can_decide": member and review.status == "shared" and (bool(user.get("is_superuser")) or P.REVIEW.value in held),
        "can_manage": bool(user.get("is_superuser")) or P.SUBMIT.value in held,
    }


async def _add_document(db: AsyncSession, review: PlanReview, file_id: int, title: str | None) -> PlanReviewDocument:
    f = await db.get(StoredFile, file_id)
    if f is None or f.project_id != review.project_id:
        raise WrongFile(str(file_id))
    doc = PlanReviewDocument(review_id=review.id, file_id=f.id, title=title or f.name)
    db.add(doc)
    await db.flush()
    return doc


async def create(db: AsyncSession, values: dict[str, Any], user_id: int) -> PlanReview:
    project = await db.get(Project, values["project_id"])
    assert project is not None
    team_id = values.get("client_team_id") or project.client_team_id
    if values.get("client_team_id") and await db.get(Team, values["client_team_id"]) is None:
        raise NoClientTeam("no such team")
    review = PlanReview(
        project_id=project.id,
        code=await next_reference(db, "PRV", project.id),
        title=values["title"],
        kind=values.get("kind") or "work_plan",
        message=values.get("message"),
        client_team_id=team_id,
        due_date=values.get("due_date"),
        created_by_id=user_id,
    )
    db.add(review)
    await db.flush()
    for doc in values.get("documents") or []:
        await _add_document(db, review, doc["file_id"], doc.get("title"))
    await record_transition(db, ENTITY, review.id, None, "draft", user_id, None)
    await db.commit()
    return review


async def add_document(db: AsyncSession, review: PlanReview, file_id: int, title: str | None, user_id: int) -> None:
    """Add a document (a revised plan, say). On a shared or reviewed package it goes back to the client."""
    if review.status == "withdrawn":
        raise ReviewStateError(review.status)
    doc = await _add_document(db, review, file_id, title)
    if review.status == "reviewed":
        await record_transition(db, ENTITY, review.id, review.status, "shared", user_id, f"Added {doc.title}")
        review.status, review.outcome, review.reviewed_at = "shared", None, None
    if review.status == "shared":
        await notify(
            db,
            await team_members(db, review.client_team_id),
            Category.APPROVAL,
            f"{review.code}: {doc.title} added for your review",
            body=review.title,
            link=link_of(review),
            entity=(ENTITY, review.id),
            actor_id=user_id,
        )
    await db.commit()


async def share(db: AsyncSession, review: PlanReview, note: str | None, user_id: int) -> None:
    if review.status != "draft":
        raise ReviewStateError(review.status)
    if review.client_team_id is None:
        project = await db.get(Project, review.project_id)
        review.client_team_id = project.client_team_id if project else None
    if review.client_team_id is None:
        raise NoClientTeam(review.code)
    if not await db.scalar(select(PlanReviewDocument.id).where(PlanReviewDocument.review_id == review.id).limit(1)):
        raise NothingToShare(review.code)
    await record_transition(db, ENTITY, review.id, review.status, "shared", user_id, note)
    review.status, review.shared_by_id, review.shared_at = "shared", user_id, utcnow()
    due = f" by {review.due_date.isoformat()}" if review.due_date else ""
    await notify(
        db,
        await team_members(db, review.client_team_id),
        Category.APPROVAL,
        f"{review.code}: {review.title} shared for your review{due}",
        body=note or review.message,
        link=link_of(review),
        entity=(ENTITY, review.id),
        actor_id=user_id,
    )
    await db.commit()


async def withdraw(db: AsyncSession, review: PlanReview, user_id: int) -> None:
    if review.status not in {"draft", "shared"}:
        raise ReviewStateError(review.status)
    await record_transition(db, ENTITY, review.id, review.status, "withdrawn", user_id, None)
    was_shared = review.status == "shared"
    review.status = "withdrawn"
    if was_shared:
        await notify(
            db,
            await team_members(db, review.client_team_id),
            Category.STATUS,
            f"{review.code}: {review.title} withdrawn",
            link=link_of(review),
            entity=(ENTITY, review.id),
            actor_id=user_id,
        )
    await db.commit()


def _staff_watchers(review: PlanReview) -> list[int]:
    return [u for u in {review.created_by_id, review.shared_by_id} if u]


async def decide(
    db: AsyncSession, review: PlanReview, document_id: int, decision: str, comment: str | None, user_id: int
) -> None:
    if review.status != "shared":
        raise ReviewStateError(review.status)
    if not await in_team(db, review.client_team_id, user_id):
        raise NotReviewer(str(review.id))
    if decision != "approved" and not (comment and comment.strip()):
        raise CommentRequired(decision)
    doc = await db.get(PlanReviewDocument, document_id)
    if doc is None or doc.review_id != review.id:
        raise ReviewNotFound(f"document {document_id}")
    doc.decision, doc.decision_comment, doc.decided_by_id, doc.decided_at = decision, comment, user_id, utcnow()
    await record_transition(db, "plan_review_document", doc.id, "pending", decision, user_id, comment)
    await db.flush()
    decisions = list(
        (await db.execute(select(PlanReviewDocument.decision).where(PlanReviewDocument.review_id == review.id))).scalars()
    )
    title = f"{review.code}: {doc.title} {decision.replace('_', ' ')}"
    if all(d in DECIDED for d in decisions):
        outcome = next(o for o in ("rejected", "approved_with_comments", "approved") if o in decisions)
        await record_transition(db, ENTITY, review.id, review.status, "reviewed", user_id, outcome)
        review.status, review.outcome, review.reviewed_at = "reviewed", outcome, utcnow()
        title = f"{review.code}: review complete, {outcome.replace('_', ' ')}"
    await notify(
        db,
        _staff_watchers(review),
        Category.APPROVAL,
        title,
        body=comment,
        link=link_of(review),
        entity=(ENTITY, review.id),
        actor_id=user_id,
    )
    await db.commit()


async def add_comment(
    db: AsyncSession, review: PlanReview, body: str, document_id: int | None, user: dict[str, Any], held: frozenset[str]
) -> None:
    if document_id is not None:
        doc = await db.get(PlanReviewDocument, document_id)
        if doc is None or doc.review_id != review.id:
            raise ReviewNotFound(f"document {document_id}")
    db.add(PlanReviewComment(review_id=review.id, document_id=document_id, author_id=user["id"], body=body))
    clients = await team_members(db, review.client_team_id)
    from_client = user["id"] in clients
    # Staff comments on a draft stay internal; once shared, the client team hears of them.
    targets = _staff_watchers(review) if from_client else (clients if review.status in CLIENT_VISIBLE else [])
    targets += [u for u in _staff_watchers(review) if not from_client]
    await notify(
        db,
        targets,
        Category.MENTION,
        f"{review.code}: new comment from {user['name']}",
        body=body[:500],
        link=link_of(review),
        entity=(ENTITY, review.id),
        actor_id=user["id"],
    )
    await db.commit()


async def document_file(db: AsyncSession, review: PlanReview, document_id: int) -> StoredFile:
    doc = await db.get(PlanReviewDocument, document_id)
    if doc is None or doc.review_id != review.id:
        raise ReviewNotFound(f"document {document_id}")
    f = await db.get(StoredFile, doc.file_id)
    if f is None:
        raise ReviewNotFound(f"file {doc.file_id}")
    return f

"""The submittal workflow: submit, step-by-step review, early termination, revisions."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..contacts.service import contact_names
from ..files.models import StoredFile
from ..files.service import as_read as files_as_read
from ..files.service import readable_file
from ..notifications.constants import Category
from ..notifications.service import notify
from ..role.models import RolePermission, UserRole
from ..user.models import User
from .constants import (
    ENDS_REVIEW,
    FLOW,
    IN_REVIEW,
    OPEN_STATUSES,
    REVISABLE,
    SEVERITY,
    ReviewState,
    SubmittalStatus,
    revision_letter,
)
from .models import Submittal, SubmittalReview, SubmittalRevision
from .permissions import SubmittalPermissionName
from .schemas import SubmittalDetail, SubmittalRead, SubmittalReviewRead

ENTITY = "submittal"
REVISION_ENTITY = "submittal_revision"


class SubmittalNotFoundError(ResourceNotFoundError):
    public_detail = "Submittal not found."


class NoOpenReview(PermissionDeniedError):
    public_detail = "You have no open review step on this submittal."


class WorkflowRequired(ValidationError):
    public_detail = "Add at least one review step before submitting."


class UnknownReviewer(ValidationError):
    public_detail = "A reviewer in the workflow isn't an active user."


class WorkflowLocked(ValidationError):
    public_detail = "The workflow can only change while the submittal is a draft. Revise it to start a new cycle."


class NotRevisable(ValidationError):
    public_detail = "Only a submittal that came back approved as noted, revise and resubmit, or rejected can be revised."


class FileNotAttachable(ValidationError):
    public_detail = "Attach your own unfiled uploads, or files already on this project."


def link_of(s: Submittal) -> str:
    return f"/submittals?project={s.project_id}&id={s.id}"


def now() -> datetime:
    return datetime.now(UTC)


async def user_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def get_submittal(db: AsyncSession, submittal_id: int) -> Submittal:
    s = await db.get(Submittal, submittal_id)
    if s is None:
        raise SubmittalNotFoundError("No such submittal")
    return s


async def current_revision(db: AsyncSession, s: Submittal) -> SubmittalRevision:
    rev = await db.scalar(
        select(SubmittalRevision).where(SubmittalRevision.submittal_id == s.id, SubmittalRevision.number == s.revision)
    )
    assert rev is not None
    return rev


def normalise_workflow(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Several reviewers on a sequential step become one step each, in order."""
    out: list[dict[str, Any]] = []
    for step in steps:
        ids = list(dict.fromkeys(int(i) for i in step["reviewer_ids"]))
        name = (step.get("name") or "").strip()
        if step.get("parallel") and len(ids) > 1:
            out.append({"name": name or f"Step {len(out) + 1}", "reviewer_ids": ids, "parallel": True})
        else:
            for uid in ids:
                out.append({"name": name or f"Step {len(out) + 1}", "reviewer_ids": [uid], "parallel": False})
    return out


async def check_reviewers(db: AsyncSession, steps: list[dict[str, Any]]) -> None:
    ids = {i for step in steps for i in step["reviewer_ids"]}
    if not ids:
        return
    found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(ids), User.is_deleted.is_(False)))
    if (found or 0) != len(ids):
        raise UnknownReviewer(str(sorted(ids)))


async def create(db: AsyncSession, values: dict[str, Any], user: dict[str, Any]) -> Submittal:
    workflow = normalise_workflow(values.pop("workflow", []) or [])
    await check_reviewers(db, workflow)
    project_id = values.pop("project_id")
    if not values.get("submitted_by_user_id") and not values.get("submitted_by_contact_id"):
        values["submitted_by_user_id"] = user["id"]
    s = Submittal(
        project_id=project_id,
        code=await next_reference(db, "SUB", project_id),
        created_by_id=user["id"],
        workflow=workflow,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(s)
    await db.flush()
    db.add(SubmittalRevision(submittal_id=s.id, number=0, created_by_id=user["id"]))
    await record_transition(db, ENTITY, s.id, None, SubmittalStatus.DRAFT.value, user["id"], "Created (Rev A)")
    await db.commit()
    return s


async def update(db: AsyncSession, s: Submittal, changes: dict[str, Any]) -> None:
    if "workflow" in changes:
        if s.status != SubmittalStatus.DRAFT:
            raise WorkflowLocked(s.status)
        workflow = normalise_workflow(changes.pop("workflow") or [])
        await check_reviewers(db, workflow)
        s.workflow = workflow
    for key, value in changes.items():
        setattr(s, key, value.value if hasattr(value, "value") else value)
    await db.commit()


async def _set_status(db: AsyncSession, s: Submittal, target: str, actor_id: int | None, note: str | None) -> None:
    assert_transition(FLOW, s.status, target)
    await record_transition(db, ENTITY, s.id, s.status, target, actor_id, note)
    s.status = target


async def _open_step(db: AsyncSession, s: Submittal, rev: SubmittalRevision, step: int, actor_id: int | None) -> None:
    reviews = list(
        (
            await db.execute(select(SubmittalReview).where(SubmittalReview.revision_id == rev.id, SubmittalReview.step == step))
        ).scalars()
    )
    opened = now()
    for r in reviews:
        r.state = ReviewState.OPEN.value
        r.opened_at = opened
    rev.current_step = step
    await notify(
        db,
        [r.reviewer_id for r in reviews if r.reviewer_id],
        Category.APPROVAL,
        f"{s.code} Rev {revision_letter(rev.number)} is waiting for your review",
        body=f"{s.title} · {reviews[0].step_name if reviews else ''}",
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=actor_id,
    )


async def submit(db: AsyncSession, s: Submittal, user: dict[str, Any], note: str | None = None) -> None:
    if not s.workflow:
        raise WorkflowRequired(s.code)
    await check_reviewers(db, s.workflow)
    await _set_status(db, s, SubmittalStatus.SUBMITTED.value, user["id"], note or f"Rev {revision_letter(s.revision)}")
    rev = await current_revision(db, s)
    rev.submitted_at = now()
    if note:
        rev.note = note
    for index, step in enumerate(s.workflow):
        for uid in step["reviewer_ids"]:
            db.add(
                SubmittalReview(
                    revision_id=rev.id,
                    submittal_id=s.id,
                    step=index,
                    step_name=step["name"],
                    parallel=bool(step.get("parallel")),
                    reviewer_id=uid,
                )
            )
    await db.flush()
    await _open_step(db, s, rev, 0, user["id"])
    await db.commit()


def _most_severe(decisions: list[str]) -> str:
    return max(decisions, key=lambda d: SEVERITY[d])


async def _finish(
    db: AsyncSession, s: Submittal, rev: SubmittalRevision, outcome: str, actor: dict[str, Any], comment: str | None
) -> None:
    rev.outcome = outcome
    rev.completed_at = now()
    rev.current_step = None
    leftover = (
        await db.execute(
            select(SubmittalReview).where(
                SubmittalReview.revision_id == rev.id,
                SubmittalReview.state.in_([ReviewState.OPEN.value, ReviewState.PENDING.value]),
            )
        )
    ).scalars()
    for r in leftover:
        r.state = ReviewState.SKIPPED.value
    await _set_status(db, s, outcome, actor["id"], comment)
    await notify(
        db,
        [s.created_by_id or 0, s.submitted_by_user_id or 0],
        Category.STATUS,
        f"{s.code} Rev {revision_letter(rev.number)}: {outcome.replace('_', ' ')}",
        body=s.title,
        link=link_of(s),
        entity=(ENTITY, s.id),
        actor_id=actor["id"],
    )


async def review(db: AsyncSession, s: Submittal, user: dict[str, Any], decision: str, comment: str | None) -> None:
    if s.status not in IN_REVIEW:
        raise NoOpenReview(s.status)
    rev = await current_revision(db, s)
    mine = await db.scalar(
        select(SubmittalReview).where(
            SubmittalReview.revision_id == rev.id,
            SubmittalReview.reviewer_id == user["id"],
            SubmittalReview.state == ReviewState.OPEN.value,
        )
    )
    if mine is None:
        raise NoOpenReview(f"user {user['id']}")
    mine.state = ReviewState.DECIDED.value
    mine.decision = decision
    mine.comment = comment
    mine.decided_at = now()
    if s.status == SubmittalStatus.SUBMITTED:
        await _set_status(db, s, SubmittalStatus.UNDER_REVIEW.value, user["id"], None)
    await db.flush()

    step_reviews = list(
        (
            await db.execute(
                select(SubmittalReview).where(SubmittalReview.revision_id == rev.id, SubmittalReview.step == mine.step)
            )
        ).scalars()
    )
    decided = [r.decision for r in step_reviews if r.decision]
    stamp = f"{mine.step_name}: {decision.replace('_', ' ')}" + (f" — {comment}" if comment else "")
    if decision in ENDS_REVIEW:
        await _finish(db, s, rev, _most_severe(decided), user, stamp)
    elif len(decided) == len(step_reviews):
        last = await db.scalar(select(func.max(SubmittalReview.step)).where(SubmittalReview.revision_id == rev.id))
        if mine.step >= (last or 0):
            await _finish(db, s, rev, _most_severe(decided), user, stamp)
        else:
            await _open_step(db, s, rev, mine.step + 1, user["id"])
    await db.commit()


async def revise(
    db: AsyncSession,
    s: Submittal,
    user: dict[str, Any],
    held: frozenset[str],
    *,
    note: str | None,
    file_ids: list[int],
    workflow: list[dict[str, Any]] | None,
    submit_now: bool,
) -> None:
    if s.status not in REVISABLE:
        raise NotRevisable(s.status)
    if workflow is not None:
        normalised = normalise_workflow(workflow)
        await check_reviewers(db, normalised)
        s.workflow = normalised
    files: list[StoredFile] = []
    for fid in dict.fromkeys(file_ids):
        f = await readable_file(db, fid, user, held)
        own_unfiled = f.project_id is None and f.uploaded_by_id == user["id"]
        if not own_unfiled and f.project_id != s.project_id:
            raise FileNotAttachable(str(fid))
        files.append(f)
    s.revision += 1
    rev = SubmittalRevision(submittal_id=s.id, number=s.revision, note=note, created_by_id=user["id"])
    db.add(rev)
    await db.flush()
    for f in files:
        f.project_id, f.entity_type, f.entity_id = s.project_id, REVISION_ENTITY, rev.id
    letter = revision_letter(s.revision)
    await _set_status(
        db, s, SubmittalStatus.DRAFT.value, user["id"], f"Revised to Rev {letter}" + (f": {note}" if note else "")
    )
    if submit_now:
        await submit(db, s, user)
    else:
        await db.commit()


async def close(db: AsyncSession, s: Submittal, user: dict[str, Any], note: str | None) -> None:
    await _set_status(db, s, SubmittalStatus.CLOSED.value, user["id"], note)
    await db.commit()


# --- reading ----------------------------------------------------------------------------------


def _days_since(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    return (now().date() - moment.astimezone(UTC).date()).days


async def read_many(db: AsyncSession, rows: list[Submittal]) -> list[dict[str, Any]]:
    if not rows:
        return []
    ids = [s.id for s in rows]
    revisions = {
        (r.submittal_id, r.number): r
        for r in (await db.execute(select(SubmittalRevision).where(SubmittalRevision.submittal_id.in_(ids)))).scalars()
    }
    current = {s.id: revisions[(s.id, s.revision)] for s in rows if (s.id, s.revision) in revisions}
    open_reviews = list(
        (
            await db.execute(
                select(SubmittalReview.revision_id, SubmittalReview.reviewer_id).where(
                    SubmittalReview.revision_id.in_([r.id for r in current.values()]),
                    SubmittalReview.state == ReviewState.OPEN.value,
                )
            )
        ).tuples()
    )
    reviewers_of: dict[int, list[int]] = {}
    for revision_id, reviewer_id in open_reviews:
        if reviewer_id:
            reviewers_of.setdefault(revision_id, []).append(reviewer_id)
    names = await user_names(
        db, {uid for uids in reviewers_of.values() for uid in uids} | {s.submitted_by_user_id or 0 for s in rows}
    )
    contacts = await contact_names(db, {s.submitted_by_contact_id for s in rows if s.submitted_by_contact_id})
    today = date.today()
    out = []
    for s in rows:
        rev = current.get(s.id)
        reviewer_ids = reviewers_of.get(rev.id, []) if rev else []
        in_review = s.status in IN_REVIEW
        submitted_by = (
            contacts.get(s.submitted_by_contact_id) if s.submitted_by_contact_id else names.get(s.submitted_by_user_id or 0)
        )
        out.append(
            SubmittalRead.model_validate(s)
            .model_copy(
                update={
                    "revision_letter": revision_letter(s.revision),
                    "current_revision_id": rev.id if rev else None,
                    "current_reviewer_ids": reviewer_ids,
                    "current_reviewers": [names.get(uid, f"User {uid}") for uid in reviewer_ids],
                    "submitted_by_name": submitted_by,
                    "submitted_at": rev.submitted_at if rev else None,
                    "days_outstanding": _days_since(rev.submitted_at) if rev and in_review else None,
                    "overdue": bool(s.required_by and s.required_by < today and s.status in OPEN_STATUSES),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def read_reviews(db: AsyncSession, revision_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    rows = list(
        (
            await db.execute(
                select(SubmittalReview)
                .where(SubmittalReview.revision_id.in_(revision_ids))
                .order_by(SubmittalReview.step, SubmittalReview.id)
            )
        ).scalars()
    )
    names = await user_names(db, {r.reviewer_id for r in rows if r.reviewer_id})
    out: dict[int, list[dict[str, Any]]] = {i: [] for i in revision_ids}
    for r in rows:
        out[r.revision_id].append(
            SubmittalReviewRead.model_validate(r)
            .model_copy(update={"reviewer_name": names.get(r.reviewer_id) if r.reviewer_id else None})
            .model_dump(mode="json")
        )
    return out


async def detail(db: AsyncSession, s: Submittal, user: dict[str, Any]) -> dict[str, Any]:
    base = (await read_many(db, [s]))[0]
    rev_id = base["current_revision_id"]
    reviews = (await read_reviews(db, [rev_id]))[rev_id] if rev_id else []
    mine = next((r["id"] for r in reviews if r["reviewer_id"] == user["id"] and r["state"] == ReviewState.OPEN), None)
    return SubmittalDetail(**base, reviews=reviews, my_open_review_id=mine).model_dump(mode="json")


async def revisions(db: AsyncSession, s: Submittal) -> list[dict[str, Any]]:
    revs = list(
        (
            await db.execute(
                select(SubmittalRevision)
                .where(SubmittalRevision.submittal_id == s.id)
                .order_by(SubmittalRevision.number.desc())
            )
        ).scalars()
    )
    reviews = await read_reviews(db, [r.id for r in revs])
    files = list(
        (
            await db.execute(
                select(StoredFile)
                .where(StoredFile.entity_type == REVISION_ENTITY, StoredFile.entity_id.in_([r.id for r in revs]))
                .order_by(StoredFile.name)
            )
        ).scalars()
    )
    read_files = await files_as_read(db, files)
    by_revision: dict[int, list[dict[str, Any]]] = {}
    for f in read_files:
        by_revision.setdefault(f["entity_id"], []).append(f)
    return [
        {
            "id": r.id,
            "number": r.number,
            "letter": revision_letter(r.number),
            "note": r.note,
            "outcome": r.outcome,
            "submitted_at": r.submitted_at,
            "completed_at": r.completed_at,
            "created_at": r.created_at,
            "reviews": reviews.get(r.id, []),
            "files": by_revision.get(r.id, []),
        }
        for r in revs
    ]


async def reviewer_options(db: AsyncSession, search: str | None, skip: int, limit: int) -> dict[str, Any]:
    """Active users who may review submittals: holders of ``submittals.review`` and superusers."""
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_name == SubmittalPermissionName.REVIEW.value)
    )
    where: list[Any] = [User.is_deleted.is_(False), or_(User.id.in_(holders), User.is_superuser.is_(True))]
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(User.name).like(like), func.lower(User.email).like(like)))
    total = await db.scalar(select(func.count()).select_from(User).where(*where))
    rows = await db.execute(select(User.id, User.name, User.email).where(*where).order_by(User.name).offset(skip).limit(limit))
    return {
        "data": [{"id": i, "name": n, "email": e} for i, n, e in rows.tuples().all()],
        "total_count": total or 0,
    }

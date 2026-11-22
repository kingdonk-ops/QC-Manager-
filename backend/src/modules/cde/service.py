"""CDE rules: who sees which state, revision numbering, transitions and their approval gates."""

import copy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, record_transition
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.permissions import ProjectPermissionName
from ..role.models import RolePermission, UserRole
from ..user.models import User
from .constants import DEFAULT_CONVENTION, ENTITY, FLOW, SUITABILITY, CdeState
from .models import CdeDocument, CdeNamingConvention, CdeRevision
from .permissions import CdePermissionName as P
from .schemas import CdeDocumentDetail, CdeDocumentRead, CdeRevisionRead


class DocumentNotFoundError(ResourceNotFoundError):
    public_detail = "Document not found."


class NotYours(PermissionDeniedError):
    public_detail = "Only the author or a task-team reviewer can change a work-in-progress document."


class CannotDecide(PermissionDeniedError):
    public_detail = "You can't decide this request: it needs another person holding the approving permission."


class NothingPending(ValidationError):
    public_detail = "There is no request waiting for a decision on this document."


class AwaitingApproval(ValidationError):
    public_detail = "This document is waiting for an approval decision. Decide or withdraw it first."


class ArchivedDocument(ValidationError):
    public_detail = "Archived documents can't be revised."


class BadSuitability(ValidationError):
    public_detail = "That suitability code doesn't belong to the target state (S0 WIP; S1-S4 Shared; A1-A9 or CR Published)."


class NeedsApprover(PermissionDeniedError):
    public_detail = "Archiving needs the cde.approve permission."


class NeedsTransition(PermissionDeniedError):
    public_detail = "Changing a document's state needs the cde.transition permission."


def now() -> datetime:
    return datetime.now(UTC)


def link_of(doc: CdeDocument) -> str:
    return f"/cde?project={doc.project_id}&id={doc.id}"


# --- naming conventions -------------------------------------------------------------------------


async def convention_of(db: AsyncSession, project_id: int) -> tuple[dict[str, Any], bool]:
    """The project's convention, and whether it is the default."""
    stored = await db.get(CdeNamingConvention, project_id)
    if stored is None:
        return copy.deepcopy(DEFAULT_CONVENTION), True
    return {
        "separator": stored.separator,
        "fields": stored.fields,
        "require_share_approval": stored.require_share_approval,
    }, False


async def save_convention(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    stored = await db.get(CdeNamingConvention, project_id)
    if stored is None:
        db.add(CdeNamingConvention(project_id=project_id, **values))
    else:
        stored.separator = values["separator"]
        stored.fields = values["fields"]
        stored.require_share_approval = values["require_share_approval"]
    await db.commit()


# --- visibility ---------------------------------------------------------------------------------


def is_external(user: dict[str, Any], held: frozenset[str]) -> bool:
    """Portal users reach a project only through its client team, without ``projects.read``."""
    return not user.get("is_superuser") and ProjectPermissionName.READ.value not in held


def visible(user: dict[str, Any], held: frozenset[str]) -> Any:
    """A filter for the documents this caller may see."""
    if is_external(user, held):
        return CdeDocument.state == CdeState.PUBLISHED.value
    if user.get("is_superuser") or P.REVIEW.value in held:
        return true()
    return or_(CdeDocument.state != CdeState.WIP.value, CdeDocument.created_by_id == user["id"])


def can_edit_wip(doc: CdeDocument, user: dict[str, Any], held: frozenset[str]) -> bool:
    return bool(user.get("is_superuser")) or doc.created_by_id == user["id"] or P.REVIEW.value in held


def awaiting(user: dict[str, Any], held: frozenset[str]) -> Any:
    """A filter for requests this caller may decide."""
    gates = []
    if P.REVIEW.value in held:
        gates.append(CdeDocument.pending_state == CdeState.SHARED.value)
    if P.APPROVE.value in held:
        gates.append(CdeDocument.pending_state == CdeState.PUBLISHED.value)
    if not gates:
        return false()
    return (or_(*gates)) & (CdeDocument.requested_by_id != user["id"])


def may_decide(doc: CdeDocument, user: dict[str, Any], held: frozenset[str]) -> bool:
    if not doc.pending_state or doc.requested_by_id == user["id"]:
        return False
    needed = P.REVIEW if doc.pending_state == CdeState.SHARED else P.APPROVE
    return needed.value in held


async def readable_document(db: AsyncSession, doc_id: int, user: dict[str, Any], held: frozenset[str]) -> CdeDocument:
    doc = await db.scalar(select(CdeDocument).where(CdeDocument.id == doc_id, visible(user, held)))
    if doc is None:
        raise DocumentNotFoundError("Hidden or missing")
    return doc


def scoped(statement: Select, project_id: int, user: dict[str, Any], held: frozenset[str]) -> Select:
    return statement.where(CdeDocument.project_id == project_id, visible(user, held))


# --- revisions ----------------------------------------------------------------------------------


async def _revisions(db: AsyncSession, doc_id: int) -> list[CdeRevision]:
    rows = await db.execute(select(CdeRevision).where(CdeRevision.document_id == doc_id).order_by(CdeRevision.id))
    return list(rows.scalars())


def next_code(existing: list[str], series: str) -> str:
    """P01 -> P02; the first C revision is C01."""
    numbers = [int(c[1:]) for c in existing if c.startswith(series) and c[1:].isdigit()]
    return f"{series}{(max(numbers) if numbers else 0) + 1:02d}"


async def _add_revision(
    db: AsyncSession,
    doc: CdeDocument,
    code: str,
    file_id: int | None,
    user_id: int,
    comment: str | None,
) -> CdeRevision:
    if doc.current_revision_id:
        previous = await db.get(CdeRevision, doc.current_revision_id)
        if previous is not None:
            previous.superseded = True
    revision = CdeRevision(
        document_id=doc.id,
        code=code,
        state=doc.state,
        suitability=doc.suitability,
        file_id=file_id,
        comment=comment,
        created_by_id=user_id,
    )
    db.add(revision)
    await db.flush()
    doc.revision = code
    doc.current_revision_id = revision.id
    return revision


async def register(
    db: AsyncSession,
    *,
    project_id: int,
    name: str,
    fields: dict[str, str],
    title: str,
    description: str | None,
    stored: StoredFile,
    user: dict[str, Any],
) -> CdeDocument:
    doc = CdeDocument(
        project_id=project_id,
        name=name,
        title=title,
        fields=fields,
        description=description,
        created_by_id=user["id"],
    )
    db.add(doc)
    db.add(stored)
    await db.flush()
    stored.entity_id = doc.id
    await _add_revision(db, doc, "P01", stored.id, user["id"], "First issue")
    await record_transition(db, ENTITY, doc.id, None, CdeState.WIP.value, user["id"], "Registered at P01 (S0)")
    await db.commit()
    return doc


def check_revisable(doc: CdeDocument, user: dict[str, Any], held: frozenset[str]) -> None:
    if doc.state == CdeState.ARCHIVED:
        raise ArchivedDocument(str(doc.id))
    if doc.pending_state:
        raise AwaitingApproval(str(doc.id))
    if doc.state == CdeState.WIP and not can_edit_wip(doc, user, held):
        raise NotYours(str(doc.id))


async def new_revision(
    db: AsyncSession, doc: CdeDocument, stored: StoredFile, user: dict[str, Any], held: frozenset[str], comment: str | None
) -> CdeRevision:
    check_revisable(doc, user, held)
    codes = [r.code for r in await _revisions(db, doc.id)]
    code = next_code(codes, "P")
    previous_state = doc.state
    doc.state, doc.suitability = CdeState.WIP.value, "S0"
    db.add(stored)
    await db.flush()
    revision = await _add_revision(db, doc, code, stored.id, user["id"], comment)
    note = f"New revision {code} supersedes {codes[-1] if codes else '-'}" + (f": {comment}" if comment else "")
    await record_transition(db, ENTITY, doc.id, previous_state, CdeState.WIP.value, user["id"], note)
    await db.commit()
    return revision


# --- transitions --------------------------------------------------------------------------------


def _check_suitability(target: str, code: str | None, current: str) -> str:
    if target == CdeState.ARCHIVED:
        return current
    if target == CdeState.WIP:
        code = code or "S0"
    allowed = SUITABILITY[target]
    if not code or code.upper() not in allowed:
        raise BadSuitability(f"{target}: {code}")
    return code.upper()


async def _holders(db: AsyncSession, permission: str) -> list[int]:
    rows = await db.execute(
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_name == permission)
        .distinct()
    )
    return list(rows.scalars())


async def _apply(db: AsyncSession, doc: CdeDocument, target: str, suitability: str, actor_id: int, note: str | None) -> None:
    previous = doc.state
    doc.state, doc.suitability = target, suitability
    if target == CdeState.PUBLISHED:
        codes = [r.code for r in await _revisions(db, doc.id)]
        current = await db.get(CdeRevision, doc.current_revision_id) if doc.current_revision_id else None
        await _add_revision(db, doc, next_code(codes, "C"), current.file_id if current else None, actor_id, note)
    elif doc.current_revision_id:
        current = await db.get(CdeRevision, doc.current_revision_id)
        if current is not None:
            current.state, current.suitability = target, suitability
    await record_transition(db, ENTITY, doc.id, previous, target, actor_id, f"{suitability} · {note}" if note else suitability)


async def change_status(
    db: AsyncSession,
    doc: CdeDocument,
    user: dict[str, Any],
    held: frozenset[str],
    *,
    state: str | None,
    suitability: str | None,
    decision: str | None,
    comment: str | None,
) -> None:
    if decision:
        await _decide(db, doc, user, held, decision, comment)
        await db.commit()
        return
    assert state is not None
    if P.TRANSITION.value not in held:
        raise NeedsTransition(str(doc.id))
    if doc.pending_state:
        raise AwaitingApproval(str(doc.id))
    assert_transition(FLOW, doc.state, state)
    if doc.state == CdeState.WIP and not can_edit_wip(doc, user, held):
        raise NotYours(str(doc.id))
    code = _check_suitability(state, suitability, doc.suitability)
    needs_approval = state == CdeState.PUBLISHED or (
        state == CdeState.SHARED and (await convention_of(db, doc.project_id))[0]["require_share_approval"]
    )
    if state == CdeState.ARCHIVED and P.APPROVE.value not in held:
        raise NeedsApprover(str(doc.id))
    if not needs_approval:
        await _apply(db, doc, state, code, user["id"], comment)
        await db.commit()
        return

    doc.pending_state, doc.pending_suitability = state, code
    doc.requested_by_id, doc.requested_at, doc.request_comment = user["id"], now(), comment
    await record_transition(
        db, ENTITY, doc.id, doc.state, f"{state}_requested", user["id"], f"{code} · {comment}" if comment else code
    )
    gate = P.REVIEW if state == CdeState.SHARED else P.APPROVE
    verb = "share" if state == CdeState.SHARED else "publish"
    await notify(
        db,
        await _holders(db, gate.value),
        Category.APPROVAL,
        f"Approve to {verb} {doc.name} {doc.revision} as {code}",
        body=f"{doc.title}" + (f"\n{comment}" if comment else ""),
        link=link_of(doc),
        entity=(ENTITY, doc.id),
        actor_id=user["id"],
    )
    await db.commit()


async def _decide(
    db: AsyncSession, doc: CdeDocument, user: dict[str, Any], held: frozenset[str], decision: str, comment: str | None
) -> None:
    if not doc.pending_state:
        raise NothingPending(str(doc.id))
    if not may_decide(doc, user, held):
        raise CannotDecide(str(doc.id))
    target, code, requester = doc.pending_state, doc.pending_suitability or "", doc.requested_by_id
    doc.pending_state = doc.pending_suitability = doc.requested_by_id = doc.requested_at = doc.request_comment = None
    if decision == "approve":
        await _apply(db, doc, target, code, user["id"], f"Approved: {comment}" if comment else "Approved")
        title = f"{doc.name} is now {target} ({code}, {doc.revision})"
    else:
        await record_transition(db, ENTITY, doc.id, doc.state, f"{target}_rejected", user["id"], comment or "Rejected")
        title = f"Request to make {doc.name} {target} was rejected"
    await notify(
        db,
        [requester or 0],
        Category.APPROVAL,
        title,
        body=comment,
        link=link_of(doc),
        entity=(ENTITY, doc.id),
        actor_id=user["id"],
    )


# --- reading ------------------------------------------------------------------------------------


async def names_of(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def read_many(
    db: AsyncSession, docs: list[CdeDocument], user: dict[str, Any], held: frozenset[str]
) -> list[dict[str, Any]]:
    if not docs:
        return []
    names = await names_of(db, {d.created_by_id or 0 for d in docs} | {d.requested_by_id or 0 for d in docs})
    rev_ids = [d.current_revision_id for d in docs if d.current_revision_id]
    file_names = dict(
        (
            await db.execute(
                select(CdeRevision.id, StoredFile.name)
                .join(StoredFile, StoredFile.id == CdeRevision.file_id)
                .where(CdeRevision.id.in_(rev_ids))
            )
        )
        .tuples()
        .all()
    )
    return [
        CdeDocumentRead.model_validate(d)
        .model_copy(
            update={
                "created_by_name": names.get(d.created_by_id or 0),
                "requested_by_name": names.get(d.requested_by_id or 0),
                "file_name": file_names.get(d.current_revision_id or 0),
                "can_decide": may_decide(d, user, held),
            }
        )
        .model_dump(mode="json")
        for d in docs
    ]


def revision_visible(revision: CdeRevision, user: dict[str, Any], held: frozenset[str]) -> bool:
    """External users get the published (C) revisions only."""
    return not is_external(user, held) or revision.code.startswith("C")


async def detail(db: AsyncSession, doc: CdeDocument, user: dict[str, Any], held: frozenset[str]) -> dict[str, Any]:
    base = (await read_many(db, [doc], user, held))[0]
    revisions = [r for r in await _revisions(db, doc.id) if revision_visible(r, user, held)]
    files = {
        f.id: f
        for f in (
            await db.execute(select(StoredFile).where(StoredFile.id.in_([r.file_id for r in revisions if r.file_id])))
        ).scalars()
    }
    names = await names_of(db, {r.created_by_id or 0 for r in revisions})
    read = []
    for r in reversed(revisions):
        f = files.get(r.file_id or 0)
        read.append(
            CdeRevisionRead.model_validate(r).model_copy(
                update={
                    "file_name": f.name if f else None,
                    "file_size": f.size if f else None,
                    "content_type": f.content_type if f else None,
                    "created_by_name": names.get(r.created_by_id or 0),
                }
            )
        )
    return CdeDocumentDetail(**base, revisions=read).model_dump(mode="json")


async def revision_file(
    db: AsyncSession, doc: CdeDocument, revision_id: int | None, user: dict[str, Any], held: frozenset[str]
) -> StoredFile:
    revision = await db.get(CdeRevision, revision_id or doc.current_revision_id or 0)
    if revision is None or revision.document_id != doc.id or not revision_visible(revision, user, held):
        raise DocumentNotFoundError("No such revision")
    f = await db.get(StoredFile, revision.file_id or 0)
    if f is None:
        raise DocumentNotFoundError("No file")
    return f


async def counts(db: AsyncSession, project_id: int, user: dict[str, Any], held: frozenset[str]) -> dict[str, int]:
    rows = await db.execute(scoped(select(CdeDocument.state, func.count()).group_by(CdeDocument.state), project_id, user, held))
    out = {state: n for state, n in rows.tuples().all()}
    pending = await db.scalar(
        scoped(select(func.count()).select_from(CdeDocument), project_id, user, held).where(awaiting(user, held))
    )
    return {**{s.value: out.get(s.value, 0) for s in CdeState}, "awaiting_me": pending or 0}

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..contacts.service import contact_names
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .constants import DEFAULT_DUE_DAYS, ENTITY, FLOW, RESPONSE_ENTITY, Party, RfiStatus
from .models import Rfi, RfiResponse, RfiSettings
from .schemas import Attachment, ResponseRead, RfiRead

LIVE = (RfiStatus.OPEN.value,)
"""Statuses whose due date counts: an open RFI is waiting for an answer."""


class RfiNotFoundError(ResourceNotFoundError):
    public_detail = "RFI not found."


class RfiClosedError(ValidationError):
    public_detail = "Only an open or answered RFI takes responses."


class RfiCreateStatusError(ValidationError):
    public_detail = "A new RFI starts as draft or open."


class AttachmentError(ValidationError):
    public_detail = "Attach files uploaded to this project that aren't attached elsewhere."


def link_of(rfi: Rfi) -> str:
    return f"/rfi?project={rfi.project_id}&id={rfi.id}"


async def user_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def due_days(db: AsyncSession, project_id: int) -> int:
    settings = await db.get(RfiSettings, project_id)
    return settings.default_due_days if settings else DEFAULT_DUE_DAYS


def is_overdue(rfi: Rfi, today: date | None = None) -> bool:
    return bool(rfi.status in LIVE and rfi.due_date and rfi.due_date < (today or date.today()))


def days_open(rfi: Rfi, today: date | None = None) -> int | None:
    if rfi.opened_on is None:
        return None
    end = rfi.closed_at or rfi.answered_at
    until = end.date() if end else (today or date.today())
    return max(0, (until - rfi.opened_on).days)


def overdue_filter(today: date) -> list[Any]:
    return [Rfi.status.in_(LIVE), Rfi.due_date.is_not(None), Rfi.due_date < today]


def search_filter(search: str) -> Any:
    like = f"%{search.lower()}%"
    return or_(
        func.lower(Rfi.code).like(like),
        func.lower(Rfi.subject).like(like),
        func.lower(Rfi.question).like(like),
        func.lower(func.coalesce(Rfi.location, "")).like(like),
    )


async def read_rfis(db: AsyncSession, rfis: list[Rfi]) -> list[dict[str, Any]]:
    users = await user_names(
        db, {u for r in rfis for u in (r.raised_by_id, r.addressed_to_user_id, r.bic_user_id) if u is not None}
    )
    contacts = await contact_names(
        db, {c for r in rfis for c in (r.addressed_to_contact_id, r.bic_contact_id) if c is not None}
    )
    ids = [r.id for r in rfis]
    counts: dict[int, int] = {}
    if ids:
        counts = dict(
            (
                await db.execute(
                    select(RfiResponse.rfi_id, func.count()).where(RfiResponse.rfi_id.in_(ids)).group_by(RfiResponse.rfi_id)
                )
            )
            .tuples()
            .all()
        )
    today = date.today()

    def name(table: dict[int, str], key: int | None) -> str | None:
        return table.get(key) if key else None

    return [
        RfiRead.model_validate(r)
        .model_copy(
            update={
                "raised_by_name": name(users, r.raised_by_id),
                "addressed_to_user_name": name(users, r.addressed_to_user_id),
                "bic_user_name": name(users, r.bic_user_id),
                "addressed_to_contact_name": name(contacts, r.addressed_to_contact_id),
                "bic_contact_name": name(contacts, r.bic_contact_id),
                "overdue": is_overdue(r, today),
                "days_open": days_open(r, today),
                "response_count": counts.get(r.id, 0),
            }
        )
        .model_dump(mode="json")
        for r in rfis
    ]


async def responses_of(db: AsyncSession, rfi_id: int) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(RfiResponse).where(RfiResponse.rfi_id == rfi_id).order_by(RfiResponse.id))).scalars())
    names = await user_names(db, {r.author_id for r in rows if r.author_id})
    files: dict[int, list[Attachment]] = defaultdict(list)
    if rows:
        attached = (
            await db.execute(
                select(StoredFile)
                .where(StoredFile.entity_type == RESPONSE_ENTITY, StoredFile.entity_id.in_([r.id for r in rows]))
                .order_by(StoredFile.id)
            )
        ).scalars()
        for f in attached:
            assert f.entity_id is not None
            files[f.entity_id].append(Attachment(id=f.id, name=f.name, size=f.size, revision=f.revision))
    return [
        ResponseRead(
            id=r.id,
            rfi_id=r.rfi_id,
            body=r.body,
            is_answer=r.is_answer,
            author_id=r.author_id,
            author_name=names.get(r.author_id) if r.author_id else None,
            created_at=r.created_at,
            attachments=files[r.id],
        ).model_dump(mode="json")
        for r in rows
    ]


async def get_rfi(db: AsyncSession, rfi_id: int) -> Rfi:
    rfi = await db.get(Rfi, rfi_id)
    if rfi is None:
        raise RfiNotFoundError("No such RFI")
    return rfi


async def _notify_ball(db: AsyncSession, rfi: Rfi, actor_id: int | None) -> None:
    if rfi.bic_user_id:
        await notify(
            db,
            [rfi.bic_user_id],
            Category.ASSIGNMENT,
            f"{rfi.code}: the ball is in your court",
            body=rfi.subject,
            link=link_of(rfi),
            entity=(ENTITY, rfi.id),
            actor_id=actor_id,
        )


async def _set_status(db: AsyncSession, rfi: Rfi, target: str, actor_id: int | None, note: str | None = None) -> None:
    assert_transition(FLOW, rfi.status, target)
    await record_transition(db, ENTITY, rfi.id, rfi.status, target, actor_id, note)
    now = datetime.now(UTC)
    if target == RfiStatus.OPEN:
        rfi.opened_on = rfi.opened_on or date.today()
        rfi.answered_at = None
        rfi.closed_at = None
    elif target == RfiStatus.ANSWERED:
        rfi.answered_at = now
    elif target == RfiStatus.CLOSED:
        rfi.closed_at = now
    rfi.status = target


def _hand_to_addressee(rfi: Rfi) -> None:
    """On issue, the ball goes to whoever the RFI is addressed to, unless someone was named."""
    if not rfi.ball_in_court:
        rfi.ball_in_court = Party.DESIGNER.value
    if not rfi.bic_user_id and not rfi.bic_contact_id:
        rfi.bic_user_id = rfi.addressed_to_user_id
        rfi.bic_contact_id = rfi.addressed_to_contact_id


async def create_rfi(db: AsyncSession, values: dict[str, Any], actor: dict[str, Any]) -> Rfi:
    status = values.pop("status", RfiStatus.DRAFT)
    if status not in (RfiStatus.DRAFT, RfiStatus.OPEN):
        raise RfiCreateStatusError(status)
    project_id = values.pop("project_id")
    if values.get("due_date") is None:
        values["due_date"] = date.today() + timedelta(days=await due_days(db, project_id))
    rfi = Rfi(
        project_id=project_id,
        code=await next_reference(db, "RFI", project_id),
        subject=values.pop("subject"),
        question=values.pop("question"),
        raised_by_id=actor["id"],
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(rfi)
    await db.flush()
    await record_transition(db, ENTITY, rfi.id, None, RfiStatus.DRAFT.value, actor["id"])
    if status == RfiStatus.OPEN:
        _hand_to_addressee(rfi)
        await _set_status(db, rfi, RfiStatus.OPEN.value, actor["id"])
        await _notify_ball(db, rfi, actor["id"])
    await db.commit()
    return rfi


async def update_rfi(db: AsyncSession, rfi: Rfi, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        setattr(rfi, key, value.value if hasattr(value, "value") else value)
    await db.commit()


async def change_status(db: AsyncSession, rfi: Rfi, changes: dict[str, Any], actor: dict[str, Any]) -> None:
    before_bic = (rfi.ball_in_court, rfi.bic_user_id, rfi.bic_contact_id)
    target = changes.get("status")
    for key in ("ball_in_court", "bic_user_id", "bic_contact_id"):
        if key in changes:
            value = changes[key]
            setattr(rfi, key, value.value if hasattr(value, "value") else value)
    if target and target != rfi.status:
        if target == RfiStatus.OPEN and rfi.status == RfiStatus.DRAFT:
            _hand_to_addressee(rfi)
        await _set_status(db, rfi, str(target), actor["id"], changes.get("note"))
        watchers = {rfi.raised_by_id, rfi.bic_user_id, rfi.addressed_to_user_id} - {None}
        await notify(
            db,
            [w for w in watchers if w],
            Category.STATUS,
            f"{rfi.code} is now {rfi.status}",
            body=rfi.subject,
            link=link_of(rfi),
            entity=(ENTITY, rfi.id),
            actor_id=actor["id"],
        )
    if (rfi.ball_in_court, rfi.bic_user_id, rfi.bic_contact_id) != before_bic and rfi.bic_user_id != before_bic[1]:
        await _notify_ball(db, rfi, actor["id"])
    await db.commit()


async def respond(
    db: AsyncSession, rfi: Rfi, body: str, is_answer: bool, attachment_ids: list[int], actor: dict[str, Any]
) -> RfiResponse:
    if rfi.status not in (RfiStatus.OPEN, RfiStatus.ANSWERED):
        raise RfiClosedError(rfi.status)
    response = RfiResponse(rfi_id=rfi.id, body=body, author_id=actor["id"], is_answer=is_answer)
    db.add(response)
    await db.flush()
    if attachment_ids:
        files = list((await db.execute(select(StoredFile).where(StoredFile.id.in_(attachment_ids)))).scalars())
        if len(files) != len(set(attachment_ids)) or any(
            f.project_id != rfi.project_id or f.entity_type is not None for f in files
        ):
            raise AttachmentError("bad attachment")
        for f in files:
            f.entity_type, f.entity_id = RESPONSE_ENTITY, response.id
    if is_answer and rfi.status == RfiStatus.OPEN:
        await _set_status(db, rfi, RfiStatus.ANSWERED.value, actor["id"], "Answered")
        rfi.ball_in_court = rfi.raised_by_party
        rfi.bic_user_id = rfi.raised_by_id
        rfi.bic_contact_id = None
    watchers = {rfi.raised_by_id, rfi.bic_user_id, rfi.addressed_to_user_id} - {None}
    await notify(
        db,
        [w for w in watchers if w],
        Category.STATUS,
        f"{rfi.code}: {'answered' if is_answer else 'new response'}",
        body=body[:280],
        link=link_of(rfi),
        entity=(ENTITY, rfi.id),
        actor_id=actor["id"],
    )
    await db.commit()
    return response


async def overdue_reminders(db: AsyncSession) -> int:
    """Notify whoever holds the ball on each overdue RFI. Returns how many reminders went out."""
    today = date.today()
    rows = (await db.execute(select(Rfi).where(*overdue_filter(today), Rfi.bic_user_id.is_not(None)))).scalars()
    count = 0
    for rfi in rows:
        assert rfi.bic_user_id is not None and rfi.due_date is not None
        late = (today - rfi.due_date).days
        await notify(
            db,
            [rfi.bic_user_id],
            Category.DUE,
            f"{rfi.code} is overdue by {late} day{'s' if late != 1 else ''}",
            body=rfi.subject,
            link=link_of(rfi),
            entity=(ENTITY, rfi.id),
        )
        count += 1
    await db.commit()
    return count

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.mail import Attachment as MailAttachment
from ...infrastructure.mail import Mail, deliver
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..contacts.service import contact_emails, contact_names, get_contact
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..tasks.models import Task
from ..tasks.service import create_task
from ..user.models import User
from .constants import FLOW, ActionStatus, Cadence, MeetingStatus
from .models import ActionItem, AgendaItem, Attendee, Meeting, MeetingSeries
from .schemas import (
    ActionRead,
    AgendaItemRead,
    AttendeeRead,
    MeetingRead,
    MinutesRead,
    SeriesRead,
)

ENTITY = "meeting"
T = TypeVar("T", AgendaItem, Attendee, ActionItem)


class MeetingNotFoundError(ResourceNotFoundError):
    public_detail = "Meeting not found."


class SeriesNotFoundError(ResourceNotFoundError):
    public_detail = "Meeting series not found."


class ItemNotFoundError(ResourceNotFoundError):
    public_detail = "Not found on this meeting."


class UserNotFoundError(ResourceNotFoundError):
    public_detail = "User not found."


class AlreadyInvited(ValidationError):
    public_detail = "That person is already on the attendee list."


class AlreadyATask(ValidationError):
    public_detail = "That action already has a task."


class NotReadyToIssue(ValidationError):
    public_detail = "Mark the meeting as held before issuing its minutes."


def link_of(meeting: Meeting) -> str:
    return f"/meetings?project={meeting.project_id}&meeting={meeting.id}"


# --- lookups ------------------------------------------------------------------------------------------


async def get_meeting(db: AsyncSession, meeting_id: int) -> Meeting:
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None:
        raise MeetingNotFoundError("No such meeting")
    return meeting


async def get_series(db: AsyncSession, series_id: int) -> MeetingSeries:
    series = await db.get(MeetingSeries, series_id)
    if series is None:
        raise SeriesNotFoundError("No such series")
    return series


async def get_child(db: AsyncSession, model: type[T], meeting_id: int, item_id: int) -> T:
    item = await db.get(model, item_id)
    if item is None or item.meeting_id != meeting_id:
        raise ItemNotFoundError(f"No such {model.__name__}")
    return item


async def check_user(db: AsyncSession, user_id: int | None) -> None:
    if user_id is not None and await db.scalar(select(User.id).where(User.id == user_id, User.is_deleted.is_(False))) is None:
        raise UserNotFoundError("No such user")


async def check_person(db: AsyncSession, user_id: int | None, contact_id: int | None) -> None:
    await check_user(db, user_id)
    if contact_id is not None:
        await get_contact(db, contact_id)


async def user_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def user_emails(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.email).where(User.id.in_(ids), User.is_deleted.is_(False)))
    return dict(rows.tuples().all())


# --- reading ------------------------------------------------------------------------------------------


def add_cadence(day: date, cadence: str) -> date:
    if cadence == Cadence.WEEKLY:
        return day + timedelta(days=7)
    if cadence == Cadence.FORTNIGHTLY:
        return day + timedelta(days=14)
    month = day.month % 12 + 1
    year = day.year + (1 if day.month == 12 else 0)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


async def read_series(db: AsyncSession, rows: list[MeetingSeries]) -> list[dict[str, Any]]:
    ids = [s.id for s in rows]
    stats: dict[int, tuple[int, datetime | None]] = {}
    if ids:
        result = await db.execute(
            select(Meeting.series_id, func.count(), func.max(Meeting.starts_at))
            .where(Meeting.series_id.in_(ids))
            .group_by(Meeting.series_id)
        )
        stats = {sid: (n, last) for sid, n, last in result.tuples().all() if sid is not None}
    out = []
    for s in rows:
        count, last = stats.get(s.id, (0, None))
        out.append(
            SeriesRead.model_validate(s)
            .model_copy(update={"meeting_count": count, "next_date": add_cadence(last.date(), s.cadence) if last else None})
            .model_dump(mode="json")
        )
    return out


async def read_meetings(db: AsyncSession, meetings: list[Meeting]) -> list[dict[str, Any]]:
    ids = [m.id for m in meetings]
    series_ids = {m.series_id for m in meetings if m.series_id}
    series = (
        dict(
            (await db.execute(select(MeetingSeries.id, MeetingSeries.name).where(MeetingSeries.id.in_(series_ids))))
            .tuples()
            .all()
        )
        if series_ids
        else {}
    )
    attendees: dict[int, int] = {}
    actions: dict[int, int] = {}
    if ids:
        attendees = dict(
            (
                await db.execute(
                    select(Attendee.meeting_id, func.count()).where(Attendee.meeting_id.in_(ids)).group_by(Attendee.meeting_id)
                )
            )
            .tuples()
            .all()
        )
        actions = dict(
            (
                await db.execute(
                    select(ActionItem.meeting_id, func.count())
                    .where(ActionItem.meeting_id.in_(ids), ActionItem.status == ActionStatus.OPEN.value)
                    .group_by(ActionItem.meeting_id)
                )
            )
            .tuples()
            .all()
        )
    return [
        MeetingRead.model_validate(m)
        .model_copy(
            update={
                "series_name": series.get(m.series_id) if m.series_id else None,
                "attendee_count": attendees.get(m.id, 0),
                "open_actions": actions.get(m.id, 0),
            }
        )
        .model_dump(mode="json")
        for m in meetings
    ]


async def read_agenda(db: AsyncSession, items: list[AgendaItem]) -> list[dict[str, Any]]:
    users = await user_names(db, {i.presenter_user_id for i in items if i.presenter_user_id})
    contacts = await contact_names(db, {i.presenter_contact_id for i in items if i.presenter_contact_id})
    out = []
    for number, item in enumerate(sorted(items, key=lambda i: (i.position, i.id)), start=1):
        presenter = (
            users.get(item.presenter_user_id)
            if item.presenter_user_id
            else contacts.get(item.presenter_contact_id)
            if item.presenter_contact_id
            else None
        )
        out.append(
            AgendaItemRead.model_validate(item)
            .model_copy(update={"number": number, "presenter_name": presenter})
            .model_dump(mode="json")
        )
    return out


async def read_attendees(db: AsyncSession, rows: list[Attendee]) -> list[dict[str, Any]]:
    user_ids = {a.user_id for a in rows if a.user_id}
    contact_ids = {a.contact_id for a in rows if a.contact_id}
    users = (
        {
            uid: (name, email)
            for uid, name, email in (await db.execute(select(User.id, User.name, User.email).where(User.id.in_(user_ids))))
            .tuples()
            .all()
        }
        if user_ids
        else {}
    )
    names = await contact_names(db, contact_ids)
    emails = await contact_emails(db, list(contact_ids)) if contact_ids else {}
    out = []
    for a in rows:
        if a.user_id:
            name, email = users.get(a.user_id, ("", None))
        else:
            name, email = names.get(a.contact_id or 0, ""), emails.get(a.contact_id or 0)
        out.append(AttendeeRead.model_validate(a).model_copy(update={"name": name, "email": email}).model_dump(mode="json"))
    return sorted(out, key=lambda a: (a["contact_id"] is not None, a["name"].lower()))


async def read_actions(db: AsyncSession, rows: list[ActionItem]) -> list[dict[str, Any]]:
    names = await user_names(db, {a.assignee_id for a in rows if a.assignee_id})
    task_ids = {a.task_id for a in rows if a.task_id}
    tasks = (
        {
            tid: (code, status)
            for tid, code, status in (await db.execute(select(Task.id, Task.code, Task.status).where(Task.id.in_(task_ids))))
            .tuples()
            .all()
        }
        if task_ids
        else {}
    )
    meeting_ids = {a.meeting_id for a in rows}
    codes = (
        dict((await db.execute(select(Meeting.id, Meeting.code).where(Meeting.id.in_(meeting_ids)))).tuples().all())
        if meeting_ids
        else {}
    )
    today = date.today()
    out = []
    for a in rows:
        code, status = tasks.get(a.task_id or 0, (None, None))
        out.append(
            ActionRead.model_validate(a)
            .model_copy(
                update={
                    "meeting_code": codes.get(a.meeting_id),
                    "assignee_name": names.get(a.assignee_id) if a.assignee_id else None,
                    "task_code": code,
                    "task_status": status,
                    "overdue": bool(a.due_date and a.due_date < today and a.status == ActionStatus.OPEN),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def children(db: AsyncSession, model: type[T], meeting_id: int) -> list[T]:
    return list((await db.execute(select(model).where(model.meeting_id == meeting_id).order_by(model.id))).scalars())


async def detail(db: AsyncSession, meeting: Meeting) -> dict[str, Any]:
    base = (await read_meetings(db, [meeting]))[0]
    return {
        **base,
        "agenda": await read_agenda(db, await children(db, AgendaItem, meeting.id)),
        "attendees": await read_attendees(db, await children(db, Attendee, meeting.id)),
        "actions": await read_actions(db, await children(db, ActionItem, meeting.id)),
    }


# --- writing ------------------------------------------------------------------------------------------


async def create_meeting(db: AsyncSession, values: dict[str, Any], user_id: int) -> Meeting:
    series = None
    if values.get("series_id"):
        series = await get_series(db, values["series_id"])
        if series.project_id != values["project_id"]:
            raise SeriesNotFoundError("Series belongs to another project")
    title = values.get("title") or (series.name if series else None)
    if not title:
        raise ValidationError("Give the meeting a title.")
    meeting = Meeting(
        project_id=values["project_id"],
        code=await next_reference(db, "MTG", values["project_id"]),
        title=title,
        starts_at=values["starts_at"],
        series_id=series.id if series else None,
        duration_minutes=values.get("duration_minutes") or (series.duration_minutes if series else 60),
        location=values.get("location") or (series.location if series else None),
        online_link=values.get("online_link") or (series.online_link if series else None),
        created_by_id=user_id,
    )
    db.add(meeting)
    await db.flush()
    if series and values.get("copy_template", True):
        for position, item in enumerate(series.agenda_template):
            db.add(
                AgendaItem(
                    meeting_id=meeting.id,
                    title=str(item.get("title", ""))[:300] or "Item",
                    position=position,
                    duration_minutes=item.get("duration_minutes"),
                )
            )
        seen: set[tuple[int | None, int | None]] = set()
        for person in series.default_attendees:
            key = (person.get("user_id"), person.get("contact_id"))
            if key in seen or key == (None, None):
                continue
            seen.add(key)
            db.add(Attendee(meeting_id=meeting.id, user_id=key[0], contact_id=key[1]))
    await record_transition(db, ENTITY, meeting.id, None, meeting.status, user_id)
    await db.commit()
    return meeting


async def change_status(db: AsyncSession, meeting: Meeting, target: str, user_id: int, note: str | None = None) -> None:
    assert_transition(FLOW, meeting.status, target)
    await record_transition(db, ENTITY, meeting.id, meeting.status, target, user_id, note)
    meeting.status = target
    if target != MeetingStatus.MINUTES_ISSUED:
        meeting.issued_at = None


async def add_attendee(db: AsyncSession, meeting: Meeting, values: dict[str, Any]) -> Attendee:
    await check_person(db, values.get("user_id"), values.get("contact_id"))
    clash = await db.scalar(
        select(Attendee.id).where(
            Attendee.meeting_id == meeting.id,
            Attendee.user_id == values["user_id"] if values.get("user_id") else Attendee.contact_id == values["contact_id"],
        )
    )
    if clash:
        raise AlreadyInvited("duplicate attendee")
    attendee = Attendee(meeting_id=meeting.id, **values)
    db.add(attendee)
    await db.commit()
    return attendee


async def _notify_assignee(db: AsyncSession, meeting: Meeting, action: ActionItem, actor_id: int) -> None:
    if action.assignee_id:
        await notify(
            db,
            [action.assignee_id],
            Category.ASSIGNMENT,
            f"{meeting.code} action: {action.description[:200]}",
            body=f"From {meeting.title}" + (f", due {action.due_date.isoformat()}" if action.due_date else ""),
            link=link_of(meeting),
            entity=(ENTITY, meeting.id),
            actor_id=actor_id,
        )


async def _check_agenda_item(db: AsyncSession, meeting: Meeting, agenda_item_id: int | None) -> None:
    if agenda_item_id is not None:
        await get_child(db, AgendaItem, meeting.id, agenda_item_id)


async def add_action(db: AsyncSession, meeting: Meeting, values: dict[str, Any], actor_id: int) -> ActionItem:
    await check_user(db, values.get("assignee_id"))
    await _check_agenda_item(db, meeting, values.get("agenda_item_id"))
    action = ActionItem(meeting_id=meeting.id, **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()})
    db.add(action)
    await db.flush()
    await _notify_assignee(db, meeting, action, actor_id)
    await db.commit()
    return action


async def update_action(db: AsyncSession, meeting: Meeting, action: ActionItem, changes: dict[str, Any], actor_id: int) -> None:
    if "assignee_id" in changes:
        await check_user(db, changes["assignee_id"])
    if "agenda_item_id" in changes:
        await _check_agenda_item(db, meeting, changes["agenda_item_id"])
    before = action.assignee_id
    for key, value in changes.items():
        setattr(action, key, value.value if hasattr(value, "value") else value)
    if action.assignee_id and action.assignee_id != before:
        await _notify_assignee(db, meeting, action, actor_id)
    await db.commit()


async def action_to_task(db: AsyncSession, meeting: Meeting, action: ActionItem, actor_id: int) -> Task:
    if action.task_id is not None and await db.get(Task, action.task_id) is not None:
        raise AlreadyATask("task exists")
    description = action.description.strip()
    title = description.splitlines()[0][:300] if description else "Meeting action"
    task = await create_task(
        db,
        project_id=meeting.project_id,
        title=title,
        created_by_id=actor_id,
        entity=(ENTITY, meeting.id),
        description=f"{description}\n\nFrom {meeting.code} {meeting.title} ({meeting.starts_at.date().isoformat()}).",
        assignee_id=action.assignee_id,
        due_date=action.due_date,
        commit=False,
    )
    action.task_id = task.id
    await db.commit()
    return task


async def previous(db: AsyncSession, meeting: Meeting) -> dict[str, Any]:
    if meeting.series_id is None:
        return {"meeting": None, "agenda": [], "open_actions": []}
    earlier = select(Meeting.id).where(
        Meeting.series_id == meeting.series_id,
        Meeting.id != meeting.id,
        Meeting.starts_at <= meeting.starts_at,
        Meeting.status != MeetingStatus.CANCELLED.value,
    )
    last = await db.scalar(
        select(Meeting).where(Meeting.id.in_(earlier)).order_by(Meeting.starts_at.desc(), Meeting.id.desc()).limit(1)
    )
    if last is None:
        return {"meeting": None, "agenda": [], "open_actions": []}
    actions = list(
        (
            await db.execute(
                select(ActionItem)
                .where(ActionItem.meeting_id.in_(earlier), ActionItem.status == ActionStatus.OPEN.value)
                .order_by(ActionItem.meeting_id, ActionItem.id)
            )
        ).scalars()
    )
    return {
        "meeting": (await read_meetings(db, [last]))[0],
        "agenda": await read_agenda(db, await children(db, AgendaItem, last.id)),
        "open_actions": await read_actions(db, actions),
    }


# --- minutes ------------------------------------------------------------------------------------------


async def minutes(db: AsyncSession, meeting: Meeting) -> dict[str, Any]:
    full = await detail(db, meeting)
    project = await db.get(Project, meeting.project_id)
    assert project is not None
    base = {k: v for k, v in full.items() if k not in {"agenda", "attendees", "actions"}}
    return MinutesRead.model_validate(
        {
            "meeting": base,
            "project_code": project.code,
            "project_name": project.name,
            "present": [a for a in full["attendees"] if a["attended"]],
            "apologies": [a for a in full["attendees"] if a["invited"] and not a["attended"]],
            "agenda": full["agenda"],
            "actions": full["actions"],
        }
    ).model_dump(mode="json")


def _when(meeting: dict[str, Any]) -> str:
    starts = datetime.fromisoformat(meeting["starts_at"])
    return f"{starts:%d %b %Y %H:%M} ({meeting['duration_minutes']} min)"


def minutes_document(m: dict[str, Any]) -> Document:
    meeting = m["meeting"]
    doc = Document(
        title=f"Minutes {meeting['code']}: {meeting['title']}",
        subtitle=f"{m['project_name']} · {m['project_code']}",
        footer=f"{m['project_code']} {meeting['code']} minutes",
    )
    pairs: list[tuple[str, Any]] = [("Date", _when(meeting))]
    if meeting.get("location"):
        pairs.append(("Location", meeting["location"]))
    if meeting.get("online_link"):
        pairs.append(("Online", meeting["online_link"]))
    if meeting.get("series_name"):
        pairs.append(("Series", meeting["series_name"]))
    pairs.append(("Status", meeting["status"].replace("_", " ").capitalize()))
    pairs.append(("Present", ", ".join(a["name"] for a in m["present"]) or "-"))
    if m["apologies"]:
        pairs.append(("Apologies", ", ".join(a["name"] for a in m["apologies"])))
    doc.fields(pairs)
    if meeting.get("minutes"):
        doc.heading("Summary")
        doc.paragraph(meeting["minutes"])
    doc.heading("Agenda and discussion")
    if m["agenda"]:
        rows = [
            [
                item["number"],
                item["title"] + (f"\n{item['presenter_name']}" if item.get("presenter_name") else ""),
                item.get("notes") or "",
                item.get("decisions") or "",
            ]
            for item in m["agenda"]
        ]
        doc.table(["No.", "Item", "Discussion", "Decisions"], rows, widths=[0.06, 0.26, 0.38, 0.30])
    else:
        doc.paragraph("No agenda items.")
    doc.heading("Actions")
    if m["actions"]:
        rows = [
            [
                i,
                a["description"],
                a.get("assignee_name") or "",
                a.get("due_date") or "",
                a["status"].capitalize() + (f" ({a['task_code']})" if a.get("task_code") else ""),
            ]
            for i, a in enumerate(m["actions"], start=1)
        ]
        doc.table(["No.", "Action", "Owner", "Due", "Status"], rows, widths=[0.06, 0.5, 0.18, 0.12, 0.14])
    else:
        doc.paragraph("No actions.")
    return doc


async def minutes_pdf(db: AsyncSession, meeting: Meeting) -> bytes:
    return render_pdf(minutes_document(await minutes(db, meeting)))


def pdf_name(meeting: Meeting) -> str:
    return f"{meeting.code}-minutes.pdf"


async def issue(db: AsyncSession, meeting: Meeting, user_id: int, note: str | None = None) -> tuple[list[str], list[str]]:
    """Issue (or re-issue) the minutes and email them, with the PDF, to every attendee who has an address."""
    if meeting.status != MeetingStatus.MINUTES_ISSUED:
        if meeting.status != MeetingStatus.HELD:
            raise NotReadyToIssue(meeting.status)
        await change_status(db, meeting, MeetingStatus.MINUTES_ISSUED.value, user_id, note)
    else:
        await record_transition(db, ENTITY, meeting.id, meeting.status, meeting.status, user_id, note or "Re-issued")
    meeting.issued_at = datetime.now(UTC)
    await db.flush()
    content = await minutes(db, meeting)
    pdf = render_pdf(minutes_document(content))
    attendees = await read_attendees(db, await children(db, Attendee, meeting.id))
    emailed: list[str] = []
    missing: list[str] = []
    for a in attendees:
        email = a.get("email")
        if not email:
            missing.append(a["name"])
        elif email.lower() not in {e.lower() for e in emailed}:
            emailed.append(email)
    await db.commit()
    subject = f"Minutes {meeting.code}: {meeting.title}"
    text = "\n".join(
        [
            f"The minutes of {meeting.title} ({content['project_code']} {content['project_name']},"
            f" {meeting.starts_at:%d %b %Y}) are attached.",
            "",
            *(
                [f"Actions ({len(content['actions'])}):"]
                + [
                    f"- {a['description']}"
                    + (f" ({a['assignee_name']})" if a.get("assignee_name") else "")
                    + (f", due {a['due_date']}" if a.get("due_date") else "")
                    for a in content["actions"]
                ]
                if content["actions"]
                else []
            ),
        ]
    )
    for email in emailed:
        await deliver(
            Mail(
                to=[email], subject=subject, text=text, attachments=[MailAttachment(pdf_name(meeting), pdf, "application/pdf")]
            )
        )
    return emailed, missing

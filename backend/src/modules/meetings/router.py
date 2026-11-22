"""Mounted at /api/v1/meetings. Every route reads the project through ``projects``' visibility rule first."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from ..tasks.models import Task
from ..tasks.service import read_tasks
from . import service
from .constants import MeetingStatus
from .models import ActionItem, AgendaItem, Attendee, Meeting, MeetingSeries
from .permissions import MeetingPermissionName as P
from .schemas import (
    ActionIn,
    ActionRead,
    ActionUpdate,
    AgendaItemIn,
    AgendaItemRead,
    AgendaItemUpdate,
    AgendaOrder,
    AttendeeIn,
    AttendeeRead,
    AttendeeUpdate,
    IssueResult,
    MeetingCreate,
    MeetingDetail,
    MeetingRead,
    MeetingUpdate,
    MinutesRead,
    PreviousMeeting,
    SeriesIn,
    SeriesRead,
    SeriesUpdate,
    StatusChange,
)

router = APIRouter(tags=["Meetings"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _meeting(db: AsyncSession, meeting_id: int, user: dict[str, Any], held: frozenset[str]) -> Meeting:
    meeting = await service.get_meeting(db, meeting_id)
    await readable_project(db, meeting.project_id, user["id"], held)
    return meeting


async def _series(db: AsyncSession, series_id: int, user: dict[str, Any], held: frozenset[str]) -> MeetingSeries:
    series = await service.get_series(db, series_id)
    await readable_project(db, series.project_id, user["id"], held)
    return series


async def _detail(db: AsyncSession, meeting: Meeting) -> dict[str, Any]:
    await db.refresh(meeting)
    return await service.detail(db, meeting)


# --- series (before /{meeting_id} so the path isn't read as an id) ------------------------------------


@router.get(
    "/series/", response_model=PaginatedListResponse[SeriesRead], summary="List Meeting Series", dependencies=perm(P.READ)
)
async def list_series(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    include_inactive: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [MeetingSeries.project_id == project_id]
    if not include_inactive:
        where.append(MeetingSeries.active.is_(True))
    total = await db.scalar(select(func.count()).select_from(MeetingSeries).where(*where))
    rows = (
        await db.execute(
            select(MeetingSeries)
            .where(*where)
            .order_by(MeetingSeries.name)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_series(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/series/", response_model=SeriesRead, status_code=201, summary="Create a Meeting Series", dependencies=perm(P.CREATE)
)
async def create_series(values: SeriesIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    for person in values.default_attendees:
        await service.check_person(db, person.user_id, person.contact_id)
    series = MeetingSeries(
        **values.model_dump(exclude={"agenda_template", "default_attendees"}, mode="json"),
        agenda_template=[t.model_dump(mode="json") for t in values.agenda_template],
        default_attendees=[a.model_dump(mode="json", exclude_none=True) for a in values.default_attendees],
    )
    db.add(series)
    await db.commit()
    return (await service.read_series(db, [series]))[0]


@router.get("/series/{series_id}", response_model=SeriesRead, summary="Get a Meeting Series", dependencies=perm(P.READ))
async def get_series(series_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_series(db, [await _series(db, series_id, user, held)]))[0]


@router.patch("/series/{series_id}", response_model=SeriesRead, summary="Update a Meeting Series", dependencies=perm(P.UPDATE))
async def update_series(
    series_id: Id, values: SeriesUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    series = await _series(db, series_id, user, held)
    changes = values.model_dump(exclude_unset=True, mode="json")
    if values.default_attendees is not None:
        for person in values.default_attendees:
            await service.check_person(db, person.user_id, person.contact_id)
        changes["default_attendees"] = [a.model_dump(mode="json", exclude_none=True) for a in values.default_attendees]
    for key, value in changes.items():
        if value is None and key in {"name", "cadence", "duration_minutes", "agenda_template", "default_attendees", "active"}:
            continue
        setattr(series, key, value)
    await db.commit()
    return (await service.read_series(db, [series]))[0]


@router.delete(
    "/series/{series_id}",
    summary="Delete a Meeting Series",
    description="Its meetings stay, outside any series.",
    dependencies=perm(P.DELETE),
)
async def delete_series(
    series_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await db.delete(await _series(db, series_id, user, held))
    await db.commit()
    return {"message": "Series deleted"}


# --- meetings -----------------------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedListResponse[MeetingRead],
    summary="List Meetings",
    description="A project's meetings, newest first. Filter by series, status or title.",
    dependencies=perm(P.READ),
)
async def list_meetings(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    series_id: Annotated[int | None, Query(ge=1)] = None,
    status: MeetingStatus | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Meeting.project_id == project_id]
    if series_id:
        where.append(Meeting.series_id == series_id)
    if status:
        where.append(Meeting.status == status.value)
    if search:
        where.append(func.lower(Meeting.title + " " + Meeting.code).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(Meeting).where(*where))
    rows = (
        await db.execute(
            select(Meeting)
            .where(*where)
            .order_by(Meeting.starts_at.desc(), Meeting.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_meetings(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=MeetingDetail,
    status_code=201,
    summary="Schedule a Meeting",
    description="In a series, the meeting starts from the series' agenda template and default attendees.",
    dependencies=perm(P.CREATE),
)
async def create_meeting(values: MeetingCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    meeting = await service.create_meeting(db, values.model_dump(), user["id"])
    return await _detail(db, meeting)


@router.get("/{meeting_id}", response_model=MeetingDetail, summary="Get a Meeting", dependencies=perm(P.READ))
async def get_meeting(meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.detail(db, await _meeting(db, meeting_id, user, held))


@router.patch("/{meeting_id}", response_model=MeetingDetail, summary="Update a Meeting", dependencies=perm(P.UPDATE))
async def update_meeting(
    meeting_id: Id, values: MeetingUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    for key, value in values.model_dump(exclude_unset=True).items():
        if value is None and key in {"title", "starts_at", "duration_minutes"}:
            continue
        setattr(meeting, key, value)
    await db.commit()
    return await _detail(db, meeting)


@router.delete("/{meeting_id}", summary="Delete a Meeting", dependencies=perm(P.DELETE))
async def delete_meeting(
    meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await db.delete(await _meeting(db, meeting_id, user, held))
    await db.commit()
    return {"message": "Meeting deleted"}


@router.post(
    "/{meeting_id}/status",
    response_model=MeetingDetail,
    summary="Change a Meeting's Status",
    description="planned → held or cancelled; held → planned; cancelled → planned. Issue minutes with `/issue`.",
    dependencies=perm(P.TRANSITION),
)
async def set_status(
    meeting_id: Id, values: StatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    if values.status == MeetingStatus.MINUTES_ISSUED:
        raise service.NotReadyToIssue("use /issue")
    await service.change_status(db, meeting, values.status.value, user["id"], values.note)
    await db.commit()
    return await _detail(db, meeting)


@router.get("/{meeting_id}/history", summary="A Meeting's Status History", dependencies=perm(P.READ))
async def history(
    meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    meeting = await _meeting(db, meeting_id, user, held)
    return await history_of(db, service.ENTITY, meeting.id)


@router.get(
    "/{meeting_id}/previous",
    response_model=PreviousMeeting,
    summary="The Series' Previous Meeting",
    description="Its agenda and minutes, and every open action from earlier meetings in the series.",
    dependencies=perm(P.READ),
)
async def previous(meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.previous(db, await _meeting(db, meeting_id, user, held))


# --- agenda -------------------------------------------------------------------------------------------


@router.post(
    "/{meeting_id}/agenda",
    response_model=AgendaItemRead,
    status_code=201,
    summary="Add an Agenda Item",
    dependencies=perm(P.UPDATE),
)
async def add_agenda_item(
    meeting_id: Id, values: AgendaItemIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    await service.check_person(db, values.presenter_user_id, values.presenter_contact_id)
    last = await db.scalar(select(func.max(AgendaItem.position)).where(AgendaItem.meeting_id == meeting.id))
    item = AgendaItem(meeting_id=meeting.id, position=(last if last is not None else -1) + 1, **values.model_dump())
    db.add(item)
    await db.commit()
    agenda = await service.read_agenda(db, await service.children(db, AgendaItem, meeting.id))
    return next(a for a in agenda if a["id"] == item.id)


@router.patch(
    "/{meeting_id}/agenda/{item_id}",
    response_model=AgendaItemRead,
    summary="Update an Agenda Item",
    dependencies=perm(P.UPDATE),
)
async def update_agenda_item(
    meeting_id: Id,
    item_id: Id,
    values: AgendaItemUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    item = await service.get_child(db, AgendaItem, meeting.id, item_id)
    changes = values.model_dump(exclude_unset=True)
    await service.check_person(db, changes.get("presenter_user_id"), changes.get("presenter_contact_id"))
    if changes.get("presenter_user_id"):
        changes["presenter_contact_id"] = None
    elif changes.get("presenter_contact_id"):
        changes["presenter_user_id"] = None
    for key, value in changes.items():
        if value is None and key == "title":
            continue
        setattr(item, key, value)
    await db.commit()
    agenda = await service.read_agenda(db, await service.children(db, AgendaItem, meeting.id))
    return next(a for a in agenda if a["id"] == item.id)


@router.put(
    "/{meeting_id}/agenda/order",
    response_model=list[AgendaItemRead],
    summary="Reorder the Agenda",
    description="`ids` in their new order; items left out keep their place after them.",
    dependencies=perm(P.UPDATE),
)
async def reorder_agenda(
    meeting_id: Id, values: AgendaOrder, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    items = await service.children(db, AgendaItem, meeting.id)
    rank = {item_id: i for i, item_id in enumerate(values.ids)}
    ordered = sorted(items, key=lambda i: (rank.get(i.id, len(rank)), i.position, i.id))
    for position, item in enumerate(ordered):
        item.position = position
    await db.commit()
    return await service.read_agenda(db, ordered)


@router.delete("/{meeting_id}/agenda/{item_id}", summary="Remove an Agenda Item", dependencies=perm(P.UPDATE))
async def delete_agenda_item(
    meeting_id: Id, item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    meeting = await _meeting(db, meeting_id, user, held)
    await db.delete(await service.get_child(db, AgendaItem, meeting.id, item_id))
    await db.commit()
    return {"message": "Agenda item removed"}


# --- attendees ----------------------------------------------------------------------------------------


@router.post(
    "/{meeting_id}/attendees",
    response_model=AttendeeRead,
    status_code=201,
    summary="Invite Someone",
    dependencies=perm(P.UPDATE),
)
async def add_attendee(
    meeting_id: Id, values: AttendeeIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    attendee = await service.add_attendee(db, meeting, values.model_dump())
    return (await service.read_attendees(db, [attendee]))[0]


@router.patch(
    "/{meeting_id}/attendees/{attendee_id}",
    response_model=AttendeeRead,
    summary="Mark Attendance",
    dependencies=perm(P.UPDATE),
)
async def update_attendee(
    meeting_id: Id,
    attendee_id: Id,
    values: AttendeeUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    attendee = await service.get_child(db, Attendee, meeting.id, attendee_id)
    for key, value in values.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(attendee, key, value)
    await db.commit()
    return (await service.read_attendees(db, [attendee]))[0]


@router.delete("/{meeting_id}/attendees/{attendee_id}", summary="Remove an Attendee", dependencies=perm(P.UPDATE))
async def delete_attendee(
    meeting_id: Id, attendee_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    meeting = await _meeting(db, meeting_id, user, held)
    await db.delete(await service.get_child(db, Attendee, meeting.id, attendee_id))
    await db.commit()
    return {"message": "Attendee removed"}


# --- actions ------------------------------------------------------------------------------------------


@router.post(
    "/{meeting_id}/actions",
    response_model=ActionRead,
    status_code=201,
    summary="Record an Action",
    description="The assignee is notified.",
    dependencies=perm(P.UPDATE),
)
async def add_action(
    meeting_id: Id, values: ActionIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    action = await service.add_action(db, meeting, values.model_dump(), user["id"])
    return (await service.read_actions(db, [action]))[0]


@router.patch(
    "/{meeting_id}/actions/{action_id}", response_model=ActionRead, summary="Update an Action", dependencies=perm(P.UPDATE)
)
async def update_action(
    meeting_id: Id, action_id: Id, values: ActionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    action = await service.get_child(db, ActionItem, meeting.id, action_id)
    changes = {
        k: v for k, v in values.model_dump(exclude_unset=True).items() if v is not None or k not in {"description", "status"}
    }
    await service.update_action(db, meeting, action, changes, user["id"])
    return (await service.read_actions(db, [action]))[0]


@router.delete("/{meeting_id}/actions/{action_id}", summary="Delete an Action", dependencies=perm(P.UPDATE))
async def delete_action(
    meeting_id: Id, action_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    meeting = await _meeting(db, meeting_id, user, held)
    await db.delete(await service.get_child(db, ActionItem, meeting.id, action_id))
    await db.commit()
    return {"message": "Action deleted"}


@router.post(
    "/{meeting_id}/actions/{action_id}/task",
    response_model=ActionRead,
    status_code=201,
    summary="Convert an Action to a Task",
    description="Creates a project task linked to the meeting, with the action's assignee and due date; needs `tasks.create`.",
    dependencies=[*perm(P.UPDATE), require_permissions("tasks.create")],
)
async def action_to_task(
    meeting_id: Id, action_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    action = await service.get_child(db, ActionItem, meeting.id, action_id)
    await service.action_to_task(db, meeting, action, user["id"])
    return (await service.read_actions(db, [action]))[0]


@router.get(
    "/{meeting_id}/tasks",
    summary="Tasks Created from a Meeting",
    dependencies=[*perm(P.READ), require_permissions("tasks.read")],
)
async def meeting_tasks(
    meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    meeting = await _meeting(db, meeting_id, user, held)
    rows = (
        await db.execute(select(Task).where(Task.entity_type == service.ENTITY, Task.entity_id == meeting.id).order_by(Task.id))
    ).scalars()
    return await read_tasks(db, list(rows))


# --- minutes ------------------------------------------------------------------------------------------


@router.get("/{meeting_id}/minutes", response_model=MinutesRead, summary="The Meeting's Minutes", dependencies=perm(P.READ))
async def minutes(meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.minutes(db, await _meeting(db, meeting_id, user, held))


@router.get(
    "/{meeting_id}/minutes.pdf",
    summary="The Minutes as PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    dependencies=perm(P.READ),
)
async def minutes_pdf(meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    meeting = await _meeting(db, meeting_id, user, held)
    pdf = await service.minutes_pdf(db, meeting)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{service.pdf_name(meeting)}"'},
    )


@router.post(
    "/{meeting_id}/issue",
    response_model=IssueResult,
    summary="Issue the Minutes",
    description="Moves a held meeting to `minutes_issued` (or re-issues) and emails the PDF to every attendee with an address.",
    dependencies=perm(P.TRANSITION),
)
async def issue(meeting_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    meeting = await _meeting(db, meeting_id, user, held)
    emailed, missing = await service.issue(db, meeting, user["id"])
    await db.refresh(meeting)
    return {"meeting": (await service.read_meetings(db, [meeting]))[0], "emailed": emailed, "no_email": missing}

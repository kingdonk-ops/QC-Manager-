from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .constants import ActionStatus, Cadence, MeetingStatus

Title = Annotated[str, Field(min_length=1, max_length=300)]
Location = Annotated[str | None, Field(max_length=300)]
Link = Annotated[str | None, Field(max_length=500)]
Mins = Annotated[int, Field(ge=0, le=1440)]


class _OnePerson(EncodableText):
    """A user or a contact: exactly one of the two."""

    user_id: int | None = Field(None, ge=1)
    contact_id: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> "_OnePerson":
        if (self.user_id is None) == (self.contact_id is None):
            raise ValueError("Give either user_id or contact_id.")
        return self


class TemplateItem(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title
    duration_minutes: Mins | None = None


class DefaultAttendee(_OnePerson):
    model_config = ConfigDict(extra="forbid")


# --- series -------------------------------------------------------------------------------------------


class SeriesIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    cadence: Cadence = Cadence.WEEKLY
    location: Location = None
    online_link: Link = None
    duration_minutes: Mins = 60
    agenda_template: list[TemplateItem] = Field(default_factory=list, max_length=100)
    default_attendees: list[DefaultAttendee] = Field(default_factory=list, max_length=200)
    active: bool = True


class SeriesUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    cadence: Cadence | None = None
    location: Location = None
    online_link: Link = None
    duration_minutes: Mins | None = None
    agenda_template: list[TemplateItem] | None = Field(None, max_length=100)
    default_attendees: list[DefaultAttendee] | None = Field(None, max_length=200)
    active: bool | None = None


class SeriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    cadence: str
    location: str | None
    online_link: str | None
    duration_minutes: int
    agenda_template: list[dict[str, Any]]
    default_attendees: list[dict[str, Any]]
    active: bool
    meeting_count: int = 0
    next_date: date | None = None
    """The last meeting's date plus the cadence, as a suggestion for the next one."""


# --- meetings -----------------------------------------------------------------------------------------


class MeetingCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    series_id: int | None = Field(None, ge=1)
    title: Title | None = Field(None, description="Defaults to the series name")
    starts_at: datetime
    duration_minutes: Mins | None = None
    location: Location = None
    online_link: Link = None
    copy_template: bool = Field(True, description="Start from the series' agenda template and default attendees")


class MeetingUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    starts_at: datetime | None = None
    duration_minutes: Mins | None = None
    location: Location = None
    online_link: Link = None
    minutes: str | None = None


class StatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: MeetingStatus
    note: Annotated[str | None, Field(max_length=1000)] = None


class AgendaItemIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title
    duration_minutes: Mins | None = None
    presenter_user_id: int | None = Field(None, ge=1)
    presenter_contact_id: int | None = Field(None, ge=1)
    notes: str | None = None
    decisions: str | None = None


class AgendaItemUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    duration_minutes: Mins | None = None
    presenter_user_id: int | None = Field(None, ge=1)
    presenter_contact_id: int | None = Field(None, ge=1)
    notes: str | None = None
    decisions: str | None = None


class AgendaOrder(EncodableText):
    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(max_length=200)


class AgendaItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int = 0
    title: str
    position: int
    duration_minutes: int | None
    presenter_user_id: int | None
    presenter_contact_id: int | None
    presenter_name: str | None = None
    notes: str | None
    decisions: str | None


class AttendeeIn(_OnePerson):
    model_config = ConfigDict(extra="forbid")

    invited: bool = True
    attended: bool = False


class AttendeeUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    invited: bool | None = None
    attended: bool | None = None


class AttendeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    contact_id: int | None
    name: str = ""
    email: str | None = None
    invited: bool
    attended: bool


class ActionIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, Field(min_length=1, max_length=5000)]
    agenda_item_id: int | None = Field(None, ge=1)
    assignee_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    status: ActionStatus = ActionStatus.OPEN


class ActionUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str | None, Field(min_length=1, max_length=5000)] = None
    agenda_item_id: int | None = Field(None, ge=1)
    assignee_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    status: ActionStatus | None = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: int
    meeting_code: str | None = None
    description: str
    agenda_item_id: int | None
    assignee_id: int | None
    assignee_name: str | None = None
    due_date: date | None
    status: str
    task_id: int | None
    task_code: str | None = None
    task_status: str | None = None
    overdue: bool = False


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    series_id: int | None
    series_name: str | None = None
    code: str
    title: str
    starts_at: datetime
    duration_minutes: int
    location: str | None
    online_link: str | None
    status: str
    minutes: str | None
    issued_at: datetime | None
    created_at: datetime | None = None
    attendee_count: int = 0
    open_actions: int = 0


class MeetingDetail(MeetingRead):
    agenda: list[AgendaItemRead] = Field(default_factory=list)
    attendees: list[AttendeeRead] = Field(default_factory=list)
    actions: list[ActionRead] = Field(default_factory=list)


class PreviousMeeting(BaseModel):
    """The series' previous meeting, for reference while running this one."""

    meeting: MeetingRead | None
    agenda: list[AgendaItemRead] = Field(default_factory=list)
    open_actions: list[ActionRead] = Field(default_factory=list)
    """Open actions from every earlier meeting in the series, oldest first."""


class MinutesRead(BaseModel):
    meeting: MeetingRead
    project_code: str
    project_name: str
    present: list[AttendeeRead]
    apologies: list[AttendeeRead]
    """Invited, but did not attend."""
    agenda: list[AgendaItemRead]
    actions: list[ActionRead]


class IssueResult(BaseModel):
    meeting: MeetingRead
    emailed: list[str]
    no_email: list[str] = Field(default_factory=list)

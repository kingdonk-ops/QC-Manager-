from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class MeetingSeries(Base, TimestampMixin):
    """A recurring meeting: its cadence, the agenda each meeting starts from, and who is usually invited."""

    __tablename__ = "meetings_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    cadence: Mapped[str] = mapped_column(String(20), default="weekly")
    location: Mapped[str | None] = mapped_column(String(300), default=None)
    online_link: Mapped[str | None] = mapped_column(String(500), default=None)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    agenda_template: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"title": ..., "duration_minutes": ...}]``"""
    default_attendees: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{"user_id": 3}, {"contact_id": 9}]``"""
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_project_starts", "project_id", "starts_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    series_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meetings_series.id", ondelete="SET NULL"), index=True, default=None
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str | None] = mapped_column(String(300), default=None)
    online_link: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    minutes: Mapped[str | None] = mapped_column(Text, default=None)
    """General minutes: a summary of the meeting beyond the agenda items' notes."""
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class AgendaItem(Base, TimestampMixin):
    __tablename__ = "meetings_agenda_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    presenter_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    presenter_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    decisions: Mapped[str | None] = mapped_column(Text, default=None)


class Attendee(Base, TimestampMixin):
    """Someone invited to a meeting: an app user or a contact, never both."""

    __tablename__ = "meetings_attendees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), default=None)
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), default=None)
    invited: Mapped[bool] = mapped_column(Boolean, default=True)
    attended: Mapped[bool] = mapped_column(Boolean, default=False)


class ActionItem(Base, TimestampMixin):
    __tablename__ = "meetings_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    agenda_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meetings_agenda_items.id", ondelete="SET NULL"), default=None
    )
    assignee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), default=None)

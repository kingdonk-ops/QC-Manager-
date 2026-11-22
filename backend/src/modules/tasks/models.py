from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    type: Mapped[str] = mapped_column(String(20), default="general")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    assignee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    type_fields: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    entity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    entity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TaskBoard(Base, TimestampMixin):
    """A project's board settings: WIP limit per column (0 = none)."""

    __tablename__ = "task_boards"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    wip_limits: Mapped[dict] = mapped_column(JSON, default_factory=dict)

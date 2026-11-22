from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Submittal(Base, TimestampMixin):
    __tablename__ = "submittals"
    __table_args__ = (Index("ix_submittals_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    type: Mapped[str] = mapped_column(String(30), default="shop_drawing")
    spec_section: Mapped[str | None] = mapped_column(String(50), default=None)
    entity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    """An optional linked record, e.g. a cost head or BOQ position."""
    entity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    submitted_by_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None
    )
    submitted_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    required_by: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    """The current revision number: 0 is Rev A."""
    workflow: Mapped[list] = mapped_column(JSON, default_factory=list)
    """The review steps for the next cycle: ``[{"name", "reviewer_ids", "parallel"}]``."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class SubmittalRevision(Base, TimestampMixin):
    """One review cycle: Rev A, Rev B, ... Its files are stored with entity_type ``submittal_revision``."""

    __tablename__ = "submittals_revisions"
    __table_args__ = (Index("ix_submittals_revisions_submittal", "submittal_id", "number", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    submittal_id: Mapped[int] = mapped_column(Integer, ForeignKey("submittals.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    current_step: Mapped[int | None] = mapped_column(Integer, default=None)
    """The open step's index while under review."""
    outcome: Mapped[str | None] = mapped_column(String(30), default=None)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class SubmittalReview(Base, TimestampMixin):
    """One reviewer's place in a revision's workflow, and their stamped decision."""

    __tablename__ = "submittals_reviews"
    __table_args__ = (Index("ix_submittals_reviews_reviewer_state", "reviewer_id", "state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    revision_id: Mapped[int] = mapped_column(Integer, ForeignKey("submittals_revisions.id", ondelete="CASCADE"), index=True)
    submittal_id: Mapped[int] = mapped_column(Integer, ForeignKey("submittals.id", ondelete="CASCADE"))
    step: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(100))
    reviewer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    parallel: Mapped[bool] = mapped_column(default=False)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    decision: Mapped[str | None] = mapped_column(String(30), default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

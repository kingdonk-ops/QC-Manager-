"""Client plan review: plans shared with a project's client team, decided per document."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class PlanReview(Base, TimestampMixin):
    """A package of plans (work plans, ITPs, method statements, schedules) sent to the client for review."""

    __tablename__ = "portal_plan_reviews"
    __table_args__ = (Index("ix_portal_plan_reviews_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="work_plan")
    message: Mapped[str | None] = mapped_column(Text, default=None)
    client_team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), default=None)
    """Who reviews it: set from the project's client team when shared, unless chosen."""
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    """``draft`` -> ``shared`` -> ``reviewed``; ``withdrawn`` by staff."""
    outcome: Mapped[str | None] = mapped_column(String(30), default=None)
    """Once every document is decided: ``approved``, ``approved_with_comments`` or ``rejected``."""
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    shared_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PlanReviewDocument(Base, TimestampMixin):
    __tablename__ = "portal_plan_review_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("portal_plan_reviews.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    decision: Mapped[str] = mapped_column(String(30), default="pending")
    decision_comment: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PlanReviewComment(Base, TimestampMixin):
    """A comment on the package or on one document, by the client or by staff. Both sides see every comment."""

    __tablename__ = "portal_plan_review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("portal_plan_reviews.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("portal_plan_review_documents.id", ondelete="CASCADE"))
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)

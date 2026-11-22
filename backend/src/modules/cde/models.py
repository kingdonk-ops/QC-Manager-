from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class CdeNamingConvention(Base, TimestampMixin):
    """A project's naming convention; projects without one use the default."""

    __tablename__ = "cde_naming_conventions"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    separator: Mapped[str] = mapped_column(String(1), default="-")
    fields: Mapped[list] = mapped_column(JSON, default_factory=list)
    require_share_approval: Mapped[bool] = mapped_column(default=True)


class CdeDocument(Base, TimestampMixin):
    """An information container."""

    __tablename__ = "cde_documents"
    __table_args__ = (
        Index("ix_cde_documents_project_name", "project_id", "name", unique=True),
        Index("ix_cde_documents_project_state", "project_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    """The container id built from the naming fields, e.g. ``PRJ-ORG-ZZ-XX-DR-A-0001``."""
    title: Mapped[str] = mapped_column(String(300))
    fields: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    state: Mapped[str] = mapped_column(String(20), default="wip")
    suitability: Mapped[str] = mapped_column(String(4), default="S0")
    revision: Mapped[str] = mapped_column(String(5), default="P01")
    current_revision_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    pending_state: Mapped[str | None] = mapped_column(String(20), default=None)
    """A transition waiting for approval."""
    pending_suitability: Mapped[str | None] = mapped_column(String(4), default=None)
    requested_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    request_comment: Mapped[str | None] = mapped_column(Text, default=None)


class CdeRevision(Base, TimestampMixin):
    """One revision of a container (P01, P02, C01, ...) and its file."""

    __tablename__ = "cde_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("cde_documents.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(5))
    state: Mapped[str] = mapped_column(String(20))
    suitability: Mapped[str] = mapped_column(String(4))
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    superseded: Mapped[bool] = mapped_column(default=False)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)

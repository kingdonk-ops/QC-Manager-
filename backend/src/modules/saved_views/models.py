from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class SavedView(Base, TimestampMixin):
    """One saved view of one register in one project. ``config`` is a ``SavedViewConfig`` (columns, sort, filters...)."""

    __tablename__ = "saved_views"
    __table_args__ = (Index("ix_saved_views_project_register", "project_id", "register_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    register_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    """A private view: the owner's default for the register. A project view: the project default."""
    config: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)


class SavedViewTeam(Base):
    """A team a ``team`` view is shared with."""

    __tablename__ = "saved_view_teams"

    view_id: Mapped[int] = mapped_column(Integer, ForeignKey("saved_views.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True, index=True)

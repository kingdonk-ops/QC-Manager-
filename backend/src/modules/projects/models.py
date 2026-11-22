from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import ProjectStatus


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str | None] = mapped_column(String(200), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.ACTIVE.value)
    currency: Mapped[str] = mapped_column(String(3), default="AUD")
    client_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), index=True, default=None
    )
    """Members of this team (typically external portal users) may read the project."""
    region: Mapped[str | None] = mapped_column(String(10), default=None)
    classification_standard: Mapped[str | None] = mapped_column(String(20), default=None)
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)


class ProjectMember(Base, TimestampMixin):
    """A direct grant to read one project, for someone outside its client team and without ``projects.read``.

    Written when an access request is approved or a project invite is accepted (the ``lobby`` module),
    or by a project admin. ``readable_project`` honours it like client-team membership.
    """

    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    """``access_request``, ``invite`` or ``manual``."""
    added_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class ProjectModuleOverride(Base, TimestampMixin):
    """Switches a module on or off for one project, over the system-wide switch.

    Switching on only matters where the module is on system-wide: a module switched off there
    stays off everywhere.
    """

    __tablename__ = "project_module_overrides"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    module: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)

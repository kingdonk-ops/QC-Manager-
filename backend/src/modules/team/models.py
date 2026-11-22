"""Teams, their memberships, and the map from Entra app roles to this app's roles.

A team with ``entra_group_id`` set takes its members from that Entra group: the sign-in sync and the
scheduled Graph sync add and remove them, and the API refuses to. Who leads such a team is still
decided here, through each membership's ``role``, which the syncs leave alone.

A role named in ``entra_role_mappings`` is held exactly by the users Entra assigns that app role to,
and is refreshed on every sign-in. A role with no mapping is assigned by hand, through ``/roles``.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import APP_ROLE_VALUE_MAX_LENGTH, ENTRA_OBJECT_ID_LENGTH, TEAM_NAME_MAX_LENGTH, TeamRole


class Team(Base, TimestampMixin):
    """A group of people who work together."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(TEAM_NAME_MAX_LENGTH), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    entra_group_id: Mapped[str | None] = mapped_column(String(ENTRA_OBJECT_ID_LENGTH), unique=True, index=True, default=None)

    memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership",
        back_populates="team",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
        default_factory=list,
        init=False,
    )

    def __repr__(self) -> str:
        return self.name


class TeamMembership(Base, TimestampMixin):
    """One user in one team, and their role there."""

    __tablename__ = "team_memberships"

    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default=TeamRole.MEMBER.value)

    team: Mapped["Team"] = relationship("Team", back_populates="memberships", lazy="select", init=False)

    def __repr__(self) -> str:
        return f"team={self.team_id} user={self.user_id} ({self.role})"


class EntraRoleMapping(Base, TimestampMixin):
    """Entra app role ``app_role_value`` grants this app's role ``role_id``."""

    __tablename__ = "entra_role_mappings"

    app_role_value: Mapped[str] = mapped_column(String(APP_ROLE_VALUE_MAX_LENGTH), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True)

    def __repr__(self) -> str:
        return f"{self.app_role_value} -> role {self.role_id}"

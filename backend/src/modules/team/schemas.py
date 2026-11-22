"""What teams, memberships and role mappings look like coming in and going out."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText
from .constants import APP_ROLE_VALUE_MAX_LENGTH, TEAM_NAME_MAX_LENGTH, TeamRole

TeamName = Annotated[str, Field(min_length=1, max_length=TEAM_NAME_MAX_LENGTH, examples=["QC Inspectors - Perth"])]
TeamDescription = Annotated[str | None, Field(max_length=2000)]
EntraGroupId = Annotated[
    str | None,
    Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        description="Object id of the Entra security group this team's members come from",
    ),
]


class _LinksAGroup(EncodableText):
    """Group ids are stored lower-case, the way Graph and the ``groups`` claim spell them."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("entra_group_id", check_fields=False)
    @classmethod
    def _lower_case(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class TeamCreate(_LinksAGroup):
    name: TeamName
    description: TeamDescription = None
    entra_group_id: EntraGroupId = None


class TeamUpdate(_LinksAGroup):
    """Only the fields sent are changed; ``entra_group_id: null`` unlinks the group."""

    name: TeamName | None = None
    description: TeamDescription = None
    entra_group_id: EntraGroupId = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    entra_group_id: str | None = None
    member_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TeamMemberRead(BaseModel):
    user_id: int
    name: str
    username: str
    email: str
    role: TeamRole
    joined_at: datetime | None = None


class TeamDetail(TeamRead):
    members: list[TeamMemberRead] = Field(default_factory=list)


class MyTeamRead(TeamRead):
    my_role: TeamRole


class MembershipSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    role: TeamRole = TeamRole.MEMBER


class RoleMappingSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    role_id: int = Field(ge=1)


class RoleMappingRead(BaseModel):
    app_role_value: Annotated[str, Field(max_length=APP_ROLE_VALUE_MAX_LENGTH)]
    role_id: int
    role_name: str


class SyncReport(BaseModel):
    teams_synced: int = 0
    memberships_added: int = 0
    memberships_removed: int = 0
    unknown_users_skipped: int = 0
    teams_failed: list[str] = Field(default_factory=list)

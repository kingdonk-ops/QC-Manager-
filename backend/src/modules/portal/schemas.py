from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import EncodableText
from ..user.constants import EMAIL_MAX_LENGTH, NAME_MAX_LENGTH


class InvitationCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=2, max_length=NAME_MAX_LENGTH)]
    email: Annotated[EmailStr, Field(max_length=EMAIL_MAX_LENGTH)]
    team_ids: list[int] = Field(default_factory=list, description="Teams (not Entra-linked) to place them in")


class ExternalUserRead(BaseModel):
    id: int
    name: str
    username: str
    email: str
    email_verified: bool
    activated: bool = Field(description="Has set a password from the invitation")
    created_at: datetime | None = None
    teams: list[str] = Field(default_factory=list)

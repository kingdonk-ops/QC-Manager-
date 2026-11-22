from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import EncodableText
from ..user.constants import EMAIL_MAX_LENGTH, NAME_MAX_LENGTH
from .constants import MESSAGE_MAX, REASON_MAX, Grant

Token = Annotated[str, Field(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")]


class LobbyProject(BaseModel):
    id: int
    code: str
    name: str
    client_name: str | None = None
    request_status: str | None = Field(None, description="Your latest request for it, if any")
    invite_id: int | None = Field(None, description="Set when you hold a pending invite for it")
    invite_expires_at: datetime | None = None


class AccessRequestCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = Field(None, ge=1, description="A project listed in the lobby")
    code: Annotated[str | None, Field(max_length=30, description="Or a project's exact code")] = None
    message: Annotated[str | None, Field(max_length=MESSAGE_MAX)] = None


class AccessRequestRead(BaseModel):
    id: int
    project_id: int
    project_code: str
    project_name: str
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    message: str | None
    status: str
    grant: str | None
    rejection_reason: str | None
    decided_by_name: str | None = None
    decided_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime | None
    request_again_at: datetime | None = Field(None, description="After a rejection: when a new request is allowed")


class ApproveRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    grant: Grant | None = Field(None, description="member (default for staff) or client_team")


class RejectRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str | None, Field(max_length=REASON_MAX)] = None


class ListingSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    visible: bool


class ListingRead(BaseModel):
    project_id: int
    visible: bool


class MemberRead(BaseModel):
    user_id: int
    name: str
    email: str
    account_type: str
    source: str
    via: str = Field(description="direct (project member) or client_team")
    added_at: datetime | None


class InviteCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[EmailStr, Field(max_length=EMAIL_MAX_LENGTH)]
    name: Annotated[str | None, Field(min_length=2, max_length=NAME_MAX_LENGTH)] = Field(
        None, description="For a new account: the person's name"
    )
    grant: Grant | None = Field(None, description="client_team by default for external people when the project has one")
    message: Annotated[str | None, Field(max_length=MESSAGE_MAX)] = None


class InviteRead(BaseModel):
    id: int
    project_id: int
    email: str
    grant: str
    status: str
    expired: bool
    expires_at: datetime
    created_account: bool
    invited_by_name: str | None = None
    last_sent_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime | None


class InviteCreated(InviteRead):
    link: str = Field(description="The invite link, shown once. Only its hash is stored.")


class InviteToken(EncodableText):
    model_config = ConfigDict(extra="forbid")

    token: Token


class InvitePreview(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    email_hint: str
    for_you: bool
    status: str
    expires_at: datetime


class Joined(BaseModel):
    project_id: int
    project_code: str
    project_name: str


class ProjectRef(BaseModel):
    id: int
    code: str
    name: str

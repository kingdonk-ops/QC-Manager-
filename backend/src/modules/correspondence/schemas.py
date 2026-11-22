from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import CorrespondenceStatus, CorrespondenceType, Direction

Subject = Annotated[str, Field(min_length=1, max_length=300)]
Ids = Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=50)]


class CorrespondenceCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    subject: Subject
    type: CorrespondenceType = CorrespondenceType.LETTER
    custom_type: str | None = Field(None, max_length=60, description="The type's name when `type` is `other`")
    direction: Direction = Direction.OUTGOING
    status: CorrespondenceStatus = CorrespondenceStatus.DRAFT
    body: str | None = Field(None, max_length=50000)
    external_reference: str | None = Field(None, max_length=100)
    sender_contact_id: int | None = Field(None, ge=1)
    sender_user_id: int | None = Field(None, ge=1)
    recipient_contact_ids: Ids = Field(default_factory=list)
    recipient_user_ids: Ids = Field(default_factory=list)
    date_sent: date | None = None
    date_received: date | None = None
    response_required_by: date | None = None
    in_reply_to_id: int | None = Field(None, ge=1, description="The item this one answers")


class CorrespondenceUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    subject: Subject | None = None
    type: CorrespondenceType | None = None
    custom_type: str | None = Field(None, max_length=60)
    direction: Direction | None = None
    status: CorrespondenceStatus | None = None
    status_note: str | None = Field(None, max_length=2000)
    body: str | None = Field(None, max_length=50000)
    external_reference: str | None = Field(None, max_length=100)
    sender_contact_id: int | None = Field(None, ge=1)
    sender_user_id: int | None = Field(None, ge=1)
    recipient_contact_ids: Ids | None = None
    recipient_user_ids: Ids | None = None
    date_sent: date | None = None
    date_received: date | None = None
    response_required_by: date | None = None


class Party(BaseModel):
    kind: str
    id: int
    name: str | None = None


class CorrespondenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    reference: str
    subject: str
    type: str
    custom_type: str | None
    direction: str
    status: str
    body: str | None
    external_reference: str | None
    sender_contact_id: int | None
    sender_user_id: int | None
    sender_name: str | None = None
    recipient_contact_ids: list[int]
    recipient_user_ids: list[int]
    recipients: list[Party] = Field(default_factory=list)
    date_sent: date | None
    date_received: date | None
    response_required_by: date | None
    overdue: bool = False
    in_reply_to_id: int | None
    in_reply_to_reference: str | None = None
    reply_count: int = 0
    created_by_id: int | None
    created_at: datetime | None = None


class ThreadEntry(CorrespondenceRead):
    depth: int = 0

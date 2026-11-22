from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import Purpose

Subject = Annotated[str, Field(min_length=1, max_length=300)]
Ids = Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=200)]


class TransmittalCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    subject: Subject
    purpose: Purpose = Purpose.FOR_INFORMATION
    notes: str | None = Field(None, max_length=10000)
    response_due: date | None = None
    file_ids: Ids = Field(default_factory=list)
    contact_ids: Ids = Field(default_factory=list)


class TransmittalUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    subject: Subject | None = None
    purpose: Purpose | None = None
    notes: str | None = Field(None, max_length=10000)
    response_due: date | None = None


class DocumentsAdd(EncodableText):
    model_config = ConfigDict(extra="forbid")

    file_ids: Ids = Field(min_length=1)


class RecipientsAdd(EncodableText):
    model_config = ConfigDict(extra="forbid")

    contact_ids: Ids = Field(min_length=1)


class SendRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(None, max_length=5000, description="A note added to the email")


class Acknowledge(EncodableText):
    """Record what a recipient told you. Leave a date out to keep what's recorded; `now` is the default for both."""

    model_config = ConfigDict(extra="forbid")

    recipient_id: int = Field(ge=1)
    received_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged: bool = Field(True, description="False records receipt only")
    note: str | None = Field(None, max_length=2000)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int | None
    name: str
    revision: int
    category: str
    copies: int
    is_latest: bool = True
    latest_file_id: int | None = None
    latest_revision: int | None = None


class RecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    name: str
    email: str | None
    sent_at: datetime | None
    received_at: datetime | None
    acknowledged_at: datetime | None
    acknowledgement_note: str | None
    delivery: str = "pending"
    """pending, sent, no_email, received or acknowledged."""


class RevisionWarning(BaseModel):
    document_id: int
    file_id: int | None
    name: str
    revision: int
    latest_file_id: int | None
    latest_revision: int | None
    message: str


class TransmittalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    subject: str
    purpose: str
    notes: str | None
    status: str
    response_due: date | None
    sent_at: datetime | None
    sent_by_id: int | None
    created_by_id: int | None
    created_at: datetime | None = None
    document_count: int = 0
    recipient_count: int = 0
    acknowledged_count: int = 0
    documents: list[DocumentRead] = Field(default_factory=list)
    recipients: list[RecipientRead] = Field(default_factory=list)
    warnings: list[RevisionWarning] = Field(default_factory=list)

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..common.schemas import EncodableText
from .constants import Category


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    title: str
    body: str | None
    link: str | None
    entity_type: str | None
    entity_id: int | None
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class PreferenceRow(BaseModel):
    category: Category
    in_app: bool
    email: bool


class PreferencesSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    preferences: list[PreferenceRow]

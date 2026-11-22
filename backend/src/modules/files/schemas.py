from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import FileCategory


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    content_type: str
    size: int
    project_id: int | None
    entity_type: str | None
    entity_id: int | None
    category: str
    tags: list[str] = Field(default_factory=list)
    revision: int
    supersedes_id: int | None
    is_latest: bool
    uploaded_by_id: int | None
    uploaded_by_name: str | None = None
    created_at: datetime | None = None


class FileUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=300)
    category: FileCategory | None = None
    tags: list[str] | None = Field(None, max_length=30)

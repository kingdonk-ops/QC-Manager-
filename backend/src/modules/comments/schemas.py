from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

EntityType = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]


class CommentCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    entity_type: EntityType
    entity_id: int = Field(ge=1)
    body: Annotated[str, Field(min_length=1, max_length=10_000)]
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)


class ReplyCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=10_000)]
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)


class CommentEdit(EncodableText):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=10_000)]


class ResolveSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    resolved: bool = True


class CommentRead(BaseModel):
    id: int
    project_id: int
    entity_type: str
    entity_id: int
    parent_id: int | None
    author_id: int | None
    author_name: str | None
    body: str
    mentions: list[int]
    attachment_ids: list[int]
    resolved: bool
    resolved_by_id: int | None
    edited: bool
    created_at: datetime | None
    replies: list["CommentRead"] = Field(default_factory=list)

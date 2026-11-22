from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

Kind = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]
Pattern = Annotated[str, Field(min_length=1, max_length=200)]
TokenName = Annotated[str, Field(max_length=40)]


class CodeEntry(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=20)]
    label: Annotated[str, Field(max_length=120)] = ""


CodeLists = dict[TokenName, Annotated[list[CodeEntry], Field(max_length=500)]]


class SchemeIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    record_kind: Kind = Field(description="What the scheme numbers: `document`, `itp`, `transmittal`, `mdr`, `rfi` ...")
    name: Annotated[str | None, Field(max_length=120)] = None
    pattern: Pattern = Field(description="Tokens: {project} {year} {seq:N} and code tokens such as {discipline} {type}")
    counter_scope: Annotated[list[TokenName], Field(max_length=10)] = []
    code_lists: CodeLists = {}
    start_value: int = Field(1, ge=1, le=10**9, description="Continue a client's existing sequence")
    active: bool = True


class SchemeUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(max_length=120)] = None
    pattern: Pattern | None = None
    counter_scope: Annotated[list[TokenName] | None, Field(max_length=10)] = None
    code_lists: CodeLists | None = None
    start_value: int | None = Field(None, ge=1, le=10**9)
    active: bool | None = None


class SchemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    record_kind: str
    name: str | None
    pattern: str
    counter_scope: list[str]
    code_lists: dict[str, list[CodeEntry]]
    start_value: int
    active: bool
    created_at: datetime | None = None
    allocated: int = 0


class PreviewIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    pattern: Pattern
    counter_scope: Annotated[list[TokenName], Field(max_length=10)] = []
    code_lists: CodeLists = {}
    start_value: int = Field(1, ge=1, le=10**9)
    values: dict[TokenName, Annotated[str, Field(max_length=40)]] = {}
    scheme_id: int | None = Field(None, ge=1, description="Peek at this scheme's counter for the next sequence")


class PreviewRead(BaseModel):
    number: str | None
    sequence: int | None
    scope_key: str
    errors: list[str]
    tokens: list[str]


class TokenRead(BaseModel):
    token: str
    kind: str
    description: str


class AllocateIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    values: dict[TokenName, Annotated[str, Field(max_length=40)]] = {}
    entity_type: Annotated[str | None, Field(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")] = None
    entity_id: int | None = Field(None, ge=1)


class VoidIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=300)]


class AllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    record_kind: str
    number: str
    scheme_id: int | None
    sequence: int
    values: dict[str, str]
    entity_type: str | None
    entity_id: int | None
    allocated_by_id: int | None
    voided: bool
    void_reason: str | None
    allocated_at: datetime | None = None

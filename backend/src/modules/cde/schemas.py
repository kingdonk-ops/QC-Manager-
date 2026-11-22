from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .constants import CdeState

Code = Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")]
Comment = Annotated[str | None, Field(max_length=5000)]


class CdeCodeOption(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code
    description: Annotated[str, Field(max_length=100)] = ""


class CdeNamingField(EncodableText):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]
    label: Annotated[str, Field(min_length=1, max_length=60)]
    codes: list[CdeCodeOption] = Field(
        default_factory=list, max_length=500, description="Allowed codes; empty accepts any value of the right shape"
    )
    min_length: Annotated[int, Field(ge=1, le=20)] = 1
    max_length: Annotated[int, Field(ge=1, le=20)] = 20
    charset: Literal["alnum", "alpha", "numeric"] = "alnum"

    @model_validator(mode="after")
    def _lengths(self) -> "CdeNamingField":
        if self.min_length > self.max_length:
            raise ValueError(f"{self.label}: the minimum length is above the maximum")
        return self


class CdeNamingConventionIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    separator: Literal["-", "_", "."] = "-"
    fields: list[CdeNamingField] = Field(min_length=1, max_length=12)
    require_share_approval: bool = Field(True, description="Sharing WIP needs a task-team reviewer's check")

    @model_validator(mode="after")
    def _unique_keys(self) -> "CdeNamingConventionIn":
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Each field needs its own key")
        return self


class CdeNamingConventionRead(BaseModel):
    project_id: int
    separator: str
    fields: list[CdeNamingField]
    require_share_approval: bool
    is_default: bool
    example: str


class CdeDocumentRegister(EncodableText):
    """The metadata half of a registration; the file comes alongside as multipart."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Annotated[str | None, Field(max_length=5000)] = None
    fields: dict[Annotated[str, Field(max_length=30)], Annotated[str, Field(max_length=40)]] | None = None
    name: Annotated[str | None, Field(max_length=200)] = None

    @model_validator(mode="after")
    def _fields_or_name(self) -> "CdeDocumentRegister":
        if not self.fields and not self.name:
            raise ValueError("Give the naming fields, or a name to check")
        return self


class CdeStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    state: CdeState | None = Field(None, description="Request or make this transition")
    suitability: Annotated[str | None, Field(max_length=4)] = None
    decision: Literal["approve", "reject"] | None = Field(None, description="Decide the pending request")
    comment: Comment = None

    @model_validator(mode="after")
    def _one(self) -> "CdeStatusChange":
        if (self.state is None) == (self.decision is None):
            raise ValueError("Give either a state or a decision")
        return self


class CdeRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    state: str
    suitability: str
    superseded: bool
    comment: str | None
    file_id: int | None
    file_name: str | None = None
    file_size: int | None = None
    content_type: str | None = None
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime | None = None


class CdeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    title: str
    description: str | None
    fields: dict[str, str]
    state: str
    suitability: str
    revision: str
    current_revision_id: int | None
    file_name: str | None = None
    created_by_id: int | None
    created_by_name: str | None = None
    pending_state: str | None
    pending_suitability: str | None
    requested_by_id: int | None
    requested_by_name: str | None = None
    requested_at: datetime | None
    request_comment: str | None
    can_decide: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CdeDocumentDetail(CdeDocumentRead):
    revisions: list[CdeRevisionRead] = Field(default_factory=list)


class CdeStateCounts(BaseModel):
    wip: int = 0
    shared: int = 0
    published: int = 0
    archived: int = 0
    awaiting_me: int = 0


class CdeHistoryRead(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    changed_by_name: str | None = None
    note: str | None
    changed_at: str | None

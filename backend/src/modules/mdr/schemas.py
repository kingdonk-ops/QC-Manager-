from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import IssuePurpose, MdrDecision

Ids = Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=500)]
Code = Annotated[str, Field(max_length=40)]


class SectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(max_length=40)]
    title: Annotated[str | None, Field(max_length=120)] = None
    enabled: bool = True


class DossierIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Annotated[str | None, Field(max_length=5000)] = None
    scope_node_ids: Ids = []
    scope_collection_ids: Ids = []
    sections: Annotated[list[SectionIn] | None, Field(max_length=20, description="Defaults to every section in order")] = None
    number_values: dict[Code, Code] = Field(
        default_factory=dict, description="Code token values for the project's `mdr` numbering scheme"
    )


class DossierUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    scope_node_ids: Ids | None = None
    scope_collection_ids: Ids | None = None
    sections: Annotated[list[SectionIn] | None, Field(max_length=20)] = None


class SectionRead(BaseModel):
    key: str
    title: str
    enabled: bool


class DossierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    scope_node_ids: list[int]
    scope_collection_ids: list[int]
    scope_labels: list[str] = []
    sections: list[SectionRead]
    status: str
    current_revision: str | None
    created_by_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CatalogueRead(BaseModel):
    key: str
    title: str
    providers: list[str]
    """Modules that provide records for the section (switched-off modules left out)."""
    generated: bool = False


class Finding(BaseModel):
    message: str
    reference: str | None = None
    link: str | None = None


class CheckRead(BaseModel):
    key: str
    title: str
    module: str
    blocking: bool
    status: str
    """``pass``, ``fail`` or ``not_available``."""
    findings: list[Finding]
    detail: str | None = None


class GateRead(BaseModel):
    purpose: str | None
    ready: bool
    checks: list[CheckRead]


class IssueIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    purpose: IssuePurpose
    note: Annotated[str | None, Field(max_length=2000)] = None


class SignIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = Field(description="The signer confirms the intent statement")


class DecisionIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    decision: MdrDecision
    note: Annotated[str | None, Field(max_length=2000)] = None


class HashCheckIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class HashCheckRead(BaseModel):
    match: bool
    revision_id: int | None = None
    revision: str | None = None
    kind: str | None = None
    signed: bool = False
    file_id: int | None = None


class RevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dossier_id: int
    kind: str
    revision: str | None
    status: str
    file_id: int | None
    unsigned_file_id: int | None
    sha256: str | None
    page_count: int
    gate: list[Any]
    manifest: dict[str, Any]
    note: str | None
    compiled_by_id: int | None
    compiled_by_name: str | None = None
    issued_at: datetime | None
    signed_by_id: int | None
    signed_by_name: str | None = None
    signed_at: datetime | None
    signature: dict[str, Any]
    decided_by_id: int | None
    decided_by_name: str | None = None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime | None = None

"""Request and response bodies of the quality gates and the can-proceed query."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common.schemas import EncodableText, PartialUpdate, refuse_oversized_json, within_utc_range
from .constants import AttachmentKind, Authority, GateKind
from .gate_rules import attachment_pair_error


class GateCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    kind: GateKind = GateKind.HOLD
    description: Annotated[str | None, Field(max_length=5000)] = None
    authority: Authority = Authority.QUALITY_ASSURANCE
    inspection_id: int | None = Field(None, ge=1, description="A record of the inspection register, ITP lines included")
    criterion_id: int | None = Field(None, ge=1)
    attachment_kind: AttachmentKind | None = None
    attachment_id: int | None = Field(None, ge=1)
    package_ref: Annotated[str | None, Field(max_length=100)] = None
    blocks_progress: bool | None = Field(None, description="Omitted: a hold blocks, the other kinds do not")
    approval_ref: Annotated[str | None, Field(max_length=100)] = None
    supplementary: dict[str, Any] = {}

    @model_validator(mode="after")
    def _attachment_pair(self) -> "GateCreate":
        error = attachment_pair_error(self.attachment_kind, self.attachment_id)
        if error:
            raise ValueError(error)
        return self

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any]) -> dict[str, Any]:
        refuse_oversized_json("supplementary", value)
        return value


class GateUpdate(EncodableText, PartialUpdate):
    """Any subset, while the gate is pending. The status moves only through release, waive and void."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title", "kind", "authority", "blocks_progress", "supplementary")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    kind: GateKind | None = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    authority: Authority | None = None
    inspection_id: int | None = Field(None, ge=1)
    criterion_id: int | None = Field(None, ge=1)
    attachment_kind: AttachmentKind | None = None
    attachment_id: int | None = Field(None, ge=1)
    package_ref: Annotated[str | None, Field(max_length=100)] = None
    blocks_progress: bool | None = None
    approval_ref: Annotated[str | None, Field(max_length=100)] = None
    supplementary: dict[str, Any] | None = None

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            refuse_oversized_json("supplementary", value)
        return value


class GateRelease(EncodableText):
    model_config = ConfigDict(extra="forbid")

    authority: Authority = Field(description="The level the releasing party asserts; it must meet the gate's requirement")
    justification: Annotated[str | None, Field(max_length=2000)] = None
    released_at: AwareDatetime | None = Field(None, description="Defaults to now")

    _range = field_validator("released_at")(within_utc_range)


class GateWaive(EncodableText):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A waiver needs a reason")
        return value


class QualityGateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    number: str
    kind: str
    title: str
    description: str | None
    authority: str
    inspection_id: int | None
    criterion_id: int | None
    attachment_kind: str | None
    attachment_id: int | None
    package_ref: str | None
    blocks_progress: bool
    status: str
    released_by_id: int | None
    released_level: str | None
    released_at: datetime | None
    release_justification: str | None
    release_ip: str | None
    release_digest: str | None
    waived_by_id: int | None
    waiver_reason: str | None
    approval_ref: str | None
    created_by_id: int | None
    supplementary: dict[str, Any]
    override_id: int | None = None
    override_ref: str | None = Field(None, description="Set while a dossier issue override covers this pending gate")
    created_at: datetime | None
    updated_at: datetime | None


class HoldPointRef(BaseModel):
    id: int
    code: str
    title: str


class GateProceed(BaseModel):
    """Whether work may go ahead on one entity: blocking gates oldest first (numbers and identifiers in step), and,
    for an inspection, the earlier ITP hold points that are still unreleased. Gates a dossier issue override covers are
    listed apart; they stay pending and still make the answer false, except for a dossier attachment."""

    project_id: int
    attachment_kind: str
    attachment_id: int
    can_proceed: bool
    gate_numbers: list[str]
    gate_ids: list[int]
    overridden_gate_numbers: list[str] = []
    overridden_gate_ids: list[int] = []
    hold_points: list[HoldPointRef] = []

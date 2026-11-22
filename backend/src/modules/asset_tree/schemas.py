from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import CodeUniqueness, CollectionKind, IdentifierKind, Role

Code = Annotated[str, Field(min_length=1, max_length=120)]
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


class LevelIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    key: Key
    label: Annotated[str, Field(max_length=80)]
    label_plural: Annotated[str, Field(max_length=80)]
    depth: int = 0
    allowed_parent_keys: list[str] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    code_pattern: Annotated[str | None, Field(max_length=200)] = None
    code_uniqueness: CodeUniqueness = CodeUniqueness.PER_PARENT
    display_code_template: Annotated[str | None, Field(max_length=200)] = None
    field_schema: dict[str, Any] = Field(default_factory=dict)


class LevelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    label_plural: str
    depth: int
    allowed_parent_keys: list[str]
    roles: list[str]
    code_pattern: str | None
    code_uniqueness: str
    display_code_template: str | None
    field_schema: dict[str, Any]
    pack_key: str | None


class NodeIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    level_key: Key
    code: Code
    name: Annotated[str | None, Field(max_length=300)] = None
    parent_id: int | None = None
    discipline_code: Annotated[str | None, Field(max_length=40)] = None
    wbs_code: Annotated[str | None, Field(max_length=120)] = None
    planned_start: date | None = None
    planned_finish: date | None = None
    budget_qty: Decimal | None = None
    uom: Annotated[str | None, Field(max_length=20)] = None
    budget_hours: Decimal | None = None
    latitude: float | None = None
    longitude: float | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class NodeUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(max_length=300)] = None
    discipline_code: Annotated[str | None, Field(max_length=40)] = None
    wbs_code: Annotated[str | None, Field(max_length=120)] = None
    planned_start: date | None = None
    planned_finish: date | None = None
    budget_qty: Decimal | None = None
    uom: Annotated[str | None, Field(max_length=20)] = None
    budget_hours: Decimal | None = None
    earned_qty: Decimal | None = None
    latitude: float | None = None
    longitude: float | None = None
    custom_fields: dict[str, Any] | None = None


class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    level_key: str
    code: str
    name: str | None
    parent_id: int | None
    path: str
    display_path: str
    display_code: str | None
    status: str
    discipline_code: str | None
    wbs_code: str | None
    external_source: str | None
    external_id: str | None
    planned_start: date | None
    planned_finish: date | None
    budget_qty: Decimal | None
    uom: str | None
    budget_hours: Decimal | None
    earned_qty: Decimal | None
    superseded_by: list[int]
    derived_from: list[int]
    custom_fields: dict[str, Any]
    child_count: int = 0
    item_count: int = 0


class MoveIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    parent_id: int | None


class SplitPart(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Annotated[str | None, Field(max_length=300)] = None


class SplitIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    parts: Annotated[list[SplitPart], Field(min_length=2, max_length=50)]


class MergeIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    source_ids: Annotated[list[int], Field(min_length=1, max_length=50)]


class RetireIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    superseded_by: list[int] = Field(default_factory=list)


class ItemTypeIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    key: Key
    name: Annotated[str, Field(max_length=120)]
    field_schema: dict[str, Any] = Field(default_factory=dict)
    inspectable: bool = True


class ItemTypeRead(ItemTypeIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: int
    revision: int


class ItemIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    node_id: int = Field(ge=1)
    item_type_key: Key
    tag: Code
    parent_item_id: int | None = None
    work_anchor_id: int | None = None
    spec_ref: Annotated[str | None, Field(max_length=120)] = None
    discipline: Annotated[str | None, Field(max_length=40)] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class ItemUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    tag: Code | None = None
    spec_ref: Annotated[str | None, Field(max_length=120)] = None
    discipline: Annotated[str | None, Field(max_length=40)] = None
    status: Annotated[str | None, Field(max_length=20)] = None
    custom_fields: dict[str, Any] | None = None
    notes: str | None = None


class IdentifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    value: str
    is_active: bool


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    node_id: int
    item_type_key: str
    tag: str
    parent_item_id: int | None
    work_anchor_id: int | None
    spec_ref: str | None
    discipline: str | None
    status: str
    inspectable: bool
    type_revision: int
    custom_fields: dict[str, Any]
    notes: str | None
    node_display_path: str | None = None
    identifiers: list[IdentifierRead] = Field(default_factory=list)


class IdentifierIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    kind: IdentifierKind
    value: Annotated[str, Field(min_length=1, max_length=200)]


class CollectionIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    kind: CollectionKind
    code: Annotated[str, Field(min_length=1, max_length=60)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    window_start: date | None = None
    window_end: date | None = None


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    kind: str
    code: str
    name: str
    window_start: date | None
    window_end: date | None
    node_ids: list[int] = Field(default_factory=list)


class MembersIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_ids: Annotated[list[int], Field(max_length=5000)]

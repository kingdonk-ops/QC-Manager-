from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# --- terminology ---------------------------------------------------------------------------------------

TermKey = Annotated[str, Field(pattern=r"^(level|role|noun)\.[a-z][a-z0-9_]*$", max_length=80)]


class AssetTermForms(EncodableText):
    model_config = ConfigDict(extra="forbid")

    one: Annotated[str, Field(min_length=1, max_length=80)]
    other: Annotated[str, Field(min_length=1, max_length=80)]


class AssetTermsIn(EncodableText):
    """``{"level.rsw": {"one": "Work order", "other": "Work orders"}, "noun.item": null}``; null clears an override."""

    model_config = ConfigDict(extra="forbid")

    terms: Annotated[dict[TermKey, AssetTermForms | None], Field(max_length=200)]


class AssetTermRead(BaseModel):
    key: str
    one: str
    other: str
    source: Literal["default", "level", "project"]


# --- import --------------------------------------------------------------------------------------------

Column = Annotated[str, Field(min_length=1, max_length=200)]
NodeField = Literal[
    "name",
    "discipline_code",
    "wbs_code",
    "external_id",
    "external_source",
    "planned_start",
    "planned_finish",
    "budget_qty",
    "uom",
    "budget_hours",
    "earned_qty",
]
FieldPath = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$", max_length=120)]


class TreeMode(StrEnum):
    COLUMNS = "columns"
    PATH = "path"
    PARENT_ROW = "parent_row"


class UpdateMode(StrEnum):
    UPSERT = "upsert"
    """Create what's new, update what's there (matched by level, code and parent)."""
    CREATE = "create"
    """Create what's new; leave existing nodes and items as they are."""
    UPDATE = "update"
    """Only update; a row naming something that isn't there is an error."""


class TreeItemMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_column: Column
    item_type_key: Key | None = None
    """Every row's item type, unless ``item_type_column`` names one per row (by key or name)."""
    item_type_column: Column | None = None
    fields: dict[Literal["spec_ref", "discipline", "notes"], Column] = Field(default_factory=dict)
    custom_fields: dict[FieldPath, Column] = Field(default_factory=dict)
    identifiers: dict[IdentifierKind, Column] = Field(default_factory=dict)


class TreeImportMapping(EncodableText):
    """How a spreadsheet's columns land in the breakdown. Saved as a mapping profile for reuse."""

    model_config = ConfigDict(extra="forbid")

    tree_mode: TreeMode = TreeMode.COLUMNS
    level_columns: dict[Key, Column] = Field(default_factory=dict)
    """``columns`` mode: level key → its code column."""
    path_column: Column | None = None
    path_separator: Annotated[str, Field(min_length=1, max_length=5)] = "/"
    path_levels: list[Key] = Field(default_factory=list)
    """``path`` mode: the level of each path segment, root first."""
    code_column: Column | None = None
    parent_column: Column | None = None
    level_column: Column | None = None
    """``parent_row`` mode: the node's code, its parent's code and its level (key or label)."""
    node_fields: dict[NodeField, Column] = Field(default_factory=dict)
    custom_fields: dict[FieldPath, Column] = Field(default_factory=dict)
    """``custom_fields`` path (dots for nesting) → column, set on each row's leaf node."""
    item: TreeItemMapping | None = None
    update_mode: UpdateMode = UpdateMode.UPSERT
    split_multi_values: bool = True
    """Split a leaf cell like ``101.1 and 101.3 ; 102`` into one node per value."""
    synonyms: dict[Column, list[Column]] = Field(default_factory=dict)
    """Other headers a mapped column may have in another file (``{"RSW": ["RSW No", "RSW #"]}``)."""

    @model_validator(mode="after")
    def _mode_has_its_columns(self) -> "TreeImportMapping":
        if self.tree_mode == TreeMode.COLUMNS and not self.level_columns:
            raise ValueError("Map at least one level to a column.")
        if self.tree_mode == TreeMode.PATH and not (self.path_column and self.path_levels):
            raise ValueError("Name the path column and the level of each segment.")
        if self.tree_mode == TreeMode.PARENT_ROW and not (self.code_column and self.level_column):
            raise ValueError("Name the code and level columns (and the parent column).")
        if self.item and not (self.item.item_type_key or self.item.item_type_column):
            raise ValueError("Items need an item type or an item type column.")
        return self


class TreeImportPreview(BaseModel):
    columns: list[str]
    rows: int
    sample: list[dict[str, Any]]
    mapping: TreeImportMapping
    """A first guess from the headers (or the chosen profile)."""
    missing: list[str] = Field(default_factory=list)
    """Columns the profile names that this file doesn't have."""


class TreeImportAction(BaseModel):
    line: int
    action: Literal["create", "update"]
    kind: Literal["node", "item"]
    label: str
    display: str


class TreeImportReport(BaseModel):
    dry_run: bool
    rows: int
    nodes_created: int
    nodes_updated: int
    nodes_unchanged: int
    items_created: int
    items_updated: int
    skipped: int
    errors: list[str]
    warnings: list[str]
    actions: list[TreeImportAction]
    profile: "MappingProfileRead | None" = None


class MappingProfileIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=120)]
    mapping: TreeImportMapping


class MappingProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    version: int
    mapping: dict[str, Any]
    created_by_id: int | None
    created_at: datetime | None = None


TreeImportReport.model_rebuild()

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

RegisterKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", max_length=64)]
Name = Annotated[str, Field(min_length=1, max_length=120)]
ColId = Annotated[str, Field(min_length=1, max_length=200)]
Visibility = Literal["private", "project", "team"]


class SavedViewColumn(BaseModel):
    """One column, in display order: AG Grid's column state, minus what a view doesn't keep."""

    model_config = ConfigDict(extra="ignore")

    colId: ColId  # noqa: N815  (AG Grid's own name, so the frontend can hand state straight over)
    width: Annotated[int, Field(ge=10, le=4000)] | None = None
    hide: bool | None = None
    pinned: Literal["left", "right"] | None = None
    flex: Annotated[float, Field(ge=0, le=100)] | None = None


class SavedViewSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colId: ColId  # noqa: N815
    sort: Literal["asc", "desc"]


class SavedViewConfig(BaseModel):
    """What a view restores. ``filters`` is the grid's filter model (``{colId: {filterType, type, filter...}}``).

    A column the register no longer has is skipped when the view is applied, never an error.
    """

    model_config = ConfigDict(extra="forbid")

    columns: Annotated[list[SavedViewColumn], Field(max_length=300)] = Field(default_factory=list)
    sort: Annotated[list[SavedViewSort], Field(max_length=20)] = Field(default_factory=list)
    filters: dict[ColId, Any] = Field(default_factory=dict)
    group_by: Annotated[list[ColId], Field(max_length=10)] = Field(default_factory=list)
    quick_search: Annotated[str | None, Field(max_length=200)] = None
    density: Literal["compact", "standard", "comfortable"] | None = None


class SavedViewIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    register_key: RegisterKey
    name: Name
    visibility: Visibility = "private"
    team_ids: Annotated[list[int], Field(max_length=50)] = Field(default_factory=list)
    is_default: bool = False
    config: SavedViewConfig = Field(default_factory=SavedViewConfig)


class SavedViewUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    visibility: Visibility | None = None
    team_ids: Annotated[list[int], Field(max_length=50)] | None = None
    is_default: bool | None = None
    config: SavedViewConfig | None = None


class SavedViewRead(BaseModel):
    id: int
    project_id: int
    register_key: str
    name: str
    owner_id: int
    owner_name: str | None
    visibility: str
    team_ids: list[int]
    is_default: bool
    config: dict[str, Any]
    can_edit: bool
    updated_at: datetime | None = None

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

MarkupType = Literal[
    "rect",
    "ellipse",
    "cloud",
    "arrow",
    "line",
    "polyline",
    "freehand",
    "text",
    "callout",
    "highlight",
    "stamp",
    "measure_length",
    "measure_polyline",
    "measure_area",
]
Unit = Literal["m", "mm", "cm", "km", "ft", "in"]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
Coordinate = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]


class _Body(EncodableText):
    model_config = ConfigDict(extra="forbid")


class MarkupStyle(_Body):
    color: Color = "#dc2626"
    width: Annotated[float, Field(gt=0, le=50)] = 1.5
    opacity: Annotated[float, Field(ge=0, le=1)] = 1
    font_size: Annotated[float, Field(ge=4, le=200)] = 12


# --- sets ---------------------------------------------------------------------------------------------


class MarkupSetCreate(_Body):
    file_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]


class MarkupSetUpdate(_Body):
    name: Annotated[str, Field(min_length=1, max_length=200)]


class MarkupSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    project_id: int
    name: str
    revision: int
    author_id: int | None
    author_name: str | None = None
    markup_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- markups ------------------------------------------------------------------------------------------


class MarkupCreate(_Body):
    file_id: int = Field(ge=1)
    set_id: int | None = Field(None, ge=1, description="Leave out to use your own set on this file, made if needed")
    page: int = Field(ge=1, le=100_000)
    type: MarkupType
    geometry: dict[str, Any] = Field(
        description="Boxes: `{x, y, w, h}`; callouts add `anchor: [x, y]`; lines, paths and areas: `{points: [[x, y], ...]}`. "
        "PDF units of the page at scale 1, origin top-left, y down."
    )
    style: MarkupStyle = Field(default_factory=MarkupStyle)
    text: Annotated[str | None, Field(max_length=4000)] = None


class MarkupUpdate(_Body):
    page: int | None = Field(None, ge=1, le=100_000)
    geometry: dict[str, Any] | None = None
    style: MarkupStyle | None = None
    text: Annotated[str | None, Field(max_length=4000)] = None


class MarkupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int
    file_id: int
    page: int
    type: str
    geometry: dict[str, Any]
    style: dict[str, Any]
    text: str | None
    measurement: dict[str, Any] | None
    author_id: int | None
    author_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- calibration --------------------------------------------------------------------------------------


class MarkupCalibrationSet(_Body):
    points: Annotated[list[Annotated[list[Coordinate], Field(min_length=2, max_length=2)]], Field(min_length=2, max_length=2)]
    real_distance: Annotated[float, Field(gt=0, le=1_000_000)]
    unit: Unit = "m"


class MarkupCalibrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: int
    page: int
    points: list[list[float]]
    real_distance: float
    unit: str
    meters_per_unit: float
    set_by_id: int | None
    updated_at: datetime | None = None


# --- stamps -------------------------------------------------------------------------------------------


class MarkupStampFields(_Body):
    color: Color = "#16a34a"
    include_date: bool = True
    include_author: bool = True
    position: int = 0
    note: Annotated[str | None, Field(max_length=500)] = None


class MarkupStampCreate(MarkupStampFields):
    project_id: int = Field(ge=1)
    label: Annotated[str, Field(min_length=1, max_length=60)]


class MarkupStampUpdate(MarkupStampFields):
    label: Annotated[str | None, Field(min_length=1, max_length=60)] = None


class MarkupStampRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    label: str
    color: str
    include_date: bool
    include_author: bool
    position: int
    note: str | None

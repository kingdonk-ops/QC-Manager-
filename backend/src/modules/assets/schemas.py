from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import AssetKind, ComponentStatus

Name = Annotated[str, Field(min_length=1, max_length=200)]
Short = Annotated[str | None, Field(max_length=200)]
Tiny = Annotated[str | None, Field(max_length=100)]
Measure = Annotated[float | None, Field(ge=0)]
Attributes = Annotated[dict[str, str], Field(max_length=200)]
Id = Annotated[int, Field(ge=1)]


class _Body(EncodableText):
    model_config = ConfigDict(extra="forbid")


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime | None = None


# --- facility -----------------------------------------------------------------------------------------


class AssetFacilityFields(_Body):
    description: str | None = None
    category: Short = None
    site_name: Short = None
    linear_units: Annotated[str, Field(max_length=30)] = "meters"
    area_units: Annotated[str, Field(max_length=30)] = "squaremeters"
    volume_units: Annotated[str, Field(max_length=30)] = "cubicmeters"
    area_measurement: Tiny = None
    phase: Tiny = None


class AssetFacilityCreate(AssetFacilityFields):
    name: Name


class AssetFacilityUpdate(AssetFacilityFields):
    name: Name | None = None


class AssetFacilityRead(_Read, AssetFacilityFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str


# --- floor --------------------------------------------------------------------------------------------


class AssetFloorFields(_Body):
    description: str | None = None
    category: Short = "Floor"
    elevation: float | None = None
    height: Measure = None
    position: int = 0


class AssetFloorCreate(AssetFloorFields):
    facility_id: Id
    name: Name


class AssetFloorUpdate(AssetFloorFields):
    name: Name | None = None


class AssetFloorRead(_Read, AssetFloorFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    facility_id: int
    name: str


# --- space --------------------------------------------------------------------------------------------


class AssetSpaceFields(_Body):
    description: str | None = None
    category: Short = None
    room_tag: Tiny = None
    usable_height: Measure = None
    gross_area: Measure = None
    net_area: Measure = None


class AssetSpaceCreate(AssetSpaceFields):
    floor_id: Id
    name: Name


class AssetSpaceUpdate(AssetSpaceFields):
    floor_id: Id | None = None
    name: Name | None = None


class AssetSpaceRead(_Read, AssetSpaceFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    floor_id: int
    name: str
    component_count: int = 0


# --- zone ---------------------------------------------------------------------------------------------


class AssetZoneFields(_Body):
    description: str | None = None
    category: Short = None
    space_ids: Annotated[list[int], Field(max_length=2000)] = Field(default_factory=list)


class AssetZoneCreate(AssetZoneFields):
    name: Name


class AssetZoneUpdate(AssetZoneFields):
    name: Name | None = None


class AssetZoneRead(_Read, AssetZoneFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str


# --- type ---------------------------------------------------------------------------------------------


class AssetTypeFields(_Body):
    description: str | None = None
    category: Short = None
    asset_kind: AssetKind = AssetKind.FIXED
    manufacturer_id: Id | None = None
    model_number: Short = None
    warranty_guarantor_id: Id | None = None
    warranty_duration_parts: Measure = None
    warranty_duration_labor: Measure = None
    warranty_duration_unit: Annotated[str, Field(max_length=20)] = "year"
    warranty_description: str | None = None
    replacement_cost: Annotated[Decimal | None, Field(ge=0, max_digits=14, decimal_places=2)] = None
    expected_life: Measure = None
    duration_unit: Annotated[str, Field(max_length=20)] = "year"
    nominal_length: Measure = None
    nominal_width: Measure = None
    nominal_height: Measure = None
    model_reference: Short = None
    shape: Tiny = None
    size: Tiny = None
    color: Tiny = None
    finish: Tiny = None
    grade: Tiny = None
    material: Tiny = None
    attributes: Attributes = Field(default_factory=dict)


class AssetTypeCreate(AssetTypeFields):
    name: Name


class AssetTypeUpdate(AssetTypeFields):
    name: Name | None = None


class AssetTypeRead(_Read, AssetTypeFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str
    manufacturer_name: str | None = None
    warranty_guarantor_name: str | None = None
    component_count: int = 0


# --- component ----------------------------------------------------------------------------------------


class AssetComponentFields(_Body):
    description: str | None = None
    type_id: Id | None = None
    space_id: Id | None = None
    serial_number: Short = None
    installation_date: date | None = None
    warranty_start_date: date | None = None
    tag_number: Short = None
    bar_code: Short = None
    asset_identifier: Short = None
    attributes: Attributes = Field(default_factory=dict)


class AssetComponentCreate(AssetComponentFields):
    name: Name
    status: ComponentStatus = ComponentStatus.PLANNED
    system_ids: Annotated[list[int], Field(max_length=100)] = Field(default_factory=list)


class AssetComponentUpdate(AssetComponentFields):
    name: Name | None = None
    status: ComponentStatus | None = None
    status_note: Annotated[str | None, Field(max_length=500)] = None
    system_ids: Annotated[list[int] | None, Field(max_length=100)] = None


class AssetComponentRead(_Read, AssetComponentFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str
    status: str
    type_name: str | None = None
    space_name: str | None = None
    floor_id: int | None = None
    floor_name: str | None = None
    facility_id: int | None = None
    system_ids: list[int] = Field(default_factory=list)
    document_count: int = 0


class AssetComponentBulk(_Body):
    names: Annotated[list[Annotated[str, Field(min_length=1, max_length=200)]], Field(min_length=1, max_length=1000)]
    type_id: Id | None = None
    space_id: Id | None = None
    status: ComponentStatus = ComponentStatus.PLANNED


class AssetBulkResult(BaseModel):
    created: list[AssetComponentRead]
    skipped: list[str] = Field(default_factory=list, description="Names already in the register")


# --- system -------------------------------------------------------------------------------------------


class AssetSystemFields(_Body):
    description: str | None = None
    category: Short = None


class AssetSystemCreate(AssetSystemFields):
    name: Name
    component_ids: Annotated[list[int], Field(max_length=5000)] = Field(default_factory=list)


class AssetSystemUpdate(AssetSystemFields):
    name: Name | None = None
    component_ids: Annotated[list[int] | None, Field(max_length=5000)] = None


class AssetSystemRead(_Read, AssetSystemFields):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str
    component_ids: list[int] = Field(default_factory=list)


# --- tree, import, COBie ------------------------------------------------------------------------------


class AssetTreeSpace(BaseModel):
    id: int
    name: str
    category: str | None
    component_count: int


class AssetTreeFloor(BaseModel):
    id: int
    name: str
    elevation: float | None
    component_count: int
    spaces: list[AssetTreeSpace]


class AssetTreeFacility(BaseModel):
    id: int
    name: str
    component_count: int
    floors: list[AssetTreeFloor]


class AssetTree(BaseModel):
    facilities: list[AssetTreeFacility]
    unplaced_components: int


ImportTarget = Literal["components", "types"]


class AssetImportPreview(BaseModel):
    target: ImportTarget
    columns: list[str]
    fields: list[str]
    mapping: dict[str, str]
    sample: list[dict[str, Any]]
    rows: int


class AssetImportReport(BaseModel):
    target: ImportTarget
    dry_run: bool
    rows: int
    created: int
    updated: int
    skipped: int
    duplicates: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CobieIssue(BaseModel):
    severity: Literal["error", "warning"]
    row: str | None = Field(None, description="The Name of the row at fault, when there is one")
    field: str | None = None
    message: str


class CobieSheetReport(BaseModel):
    sheet: str
    rows: int
    issues: list[CobieIssue] = Field(default_factory=list)


class CobieReport(BaseModel):
    valid: bool
    errors: int
    warnings: int
    sheets: list[CobieSheetReport]

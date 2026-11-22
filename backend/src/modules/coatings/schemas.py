from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .calc import DftRule

Microns = Annotated[float, Field(ge=0, le=100_000)]
Celsius = Annotated[float, Field(ge=-60, le=150)]
EquipmentIds = Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=20)]


class CoatSpec(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    product: Annotated[str | None, Field(max_length=200)] = None
    dft_min_um: Microns
    dft_max_um: Microns | None = None


class SystemCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    code: Annotated[str, Field(min_length=1, max_length=40)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    surface_prep_standard: Annotated[str | None, Field(max_length=120)] = None
    profile_min_um: Microns | None = None
    profile_max_um: Microns | None = None
    coats: list[CoatSpec] = Field(default_factory=list, max_length=12)
    dft_rule: DftRule = DftRule.EIGHTY_TWENTY
    dew_point_margin_c: Annotated[float, Field(ge=0, le=20)] = 3.0
    max_rh_pct: Annotated[float | None, Field(gt=0, le=100)] = 85.0
    notes: Annotated[str | None, Field(max_length=10_000)] = None


class SystemUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    surface_prep_standard: Annotated[str | None, Field(max_length=120)] = None
    profile_min_um: Microns | None = None
    profile_max_um: Microns | None = None
    coats: list[CoatSpec] | None = Field(None, max_length=12)
    dft_rule: DftRule | None = None
    dew_point_margin_c: Annotated[float | None, Field(ge=0, le=20)] = None
    max_rh_pct: Annotated[float | None, Field(gt=0, le=100)] = None
    notes: Annotated[str | None, Field(max_length=10_000)] = None


class SystemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    name: str
    surface_prep_standard: str | None
    profile_min_um: float | None
    profile_max_um: float | None
    coats: list[dict[str, Any]]
    dft_rule: str
    dew_point_margin_c: float
    max_rh_pct: float | None
    notes: str | None


class JobCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    system_id: int = Field(ge=1)
    node_id: int = Field(ge=1, description="The work anchor (or any node) being coated")
    item_id: int | None = Field(None, ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    area_m2: Annotated[Decimal | None, Field(ge=0, le=10_000_000)] = None
    dft_rule: DftRule | None = Field(None, description="The system's rule by default")
    notes: Annotated[str | None, Field(max_length=10_000)] = None


class JobUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    area_m2: Annotated[Decimal | None, Field(ge=0, le=10_000_000)] = None
    dft_rule: DftRule | None = None
    notes: Annotated[str | None, Field(max_length=10_000)] = None


class Batch(EncodableText):
    model_config = ConfigDict(extra="forbid")

    product: Annotated[str | None, Field(max_length=200)] = None
    batch: Annotated[str, Field(min_length=1, max_length=80)]
    expiry: Annotated[str | None, Field(max_length=20)] = None


class StageUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    batch_numbers: list[Batch] | None = Field(None, max_length=20)
    measured_profile_um: Microns | None = None
    cleanliness: Annotated[str | None, Field(max_length=40)] = None
    note: Annotated[str | None, Field(max_length=5000)] = None


class StageRelease(EncodableText):
    model_config = ConfigDict(extra="forbid")

    result: Literal["passed", "failed"]
    note: Annotated[str | None, Field(max_length=5000)] = None


class EnvironmentCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    stage_id: int | None = Field(None, ge=1)
    taken_at: datetime | None = None
    air_temp_c: Celsius | None = None
    surface_temp_c: Celsius
    rh_pct: Annotated[float | None, Field(gt=0, le=100)] = None
    dew_point_c: Celsius | None = Field(None, description="Measured; calculated from air temperature and RH when left out")
    equipment_ids: EquipmentIds = Field(default_factory=list)
    note: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _dew_point_source(self) -> "EnvironmentCreate":
        if self.dew_point_c is None and (self.air_temp_c is None or self.rh_pct is None):
            raise ValueError("Give the dew point, or the air temperature and relative humidity")
        return self


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    stage_id: int | None
    taken_at: datetime
    air_temp_c: float | None
    surface_temp_c: float
    rh_pct: float | None
    dew_point_c: float
    margin_c: float
    required_margin_c: float
    passed: bool
    failures: list[str]
    equipment_ids: list[int]
    taken_by_id: int | None
    note: str | None


class DftCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    stage_id: int = Field(ge=1, description="The coat")
    readings: Annotated[list[Microns], Field(min_length=1, max_length=500)]
    location: Annotated[str | None, Field(max_length=200)] = None
    taken_at: datetime | None = None
    rule: DftRule | None = Field(None, description="The job's rule by default")
    equipment_ids: EquipmentIds = Field(default_factory=list)


class DftPreview(EncodableText):
    model_config = ConfigDict(extra="forbid")

    readings: Annotated[list[Microns], Field(min_length=1, max_length=500)]
    dft_min_um: Microns
    dft_max_um: Microns | None = None
    rule: DftRule = DftRule.EIGHTY_TWENTY


class DftStatsRead(BaseModel):
    count: int
    mean: float
    minimum: float
    maximum: float
    pct_within: float
    pct_below_min: float
    passed: bool
    failures: list[str]


class DftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    stage_id: int
    taken_at: datetime
    location: str | None
    readings: list[float]
    rule: str
    dft_min_um: float
    dft_max_um: float | None
    count: int
    mean: float
    minimum: float
    maximum: float
    pct_within: float
    pct_below_min: float
    passed: bool
    failures: list[str]
    equipment_ids: list[int]
    taken_by_id: int | None


class EnvironmentPreview(EncodableText):
    model_config = ConfigDict(extra="forbid")

    surface_temp_c: Celsius
    air_temp_c: Celsius | None = None
    rh_pct: Annotated[float | None, Field(gt=0, le=100)] = None
    dew_point_c: Celsius | None = None
    required_margin_c: Annotated[float, Field(ge=0, le=20)] = 3.0


class EnvironmentCheckRead(BaseModel):
    dew_point_c: float
    margin_c: float
    required_margin_c: float
    passed: bool


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    kind: str
    name: str
    product: str | None
    dft_min_um: float | None
    dft_max_um: float | None
    status: str
    batch_numbers: list[dict[str, Any]]
    measured_profile_um: float | None
    cleanliness: str | None
    released_by_id: int | None
    released_at: datetime | None
    note: str | None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    system_id: int
    system_code: str | None = None
    node_id: int
    node_path: str | None = None
    item_id: int | None
    area_m2: Decimal | None
    dft_rule: str
    status: str
    current_stage: str | None = None
    notes: str | None
    created_at: datetime | None = None


class JobDetail(JobRead):
    system: SystemRead
    stages: list[StageRead]
    environment: list[EnvironmentRead]
    dft_sets: list[DftRead]

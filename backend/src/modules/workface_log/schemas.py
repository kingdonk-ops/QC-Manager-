from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import DelayCode, EquipmentStatus, OverheadCode, Shift

Hours = Annotated[Decimal, Field(ge=0, le=24, max_digits=8, decimal_places=2)]
Qty = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]
Measure = Annotated[Decimal | None, Field(ge=-100, le=10000, max_digits=7, decimal_places=1)]
Note = Annotated[str | None, Field(max_length=300)]


class LogHoursIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    person: Annotated[str, Field(min_length=1, max_length=120)]
    hours: Hours
    user_id: int | None = Field(None, ge=1)
    trade: Annotated[str | None, Field(max_length=60)] = None
    node_id: int | None = Field(
        None, ge=1, description="Where the hours were worked; resolved to its work anchor. Required unless a code is given."
    )
    delay_code: DelayCode | None = None
    overhead_code: OverheadCode | None = None
    note: Note = None


class LogQuantityIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(ge=1, description="A progress-unit node or anything with a work anchor on its path.")
    qty: Qty
    uom: Annotated[str | None, Field(max_length=20)] = None
    note: Note = None


class LogDelayIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: DelayCode
    hours: Hours
    node_id: int | None = Field(None, ge=1)
    description: Annotated[str | None, Field(max_length=500)] = None


class LogEquipmentIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    equipment: Annotated[str, Field(min_length=1, max_length=120)]
    hours: Hours
    status: EquipmentStatus = EquipmentStatus.OPERATING
    node_id: int | None = Field(None, ge=1)
    note: Note = None


class LogCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    crew_id: int = Field(ge=1)
    work_date: date
    shift: Shift = Shift.DAY
    area_node_id: int | None = Field(None, ge=1)
    prefill: bool = Field(True, description="Start from the crew's members and the day's plan from the planner.")


class LogUpdate(EncodableText):
    """The whole form. Child lists replace what was there."""

    model_config = ConfigDict(extra="forbid")

    shift: Shift | None = None
    area_node_id: int | None = Field(None, ge=1)
    weather: Annotated[str | None, Field(max_length=120)] = None
    temp_min_c: Measure = None
    temp_max_c: Measure = None
    wind_kmh: Measure = None
    rain_mm: Measure = None
    notes: str | None = None
    hours: list[LogHoursIn] | None = Field(None, max_length=500)
    quantities: list[LogQuantityIn] | None = Field(None, max_length=500)
    delays: list[LogDelayIn] | None = Field(None, max_length=200)
    equipment: list[LogEquipmentIn] | None = Field(None, max_length=200)


class LogNoteIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str | None, Field(max_length=2000)] = None


class LogHoursRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person: str
    hours: Decimal
    user_id: int | None
    trade: str | None
    anchor_id: int | None
    anchor_code: str | None = None
    delay_code: str | None
    overhead_code: str | None
    note: str | None
    category: str = "productive"


class LogQuantityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    node_code: str | None = None
    anchor_id: int
    anchor_code: str | None = None
    qty: Decimal
    uom: str | None
    note: str | None


class LogDelayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    hours: Decimal
    anchor_id: int | None
    anchor_code: str | None = None
    description: str | None


class LogEquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment: str
    hours: Decimal
    status: str
    anchor_id: int | None
    anchor_code: str | None = None
    note: str | None


class WorkfaceAnchorTotal(BaseModel):
    anchor_id: int
    anchor_code: str
    anchor_path: str
    hours: Decimal
    qty: Decimal
    uom: str | None = None


class WorkfaceTotals(BaseModel):
    productive_hours: Decimal
    delay_hours: Decimal
    overhead_hours: Decimal
    total_hours: Decimal
    headcount: int
    equipment_hours: Decimal
    by_anchor: list[WorkfaceAnchorTotal]
    by_delay_code: dict[str, Decimal]
    by_overhead_code: dict[str, Decimal]


class LogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    crew_id: int
    crew_code: str | None = None
    crew_name: str | None = None
    work_date: date
    shift: str
    status: str
    supervisor_id: int | None
    supervisor_name: str | None = None
    area_node_id: int | None
    weather: str | None
    temp_min_c: Decimal | None
    temp_max_c: Decimal | None
    wind_kmh: Decimal | None
    rain_mm: Decimal | None
    notes: str | None
    submitted_at: datetime | None
    signed_at: datetime | None
    signed_by_id: int | None
    signed_by_name: str | None = None
    sign_note: str | None
    total_hours: Decimal = Decimal(0)
    hours: list[LogHoursRead] = Field(default_factory=list)
    quantities: list[LogQuantityRead] = Field(default_factory=list)
    delays: list[LogDelayRead] = Field(default_factory=list)
    equipment: list[LogEquipmentRead] = Field(default_factory=list)
    totals: WorkfaceTotals | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkfaceCrewDay(BaseModel):
    crew_id: int
    crew_code: str
    crew_name: str
    log_id: int | None
    log_code: str | None
    status: str | None
    total_hours: Decimal
    productive_hours: Decimal
    delay_hours: Decimal
    planned_anchors: int


class WorkfaceDaySummary(BaseModel):
    project_id: int
    work_date: date
    crews: list[WorkfaceCrewDay]
    totals: WorkfaceTotals


class WorkfaceCodes(BaseModel):
    delay_codes: list[str]
    overhead_codes: list[str]
    equipment_statuses: list[str]

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import (
    BoltedJointStatus,
    JointEventKind,
    JointType,
    NdeMethod,
    NdeReason,
    NdeRequestStatus,
    NdeResultValue,
    QualificationStatus,
    TighteningMethod,
    VisualResult,
    WelderStatus,
    WpsStatus,
)

Ref = Annotated[str, Field(min_length=1, max_length=60)]
Text120 = Annotated[str, Field(max_length=120)]
Text200 = Annotated[str, Field(max_length=200)]
Dim = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]
Tags = Annotated[list[Annotated[str, Field(min_length=1, max_length=40)]], Field(max_length=30)]
Pct = Annotated[float, Field(ge=0, le=100)]


class _Body(EncodableText):
    model_config = ConfigDict(extra="forbid")


# --- settings ----------------------------------------------------------------------------------------


class WeldingSettingsIn(_Body):
    nde_rates: dict[Annotated[str, Field(min_length=1, max_length=40)], dict[NdeMethod, Pct]] | None = None
    continuity_days: int | None = Field(None, ge=1, le=3650)
    max_repairs: int | None = Field(None, ge=0, le=5)
    progressive_count: int | None = Field(None, ge=1, le=10)


class WeldingSettingsRead(BaseModel):
    project_id: int
    nde_rates: dict[str, dict[str, float]]
    continuity_days: int
    max_repairs: int
    progressive_count: int


# --- PQR / WPS ---------------------------------------------------------------------------------------


class PqrIn(_Body):
    project_id: int = Field(ge=1)
    code: Ref
    process: Annotated[str, Field(min_length=1, max_length=40)]
    standard_ref: Text120 | None = None
    base_material_group: Annotated[str, Field(max_length=60)] | None = None
    thickness_qualified: Annotated[str, Field(max_length=60)] | None = None
    tested_on: date | None = None
    laboratory: Text200 | None = None
    notes: str | None = None


class PqrUpdate(_Body):
    code: Ref | None = None
    process: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    standard_ref: Text120 | None = None
    base_material_group: Annotated[str, Field(max_length=60)] | None = None
    thickness_qualified: Annotated[str, Field(max_length=60)] | None = None
    tested_on: date | None = None
    laboratory: Text200 | None = None
    notes: str | None = None


class PqrRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    process: str
    standard_ref: str | None
    base_material_group: str | None
    thickness_qualified: str | None
    tested_on: date | None
    laboratory: str | None
    notes: str | None


class WpsIn(_Body):
    project_id: int = Field(ge=1)
    code: Ref
    process: Annotated[str, Field(min_length=1, max_length=40)]
    revision: Annotated[str, Field(min_length=1, max_length=10)] = "0"
    title: Text200 | None = None
    standard_ref: Text120 | None = None
    base_material_group: Annotated[str, Field(max_length=60)] | None = None
    filler_material: Text120 | None = None
    positions: Tags = Field(default_factory=list)
    joint_types: list[JointType] = Field(default_factory=list, max_length=10)
    thickness_min: Dim | None = None
    thickness_max: Dim | None = None
    diameter_min: Dim | None = None
    diameter_max: Dim | None = None
    pwht: bool = False
    pqr_id: int | None = Field(None, ge=1)
    notes: str | None = None


class WpsUpdate(_Body):
    title: Text200 | None = None
    standard_ref: Text120 | None = None
    base_material_group: Annotated[str, Field(max_length=60)] | None = None
    filler_material: Text120 | None = None
    positions: Tags | None = None
    joint_types: list[JointType] | None = Field(None, max_length=10)
    thickness_min: Dim | None = None
    thickness_max: Dim | None = None
    diameter_min: Dim | None = None
    diameter_max: Dim | None = None
    pwht: bool | None = None
    pqr_id: int | None = Field(None, ge=1)
    notes: str | None = None


class WpsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    revision: str
    process: str
    title: str | None
    standard_ref: str | None
    base_material_group: str | None
    filler_material: str | None
    positions: list[str]
    joint_types: list[str]
    thickness_min: Decimal | None
    thickness_max: Decimal | None
    diameter_min: Decimal | None
    diameter_max: Decimal | None
    pwht: bool
    pqr_id: int | None
    status: str
    approved_by_id: int | None
    approved_at: datetime | None
    notes: str | None


class WpsStatusIn(_Body):
    status: WpsStatus
    note: Annotated[str, Field(max_length=2000)] | None = None


# --- welders and qualifications ----------------------------------------------------------------------


class WelderIn(_Body):
    project_id: int = Field(ge=1)
    stamp: Annotated[str, Field(min_length=1, max_length=30)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    contact_id: int | None = Field(None, ge=1)
    employer: Text200 | None = None
    notes: str | None = None


class WelderUpdate(_Body):
    stamp: Annotated[str, Field(min_length=1, max_length=30)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    contact_id: int | None = Field(None, ge=1)
    employer: Text200 | None = None
    status: WelderStatus | None = None
    notes: str | None = None


class QualificationIn(_Body):
    process: Annotated[str, Field(min_length=1, max_length=40)]
    qualified_on: date
    wps_id: int | None = Field(None, ge=1, description="Qualified on this WPS only; omit for the process across WPSs")
    standard_ref: Text120 | None = None
    positions: Tags = Field(default_factory=list)
    material_groups: Tags = Field(default_factory=list)
    thickness_min: Dim | None = None
    thickness_max: Dim | None = None
    diameter_min: Dim | None = None
    expires_on: date | None = None
    certificate_ref: Text120 | None = None
    notes: str | None = None


class QualificationUpdate(_Body):
    positions: Tags | None = None
    material_groups: Tags | None = None
    thickness_min: Dim | None = None
    thickness_max: Dim | None = None
    diameter_min: Dim | None = None
    expires_on: date | None = None
    certificate_ref: Text120 | None = None
    status: QualificationStatus | None = None
    notes: str | None = None


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    welder_id: int
    process: str
    wps_id: int | None
    standard_ref: str | None
    positions: list[str]
    material_groups: list[str]
    thickness_min: Decimal | None
    thickness_max: Decimal | None
    diameter_min: Decimal | None
    qualified_on: date
    expires_on: date | None
    continuity_last_on: date | None
    continuity_until: date | None = None
    certificate_ref: str | None
    status: str
    state: str = ""
    verified_by_id: int | None
    notes: str | None


class ContinuityIn(_Body):
    process: Annotated[str, Field(min_length=1, max_length=40)]
    welded_on: date
    note: Annotated[str, Field(max_length=500)] | None = None


class ContinuityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    welder_id: int
    process: str
    welded_on: date
    qualification_id: int | None
    weld_id: int | None
    note: str | None


class WelderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    stamp: str
    name: str
    contact_id: int | None
    employer: str | None
    status: str
    notes: str | None
    processes: list[str] = Field(default_factory=list, description="Processes with a qualification usable today")


class WelderDetail(WelderRead):
    qualifications: list[QualificationRead] = Field(default_factory=list)
    continuity: list[ContinuityRead] = Field(default_factory=list)


class QualificationMatrixCell(BaseModel):
    state: str
    qualification_id: int
    expires_on: date | None
    continuity_until: date | None


class QualificationMatrixRow(BaseModel):
    welder_id: int
    stamp: str
    name: str
    status: str
    cells: dict[str, QualificationMatrixCell]


class QualificationMatrix(BaseModel):
    processes: list[str]
    rows: list[QualificationMatrixRow]


# --- welds -------------------------------------------------------------------------------------------


class WeldIn(_Body):
    project_id: int = Field(ge=1)
    weld_number: Ref
    node_id: int | None = Field(None, ge=1, description="Creates the weld item on this node (or pass item_id)")
    item_id: int | None = Field(None, ge=1, description="An existing asset item of type weld")
    drawing_ref: Text120 | None = None
    line_ref: Text120 | None = None
    joint_type: JointType = JointType.BUTT
    weld_category: Annotated[str, Field(min_length=1, max_length=40)] = "normal"
    position: Annotated[str, Field(max_length=10)] | None = None
    diameter: Dim | None = None
    schedule: Annotated[str, Field(max_length=20)] | None = None
    thickness: Dim | None = None
    material_1: Annotated[str, Field(max_length=80)] | None = None
    material_2: Annotated[str, Field(max_length=80)] | None = None
    wps_id: int | None = Field(None, ge=1)
    fit_up_on: date | None = None
    pwht_required: bool | None = Field(None, description="Defaults to the WPS's PWHT")
    nde_required: dict[NdeMethod, Pct] | None = Field(None, description="Defaults to the category's rates")
    replaces_weld_id: int | None = Field(None, ge=1)
    notes: str | None = None


class WeldUpdate(_Body):
    weld_number: Ref | None = None
    drawing_ref: Text120 | None = None
    line_ref: Text120 | None = None
    joint_type: JointType | None = None
    weld_category: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    position: Annotated[str, Field(max_length=10)] | None = None
    diameter: Dim | None = None
    schedule: Annotated[str, Field(max_length=20)] | None = None
    thickness: Dim | None = None
    material_1: Annotated[str, Field(max_length=80)] | None = None
    material_2: Annotated[str, Field(max_length=80)] | None = None
    wps_id: int | None = Field(None, ge=1)
    fit_up_on: date | None = None
    pwht_required: bool | None = None
    nde_required: dict[NdeMethod, Pct] | None = None
    notes: str | None = None


class WeldPassIn(_Body):
    welder_id: int = Field(ge=1)
    pass_name: Annotated[str, Field(min_length=1, max_length=30)] = "all"


class WeldingIn(_Body):
    welded_on: date
    passes: Annotated[list[WeldPassIn], Field(min_length=1, max_length=20)]


class WeldVisualIn(_Body):
    result: VisualResult
    inspected_on: date | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None


class WeldPwhtIn(_Body):
    done_on: date
    note: Annotated[str, Field(max_length=2000)] | None = None


class WeldRepairIn(_Body):
    repaired_on: date
    welder_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=10)]
    defect: Annotated[str, Field(max_length=300)] | None = None
    notes: str | None = None


class WeldNoteIn(_Body):
    note: Annotated[str, Field(max_length=2000)] | None = None


class WeldPassRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    welder_id: int
    welder_stamp: str | None = None
    pass_name: str
    repair_seq: int
    qualification_id: int | None


class WeldRepairRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    repaired_on: date
    defect: str | None
    cause_result_id: int | None
    notes: str | None


class NdeResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    weld_id: int
    weld_number: str | None = None
    method: str
    reason: str
    repair_seq: int
    tier: int
    triggered_by_id: int | None
    request_id: int | None
    request_code: str | None = None
    result: str
    examined_on: date | None
    report_ref: str | None
    file_id: int | None
    technician: str | None
    defect: str | None


class WeldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    item_id: int
    node_id: int | None = None
    node_path: str | None = None
    weld_number: str
    drawing_ref: str | None
    line_ref: str | None
    joint_type: str
    weld_category: str
    position: str | None
    diameter: Decimal | None
    schedule: str | None
    thickness: Decimal | None
    material_1: str | None
    material_2: str | None
    wps_id: int | None
    wps_code: str | None = None
    status: str
    fit_up_on: date | None
    welded_on: date | None
    visual_result: str
    visual_on: date | None
    pwht_required: bool
    pwht_on: date | None
    nde_required: dict[str, float]
    repair_count: int
    repair_label: str = ""
    replaces_weld_id: int | None
    welders: list[str] = Field(default_factory=list, description="Stamps of the welders on the original weld")
    nde_summary: dict[str, str] = Field(default_factory=dict, description="Latest result per method")
    accepted_on: date | None
    notes: str | None


class WeldDetail(WeldRead):
    passes: list[WeldPassRead] = Field(default_factory=list)
    repairs: list[WeldRepairRead] = Field(default_factory=list)
    nde: list[NdeResultRead] = Field(default_factory=list)


class WeldDrawingSummary(BaseModel):
    drawing_ref: str
    welds: int
    accepted: int
    rejected: int
    open: int


# --- NDE ---------------------------------------------------------------------------------------------


class NdeSamplingLot(BaseModel):
    welder_id: int
    stamp: str
    percent: float
    welds: int
    required: int
    selected: int
    shortfall: int


class NdeSampling(BaseModel):
    method: str
    lots: list[NdeSamplingLot]
    proposed_weld_ids: list[int]
    pending_weld_ids: list[int] = Field(description="Welds with a pending progressive/repair/full examination not on a request")


class NdeRequestIn(_Body):
    project_id: int = Field(ge=1)
    method: NdeMethod
    weld_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=500)] = Field(default_factory=list)
    reason: NdeReason = NdeReason.RANDOM
    include_pending: bool = Field(True, description="Also put this method's pending examinations without a request on it")
    requested_on: date | None = None
    required_by: date | None = None
    contractor: Text200 | None = None
    notes: str | None = None


class NdeRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    method: str
    status: str
    requested_on: date | None
    required_by: date | None
    contractor: str | None
    notes: str | None
    total: int = 0
    pending: int = 0
    rejected: int = 0


class NdeRequestDetail(NdeRequestRead):
    results: list[NdeResultRead] = Field(default_factory=list)


class NdeRequestStatusIn(_Body):
    status: NdeRequestStatus
    note: Annotated[str, Field(max_length=2000)] | None = None


class NdeResultIn(_Body):
    result: NdeResultValue = Field(description="accepted or rejected")
    examined_on: date
    report_ref: Text120 | None = None
    file_id: int | None = Field(None, ge=1)
    technician: Text200 | None = None
    defect: Annotated[str, Field(max_length=300)] | None = None


class NdeResultOutcome(BaseModel):
    result: NdeResultRead
    weld_status: str
    added: list[NdeResultRead] = Field(default_factory=list, description="Progressive examinations this rejection added")
    message: str | None = None


class RepairRateRow(BaseModel):
    key: str
    label: str
    examined: int
    rejected: int
    rate: float | None


class RepairRates(BaseModel):
    by_welder: list[RepairRateRow]
    by_method: list[RepairRateRow]
    overall: RepairRateRow


# --- bolted joints -----------------------------------------------------------------------------------


class BoltedJointIn(_Body):
    project_id: int = Field(ge=1)
    node_id: int = Field(ge=1)
    joint_ref: Ref
    item_id: int | None = Field(None, ge=1)
    drawing_ref: Text120 | None = None
    line_ref: Text120 | None = None
    size: Annotated[str, Field(max_length=20)] | None = None
    rating: Annotated[str, Field(max_length=20)] | None = None
    gasket: Text120 | None = None
    bolt_spec: Text120 | None = None
    bolt_count: int | None = Field(None, ge=1, le=200)
    method: TighteningMethod = TighteningMethod.TORQUE
    target_value: Dim | None = None
    unit: Annotated[str, Field(min_length=1, max_length=10)] = "Nm"
    tolerance_pct: Annotated[Decimal, Field(ge=0, le=50, max_digits=5, decimal_places=2)] = Decimal("5")
    status: BoltedJointStatus = Field(BoltedJointStatus.NEW, description="`made_up` for an existing joint in service")
    notes: str | None = None


class BoltedJointUpdate(_Body):
    joint_ref: Ref | None = None
    drawing_ref: Text120 | None = None
    line_ref: Text120 | None = None
    size: Annotated[str, Field(max_length=20)] | None = None
    rating: Annotated[str, Field(max_length=20)] | None = None
    gasket: Text120 | None = None
    bolt_spec: Text120 | None = None
    bolt_count: int | None = Field(None, ge=1, le=200)
    method: TighteningMethod | None = None
    target_value: Dim | None = None
    unit: Annotated[str, Field(min_length=1, max_length=10)] | None = None
    tolerance_pct: Annotated[Decimal, Field(ge=0, le=50, max_digits=5, decimal_places=2)] | None = None
    notes: str | None = None


class BoltedJointEventIn(_Body):
    kind: JointEventKind
    performed_on: date
    performed_by: Text200 | None = None
    equipment_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=10)] = Field(default_factory=list)
    applied_value: Dim | None = None
    pass_values: Annotated[list[Dim], Field(max_length=10)] = Field(default_factory=list)
    gasket_replaced: bool = False
    reason: Annotated[str, Field(max_length=300)] | None = None
    notes: str | None = None


class BoltedJointEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    joint_id: int
    kind: str
    performed_on: date
    performed_by: str | None
    equipment_ids: list[int]
    applied_value: Decimal | None
    pass_values: list[Any]
    gasket_replaced: bool
    reason: str | None
    notes: str | None
    recorded_by_id: int | None


class BoltedJointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    node_id: int
    node_path: str | None = None
    joint_ref: str
    item_id: int | None
    drawing_ref: str | None
    line_ref: str | None
    size: str | None
    rating: str | None
    gasket: str | None
    bolt_spec: str | None
    bolt_count: int | None
    method: str
    target_value: Decimal | None
    unit: str
    tolerance_pct: Decimal
    status: str
    notes: str | None
    breakouts: int = 0
    last_event_on: date | None = None


class BoltedJointDetail(BoltedJointRead):
    events: list[BoltedJointEventRead] = Field(default_factory=list)


class WeldingHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

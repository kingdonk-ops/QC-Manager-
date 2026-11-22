from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .constants import Basis, Curve, EacMethod, GroupBy, Interval

HoursIn = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
MoneyIn = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2)]
PercentIn = Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=3)]
Code = Annotated[str, Field(min_length=1, max_length=40)]
Label = Annotated[str | None, Field(max_length=60)]


class _Dates(BaseModel):
    @model_validator(mode="after")
    def _finish_after_start(self) -> "_Dates":
        start, finish = getattr(self, "planned_start", None), getattr(self, "planned_finish", None)
        if start and finish and finish < start:
            raise ValueError("planned_finish is before planned_start")
        return self


class EvmWorkPackageCreate(EncodableText, _Dates):
    model_config = ConfigDict(extra="forbid")

    project_id: Annotated[int, Field(ge=1)]
    code: Code
    name: Annotated[str, Field(min_length=1, max_length=300)]
    control_account: Label = None
    wbs: Label = None
    discipline: Label = None
    planned_start: date | None = None
    planned_finish: date | None = None
    budget_hours: HoursIn = Decimal(0)
    budget_cost: MoneyIn | None = None
    curve: Curve = Curve.LINEAR
    schedule_activity_id: Annotated[int | None, Field(ge=1)] = None
    cvr_cost_head_id: Annotated[int | None, Field(ge=1)] = None
    sort_order: int = 0


class EvmWorkPackageUpdate(EncodableText, _Dates):
    """Only the fields sent change; send ``null`` to clear an optional one."""

    model_config = ConfigDict(extra="forbid")

    code: Code | None = None
    name: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    control_account: Label = None
    wbs: Label = None
    discipline: Label = None
    planned_start: date | None = None
    planned_finish: date | None = None
    budget_hours: HoursIn | None = None
    budget_cost: MoneyIn | None = None
    curve: Curve | None = None
    schedule_activity_id: Annotated[int | None, Field(ge=1)] = None
    cvr_cost_head_id: Annotated[int | None, Field(ge=1)] = None
    sort_order: int | None = None


class EvmWorkPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    name: str
    control_account: str | None
    wbs: str | None
    discipline: str | None
    planned_start: date | None
    planned_finish: date | None
    budget_hours: Decimal
    budget_cost: Decimal | None
    curve: Curve
    schedule_activity_id: int | None
    cvr_cost_head_id: int | None
    sort_order: int


# --- progress ---------------------------------------------------------------------------------------


class EvmProgressEntry(EncodableText):
    """Cumulative progress for one package. Give ``percent_complete`` or ``earned_hours`` (not both)."""

    model_config = ConfigDict(extra="forbid")

    work_package_id: Annotated[int, Field(ge=1)]
    percent_complete: PercentIn | None = None
    earned_hours: HoursIn | None = None
    actual_hours: HoursIn | None = None
    actual_cost: MoneyIn | None = None
    comment: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _one_progress_measure(self) -> "EvmProgressEntry":
        if self.percent_complete is not None and self.earned_hours is not None:
            raise ValueError("Send percent_complete or earned_hours, not both")
        return self


class EvmProgressBatch(EncodableText):
    model_config = ConfigDict(extra="forbid")

    data_date: date
    entries: Annotated[list[EvmProgressEntry], Field(max_length=5000)]
    set_data_date: bool = Field(default=True, description="Make this the project's current data date")


class EvmProgressRow(BaseModel):
    """A package with its progress as at a date: the record on that date, or the latest before it."""

    work_package_id: int
    code: str
    name: str
    control_account: str | None
    discipline: str | None
    budget_hours: Decimal
    budget_cost: Decimal | None
    recorded_on: date | None
    percent_complete: Decimal
    earned_hours: Decimal
    actual_hours: Decimal
    actual_cost: Decimal | None
    comment: str | None


class EvmProgressSheet(BaseModel):
    project_id: int
    data_date: date
    rows: list[EvmProgressRow]


class EvmProgressSaved(BaseModel):
    data_date: date
    saved: int


class EvmFieldRow(BaseModel):
    work_package_id: int
    code: str
    nodes: int
    """Asset nodes in the package's scope (WBS match or linked P6 activity, with their subtrees)."""
    actual_hours: Decimal | None
    percent_complete: Decimal | None


class EvmFieldReport(BaseModel):
    data_date: date
    dry_run: bool
    saved: int
    rows: list[EvmFieldRow]


class EvmProgressImportIssue(BaseModel):
    row: int
    message: str


class EvmProgressImportReport(BaseModel):
    data_date: date
    rows: int
    saved: int
    dry_run: bool
    issues: list[EvmProgressImportIssue]


# --- settings ----------------------------------------------------------------------------------------


class EvmSettingsIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    data_date: date | None = None
    eac_method: EacMethod = EacMethod.CPI


class EvmSettingsRead(BaseModel):
    project_id: int
    data_date: date | None
    eac_method: EacMethod
    latest_progress_date: date | None
    cost_available: bool
    currency: str


# --- metrics -----------------------------------------------------------------------------------------


class EvmMetricsValues(BaseModel):
    bac: float
    pv: float
    ev: float
    ac: float
    sv: float
    cv: float
    spi: float | None
    cpi: float | None
    eac: float | None
    etc: float | None
    vac: float | None
    tcpi: float | None
    tcpi_eac: float | None
    percent_planned: float | None
    percent_complete: float | None
    productivity: float | None


class EvmMetricsRow(EvmMetricsValues):
    key: str
    label: str
    work_package_id: int | None = None
    control_account: str | None = None
    discipline: str | None = None
    packages: int = 1


class EvmMetricsReport(BaseModel):
    project_id: int
    data_date: date
    basis: Basis
    group_by: GroupBy
    eac_method: EacMethod
    cost_available: bool
    currency: str
    total: EvmMetricsValues
    rows: list[EvmMetricsRow]


class EvmCurvePoint(BaseModel):
    period_start: date
    period_end: date
    label: str
    pv: float
    ev: float | None
    ac: float | None
    forecast: float | None
    baseline_pv: float | None
    period_pv: float
    period_ev: float | None
    period_ac: float | None


class EvmSCurve(BaseModel):
    project_id: int
    basis: Basis
    interval: Interval
    data_date: date
    bac: float
    eac: float | None
    forecast_finish: date | None
    baseline_id: int | None
    points: list[EvmCurvePoint]


class EvmCashflowMonth(BaseModel):
    month: date
    planned_cost: float
    actual_cost: float | None
    cumulative_planned: float
    cumulative_actual: float | None
    cvr_planned_cost: float | None = None
    cvr_actual_cost: float | None = None


class EvmCashflow(BaseModel):
    project_id: int
    currency: str
    cost_available: bool
    cvr_included: bool
    months: list[EvmCashflowMonth]


# --- snapshots -------------------------------------------------------------------------------------


class EvmSnapshotCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    note: Annotated[str | None, Field(max_length=2000)] = None
    set_as_baseline: bool = False


class EvmSnapshotUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    note: Annotated[str | None, Field(max_length=2000)] = None
    is_baseline: bool | None = None


class EvmSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    note: str | None
    is_baseline: bool
    created_at: datetime
    created_by_id: int | None
    package_count: int
    budget_hours: float
    budget_cost: float | None


class EvmSnapshotCompareRow(BaseModel):
    code: str
    name: str
    status: str = Field(description="`changed`, `same`, `added` (only in current) or `removed` (only in snapshot)")
    snapshot_hours: float | None
    current_hours: float | None
    delta_hours: float | None
    snapshot_cost: float | None
    current_cost: float | None
    delta_cost: float | None
    snapshot_start: date | None
    current_start: date | None
    snapshot_finish: date | None
    current_finish: date | None
    snapshot_pv: float | None
    current_pv: float | None


class EvmSnapshotCompare(BaseModel):
    snapshot: EvmSnapshotRead
    data_date: date
    snapshot_hours: float
    current_hours: float
    snapshot_pv: float
    current_pv: float
    rows: list[EvmSnapshotCompareRow]

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .montecarlo import DEFAULT_ITERATIONS, MAX_ITERATIONS


class ScheduleActivityType(StrEnum):
    TASK = "task"
    MILESTONE = "milestone"
    SUMMARY = "summary"


class ScheduleActivityStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ScheduleConstraintType(StrEnum):
    ASAP = "asap"
    START_NO_EARLIER_THAN = "snet"
    FINISH_NO_LATER_THAN = "fnlt"
    MUST_START_ON = "mso"


class ScheduleLinkType(StrEnum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


Name = Annotated[str, Field(min_length=1, max_length=300)]
Wbs = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")]
Duration = Annotated[int, Field(ge=0, le=10_000)]
Estimate = Annotated[float, Field(ge=0, le=10_000)]
Percent = Annotated[float, Field(ge=0, le=100)]
Hours = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2)]
Lag = Annotated[int, Field(ge=-1000, le=1000)]


class ScheduleActivityCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Name
    wbs_code: Wbs | None = Field(None, description="Leave out to number it under its parent")
    code: Annotated[str | None, Field(max_length=40)] = None
    parent_id: int | None = Field(None, ge=1)
    type: ScheduleActivityType = ScheduleActivityType.TASK
    duration: Duration = 1
    planned_start: date | None = Field(None, description="Sets a start-no-earlier-than constraint")
    constraint_type: ScheduleConstraintType = ScheduleConstraintType.ASAP
    constraint_date: date | None = None
    resource: Annotated[str | None, Field(max_length=200)] = None
    responsible_id: int | None = Field(None, ge=1)
    budget_hours: Hours = Decimal(0)
    budget_cost: Cost = Decimal(0)
    optimistic_duration: Estimate | None = None
    most_likely_duration: Estimate | None = None
    pessimistic_duration: Estimate | None = None
    notes: Annotated[str | None, Field(max_length=10_000)] = None
    predecessor_id: int | None = Field(None, ge=1, description="Link after this activity (finish to start)")


class ScheduleActivityUpdate(EncodableText):
    """Only the fields sent change. Moving ``planned_start`` pins it with a start-no-earlier-than constraint;
    ``planned_finish`` changes the duration."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    wbs_code: Wbs | None = None
    code: Annotated[str | None, Field(max_length=40)] = None
    parent_id: int | None = Field(None, ge=1)
    type: ScheduleActivityType | None = None
    duration: Duration | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    percent_complete: Percent | None = None
    status: ScheduleActivityStatus | None = None
    constraint_type: ScheduleConstraintType | None = None
    constraint_date: date | None = None
    resource: Annotated[str | None, Field(max_length=200)] = None
    responsible_id: int | None = Field(None, ge=1)
    budget_hours: Hours | None = None
    budget_cost: Cost | None = None
    optimistic_duration: Estimate | None = None
    most_likely_duration: Estimate | None = None
    pessimistic_duration: Estimate | None = None
    notes: Annotated[str | None, Field(max_length=10_000)] = None
    sort_order: int | None = None


class ScheduleActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    wbs_code: str
    name: str
    parent_id: int | None
    type: str
    duration: int
    planned_start: date | None
    planned_finish: date | None
    actual_start: date | None
    actual_finish: date | None
    percent_complete: float
    status: str
    constraint_type: str
    constraint_date: date | None
    resource: str | None
    responsible_id: int | None
    budget_hours: Decimal
    budget_cost: Decimal
    optimistic_duration: float | None
    most_likely_duration: float | None
    pessimistic_duration: float | None
    notes: str | None
    sort_order: int
    early_start: date | None
    early_finish: date | None
    late_start: date | None
    late_finish: date | None
    total_float: int | None
    free_float: int | None
    is_critical: bool
    driving_predecessor_ids: list[int]
    baseline_start: date | None = None
    baseline_finish: date | None = None
    start_variance: int | None = Field(None, description="Working days actual (or forecast) start is later than planned")
    finish_variance: int | None = Field(None, description="Working days actual (or forecast) finish is later than planned")
    baseline_variance: int | None = Field(None, description="Working days the forecast finish is later than the baseline")
    p6_activity_id: str | None = Field(None, description="The P6 Activity ID this activity mirrors")
    schedule_state: str = Field("active", description="`removed_from_schedule` once missing from the latest P6 import")
    p6_float_days: float | None = Field(
        None, description="P6's own total float (working days on the activity's P6 calendar); null unless mirrored from P6"
    )
    p6_critical: bool | None = Field(None, description="Critical as P6 reports it; null unless mirrored from P6")


class ScheduleDependencyCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    predecessor_id: int = Field(ge=1)
    successor_id: int = Field(ge=1)
    type: ScheduleLinkType = ScheduleLinkType.FS
    lag: Lag = 0


class ScheduleDependencyUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: ScheduleLinkType | None = None
    lag: Lag | None = None


class ScheduleDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    predecessor_id: int
    successor_id: int
    type: str
    lag: int


class ScheduleBaselineCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    make_current: bool = True


class ScheduleBaselineRead(BaseModel):
    id: int
    project_id: int
    name: str
    is_current: bool
    finish_date: date | None
    activity_count: int
    created_at: str | None


class ScheduleCalendarRead(BaseModel):
    project_id: int
    working_days: list[int]
    holidays: list[date]
    start_date: date | None
    data_date: date | None
    finish_date: date | None
    current_baseline_id: int | None


class ScheduleCalendarUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    working_days: Annotated[list[Annotated[int, Field(ge=0, le=6)]], Field(min_length=1, max_length=7)] | None = None
    holidays: Annotated[list[date], Field(max_length=2000)] | None = None
    start_date: date | None = None
    data_date: date | None = None


class ScheduleSummary(BaseModel):
    project_id: int
    start: date | None
    finish: date | None
    baseline_finish: date | None
    finish_variance: int | None
    data_date: date | None
    activity_count: int
    critical_count: int
    percent_complete: float


class ScheduleGantt(BaseModel):
    project_id: int
    summary: ScheduleSummary
    calendar: ScheduleCalendarRead
    activities: list[ScheduleActivityRead]
    dependencies: list[ScheduleDependencyRead]
    baselines: list[ScheduleBaselineRead]


class ScheduleSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, Field(min_length=1, max_length=40)]
    name: Name
    value: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]


class ScheduleGenerateRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    source: Literal["sections", "cvr"] = "sections"
    sections: Annotated[list[ScheduleSection], Field(max_length=2000)] = Field(default_factory=list)
    total_duration: Annotated[int, Field(ge=1, le=10_000)]
    start_date: date | None = None
    replace: bool = Field(False, description="Delete the existing activities first")


class ScheduleMonteCarloRequest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    iterations: Annotated[int, Field(ge=1, le=MAX_ITERATIONS)] = DEFAULT_ITERATIONS
    distribution: Literal["triangular", "pert"] = "triangular"
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    target_date: date | None = None


class ScheduleHistogramBin(BaseModel):
    date: date
    count: int
    cumulative: float


class ScheduleCriticality(BaseModel):
    activity_id: int
    criticality_index: float
    name: str | None = None
    wbs_code: str | None = None


class ScheduleMonteCarloResult(BaseModel):
    iterations: int
    distribution: str
    seed: int | None
    planned_finish: date
    target_date: date
    probability_on_time: float
    p50: date
    p80: date
    p90: date
    earliest: date
    latest: date
    mean_duration_days: float
    std_dev_days: float
    histogram: list[ScheduleHistogramBin]
    criticality: list[ScheduleCriticality]


class ScheduleImportReport(BaseModel):
    format: str
    dry_run: bool
    project_name: str | None
    activities: int
    summaries: int
    milestones: int
    dependencies: int
    working_days: list[int]
    holidays: int
    created: int = 0
    replaced: int = 0

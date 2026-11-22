from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common.schemas import EncodableText, PartialUpdate, within_utc_range
from .constants import ActionStatus, IncidentStatus, IncidentType, ObservationCategory, ObservationKind, ParentType

Rating = Annotated[int, Field(ge=1, le=5)]
Short = Annotated[str | None, Field(max_length=200)]
Long = Annotated[str | None, Field(max_length=20000)]
Person = Annotated[str, Field(min_length=1, max_length=200)]


class IncidentCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    type: IncidentType
    occurred_at: datetime
    severity: Rating = Field(1, description="1 (insignificant) to 5 (catastrophic)")
    likelihood: Rating = Field(1, description="1 (rare) to 5 (almost certain)")
    location: Short = None
    people_involved: Annotated[list[Person], Field(max_length=50)] = []
    description: Long = None
    immediate_actions: Long = None
    root_cause: Long = None
    recordable: bool = False
    lost_time: bool = False
    days_lost: Annotated[int, Field(ge=0, le=10000)] = 0

    _utc = field_validator("occurred_at")(within_utc_range)

    @model_validator(mode="after")
    def _lost_time(self) -> "IncidentCreate":
        if self.days_lost and not self.lost_time:
            raise ValueError("days_lost needs lost_time")
        return self


class IncidentUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = (
        "title",
        "type",
        "occurred_at",
        "severity",
        "likelihood",
        "people_involved",
        "recordable",
        "lost_time",
        "days_lost",
    )

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    type: IncidentType | None = None
    occurred_at: datetime | None = None
    severity: Rating | None = None
    likelihood: Rating | None = None
    location: Short = None
    people_involved: Annotated[list[Person] | None, Field(max_length=50)] = None
    description: Long = None
    immediate_actions: Long = None
    root_cause: Long = None
    recordable: bool | None = None
    lost_time: bool | None = None
    days_lost: Annotated[int | None, Field(ge=0, le=10000)] = None

    _utc = field_validator("occurred_at")(within_utc_range)


class IncidentStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    type: str
    occurred_at: datetime
    severity: int
    likelihood: int
    risk_score: int
    risk_band: str
    location: str | None
    people_involved: list[str]
    description: str | None
    immediate_actions: str | None
    root_cause: str | None
    recordable: bool
    lost_time: bool
    days_lost: int
    status: str
    reported_by_id: int | None
    reported_by_name: str | None = None
    open_actions: int = 0
    created_at: datetime | None = None
    closed_at: datetime | None


class ObservationCreate(EncodableText):
    """Quick to log: a kind, a category and a sentence are enough; the time defaults to now."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    kind: ObservationKind
    category: ObservationCategory = ObservationCategory.OTHER
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    observed_at: datetime | None = None
    location: Short = None
    severity: Rating | None = None
    likelihood: Rating | None = None

    _utc = field_validator("observed_at")(within_utc_range)


class ObservationUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("kind", "category", "description", "observed_at", "status")

    kind: ObservationKind | None = None
    category: ObservationCategory | None = None
    description: Annotated[str | None, Field(min_length=1, max_length=5000)] = None
    observed_at: datetime | None = None
    location: Short = None
    severity: Rating | None = None
    likelihood: Rating | None = None
    status: Annotated[str | None, Field(pattern=r"^(open|closed)$")] = None

    _utc = field_validator("observed_at")(within_utc_range)


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    kind: str
    category: str
    description: str
    observed_at: datetime
    location: str | None
    observer_id: int | None
    observer_name: str | None = None
    severity: int | None
    likelihood: int | None
    risk_score: int | None
    risk_band: str | None
    status: str
    open_actions: int = 0
    created_at: datetime | None = None


class SafetyActionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    parent_type: ParentType
    parent_id: int = Field(ge=1)
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    assignee_id: int | None = Field(None, ge=1)
    due_date: date | None = None


class SafetyActionUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("description", "status")

    description: Annotated[str | None, Field(min_length=1, max_length=5000)] = None
    assignee_id: int | None = Field(None, ge=1)
    due_date: date | None = None
    status: ActionStatus | None = Field(None, description="`verified` records you as the verifier")
    verification_notes: Annotated[str | None, Field(max_length=5000)] = None


class SafetyActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    parent_type: str
    parent_id: int
    parent_code: str | None = None
    description: str
    assignee_id: int | None
    assignee_name: str | None = None
    due_date: date | None
    overdue: bool = False
    status: str
    completed_at: datetime | None
    verified_by_id: int | None
    verified_by_name: str | None = None
    verified_at: datetime | None
    verification_notes: str | None


class SafetyHoursSet(EncodableText):
    """Hours worked in a month; setting a month again replaces it."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")]
    hours: Annotated[float, Field(ge=0, le=1e9)]
    headcount: Annotated[int | None, Field(ge=0, le=1_000_000)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class SafetyHoursRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    month: date
    hours: float
    headcount: int | None
    notes: str | None


class SafetyMatrixCell(BaseModel):
    severity: int
    likelihood: int
    score: int
    band: str
    incidents: int
    observations: int


class SafetyMonthStats(BaseModel):
    month: str
    hours: float
    incidents: int
    recordables: int
    lost_time_injuries: int
    near_misses: int
    observations: int
    positive_observations: int
    trir: float | None
    ltifr: float | None


class SafetyLeading(BaseModel):
    observations: int
    positive_observations: int
    negative_observations: int
    positive_ratio: float | None
    """Positive observations as a share of all observations, 0-1."""
    actions_closed_on_time_pct: float | None


class SafetyLagging(BaseModel):
    incidents: int
    recordables: int
    lost_time_injuries: int
    days_lost: int
    near_misses: int
    trir: float | None
    ltifr: float | None


class SafetyDashboard(BaseModel):
    project_ids: list[int]
    date_from: date | None
    date_to: date | None
    hours_worked: float
    trir_base: int
    ltifr_base: int
    trir: float | None
    ltifr: float | None
    near_miss_ratio: float | None
    """Near misses reported per recordable incident (None with no recordables)."""
    by_type: dict[str, int]
    by_band: dict[str, int]
    open_actions: int
    overdue_actions: int
    leading: SafetyLeading
    lagging: SafetyLagging
    monthly: list[SafetyMonthStats]
    risk_matrix: list[SafetyMatrixCell]

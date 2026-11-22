import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText

Key = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.*]+$")]
DatasetName = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
Agg = Literal["sum", "avg", "count", "min", "max"]
ChartType = Literal["bar", "line", "area", "pie", "stacked"]
Filters = Annotated[dict[str, Any], Field(default_factory=dict, description="See `/data/export` for the filter syntax")]
Title = Annotated[str, Field(max_length=200)]


class KpiSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: Literal["kpis"]
    title: Title = "Key figures"
    keys: Annotated[list[Key], Field(max_length=50)] = Field(default_factory=list, description="Empty: every KPI")


class TableSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: Literal["table"]
    title: Title = ""
    dataset: DatasetName
    columns: Annotated[list[Key], Field(max_length=60)] = Field(default_factory=list, description="Empty: every column")
    filters: Filters
    group_by: Key | None = Field(None, description="Group rows by this column, summing the numeric columns")
    sort_by: Key | None = None
    descending: bool = False
    limit: Annotated[int, Field(ge=1, le=5000)] = 500


class ChartSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: Literal["chart"]
    title: Title = ""
    dataset: DatasetName
    chart: ChartType = "bar"
    x: Key
    y: Annotated[list[Key], Field(min_length=1, max_length=8)]
    agg: Agg = "sum"
    group_by: Key | None = Field(None, description="Colour by this column: one series per value")
    filters: Filters


class PivotValue(EncodableText):
    model_config = ConfigDict(extra="forbid")

    field: Key = "*"
    agg: Agg = "count"


class PivotSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pivot"]
    title: Title = ""
    dataset: DatasetName
    rows: Annotated[list[Key], Field(max_length=4)] = Field(default_factory=list)
    columns: Annotated[list[Key], Field(max_length=3)] = Field(default_factory=list)
    values: Annotated[list[PivotValue], Field(max_length=8)] = Field(default_factory=list)
    filters: Filters


class TextSection(EncodableText):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"]
    title: Title = ""
    body: Annotated[str, Field(max_length=20000)] = ""


Section = Annotated[KpiSection | TableSection | ChartSection | PivotSection | TextSection, Field(discriminator="type")]


class Branding(EncodableText):
    model_config = ConfigDict(extra="forbid")

    company_name: Annotated[str | None, Field(max_length=200)] = None
    logo_file_id: int | None = Field(None, ge=1, description="An image uploaded to Documents (PNG or JPEG)")


class TemplateIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    sections: Annotated[list[Section], Field(max_length=40)] = Field(default_factory=list)
    branding: Branding = Field(default_factory=Branding)
    landscape: bool = False


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    sections: list[Section]
    branding: Branding
    landscape: bool
    builtin_key: str | None
    created_by_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GenerateIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    template_id: int = Field(ge=1, le=2**31 - 1)
    project_id: int | None = Field(None, ge=1, le=2**31 - 1)
    format: Literal["pdf", "xlsx"] = "pdf"


class PivotIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    dataset: DatasetName
    project_id: int | None = Field(None, ge=1, le=2**31 - 1)
    rows: Annotated[list[Key], Field(max_length=4)] = Field(default_factory=list)
    columns: Annotated[list[Key], Field(max_length=3)] = Field(default_factory=list)
    values: Annotated[list[PivotValue], Field(max_length=8)] = Field(default_factory=list)
    filters: Filters


class PivotExportIn(PivotIn):
    format: Literal["xlsx", "csv"] = "xlsx"


class PivotValueRead(BaseModel):
    field: str
    agg: str


class PivotResult(BaseModel):
    row_fields: list[str]
    column_fields: list[str]
    values: list[PivotValueRead]
    row_keys: list[list[Any]]
    column_keys: list[list[Any]]
    cells: list[list[list[float | None]]]
    row_totals: list[list[float | None]]
    column_totals: list[list[float | None]]
    grand_total: list[float | None]
    source_rows: int
    truncated: bool


class DatasetRows(BaseModel):
    dataset: str
    total: int
    rows: list[dict[str, Any]]


class KpiValue(BaseModel):
    key: str
    module: str
    label: str
    unit: str
    good: str
    value: float | None
    status: Literal["good", "warning", "bad", "neutral"]
    description: str = ""


class PortfolioRow(BaseModel):
    project_id: int
    code: str
    name: str
    client_name: str | None
    region: str | None
    status: str
    currency: str
    budget: float | None
    value_to_date: float | None
    cost_to_date: float | None
    forecast_cost: float | None
    forecast_value: float | None
    variance: float | None
    variance_pct: float | None
    forecast_margin: float | None
    forecast_margin_pct: float | None
    budget_status: Literal["over", "on", "none"]
    kpis: dict[str, float | None] = Field(default_factory=dict)
    kpi_status: dict[str, str] = Field(default_factory=dict)


class CurrencyTotals(BaseModel):
    currency: str
    projects: int
    budget: float
    value_to_date: float
    cost_to_date: float
    forecast_cost: float
    forecast_value: float


class PortfolioSummary(BaseModel):
    projects: int
    over_budget: int
    on_budget: int
    no_budget: int
    average_variance_pct: float | None
    totals: list[CurrencyTotals]
    regions: list[str]
    kpis: list[dict[str, Any]]
    """The KPI columns of the portfolio table: ``key``, ``label``, ``unit``."""


TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    template_id: int = Field(ge=1, le=2**31 - 1)
    project_ids: Annotated[list[Annotated[int, Field(ge=1, le=2**31 - 1)]], Field(min_length=1, max_length=50)]
    cadence: Literal["daily", "weekly", "monthly"] = "weekly"
    weekday: int | None = Field(0, ge=0, le=6, description="0 = Monday")
    day_of_month: int | None = Field(1, ge=1, le=31, description="31 = the last day of every month")
    time_of_day: str = Field("07:00", description="HH:MM, in `timezone`")
    timezone: Annotated[str, Field(max_length=64)] = "Australia/Perth"
    format: Literal["pdf", "xlsx"] = "pdf"
    recipient_user_ids: Annotated[list[Annotated[int, Field(ge=1, le=2**31 - 1)]], Field(max_length=100)] = Field(
        default_factory=list
    )
    recipient_emails: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)] = Field(
        default_factory=list
    )
    enabled: bool = True

    @field_validator("time_of_day")
    @classmethod
    def _time(cls, value: str) -> str:
        if not TIME.match(value):
            raise ValueError("Use HH:MM, 24-hour")
        return value

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415 - only needed to validate

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown time zone {value!r}") from exc
        return value

    @field_validator("recipient_emails")
    @classmethod
    def _emails(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip().lower() for v in value if v.strip()]
        bad = [v for v in cleaned if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v)]
        if bad:
            raise ValueError(f"Not email addresses: {', '.join(bad)}")
        return sorted(set(cleaned))


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    template_id: int
    template_name: str | None = None
    project_ids: list[int]
    cadence: str
    weekday: int | None
    day_of_month: int | None
    time_of_day: str
    timezone: str
    format: str
    recipient_user_ids: list[int]
    recipient_emails: list[str]
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None = None
    created_by_id: int | None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_id: int | None
    template_id: int | None
    project_id: int | None
    status: str
    trigger: str
    format: str
    recipients: list[str]
    message: str | None
    size: int
    created_at: datetime | None = None

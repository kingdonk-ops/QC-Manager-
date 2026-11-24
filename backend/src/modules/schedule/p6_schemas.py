from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText


class RuleKind(StrEnum):
    GRAMMAR = "grammar"
    ELIGIBILITY = "eligibility"
    ALIAS = "alias"
    WBS_LEVEL = "wbs_level"


class RuleSource(StrEnum):
    NAME = "name"
    CODE = "code"
    WBS = "wbs"


class CriticalDefinition(StrEnum):
    TOTAL_FLOAT_LE = "total_float_le"
    LONGEST_PATH = "longest_path"


class ExportFormat(StrEnum):
    XER = "xer"
    P6_XML = "p6_xml"
    CSV = "csv"


class P6ImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    file_name: str
    sha256: str
    format: str
    source_project: str | None
    data_date: date | None
    status: str
    file_id: int | None
    summary: dict[str, Any]
    options: dict[str, Any]
    created_by_id: int | None
    committed_by_id: int | None
    committed_at: datetime | None
    created_at: datetime
    reused: bool = False
    """True when the same file was uploaded before: the earlier import is returned and nothing is written."""


class P6ChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_id: int
    p6_activity_id: str
    name: str
    change_type: str
    activity_id: int | None
    old: dict[str, Any]
    new: dict[str, Any]
    impact: dict[str, Any]
    excluded: bool


class P6ChangeUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    excluded: bool


class P6RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    kind: str
    name: str
    pattern: str
    source: str
    params: dict[str, Any]
    sort_order: int
    enabled: bool


class P6RuleCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    kind: RuleKind
    name: Annotated[str, Field(min_length=1, max_length=120)]
    pattern: Annotated[str, Field(max_length=1000)] = ""
    source: RuleSource = RuleSource.NAME
    params: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=100, ge=0, le=100_000)
    enabled: bool = True


class P6RuleUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    pattern: Annotated[str | None, Field(max_length=1000)] = None
    source: RuleSource | None = None
    params: dict[str, Any] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100_000)
    enabled: bool | None = None


class RuleSample(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(max_length=300)]
    code: Annotated[str | None, Field(max_length=60)] = None
    wbs: Annotated[str | None, Field(max_length=300)] = None
    task_type: Annotated[str | None, Field(max_length=20)] = None


class RuleTest(EncodableText):
    model_config = ConfigDict(extra="forbid")

    samples: Annotated[list[RuleSample], Field(min_length=1, max_length=200)]
    pattern: Annotated[str | None, Field(max_length=1000)] = Field(
        None, description="Try this pattern instead of the project's grammars (aliases and eligibility still apply)."
    )
    source: RuleSource = RuleSource.NAME
    params: dict[str, Any] = Field(default_factory=dict)


class RuleTestResult(BaseModel):
    sample: str
    matched_rule: str | None
    groups: dict[str, str] | None
    window: str | None
    eligible: bool
    ineligible_reason: str | None
    resolution: str
    """``matched``, ``create``, ``unmatched``, or ``ineligible``."""
    node_id: int | None
    node_path: str | None
    reason: str | None
    anchors: list[str] = []
    """Every work anchor the name addresses (several for a list or range such as ``728 - 732``)."""
    qualifier: str | None = None
    """A trailing note such as ``OHP``, ``Access`` or ``Props``; it never changes which RSW is meant."""


class P6Settings(EncodableText):
    model_config = ConfigDict(extra="forbid")

    critical_definition: CriticalDefinition = CriticalDefinition.TOTAL_FLOAT_LE
    critical_float_hours: float = Field(default=0.0, ge=-100_000, le=100_000)


class P6LinkRead(BaseModel):
    id: int
    project_id: int
    activity_id: int
    p6_activity_id: str | None
    activity_name: str
    node_id: int
    node_path: str
    progress_node_id: int | None
    work_window: str | None
    method: str
    status: str
    parsed: dict[str, Any]
    created_at: datetime


class P6LinkCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(ge=1)
    work_window: Annotated[str | None, Field(max_length=40)] = None
    remember: bool = Field(True, description="Link later activities with the same name to this node too.")


class UnmatchedActivity(BaseModel):
    id: int
    p6_activity_id: str | None
    name: str
    wbs_path: str | None
    planned_start: date | None
    planned_finish: date | None
    reason: str | None
    groups: dict[str, str] | None
    proposed: list[P6LinkRead]


class ScheduleFacts(BaseModel):
    node_id: int
    data_date: date | None
    critical_definition: str
    critical_float_hours: float
    total_float_hours: float | None
    on_critical_path: bool
    critical_basis: str
    activities: list[dict[str, Any]]


class VerificationCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(ge=1)
    verified_qty: Decimal = Field(ge=0, le=Decimal("99999999999999"))
    verified_on: date | None = None
    inspection_id: int | None = Field(default=None, ge=1)
    note: Annotated[str | None, Field(max_length=2000)] = None


class VerificationRead(BaseModel):
    id: int
    project_id: int
    node_id: int
    node_path: str
    verified_qty: Decimal
    verified_on: date
    inspection_id: int | None
    inspection_code: str | None
    counts: bool
    """False while the cited inspection isn't completed/closed without failures."""
    verified_by_id: int | None
    note: str | None


class ProgressRow(BaseModel):
    activity_id: int
    p6_activity_id: str | None
    name: str
    nodes: list[str]
    units: int
    p6_status: str | None
    p6_percent: float | None
    reported_percent: float | None
    verified_percent: float | None
    actual_start: date | None
    actual_finish: date | None
    status_code: str


class ExportCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    format: ExportFormat = ExportFormat.XER
    only_changed: bool = Field(True, description="Only activities whose verified progress differs from P6's.")


class P6ExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    format: str
    data_date: date
    row_count: int
    created_by_id: int | None
    created_at: datetime

"""Trends, dashboard tile and project settings schemas of the inspections module."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText, PartialUpdate


class InspectionTrendPoint(BaseModel):
    inspection_id: int
    code: str
    date: date | None
    pass_rate: float | None
    passed: int
    failed: int


class InspectionTrendMonth(BaseModel):
    month: str
    inspections: int
    passed: int
    failed: int
    pass_rate: float | None


class InspectionTrendGroup(BaseModel):
    key: str
    inspections: int
    passed: int
    failed: int
    pass_rate: float | None
    points: list[InspectionTrendPoint]
    monthly: list[InspectionTrendMonth]


class InspectionTrends(BaseModel):
    project_id: int
    group_by: str
    groups: list[InspectionTrendGroup]


class InspectionDashboard(BaseModel):
    project_id: int
    open_requests: int
    requests_today: int
    holds_awaiting_release: int
    holds_open: int
    inspections_due: int
    overdue: int
    awaiting_review: int
    pass_rate: float | None
    passed: int
    failed: int
    computed_at: datetime


class InspectionSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    min_notice_hours: int = 24
    block_short_notice: bool = False
    no_show_grace_minutes: int = 30
    allow_self_approval: bool = False
    auto_report_on_failure: bool = False


class InspectionSettingsUpdate(EncodableText, PartialUpdate):
    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = (
        "min_notice_hours",
        "block_short_notice",
        "no_show_grace_minutes",
        "allow_self_approval",
        "auto_report_on_failure",
    )

    min_notice_hours: int | None = Field(None, ge=0, le=336)
    block_short_notice: bool | None = None
    no_show_grace_minutes: int | None = Field(None, ge=0, le=720)
    allow_self_approval: bool | None = None
    auto_report_on_failure: bool | None = Field(None, description="A failed record without a criterion raises a report")

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import Impact, ResponseType, RiskCategory, RiskStatus

Amount = Annotated[Decimal, Field(max_digits=16, decimal_places=2, ge=Decimal(0))]
Probability = Annotated[
    Decimal,
    Field(ge=Decimal("0.1"), le=Decimal("0.9"), decimal_places=1, description="0.1 to 0.9 in steps of 0.1"),
]
Title = Annotated[str, Field(min_length=1, max_length=300)]
LongText = Annotated[str | None, Field(max_length=20_000)]
Days = Annotated[int, Field(ge=0, le=36_500)]


class RiskCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Title
    description: LongText = None
    category: RiskCategory = RiskCategory.TECHNICAL
    cause: LongText = None
    effect: LongText = None
    probability: Probability = Decimal("0.5")
    impact: Impact = Impact.MEDIUM
    cost_impact: Amount = Decimal(0)
    schedule_impact_days: Days = 0
    owner_id: int | None = Field(None, ge=1)
    mitigation: LongText = None
    contingency: LongText = None
    residual_probability: Probability | None = None
    residual_impact: Impact | None = None
    response: ResponseType | None = None
    review_date: date | None = None


class RiskUpdate(EncodableText):
    """Only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: LongText = None
    category: RiskCategory | None = None
    cause: LongText = None
    effect: LongText = None
    probability: Probability | None = None
    impact: Impact | None = None
    cost_impact: Amount | None = None
    schedule_impact_days: Days | None = None
    owner_id: int | None = Field(None, ge=1)
    mitigation: LongText = None
    contingency: LongText = None
    residual_probability: Probability | None = None
    residual_impact: Impact | None = None
    response: ResponseType | None = None
    review_date: date | None = None


class RiskStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: RiskStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class RiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    category: str
    cause: str | None
    effect: str | None
    probability: Decimal
    impact: str
    cost_impact: Decimal
    schedule_impact_days: int
    owner_id: int | None
    owner_name: str | None = None
    mitigation: str | None
    contingency: str | None
    residual_probability: Decimal | None
    residual_impact: str | None
    response: str | None
    status: str
    review_date: date | None
    review_due: bool = False
    band: str = ""
    exposure: Decimal = Decimal(0)
    residual_exposure: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RiskBand(BaseModel):
    key: str
    label: str
    min: Decimal
    max: Decimal


class RiskMatrixCell(BaseModel):
    band: str
    impact: str
    count: int
    exposure: Decimal


class RiskCategoryTotal(BaseModel):
    category: str
    count: int
    exposure: Decimal


class RiskMatrix(BaseModel):
    project_id: int
    currency: str
    bands: list[RiskBand]
    impacts: list[str]
    cells: list[RiskMatrixCell]
    total_exposure: Decimal
    total_residual_exposure: Decimal
    total_schedule_days: int
    count: int
    open_count: int
    high_critical_count: int
    by_category: list[RiskCategoryTotal]
    top: list[RiskRead]


class RiskHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

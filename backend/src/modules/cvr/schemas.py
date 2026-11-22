from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from ..common.schemas import EncodableText

Amount = Annotated[Decimal, Field(max_digits=16, decimal_places=2, ge=Decimal("-99999999999999"))]


class CostHeadCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, Field(min_length=1, max_length=30)]
    description: Annotated[str, Field(min_length=1, max_length=300)]
    sort_order: int = 0
    budget: Amount = Decimal(0)
    cost_to_date: Amount = Decimal(0)
    value_to_date: Amount = Decimal(0)
    forecast_cost: Amount = Decimal(0)
    forecast_value: Amount = Decimal(0)


class CostHeadUpdate(EncodableText):
    """Only the fields sent change: a grid edit sends the one cell."""

    model_config = ConfigDict(extra="forbid")

    code: Annotated[str | None, Field(min_length=1, max_length=30)] = None
    description: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    sort_order: int | None = None
    budget: Amount | None = None
    cost_to_date: Amount | None = None
    value_to_date: Amount | None = None
    forecast_cost: Amount | None = None
    forecast_value: Amount | None = None


class CostHeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    description: str
    sort_order: int
    budget: Decimal
    cost_to_date: Decimal
    value_to_date: Decimal
    forecast_cost: Decimal
    forecast_value: Decimal

    @computed_field  # type: ignore[prop-decorator]
    @property
    def margin_to_date(self) -> Decimal:
        return self.value_to_date - self.cost_to_date

    @computed_field  # type: ignore[prop-decorator]
    @property
    def forecast_margin(self) -> Decimal:
        return self.forecast_value - self.forecast_cost


class CvrSummary(BaseModel):
    project_id: int
    currency: str
    budget: Decimal
    cost_to_date: Decimal
    value_to_date: Decimal
    margin_to_date: Decimal
    margin_to_date_pct: float | None
    forecast_cost: Decimal
    forecast_value: Decimal
    forecast_margin: Decimal
    forecast_margin_pct: float | None


class CashflowPeriodIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    period: date = Field(description="Any day in the month; stored as the first of the month")
    planned_cost: Amount = Decimal(0)
    actual_cost: Amount | None = None
    planned_value: Amount = Decimal(0)
    actual_value: Amount | None = None

    @field_validator("period")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return value.replace(day=1)


class CashflowSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    periods: Annotated[list[CashflowPeriodIn], Field(max_length=240)]


class CashflowPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: date
    planned_cost: Decimal
    actual_cost: Decimal | None
    planned_value: Decimal
    actual_value: Decimal | None

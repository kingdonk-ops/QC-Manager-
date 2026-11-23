"""Request and response bodies of the acceptance-criteria library."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText, PartialUpdate, refuse_oversized_json
from .constants import RuleType

Limit = Annotated[str | None, Field(max_length=40)]


class CriterionCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    code: Annotated[str, Field(min_length=1, max_length=40)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Annotated[str | None, Field(max_length=5000)] = None
    standards_ref: Annotated[str | None, Field(max_length=200)] = None
    discipline: Annotated[str | None, Field(max_length=100)] = None
    category: Annotated[str | None, Field(max_length=100)] = None
    characteristic: Annotated[str | None, Field(max_length=200)] = None
    method: Annotated[str | None, Field(max_length=200)] = None
    unit: Annotated[str | None, Field(max_length=30)] = None
    rule_type: RuleType = RuleType.FREE_TEXT
    nominal: Limit = None
    lower_limit: Limit = None
    upper_limit: Limit = None
    active: bool = True
    supplementary: dict[str, Any] = {}

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any]) -> dict[str, Any]:
        refuse_oversized_json("supplementary", value)
        return value


class CriterionUpdate(EncodableText, PartialUpdate):
    """Any subset. Changing the rule, unit, nominal or a limit is refused once a record has been judged against it."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("code", "title", "rule_type", "active", "supplementary")

    code: Annotated[str | None, Field(min_length=1, max_length=40)] = None
    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    standards_ref: Annotated[str | None, Field(max_length=200)] = None
    discipline: Annotated[str | None, Field(max_length=100)] = None
    category: Annotated[str | None, Field(max_length=100)] = None
    characteristic: Annotated[str | None, Field(max_length=200)] = None
    method: Annotated[str | None, Field(max_length=200)] = None
    unit: Annotated[str | None, Field(max_length=30)] = None
    rule_type: RuleType | None = None
    nominal: Limit = None
    lower_limit: Limit = None
    upper_limit: Limit = None
    active: bool | None = None
    supplementary: dict[str, Any] | None = None

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            refuse_oversized_json("supplementary", value)
        return value


class CriterionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    standards_ref: str | None
    discipline: str | None
    category: str | None
    characteristic: str | None
    method: str | None
    unit: str | None
    rule_type: str
    nominal: str | None
    lower_limit: str | None
    upper_limit: str | None
    active: bool
    supplementary: dict[str, Any]
    created_by_id: int | None
    created_at: datetime | None
    updated_at: datetime | None

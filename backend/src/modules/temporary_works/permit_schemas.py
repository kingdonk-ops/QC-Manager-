"""Request and response bodies of the temporary works permits.

A permit's item and project come from the request context, never the body, and its status is never part of a body: it
moves only through the issue, activate, close and return-to-draft actions (and to expired by the hourly sweep)."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText, PartialUpdate
from .constants import PermitKind
from .schemas import TwFindingRead

Number = Annotated[str, Field(min_length=1, max_length=40, pattern=r"\S")]
Name = Annotated[str | None, Field(max_length=200)]


class TwPermitCreate(EncodableText):
    """A new permit to load, strike or dismantle. It is always created as a draft. The prerequisite flags on a permit to
    strike or dismantle are accepted and have no effect on any gate."""

    model_config = ConfigDict(extra="forbid")

    number: Number
    kind: PermitKind
    issued_by_name: Name = None
    valid_from: date | None = None
    valid_to: date | None = None
    inspection_id: int | None = Field(None, ge=1, description="A soft reference to an inspection record")
    design_check_accepted: bool = False
    inspection_passed: bool = False
    conditions: Annotated[str | None, Field(max_length=5000)] = None


class TwPermitUpdate(EncodableText, PartialUpdate):
    """Any subset, while the permit is a draft. The status, issued day and closed day are not part of an edit."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("number", "kind", "design_check_accepted", "inspection_passed")

    number: Number | None = None
    kind: PermitKind | None = None
    issued_by_name: Name = None
    valid_from: date | None = None
    valid_to: date | None = None
    inspection_id: int | None = Field(None, ge=1)
    design_check_accepted: bool | None = None
    inspection_passed: bool | None = None
    conditions: Annotated[str | None, Field(max_length=5000)] = None


class TwPermitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    item_id: int
    number: str
    kind: str
    status: str
    issued_by_name: str | None
    issued_on: date | None
    valid_from: date | None
    valid_to: date | None
    closed_on: date | None
    closed_by_id: int | None
    inspection_id: int | None
    design_check_accepted: bool
    inspection_passed: bool
    conditions: str | None
    created_by_id: int | None
    expiry_notified_on: date | None
    created_at: datetime | None
    updated_at: datetime | None


class TwPermitWriteRead(TwPermitRead):
    """A permit as returned by a write, with the non-blocking warnings of the rules that ran."""

    warnings: list[TwFindingRead] = []

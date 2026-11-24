"""Request and response bodies of the temporary works items."""

from datetime import date, datetime
from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText, PartialUpdate, refuse_oversized_json
from .constants import Family, ItemStatus

Reference = Annotated[str, Field(min_length=1, max_length=60, pattern=r"\S")]
Title = Annotated[str, Field(min_length=1, max_length=300, pattern=r"\S")]
Name = Annotated[str | None, Field(max_length=200)]
Category = Annotated[int | None, Field(ge=0, le=3, description="Design check category, zero to three; empty until assigned")]
RelatedRefs = dict[str, Annotated[str, Field(max_length=200)]]
Reason = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]
T = TypeVar("T")


def _small(name: str, value: T) -> T:
    """``value`` itself once it is known to be small enough to store (the type is kept for the caller)."""
    if value is not None:
        refuse_oversized_json(name, value)
    return value


class TwItemCreate(EncodableText):
    """A new item. It always starts in identified (the draft state); its status is never part of the body."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    reference: Reference
    title: Title
    family: Family
    description: Annotated[str | None, Field(max_length=5000)] = None
    design_check_category: Category = None
    designer: Name = None
    checker: Name = None
    coordinator_name: Name = None
    coordinator_user_id: int | None = Field(None, ge=1)
    required_load_on: date | None = None
    required_strike_on: date | None = None
    design_due_on: date | None = None
    location: Annotated[str | None, Field(max_length=300)] = None
    asset_node_id: int | None = Field(None, ge=1, description="An asset node of the same project")
    sort_order: int = Field(0, ge=0, le=1_000_000)
    notes: Annotated[str | None, Field(max_length=5000)] = None
    scaffold_id: int | None = Field(None, ge=1, description="A scaffold of the same project, when the scaffolds module is on")
    related_refs: RelatedRefs = {}

    @field_validator("related_refs")
    @classmethod
    def _storable(cls, value: dict[str, str]) -> dict[str, str]:
        return _small("related_refs", value)


class TwItemUpdate(EncodableText, PartialUpdate):
    """Any subset: an omitted field is left alone and an explicit null clears an optional one. The status is not part of
    an edit: it moves only through the transition action (and back to draft through return-to-draft)."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("reference", "title", "family", "sort_order", "related_refs")

    reference: Reference | None = None
    title: Title | None = None
    family: Family | None = None
    description: Annotated[str | None, Field(max_length=5000)] = None
    design_check_category: Category = None
    designer: Name = None
    checker: Name = None
    coordinator_name: Name = None
    coordinator_user_id: int | None = Field(None, ge=1)
    required_load_on: date | None = None
    required_strike_on: date | None = None
    design_due_on: date | None = None
    location: Annotated[str | None, Field(max_length=300)] = None
    asset_node_id: int | None = Field(None, ge=1)
    sort_order: int | None = Field(None, ge=0, le=1_000_000)
    notes: Annotated[str | None, Field(max_length=5000)] = None
    scaffold_id: int | None = Field(None, ge=1)
    related_refs: RelatedRefs | None = None

    @field_validator("related_refs")
    @classmethod
    def _storable(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return _small("related_refs", value)


class TwItemTransition(EncodableText):
    """Move one step along the guarded flow. A step back needs a note."""

    model_config = ConfigDict(extra="forbid")

    status: ItemStatus
    note: Annotated[str | None, Field(max_length=1000)] = None


class TwReasonBody(EncodableText):
    """The mandatory reason for sending an item or a permit back to draft."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason


class TwFindingRead(BaseModel):
    rule: str
    message: str


class TwItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    reference: str
    title: str
    family: str
    description: str | None
    design_check_category: int | None
    designer: str | None
    checker: str | None
    coordinator_name: str | None
    coordinator_user_id: int | None
    status: str
    held_from: str | None
    required_load_on: date | None
    required_strike_on: date | None
    design_due_on: date | None
    location: str | None
    asset_node_id: int | None
    sort_order: int
    notes: str | None
    scaffold_id: int | None
    related_refs: dict[str, Any]
    created_by_id: int | None
    breach_notified_on: date | None
    created_at: datetime | None
    updated_at: datetime | None


class TwItemWriteRead(TwItemRead):
    """An item as returned by a write: the non-blocking warnings of the rules that ran ride along."""

    warnings: list[TwFindingRead] = []


class TwHistoryRead(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

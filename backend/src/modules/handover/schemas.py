from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import ItemKind, Shift

Text4k = Annotated[str | None, Field(max_length=8000)]


class HandoverItemIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    kind: ItemKind
    title: Annotated[str, Field(min_length=1, max_length=300)]
    status: Annotated[str | None, Field(max_length=20)] = Field(None, description="Per kind; defaults to the first allowed.")
    detail: Text4k = None
    reference: Annotated[str | None, Field(max_length=120)] = None
    node_id: int | None = Field(None, ge=1, description="Resolved to its work anchor; required for work in progress.")
    link_type: Annotated[str | None, Field(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")] = None
    link_id: int | None = Field(None, ge=1)
    link_label: Annotated[str | None, Field(max_length=200)] = None


class HandoverCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    shift_date: date
    from_shift: Shift = Shift.DAY
    to_shift: Shift = Shift.NIGHT
    area_node_id: int | None = Field(None, ge=1)
    recipient_id: int | None = Field(None, ge=1)
    summary: Text4k = None
    safety_notes: Text4k = None
    items: list[HandoverItemIn] = Field(default_factory=list, max_length=300)
    carry_forward: bool = Field(True, description="Start with the items still open in the area's last handover.")


class HandoverUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    shift_date: date | None = None
    from_shift: Shift | None = None
    to_shift: Shift | None = None
    area_node_id: int | None = Field(None, ge=1)
    recipient_id: int | None = Field(None, ge=1)
    summary: Text4k = None
    safety_notes: Text4k = None
    items: list[HandoverItemIn] | None = Field(None, max_length=300)


class HandoverNoteIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str | None, Field(max_length=4000)] = None


class HandoverItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    status: str
    detail: str | None
    reference: str | None
    anchor_id: int | None
    anchor_code: str | None = None
    anchor_path: str | None = None
    link_type: str | None
    link_id: int | None
    link_label: str | None


class HandoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    shift_date: date
    from_shift: str
    to_shift: str
    area_node_id: int | None
    area_name: str | None = None
    author_id: int | None
    author_name: str | None = None
    recipient_id: int | None
    recipient_name: str | None = None
    status: str
    summary: str | None
    safety_notes: str | None
    carried_from_id: int | None
    submitted_at: datetime | None
    acknowledged_at: datetime | None
    ack_note: str | None
    reminders_sent: int
    waiting_hours: float | None = None
    """Hours since submission while unacknowledged."""
    item_count: int = 0
    open_count: int = 0
    items: list[HandoverItemRead] = Field(default_factory=list)


class HandoverItemStatuses(BaseModel):
    statuses: dict[str, list[str]]

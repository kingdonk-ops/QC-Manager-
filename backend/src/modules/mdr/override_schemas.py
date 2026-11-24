from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..common.schemas import EncodableText
from .constants import IssuePurpose

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Severity = Literal["minor", "major", "critical"]


class OverrideIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    purpose: IssuePurpose = Field(description="The issue the override is for; a final issue also needs client acceptance")
    reason: Reason = Field(description="Why the dossier is issued past the blockers; required")
    severity: Severity | None = Field(default=None, description="Severity of the documentation report; major when omitted")


class BlockerRead(BaseModel):
    check: str
    reference: str
    message: str


class OverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dossier_id: int
    reference: str
    purpose: str
    reason: str
    severity: str
    blockers: list[BlockerRead]
    gate_numbers: list[str]
    report_id: int | None
    report_code: str | None
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime | None = None

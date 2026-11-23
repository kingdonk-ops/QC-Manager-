"""Request and response bodies of the as-built records."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText, PartialUpdate, refuse_oversized_json, within_utc_range
from ..ncr.constants import Severity
from .constants import AccuracyClass, AsBuiltStatus, CaptureMethod, SourceKind

Text40 = Annotated[str | None, Field(max_length=40)]


class AsBuiltCreate(EncodableText):
    """A new record; it always starts as a draft and takes its number from the project sequence."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    discipline: Annotated[str | None, Field(max_length=100)] = None
    location: Annotated[str | None, Field(max_length=300)] = None
    capture_method: CaptureMethod = CaptureMethod.MANUAL
    instrument: Annotated[str | None, Field(max_length=200)] = None
    calibration_ref: Annotated[str | None, Field(max_length=100)] = None
    accuracy_class: AccuracyClass = AccuracyClass.STANDARD
    accuracy_value: Text40 = None
    accuracy_unit: Annotated[str | None, Field(max_length=30)] = None
    coordinate_system: Annotated[str | None, Field(max_length=100)] = None
    surveyed_on: date | None = None
    surveyed_by_id: int | None = Field(None, ge=1)
    criterion_id: int | None = Field(None, ge=1, description="An acceptance criterion of the same project")
    measured_value: Text40 = None
    deviation_value: Text40 = Field(None, description="A manually entered deviation distance")
    source_kind: SourceKind = SourceKind.MANUAL
    source_ref: Annotated[str | None, Field(max_length=200)] = None
    deviation_map_ref: Annotated[str | None, Field(max_length=300)] = None
    node_id: int | None = Field(None, ge=1)
    item_id: int | None = Field(None, ge=1)
    notes: Annotated[str | None, Field(max_length=5000)] = None
    supplementary: dict[str, Any] = {}

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any]) -> dict[str, Any]:
        refuse_oversized_json("supplementary", value)
        return value


class AsBuiltUpdate(EncodableText, PartialUpdate):
    """Any subset. The status moves only to void or superseded by edit; survey, verify and sign have their own actions,
    and the measured value and criterion change only by a new survey once one has been recorded."""

    model_config = ConfigDict(extra="forbid")
    NOT_NULLABLE = ("title", "capture_method", "accuracy_class", "source_kind", "status", "supplementary")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    status: AsBuiltStatus | None = None
    discipline: Annotated[str | None, Field(max_length=100)] = None
    location: Annotated[str | None, Field(max_length=300)] = None
    capture_method: CaptureMethod | None = None
    instrument: Annotated[str | None, Field(max_length=200)] = None
    calibration_ref: Annotated[str | None, Field(max_length=100)] = None
    accuracy_class: AccuracyClass | None = None
    accuracy_value: Text40 = None
    accuracy_unit: Annotated[str | None, Field(max_length=30)] = None
    coordinate_system: Annotated[str | None, Field(max_length=100)] = None
    surveyed_on: date | None = None
    surveyed_by_id: int | None = Field(None, ge=1)
    criterion_id: int | None = Field(None, ge=1)
    measured_value: Text40 = None
    deviation_value: Text40 = None
    source_kind: SourceKind | None = None
    source_ref: Annotated[str | None, Field(max_length=200)] = None
    deviation_map_ref: Annotated[str | None, Field(max_length=300)] = None
    node_id: int | None = Field(None, ge=1)
    item_id: int | None = Field(None, ge=1)
    notes: Annotated[str | None, Field(max_length=5000)] = None
    supplementary: dict[str, Any] | None = None

    @field_validator("supplementary")
    @classmethod
    def _storable(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            refuse_oversized_json("supplementary", value)
        return value


class AsBuiltSurvey(EncodableText):
    """A survey. Everything is optional: with no measured value the stored one is judged again."""

    model_config = ConfigDict(extra="forbid")

    measured_value: Text40 = None
    deviation_value: Text40 = None
    accuracy_value: Text40 = None
    accuracy_unit: Annotated[str | None, Field(max_length=30)] = None
    surveyed_on: date | None = None
    notes: Annotated[str | None, Field(max_length=5000)] = None


class AsBuiltVerify(EncodableText):
    model_config = ConfigDict(extra="forbid")

    notes: Annotated[str | None, Field(max_length=5000)] = None
    severity: Severity | None = Field(None, description="Report severity when out of tolerance; omitted: major")


class AsBuiltSign(EncodableText):
    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(True, description="False declines the attestation: the record stays verified")
    notes: Annotated[str | None, Field(max_length=5000)] = None
    signed_at: AwareDatetime | None = Field(None, description="Defaults to now")

    _range = field_validator("signed_at")(within_utc_range)


class AsBuiltRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    number: str
    title: str
    status: str
    discipline: str | None
    location: str | None
    capture_method: str
    instrument: str | None
    calibration_ref: str | None
    accuracy_class: str
    accuracy_value: str | None
    accuracy_unit: str | None
    coordinate_system: str | None
    surveyed_on: date | None
    surveyed_by_id: int | None
    criterion_id: int | None
    measured_value: str | None
    deviation_value: str | None
    tolerance_result: str
    source_kind: str
    source_ref: str | None
    deviation_map_ref: str | None
    node_id: int | None
    item_id: int | None
    notes: str | None
    verifier_notes: str | None
    report_id: int | None
    legal_record: bool
    signed_by_id: int | None
    signed_at: datetime | None
    signed_ip: str | None
    signed_digest: str | None
    signature_notes: str | None
    created_by_id: int | None
    supplementary: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None

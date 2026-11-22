from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import CertificateResult, EquipmentClass, EquipmentStatus, EquipmentType

Code = Annotated[str, Field(min_length=1, max_length=64)]
Short = Annotated[str, Field(max_length=120)]


class EquipmentCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    code: Code | None = Field(None, description="Asset / fleet number; numbered EQ-001... when omitted")
    equipment_type: EquipmentType = EquipmentType.OTHER
    equipment_class: EquipmentClass = EquipmentClass.INSTRUMENT
    requires_calibration: bool = True
    manufacturer: Short | None = None
    model: Short | None = None
    serial_number: Annotated[str, Field(max_length=128)] | None = None
    range_text: Short | None = None
    custodian_id: int | None = Field(None, ge=1)
    location: Annotated[str, Field(max_length=200)] | None = None
    interval_days: int = Field(365, ge=1, le=3650)
    reminder_days: int = Field(14, ge=0, le=365)
    notes: str | None = None


class EquipmentUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    code: Code | None = None
    equipment_type: EquipmentType | None = None
    equipment_class: EquipmentClass | None = None
    requires_calibration: bool | None = None
    manufacturer: Short | None = None
    model: Short | None = None
    serial_number: Annotated[str, Field(max_length=128)] | None = None
    range_text: Short | None = None
    custodian_id: int | None = Field(None, ge=1)
    location: Annotated[str, Field(max_length=200)] | None = None
    interval_days: int | None = Field(None, ge=1, le=3650)
    reminder_days: int | None = Field(None, ge=0, le=365)
    notes: str | None = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    name: str
    equipment_type: str
    equipment_class: str
    requires_calibration: bool
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    range_text: str | None
    custodian_id: int | None
    custodian_name: str | None = None
    location: str | None
    interval_days: int
    reminder_days: int
    last_calibrated_on: date | None
    due_on: date | None
    stored_status: str = ""
    status: str = Field("", description="in_service, due, overdue, sent_for_calibration, quarantined or out_of_service")
    days_to_due: int | None = None
    usable: bool = Field(False, description="Passes the calibration gate today")
    notes: str | None


class EquipmentStatusChange(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: EquipmentStatus
    note: Annotated[str, Field(max_length=2000)] | None = None


class CalibrationCertificateCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    certificate_number: Annotated[str, Field(min_length=1, max_length=128)]
    calibrated_on: date
    expires_on: date | None = Field(None, description="Defaults to the calibration date plus the equipment's interval")
    facility: Annotated[str, Field(max_length=255)] | None = None
    file_id: int | None = Field(None, ge=1, description="An uploaded certificate in Files")
    result: CertificateResult = CertificateResult.PASS
    notes: str | None = None


class CalibrationCertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    certificate_number: str
    calibrated_on: date
    expires_on: date
    facility: str | None
    file_id: int | None
    result: str
    is_active: bool
    notes: str | None
    recorded_by_id: int | None
    created_at: datetime | None = None


class CalibrationGateCheck(EncodableText):
    model_config = ConfigDict(extra="forbid")

    equipment_ids: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=50)]
    on_date: date | None = None


class CalibrationGateResult(BaseModel):
    ok: bool
    problems: list[str]


class CalibrationHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None


class CalibrationSummary(BaseModel):
    total: int
    in_service: int
    due: int
    overdue: int
    quarantined: int
    out_of_service: int
    sent_for_calibration: int

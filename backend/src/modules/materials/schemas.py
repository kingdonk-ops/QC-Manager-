from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.schemas import EncodableText
from .constants import CertificateType, HoldStatus, PmiResult, ProductForm, ReceiptStatus, SuppliedBy, VerificationStatus

Text120 = Annotated[str, Field(max_length=120)]
Text200 = Annotated[str, Field(max_length=200)]
Severity = Annotated[str, Field(pattern=r"^(minor|major|critical)$")]
MeasuredValue = Annotated[str, Field(max_length=40)]


class Outcome(StrEnum):
    """The pass, fail and conditional grammar shared with inspections; stored as accepted or rejected."""

    PASS = "pass"
    FAIL = "fail"
    CONDITIONAL = "conditional"


Qty = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
Values = Annotated[dict[Annotated[str, Field(max_length=40)], Any], Field(max_length=60)]


class _Body(EncodableText):
    model_config = ConfigDict(extra="forbid")


# --- receipts ----------------------------------------------------------------------------------------


class MaterialReceiptIn(_Body):
    project_id: int = Field(ge=1)
    received_on: date
    supplier: Text200 | None = None
    delivery_note: Text120 | None = None
    purchase_order_id: int | None = Field(None, ge=1)
    goods_receipt_id: int | None = Field(None, ge=1)
    notes: str | None = None


class MaterialReceiptUpdate(_Body):
    received_on: date | None = None
    supplier: Text200 | None = None
    delivery_note: Text120 | None = None
    purchase_order_id: int | None = Field(None, ge=1)
    goods_receipt_id: int | None = Field(None, ge=1)
    notes: str | None = None


class MaterialReceiptStatusIn(_Body):
    """Send a ``status`` (accepted, rejected, received) as before, or an ``outcome``: pass accepts, fail rejects,
    conditional accepts with a flag. A fail or conditional outcome (and a rejection) raises a report."""

    status: ReceiptStatus | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None
    outcome: Outcome | None = None
    criterion_id: int | None = Field(None, ge=1, description="An acceptance criterion of this project")
    measured_value: MeasuredValue | None = None
    severity: Severity | None = Field(None, description="Severity of the report raised (default major / minor)")

    @model_validator(mode="after")
    def _one_of(self) -> "MaterialReceiptStatusIn":
        if self.status is None and self.outcome is None:
            raise ValueError("Send a status or an outcome")
        return self


class MaterialReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    received_on: date
    supplier: str | None
    delivery_note: str | None
    purchase_order_id: int | None
    purchase_order_code: str | None = None
    goods_receipt_id: int | None
    status: str
    inspected_by_id: int | None
    notes: str | None
    heats: int = 0
    outcome: str | None = None
    criterion_id: int | None = None
    measured_value: str | None = None
    conditional: bool = False
    report_id: int | None = None


# --- heats -------------------------------------------------------------------------------------------


class HeatIn(_Body):
    project_id: int = Field(ge=1)
    heat_number: Annotated[str, Field(min_length=1, max_length=80)]
    material_grade: Annotated[str, Field(min_length=1, max_length=80)]
    product_form: ProductForm = ProductForm.PIPE
    description: Annotated[str, Field(max_length=300)] | None = None
    size: Annotated[str, Field(max_length=60)] | None = None
    lot_number: Annotated[str, Field(max_length=80)] | None = None
    manufacturer: Text200 | None = None
    receipt_id: int | None = Field(None, ge=1, description="Received on this MRIR; omit for material still expected")
    received_on: date | None = None
    quantity: Qty | None = None
    uom: Annotated[str, Field(max_length=20)] | None = None
    supplied_by: SuppliedBy = SuppliedBy.COMPANY
    expected_delivery: date | None = None
    planned_node_id: int | None = Field(None, ge=1, description="The work anchor this material is for")
    use_by: date | None = None
    notes: str | None = None


class HeatUpdate(_Body):
    heat_number: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    material_grade: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    product_form: ProductForm | None = None
    description: Annotated[str, Field(max_length=300)] | None = None
    size: Annotated[str, Field(max_length=60)] | None = None
    lot_number: Annotated[str, Field(max_length=80)] | None = None
    manufacturer: Text200 | None = None
    quantity: Qty | None = None
    uom: Annotated[str, Field(max_length=20)] | None = None
    supplied_by: SuppliedBy | None = None
    expected_delivery: date | None = None
    planned_node_id: int | None = Field(None, ge=1)
    use_by: date | None = None
    notes: str | None = None


class HeatReceiveIn(_Body):
    received_on: date
    receipt_id: int | None = Field(None, ge=1)
    quantity: Qty | None = None


class HeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    heat_number: str
    material_grade: str
    product_form: str
    description: str | None
    size: str | None
    lot_number: str | None
    manufacturer: str | None
    receipt_id: int | None
    receipt_code: str | None = None
    received_on: date | None
    quantity: Decimal | None
    issued_quantity: Decimal = Decimal(0)
    uom: str | None
    supplied_by: str
    expected_delivery: date | None
    planned_node_id: int | None
    status: str
    use_by: date | None
    certificate_status: str = Field(
        "none", description="none, pending_verification, verified or rejected (the best certificate)"
    )
    open_holds: int = 0
    notes: str | None


class MillCertificateIn(_Body):
    certificate_number: Annotated[str, Field(min_length=1, max_length=120)]
    certificate_type: CertificateType = CertificateType.EN_10204_3_1
    issuer: Text200 | None = None
    issued_on: date | None = None
    file_id: int | None = Field(None, ge=1, description="The uploaded MTC in Files")
    chemistry: Values = Field(default_factory=dict)
    mechanicals: Values = Field(default_factory=dict)


class CertificateVerifyIn(_Body):
    status: VerificationStatus = Field(description="verified or rejected")
    reason: Annotated[str, Field(max_length=500)] | None = None


class MillCertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    heat_id: int
    heat_number: str | None = None
    material_grade: str | None = None
    certificate_number: str
    certificate_type: str
    issuer: str | None
    issued_on: date | None
    file_id: int | None
    chemistry: dict[str, Any]
    mechanicals: dict[str, Any]
    status: str
    verified_by_id: int | None
    verified_at: datetime | None
    rejection_reason: str | None


class PmiIn(_Body):
    """Send a ``result`` (accepted, rejected) as before, or an ``outcome`` (pass, fail, conditional)."""

    tested_on: date
    result: PmiResult | None = None
    item_id: int | None = Field(None, ge=1)
    grade_found: Annotated[str, Field(max_length=80)] | None = None
    readings: Values = Field(default_factory=dict)
    equipment_id: int | None = Field(None, ge=1, description="The calibrated analyser")
    report_ref: Text120 | None = None
    notes: str | None = None
    outcome: Outcome | None = None
    criterion_id: int | None = Field(None, ge=1, description="An acceptance criterion of this project")
    measured_value: MeasuredValue | None = None
    severity: Severity | None = Field(None, description="Severity of the report raised (default major / minor)")

    @model_validator(mode="after")
    def _one_of(self) -> "PmiIn":
        if self.result is None and self.outcome is None:
            raise ValueError("Send a result or an outcome")
        if self.result is not None and self.outcome is not None:
            rejected = self.result == PmiResult.REJECTED
            if rejected != (self.outcome == Outcome.FAIL):
                raise ValueError("The result does not match the outcome")
        return self


class PmiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    heat_id: int
    tested_on: date
    result: str
    item_id: int | None
    grade_found: str | None
    readings: dict[str, Any]
    equipment_id: int | None
    report_ref: str | None
    notes: str | None
    outcome: str | None = None
    criterion_id: int | None = None
    measured_value: str | None = None
    conditional: bool = False
    report_id: int | None = None


class MaterialHoldIn(_Body):
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    ncr_id: int | None = Field(None, ge=1)


class MaterialHoldClose(_Body):
    status: HoldStatus = Field(description="released or rejected")
    disposition: Annotated[str, Field(max_length=500)] | None = None


class MaterialHoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    heat_id: int
    heat_number: str | None = None
    code: str
    reason: str
    status: str
    raised_on: date | None
    raised_by_id: int | None
    ncr_id: int | None
    disposition: str | None
    closed_by_id: int | None
    closed_at: datetime | None


class MaterialIssueIn(_Body):
    project_id: int = Field(ge=1)
    heat_id: int = Field(ge=1)
    item_id: int | None = Field(None, ge=1, description="Issue to this item (its work anchor is found)")
    node_id: int | None = Field(None, ge=1, description="Or to the work anchor on this node's path")
    issued_on: date | None = None
    quantity: Qty | None = None
    uom: Annotated[str, Field(max_length=20)] | None = None
    notes: str | None = None


class MaterialIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    heat_id: int
    heat_number: str | None = None
    node_id: int
    node_path: str | None = None
    item_id: int | None
    item_tag: str | None = None
    issued_on: date
    quantity: Decimal | None
    uom: str | None
    notes: str | None


class HeatDetail(HeatRead):
    certificates: list[MillCertificateRead] = Field(default_factory=list)
    pmi: list[PmiRead] = Field(default_factory=list)
    holds: list[MaterialHoldRead] = Field(default_factory=list)
    issues: list[MaterialIssueRead] = Field(default_factory=list)


class HeatTrace(BaseModel):
    heat: HeatRead
    certificates: list[MillCertificateRead]
    pmi: list[PmiRead]
    issues: list[MaterialIssueRead]


class ItemTrace(BaseModel):
    item_id: int
    tag: str
    node_path: str | None
    heats: list[HeatTrace]


class NodeTrace(BaseModel):
    node_id: int
    node_path: str
    heats: list[HeatTrace]


class WhereUsed(BaseModel):
    heat: HeatRead
    certificates: list[MillCertificateRead]
    issues: list[MaterialIssueRead]


class MaterialReadinessWarning(BaseModel):
    kind: str
    node_id: int
    node_path: str | None
    heat_id: int
    heat_number: str
    expected_delivery: date | None
    planned_start: date | None
    message: str


class CertificateAppendixRow(BaseModel):
    certificate_id: int
    certificate_number: str
    certificate_type: str
    status: str
    heat_id: int
    heat_number: str
    material_grade: str
    product_form: str
    issuer: str | None
    issued_on: date | None
    file_id: int | None
    node_ids: list[int]


class MaterialHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    note: str | None
    changed_at: str | None

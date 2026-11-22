from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

Code = Annotated[str, Field(min_length=1, max_length=40)]
Name = Annotated[str, Field(min_length=1, max_length=300)]
Unit = Annotated[str, Field(max_length=20)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Pct = Annotated[Decimal, Field(ge=0, le=1000, max_digits=7, decimal_places=3)]
Money = Annotated[Decimal, Field(ge=-(10**12), le=10**12, max_digits=16, decimal_places=4)]
Quantity = Annotated[Decimal, Field(ge=-(10**13), le=10**13, max_digits=18, decimal_places=4)]
Factor = Annotated[Decimal, Field(ge=0, le=10**7, max_digits=14, decimal_places=6)]
Classification = Annotated[str, Field(max_length=30)]


class BoqResourceType(StrEnum):
    MATERIAL = "material"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"


class BoqStatus(StrEnum):
    DRAFT = "draft"
    PRICED = "priced"
    LOCKED = "locked"


class BoqKind(StrEnum):
    SECTION = "section"
    POSITION = "position"


class BoqRuleset(StrEnum):
    BOQ_QUALITY = "boq_quality"
    DIN276 = "din276"
    NRM = "nrm"
    MASTERFORMAT = "masterformat"


# --- resources ---------------------------------------------------------------------------------------


class BoqResourceIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Name
    type: BoqResourceType = BoqResourceType.MATERIAL
    unit: Unit = ""
    rate: Money = Decimal(0)
    currency: Currency = "EUR"
    trade: Annotated[str | None, Field(max_length=60)] = None
    supplier_contact_id: Annotated[int | None, Field(ge=1)] = None
    notes: Annotated[str | None, Field(max_length=4000)] = None
    project_id: Annotated[int | None, Field(ge=1, description="Leave out for the global catalog")] = None
    base_id: Annotated[int | None, Field(ge=1, description="The global resource this project resource overrides")] = None


class BoqResourceUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code | None = None
    name: Name | None = None
    type: BoqResourceType | None = None
    unit: Unit | None = None
    rate: Money | None = None
    currency: Currency | None = None
    trade: Annotated[str | None, Field(max_length=60)] = None
    supplier_contact_id: Annotated[int | None, Field(ge=1)] = None
    notes: Annotated[str | None, Field(max_length=4000)] = None


class BoqResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    type: str
    unit: str
    rate: Decimal
    currency: str
    trade: str | None
    supplier_contact_id: int | None
    supplier_name: str | None = None
    notes: str | None
    project_id: int | None
    base_id: int | None


# --- assemblies -----------------------------------------------------------------------------------------


class BoqAssemblyLineIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    resource_id: int = Field(ge=1)
    factor: Factor = Decimal(1)
    waste_pct: Pct = Decimal(0)


class BoqAssemblyIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Name
    unit: Unit = ""
    description: Annotated[str | None, Field(max_length=4000)] = None
    classification: Classification | None = None
    project_id: Annotated[int | None, Field(ge=1)] = None
    lines: Annotated[list[BoqAssemblyLineIn], Field(max_length=200)] = Field(default_factory=list)


class BoqAssemblyLineRead(BaseModel):
    id: int
    resource_id: int
    code: str
    name: str
    type: str
    unit: str
    rate: Decimal
    factor: Decimal
    waste_pct: Decimal
    cost: Decimal


class BoqAssemblyRead(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    description: str | None
    classification: str | None
    project_id: int | None
    unit_rate: Decimal
    lines: list[BoqAssemblyLineRead]


# --- bills -----------------------------------------------------------------------------------------------


class BoqCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=4000)] = None


class BoqUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=4000)] = None
    overhead_pct: Pct | None = None
    profit_pct: Pct | None = None
    contingency_pct: Pct | None = None
    tax_pct: Pct | None = None


class BoqTransition(EncodableText):
    model_config = ConfigDict(extra="forbid")

    status: BoqStatus
    note: Annotated[str | None, Field(max_length=1000)] = None


class BoqSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    status: str
    currency: str
    net_total: Decimal
    grand_total: Decimal
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BoqLineRead(BaseModel):
    id: int
    resource_id: int
    code: str
    name: str
    type: str
    unit: str
    factor: Decimal
    waste_pct: Decimal
    rate_override: Decimal | None
    catalog_rate: Decimal
    rate: Decimal
    cost: Decimal


class BoqPositionRead(BaseModel):
    id: int
    parent_id: int | None
    kind: str
    ordinal: str
    depth: int
    sort: int
    code: str | None
    short_text: str
    long_text: str | None
    unit: str | None
    quantity: Decimal | None
    quantity_formula: str | None
    unit_rate: Decimal | None
    total: Decimal
    classification: str | None
    assembly_id: int | None
    has_children: bool
    resources: list[BoqLineRead]


class BoqTotals(BaseModel):
    net_total: Decimal
    overhead: Decimal
    profit: Decimal
    contingency: Decimal
    subtotal: Decimal
    tax: Decimal
    grand_total: Decimal


class BoqDetail(BoqSummary):
    classification_standard: str | None
    overhead_pct: Decimal
    profit_pct: Decimal
    contingency_pct: Decimal
    tax_pct: Decimal
    totals: BoqTotals
    can_undo: bool
    can_redo: bool
    undo_label: str | None
    redo_label: str | None
    positions: list[BoqPositionRead]


class BoqPositionFields(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str | None, Field(max_length=40)] = None
    short_text: Annotated[str | None, Field(max_length=500)] = None
    long_text: Annotated[str | None, Field(max_length=20000)] = None
    unit: Unit | None = None
    quantity: Quantity | None = None
    quantity_formula: Annotated[
        str | None, Field(max_length=200, description="Arithmetic like `2*3.5+1.2`; sets the quantity")
    ] = None
    unit_rate: Money | None = None
    classification: Classification | None = None


class BoqPositionCreate(BoqPositionFields):
    kind: BoqKind = BoqKind.POSITION
    parent_id: Annotated[int | None, Field(ge=1)] = None
    before_id: Annotated[int | None, Field(ge=1, description="Insert above this sibling")] = None
    after_id: Annotated[int | None, Field(ge=1, description="Insert below this sibling")] = None


class BoqPositionUpdate(BoqPositionFields):
    kind: BoqKind | None = None


class BoqBulkRows(EncodableText):
    """Rows pasted from a spreadsheet, inserted as siblings."""

    model_config = ConfigDict(extra="forbid")

    parent_id: Annotated[int | None, Field(ge=1)] = None
    after_id: Annotated[int | None, Field(ge=1)] = None
    rows: Annotated[list[BoqPositionFields], Field(min_length=1, max_length=2000)]


class BoqPositionMove(EncodableText):
    model_config = ConfigDict(extra="forbid")

    parent_id: Annotated[int | None, Field(ge=1, description="The new parent; leave out for the top level")] = None
    before_id: Annotated[int | None, Field(ge=1, description="Place above this sibling; leave out for last")] = None


class BoqLineIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    resource_id: int = Field(ge=1)
    factor: Factor = Decimal(1)
    waste_pct: Pct = Decimal(0)
    rate_override: Money | None = None


class BoqLineUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    factor: Factor | None = None
    waste_pct: Pct | None = None
    rate_override: Money | None = None


class BoqApplyAssembly(EncodableText):
    model_config = ConfigDict(extra="forbid")

    assembly_id: int = Field(ge=1)
    replace: bool = Field(True, description="Replace the position's resource lines rather than adding to them")


class BoqFinding(BaseModel):
    rule_id: str
    severity: Literal["error", "warning", "info"]
    message: str
    position_id: int | None


class BoqValidationReport(BaseModel):
    ruleset: str
    score: int
    errors: int
    warnings: int
    infos: int
    findings: list[BoqFinding]


class BoqImportReport(BaseModel):
    rows: int
    created: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)

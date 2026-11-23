from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

QTY = Numeric(18, 4)


class MaterialReceipt(Base, TimestampMixin):
    """A material receiving and inspection report (MRIR): one delivery, linked to a PO when procurement is on."""

    __tablename__ = "materials_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    received_on: Mapped[date] = mapped_column(Date)
    supplier: Mapped[str | None] = mapped_column(String(200), default=None)
    delivery_note: Mapped[str | None] = mapped_column(String(120), default=None)
    purchase_order_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A ``procurement`` purchase order (plain id, so materials works without procurement)."""
    goods_receipt_id: Mapped[int | None] = mapped_column(Integer, default=None)
    status: Mapped[str] = mapped_column(String(12), default="received")
    inspected_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    outcome: Mapped[str | None] = mapped_column(String(12), default=None)
    """``pass``, ``fail`` or ``conditional`` (accepted plus the flag); None until reviewed."""
    criterion_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """An inspections acceptance criterion (a plain id, so materials works without inspections)."""
    measured_value: Mapped[str | None] = mapped_column(String(40), default=None)
    conditional: Mapped[bool] = mapped_column(Boolean, default=False)
    report_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The report raised from the review (an issues record id; no foreign key)."""


class Heat(Base, TimestampMixin):
    """A heat, lot or batch: the unit of metallurgical traceability."""

    __tablename__ = "materials_heats"
    __table_args__ = (
        UniqueConstraint("project_id", "heat_number", "material_grade", name="uq_materials_heats_number_grade"),
        Index("ix_materials_heats_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    heat_number: Mapped[str] = mapped_column(String(80))
    material_grade: Mapped[str] = mapped_column(String(80))
    """E.g. A106 Gr.B, A182 F316L."""
    product_form: Mapped[str] = mapped_column(String(16), default="pipe")
    description: Mapped[str | None] = mapped_column(String(300), default=None)
    size: Mapped[str | None] = mapped_column(String(60), default=None)
    lot_number: Mapped[str | None] = mapped_column(String(80), default=None)
    manufacturer: Mapped[str | None] = mapped_column(String(200), default=None)
    receipt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("materials_receipts.id", ondelete="SET NULL"), index=True, default=None
    )
    received_on: Mapped[date | None] = mapped_column(Date, default=None)
    quantity: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    supplied_by: Mapped[str] = mapped_column(String(10), default="company")
    expected_delivery: Mapped[date | None] = mapped_column(Date, default=None)
    planned_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None
    )
    """The work anchor the (client-supplied) material is planned for: drives the late-for-work warning."""
    status: Mapped[str] = mapped_column(String(12), default="available")
    use_by: Mapped[date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class MillCertificate(Base, TimestampMixin):
    """A mill test certificate (MTC / MTR) or certificate of conformity for a heat."""

    __tablename__ = "materials_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    heat_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials_heats.id", ondelete="CASCADE"), index=True)
    certificate_number: Mapped[str] = mapped_column(String(120))
    certificate_type: Mapped[str] = mapped_column(String(8), default="3.1")
    issuer: Mapped[str | None] = mapped_column(String(200), default=None)
    issued_on: Mapped[date | None] = mapped_column(Date, default=None)
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    chemistry: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    mechanicals: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending_verification")
    verified_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    uploaded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class PmiTest(Base, TimestampMixin):
    """Positive material identification of a heat (optionally on one installed item)."""

    __tablename__ = "materials_pmi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    heat_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials_heats.id", ondelete="CASCADE"), index=True)
    tested_on: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    grade_found: Mapped[str | None] = mapped_column(String(80), default=None)
    readings: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    equipment_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The ``calibration`` analyser used (checked by the calibration gate)."""
    report_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    outcome: Mapped[str | None] = mapped_column(String(12), default=None)
    """``pass``, ``fail`` or ``conditional``; the stored ``result`` is accepted or rejected."""
    criterion_id: Mapped[int | None] = mapped_column(Integer, default=None)
    measured_value: Mapped[str | None] = mapped_column(String(40), default=None)
    conditional: Mapped[bool] = mapped_column(Boolean, default=False)
    report_id: Mapped[int | None] = mapped_column(Integer, default=None)


class MaterialIssue(Base, TimestampMixin):
    """Material of a heat issued to work: a work-anchor node and optionally an item on it."""

    __tablename__ = "materials_issues"
    __table_args__ = (
        Index("ix_materials_issues_node", "node_id"),
        Index("ix_materials_issues_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    heat_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials_heats.id", ondelete="RESTRICT"), index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="RESTRICT"))
    issued_on: Mapped[date] = mapped_column(Date)
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_items.id", ondelete="SET NULL"), default=None)
    quantity: Mapped[Decimal | None] = mapped_column(QTY, default=None)
    uom: Mapped[str | None] = mapped_column(String(20), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    issued_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class MaterialHold(Base, TimestampMixin):
    """A quarantine / non-conforming material hold on a heat."""

    __tablename__ = "materials_holds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    heat_id: Mapped[int] = mapped_column(Integer, ForeignKey("materials_heats.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="open")
    raised_on: Mapped[date | None] = mapped_column(Date, default=None)
    raised_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    ncr_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """An ``ncr`` record (plain id)."""
    disposition: Mapped[str | None] = mapped_column(String(500), default=None)
    closed_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

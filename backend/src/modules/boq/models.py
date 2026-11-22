from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

Money = Numeric(16, 2)
Rate = Numeric(16, 4)
Qty = Numeric(18, 4)
Factor = Numeric(14, 6)
Pct = Numeric(7, 3)


class Resource(Base, TimestampMixin):
    """A priced material, labour trade, piece of equipment or subcontract.

    ``project_id`` empty: the global catalog. Set: a project's own resource, or, with ``base_id``,
    the project's override of a global one (its rate replaces the global rate in that project).
    """

    __tablename__ = "boq_resources"
    __table_args__ = (Index("ix_boq_resources_project_code", "project_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="material")
    unit: Mapped[str] = mapped_column(String(20), default="")
    rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    trade: Mapped[str | None] = mapped_column(String(60), default=None)
    supplier_contact_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """A contact id (from ``contacts``, when that module runs)."""
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    """Productivity notes, e.g. "0.35 h/m on straight runs, double for bends"."""
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    base_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("boq_resources.id", ondelete="CASCADE"), index=True, default=None
    )


class Assembly(Base, TimestampMixin):
    """A reusable recipe: resources with quantity factors per unit of the assembly."""

    __tablename__ = "boq_assemblies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    classification: Mapped[str | None] = mapped_column(String(30), default=None)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )


class AssemblyLine(Base):
    __tablename__ = "boq_assembly_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    assembly_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_assemblies.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_resources.id", ondelete="CASCADE"), index=True)
    factor: Mapped[Decimal] = mapped_column(Factor, default=Decimal(1))
    waste_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Boq(Base, TimestampMixin):
    __tablename__ = "boq_boqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    overhead_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    profit_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    contingency_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    tax_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    net_total: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    grand_total: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    created_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class Position(Base, TimestampMixin):
    """A row of the bill: a section, a position, or a sub-position (any depth, by ``parent_id``).

    ``ordinal``, ``depth``, ``total`` and, when it has resource lines, ``unit_rate`` are derived
    and recomputed after every change (see ``calc``).
    """

    __tablename__ = "boq_positions"
    __table_args__ = (Index("ix_boq_positions_boq_parent", "boq_id", "parent_id", "sort"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    boq_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_boqs.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("boq_positions.id", ondelete="CASCADE"), index=True, default=None
    )
    sort: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(10), default="position")
    ordinal: Mapped[str] = mapped_column(String(60), default="")
    depth: Mapped[int] = mapped_column(Integer, default=0)
    code: Mapped[str | None] = mapped_column(String(40), default=None)
    short_text: Mapped[str] = mapped_column(String(500), default="")
    long_text: Mapped[str | None] = mapped_column(Text, default=None)
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    quantity: Mapped[Decimal | None] = mapped_column(Qty, default=None)
    quantity_formula: Mapped[str | None] = mapped_column(String(200), default=None)
    unit_rate: Mapped[Decimal | None] = mapped_column(Rate, default=None)
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    classification: Mapped[str | None] = mapped_column(String(30), default=None)
    assembly_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("boq_assemblies.id", ondelete="SET NULL"), default=None)


class PositionResource(Base):
    """A resource priced into a position: ``factor`` of the resource per unit of the position."""

    __tablename__ = "boq_position_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_positions.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_resources.id", ondelete="CASCADE"), index=True)
    factor: Mapped[Decimal] = mapped_column(Factor, default=Decimal(1))
    waste_pct: Mapped[Decimal] = mapped_column(Pct, default=Decimal(0))
    rate_override: Mapped[Decimal | None] = mapped_column(Rate, default=None)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Operation(Base, TimestampMixin):
    """One undoable change to a bill: the rows it touched, as they were before and after.

    Undo writes ``before`` back (and removes rows that only exist in ``after``); redo writes
    ``after`` back. Once something is undone, a new change discards the redo stack.
    """

    __tablename__ = "boq_operations"
    __table_args__ = (Index("ix_boq_operations_boq_seq", "boq_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    boq_id: Mapped[int] = mapped_column(Integer, ForeignKey("boq_boqs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)

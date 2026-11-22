from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.session import Base


class RecordCounter(Base):
    """The last number handed out for a prefix within a scope (a project, or the whole system)."""

    __tablename__ = "record_counters"
    __table_args__ = (UniqueConstraint("scope", "prefix", name="uq_record_counters_scope_prefix"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    scope: Mapped[str] = mapped_column(String(40))
    prefix: Mapped[str] = mapped_column(String(20))
    value: Mapped[int] = mapped_column(Integer, default=0)


class StatusChange(Base):
    """One status transition of any record, for its audit trail."""

    __tablename__ = "record_status_history"
    __table_args__ = (Index("ix_record_status_history_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    changed_by_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)


class NumberingScheme(Base):
    """How one kind of record is numbered in a project: ``{project}-{discipline}-{type}-{seq:4}``.

    ``code_lists`` maps a code token to its allowed codes (``{"discipline": [{"code": "ME", "label": "Mechanical"}]}``);
    an empty or missing list allows any short alphanumeric code. ``counter_scope`` names the code tokens the counter
    runs per (``["discipline"]``: one sequence per discipline); empty means one counter for the scheme.
    Changing a scheme never renumbers anything: numbers are stored strings.
    """

    __tablename__ = "numbering_schemes"
    __table_args__ = (UniqueConstraint("project_id", "record_kind", name="uq_numbering_schemes_project_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    record_kind: Mapped[str] = mapped_column(String(40))
    pattern: Mapped[str] = mapped_column(String(200))
    name: Mapped[str | None] = mapped_column(String(120), default=None)
    counter_scope: Mapped[list] = mapped_column(JSON, default_factory=list)
    code_lists: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    start_value: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)


class NumberingCounter(Base):
    """The last value handed out for one counter scope of a scheme (``""`` or ``"discipline=ME"``). Row-locked."""

    __tablename__ = "numbering_counters"
    __table_args__ = (UniqueConstraint("scheme_id", "scope_key", name="uq_numbering_counters_scheme_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    scheme_id: Mapped[int] = mapped_column(Integer, ForeignKey("numbering_schemes.id", ondelete="CASCADE"))
    scope_key: Mapped[str] = mapped_column(String(300))
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class AllocatedNumber(Base):
    """Every number handed out. Never deleted or reused: a voided record keeps its number."""

    __tablename__ = "numbering_allocations"
    __table_args__ = (
        UniqueConstraint("project_id", "record_kind", "number", name="uq_numbering_allocations_number"),
        Index("ix_numbering_allocations_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    record_kind: Mapped[str] = mapped_column(String(40))
    number: Mapped[str] = mapped_column(String(200))
    scheme_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("numbering_schemes.id", ondelete="SET NULL"), default=None
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    values: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    entity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    entity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    allocated_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), init=False)

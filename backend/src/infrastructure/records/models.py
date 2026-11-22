from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
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

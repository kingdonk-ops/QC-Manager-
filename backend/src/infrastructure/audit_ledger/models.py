"""The ``audit_ledger`` table: one append-only, hash-chained sequence of entries.

Rows are written once by ``record_audit`` and never changed. The ORM refuses updates and deletes
(``_refuse_changes`` below); the migration that creates the table should also make it append-only
in the database (``APPEND_ONLY_SQL``), so raw SQL can't quietly edit it either. Verification
(``verify_chain``) catches any edit that gets past both.
"""

from datetime import datetime
from typing import Any, Final

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Session, UOWTransaction, mapped_column

from ..database.session import Base

TABLE: Final = "audit_ledger"

APPEND_ONLY_SQL: Final = (
    "CREATE OR REPLACE FUNCTION audit_ledger_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$"
    " BEGIN RAISE EXCEPTION 'audit_ledger is append-only (% refused)', TG_OP; END $$",
    f"CREATE TRIGGER audit_ledger_append_only BEFORE UPDATE OR DELETE ON {TABLE}"
    " FOR EACH ROW EXECUTE FUNCTION audit_ledger_reject_change()",
    f"CREATE TRIGGER audit_ledger_no_truncate BEFORE TRUNCATE ON {TABLE}"
    " FOR EACH STATEMENT EXECUTE FUNCTION audit_ledger_reject_change()",
)
"""For the migration that creates the table (``op.execute`` each). Kept out of ``create_all`` so tests can tamper."""


class AppendOnlyError(RuntimeError):
    """An attempt to change or delete an audit ledger entry."""


class AuditEntry(Base):
    """One entry. ``hash`` = SHA-256 over the previous entry's hash and the canonical JSON of this one."""

    __tablename__ = TABLE
    __table_args__ = (
        Index("ix_audit_ledger_entity", "entity_type", "entity_id"),
        Index("ix_audit_ledger_project", "project_id"),
        Index("ix_audit_ledger_actor", "actor_id"),
        Index("ix_audit_ledger_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    project_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    before: Mapped[Any] = mapped_column(JSON)
    after: Mapped[Any] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


@event.listens_for(Session, "before_flush")
def _refuse_changes(session: Session, flush_context: UOWTransaction, instances: object) -> None:
    for obj in session.dirty:
        if isinstance(obj, AuditEntry) and session.is_modified(obj, include_collections=False):
            raise AppendOnlyError("audit ledger entries cannot be changed")
    for obj in session.deleted:
        if isinstance(obj, AuditEntry):
            raise AppendOnlyError("audit ledger entries cannot be deleted")

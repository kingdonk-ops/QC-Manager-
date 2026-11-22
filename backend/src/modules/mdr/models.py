from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class MdrDossier(Base, TimestampMixin):
    """A turnover dossier (Manufacturer's Data Record) definition: its scope and section outline."""

    __tablename__ = "mdr_dossiers"
    __table_args__ = (Index("ix_mdr_dossiers_project_code", "project_id", "code", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    scope_node_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    """Asset nodes whose subtrees the dossier covers; empty with no collections = the whole project."""
    scope_collection_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    sections: Mapped[list] = mapped_column(JSON, default_factory=list)
    """``[{key, title, enabled}]`` in print order."""
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_revision: Mapped[str | None] = mapped_column(String(10), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class MdrRevision(Base, TimestampMixin):
    """A compiled output: the latest draft, or an issued revision (A, B ... for review; 0, 1 ... final)."""

    __tablename__ = "mdr_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    dossier_id: Mapped[int] = mapped_column(Integer, ForeignKey("mdr_dossiers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    revision: Mapped[str | None] = mapped_column(String(10), default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    unsigned_file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"), default=None)
    sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    """SHA-256 of the final (signed) bytes; for a draft or an unsigned issue, of the compiled bytes."""
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    gate: Mapped[list] = mapped_column(JSON, default_factory=list)
    manifest: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    compiled_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    signed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    signature: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    """The signer's attestation: who, when, intent statement and version, method, address."""
    decided_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)

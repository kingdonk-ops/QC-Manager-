from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Transmittal(Base, TimestampMixin):
    __tablename__ = "transmittals"
    __table_args__ = (Index("ix_transmittals_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(300))
    purpose: Mapped[str] = mapped_column(String(30), default="for_information")
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    response_due: Mapped[date | None] = mapped_column(Date, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    sent_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)


class TransmittalDocument(Base, TimestampMixin):
    """One document in the bundle. Name, revision and category are kept as they were when added or sent."""

    __tablename__ = "transmittals_documents"
    __table_args__ = (Index("ix_transmittals_documents_transmittal", "transmittal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    transmittal_id: Mapped[int] = mapped_column(Integer, ForeignKey("transmittals.id", ondelete="CASCADE"))
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30), default="other")
    copies: Mapped[int] = mapped_column(Integer, default=1)


class TransmittalRecipient(Base, TimestampMixin):
    __tablename__ = "transmittals_recipients"
    __table_args__ = (Index("ix_transmittals_recipients_transmittal", "transmittal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    transmittal_id: Mapped[int] = mapped_column(Integer, ForeignKey("transmittals.id", ondelete="CASCADE"))
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(200), default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text, default=None)

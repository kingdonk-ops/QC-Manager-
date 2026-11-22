from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Handover(Base, TimestampMixin):
    """One shift's handover for an area, from the outgoing to the incoming supervisor."""

    __tablename__ = "handovers"
    __table_args__ = (
        Index("ix_handovers_project_status", "project_id", "status"),
        Index("ix_handovers_recipient_status", "recipient_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    shift_date: Mapped[date] = mapped_column(Date)
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    from_shift: Mapped[str] = mapped_column(String(10), default="day")
    to_shift: Mapped[str] = mapped_column(String(10), default="night")
    area_node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    recipient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    safety_notes: Mapped[str | None] = mapped_column(Text, default=None)
    carried_from_id: Mapped[int | None] = mapped_column(Integer, default=None)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    ack_note: Mapped[str | None] = mapped_column(Text, default=None)
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class HandoverItem(Base):
    """A line of the handover: an open item, safety note, permit in force, equipment status, work in progress or issue."""

    __tablename__ = "handover_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    handover_id: Mapped[int] = mapped_column(Integer, ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    """Permit number, equipment tag..."""
    anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("asset_nodes.id", ondelete="SET NULL"), default=None)
    link_type: Mapped[str | None] = mapped_column(String(40), default=None)
    """An outstanding issue elsewhere: ``ncr``, ``rfi``, ``task``, ``inspection``..."""
    link_id: Mapped[int | None] = mapped_column(Integer, default=None)
    link_label: Mapped[str | None] = mapped_column(String(200), default=None)
    seq: Mapped[int] = mapped_column(Integer, default=0)

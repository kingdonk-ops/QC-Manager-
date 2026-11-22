from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Correspondence(Base, TimestampMixin):
    __tablename__ = "correspondence"
    __table_args__ = (Index("ix_correspondence_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    reference: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(30), default="letter")
    custom_type: Mapped[str | None] = mapped_column(String(60), default=None)
    direction: Mapped[str] = mapped_column(String(10), default="outgoing")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    body: Mapped[str | None] = mapped_column(Text, default=None)
    external_reference: Mapped[str | None] = mapped_column(String(100), default=None)
    """The other party's own reference, for incoming items."""
    sender_contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), default=None)
    sender_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    recipient_contact_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    recipient_user_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    date_sent: Mapped[date | None] = mapped_column(Date, default=None)
    date_received: Mapped[date | None] = mapped_column(Date, default=None)
    response_required_by: Mapped[date | None] = mapped_column(Date, default=None)
    in_reply_to_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("correspondence.id", ondelete="SET NULL"), index=True, default=None
    )
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)

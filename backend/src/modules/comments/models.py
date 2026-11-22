from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), default=None)
    mentions: Mapped[list] = mapped_column(JSON, default_factory=list)
    attachment_ids: Mapped[list] = mapped_column(JSON, default_factory=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)

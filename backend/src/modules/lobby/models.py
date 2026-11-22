from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import Grant, InviteStatus, RequestStatus


class LobbyListing(Base, TimestampMixin):
    """Whether internal staff without access see the project in the lobby (off unless a project admin turns it on)."""

    __tablename__ = "lobby_listings"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_id: Mapped[int | None] = mapped_column(Integer, default=None)


class AccessRequest(Base, TimestampMixin):
    """One request by one user for one project. Decided and withdrawn rows are kept as history."""

    __tablename__ = "lobby_access_requests"
    __table_args__ = (
        Index(
            "uq_lobby_access_requests_pending",
            "user_id",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(10), default=RequestStatus.PENDING.value)
    grant: Mapped[str | None] = mapped_column(String(20), default=None)
    rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ProjectInvite(Base, TimestampMixin):
    """A single-use, expiring link to join one project, bound to one email address. Only the token's hash is kept."""

    __tablename__ = "lobby_project_invites"
    __table_args__ = (Index("ix_lobby_project_invites_email", "email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grant: Mapped[str] = mapped_column(String(20), default=Grant.MEMBER.value)
    status: Mapped[str] = mapped_column(String(10), default=InviteStatus.PENDING.value)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), default=None)
    """The account it was for, when one existed or was created."""
    created_account: Mapped[bool] = mapped_column(Boolean, default=False)
    """The invite created the account: it joins at the account's first sign-in."""
    message: Mapped[str | None] = mapped_column(Text, default=None)
    invited_by_id: Mapped[int | None] = mapped_column(Integer, default=None)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

from datetime import timedelta
from enum import StrEnum

from ...infrastructure.config.base import config

ACCESS_REQUEST_COOLDOWN_HOURS: int = config("LOBBY_ACCESS_REQUEST_COOLDOWN_HOURS", default=24, cast=int)
"""How long after a rejection before "Request again" works; 0 disables the wait."""

INVITE_TTL_HOURS: int = config("LOBBY_INVITE_TTL_HOURS", default=168, cast=int)
"""How long an invite link works (7 days)."""

PANEL_WINDOW = timedelta(days=30)
"""Decided requests stay in the requester's "Active requests" panel this long."""

MESSAGE_MAX = 1000
REASON_MAX = 500


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Grant(StrEnum):
    MEMBER = "member"
    """A direct project member row: the person reads the project, nothing more."""
    CLIENT_TEAM = "client_team"
    """Membership of the project's client team: what the client portal shows that team."""

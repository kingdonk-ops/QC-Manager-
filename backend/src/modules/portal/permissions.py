from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("portal")
class PortalPermissionName(StrEnum):
    INVITE = "portal.invite"
    """Invite external users, list them, and resend their invitations."""
    READ = "portal.read"
    """See plan reviews: staff see every review on their projects, clients the ones shared with their team."""
    SUBMIT = "portal.submit"
    """Share plans with the client for review, follow their status, and withdraw them (staff)."""
    REVIEW = "portal.review"
    """Approve, approve with comments or reject documents shared with your client team, and comment on them."""

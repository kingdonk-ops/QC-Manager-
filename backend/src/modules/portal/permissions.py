from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("portal")
class PortalPermissionName(StrEnum):
    INVITE = "portal.invite"
    """Invite external users, list them, and resend their invitations."""

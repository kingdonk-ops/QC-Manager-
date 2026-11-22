"""Team permissions."""

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("team")
class TeamPermissionName(StrEnum):
    """Permissions for teams and their members."""

    READ = "team.read"
    CREATE = "team.create"
    UPDATE = "team.update"
    DELETE = "team.delete"
    MANAGE_MEMBERS = "team.manage_members"


@register_permissions("entra")
class EntraPermissionName(StrEnum):
    """Permissions for the Entra ID integration."""

    MANAGE = "entra.manage"

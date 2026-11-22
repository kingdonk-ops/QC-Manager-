from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("platform")
class PlatformPermissionName(StrEnum):
    MODULES = "platform.modules"
    """Switch modules on and off, globally and per project."""
    ACCESS = "platform.access"
    """Set users' module access levels."""

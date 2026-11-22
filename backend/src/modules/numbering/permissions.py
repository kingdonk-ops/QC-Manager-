from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("numbering")
class NumberingPermissionName(StrEnum):
    READ = "numbering.read"
    ASSIGN = "numbering.assign"
    """Reserve a number by hand, and void one."""
    MANAGE = "numbering.manage"
    """Create and change schemes and code lists (the document controller's job)."""

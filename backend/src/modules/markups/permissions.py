from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("markups")
class MarkupPermissionName(StrEnum):
    READ = "markups.read"
    CREATE = "markups.create"
    """Mark up a drawing, and change or remove your own markups."""
    UPDATE = "markups.update"
    """Change anyone's markups and calibrations, and the project's stamp templates."""
    DELETE = "markups.delete"
    """Remove anyone's markups."""
    EXPORT = "markups.export"

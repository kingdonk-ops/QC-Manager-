from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("projects")
class ProjectPermissionName(StrEnum):
    READ = "projects.read"
    """Read every project. Without it, a user reads the projects whose client team they're in."""
    CREATE = "projects.create"
    UPDATE = "projects.update"
    DELETE = "projects.delete"
    MANAGE_ACCESS = "projects.manage_access"
    """Decide access requests, send project invites and manage direct members of the projects you can see."""

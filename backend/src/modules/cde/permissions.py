from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("cde")
class CdePermissionName(StrEnum):
    READ = "cde.read"
    UPLOAD = "cde.upload"
    TRANSITION = "cde.transition"
    REVIEW = "cde.review"
    """A task-team check: approve sharing WIP, and see the team's WIP."""
    APPROVE = "cde.approve"
    """Authorise publishing, and archive."""
    MANAGE = "cde.manage"
    """Edit the project's naming convention."""

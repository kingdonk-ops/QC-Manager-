from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("comments")
class CommentPermissionName(StrEnum):
    READ = "comments.read"
    CREATE = "comments.create"
    UPDATE = "comments.update"
    """Resolve any thread, and edit or delete anyone's comment."""

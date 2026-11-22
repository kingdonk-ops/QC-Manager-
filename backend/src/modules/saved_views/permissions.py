from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("saved_views")
class SavedViewPermissionName(StrEnum):
    READ = "saved_views.read"
    """Use the views shared with you."""
    CREATE = "saved_views.create"
    """Save, change and delete your own views."""
    SHARE = "saved_views.share"
    """Share your views with the project or with teams."""
    MANAGE = "saved_views.manage"
    """Change or delete anyone's shared views; set a register's project default."""

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("people")
class PeoplePermissionName(StrEnum):
    READ = "people.read"
    """See every user, with their roles and teams."""
    MANAGE = "people.manage"
    """Deactivate and reactivate accounts."""

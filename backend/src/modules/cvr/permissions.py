from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("cvr")
class CvrPermissionName(StrEnum):
    READ = "cvr.read"
    EDIT = "cvr.edit"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("ncr")
class NcrPermissionName(StrEnum):
    READ = "ncr.read"
    CREATE = "ncr.create"
    UPDATE = "ncr.update"
    DELETE = "ncr.delete"
    TRANSITION = "ncr.transition"
    EXPORT = "ncr.export"

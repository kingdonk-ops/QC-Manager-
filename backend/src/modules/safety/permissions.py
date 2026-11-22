from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("safety")
class SafetyPermissionName(StrEnum):
    READ = "safety.read"
    CREATE = "safety.create"
    UPDATE = "safety.update"
    DELETE = "safety.delete"
    TRANSITION = "safety.transition"
    EXPORT = "safety.export"

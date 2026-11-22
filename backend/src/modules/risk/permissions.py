from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("risk")
class RiskPermissionName(StrEnum):
    READ = "risk.read"
    CREATE = "risk.create"
    UPDATE = "risk.update"
    TRANSITION = "risk.transition"
    DELETE = "risk.delete"
    EXPORT = "risk.export"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("inspections")
class InspectionPermissionName(StrEnum):
    READ = "inspections.read"
    CREATE = "inspections.create"
    UPDATE = "inspections.update"
    DELETE = "inspections.delete"
    TRANSITION = "inspections.transition"

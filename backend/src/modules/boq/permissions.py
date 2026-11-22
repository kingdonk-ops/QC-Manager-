from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("boq")
class BoqPermissionName(StrEnum):
    READ = "boq.read"
    CREATE = "boq.create"
    UPDATE = "boq.update"
    DELETE = "boq.delete"
    IMPORT = "boq.import"
    EXPORT = "boq.export"
    APPROVE = "boq.approve"
    """Lock and unlock a bill."""

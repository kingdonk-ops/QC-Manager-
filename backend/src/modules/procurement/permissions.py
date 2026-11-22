from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("procurement")
class ProcurementPermissionName(StrEnum):
    READ = "procurement.read"
    CREATE = "procurement.create"
    UPDATE = "procurement.update"
    SUBMIT = "procurement.submit"
    """Send a purchase order to its supplier."""
    TRANSITION = "procurement.transition"
    """Record goods receipts; close or cancel a purchase order."""
    APPROVE = "procurement.approve"
    """Send a purchase order whose gross total is over its approval threshold."""
    DELETE = "procurement.delete"
    EXPORT = "procurement.export"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("handover")
class HandoverPermissionName(StrEnum):
    READ = "handover.read"
    CREATE = "handover.create"
    UPDATE = "handover.update"
    DELETE = "handover.delete"
    SUBMIT = "handover.submit"
    """Hand over to the incoming supervisor (the outgoing one)."""
    RESPOND = "handover.respond"
    """Acknowledge a handover addressed to you (the incoming one)."""
    EXPORT = "handover.export"

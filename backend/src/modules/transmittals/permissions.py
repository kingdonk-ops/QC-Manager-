from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("transmittals")
class TransmittalPermissionName(StrEnum):
    READ = "transmittals.read"
    CREATE = "transmittals.create"
    UPDATE = "transmittals.update"
    DELETE = "transmittals.delete"
    SUBMIT = "transmittals.submit"
    """Send a transmittal."""

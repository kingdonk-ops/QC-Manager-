from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("claims")
class ClaimPermissionName(StrEnum):
    READ = "claims.read"
    CREATE = "claims.create"
    UPDATE = "claims.update"
    DELETE = "claims.delete"
    SUBMIT = "claims.submit"
    APPROVE = "claims.approve"
    """Record the client's certification and payment."""
    EXPORT = "claims.export"

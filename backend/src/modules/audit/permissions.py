from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("audit")
class AuditPermissionName(StrEnum):
    READ = "audit.read"
    """Browse the ledger and verify the chain."""
    EXPORT = "audit.export"

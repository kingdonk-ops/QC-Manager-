from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("scaffolds")
class ScaffoldPermissionName(StrEnum):
    READ = "scaffolds.read"
    CREATE = "scaffolds.create"
    """Request a scaffold, a modification, a dismantle or an inspection (any project member)."""
    UPDATE = "scaffolds.update"
    """Edit the register: location, dimensions, custodian, interval, hire rate; record weather events."""
    TRANSITION = "scaffolds.transition"
    """Record erection and dismantling progress (scaffold supervisor)."""
    APPROVE = "scaffolds.approve"
    """Approve or reject build, modification and dismantle requests (scaffold coordinator)."""
    INSPECT = "scaffolds.inspect"
    """Inspect and tag a scaffold (competent person / scaffold inspector)."""
    DELETE = "scaffolds.delete"
    EXPORT = "scaffolds.export"

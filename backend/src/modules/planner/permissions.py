from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("planner")
class PlannerPermissionName(StrEnum):
    READ = "planner.read"
    CREATE = "planner.create"
    UPDATE = "planner.update"
    DELETE = "planner.delete"
    ASSIGN = "planner.assign"
    """Put crews on work anchors and days (the board)."""
    TRANSITION = "planner.transition"
    """Issue, start, close or cancel a plan; move work packs through readiness."""
    EXPORT = "planner.export"

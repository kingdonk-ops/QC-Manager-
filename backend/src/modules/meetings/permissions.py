from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("meetings")
class MeetingPermissionName(StrEnum):
    READ = "meetings.read"
    CREATE = "meetings.create"
    UPDATE = "meetings.update"
    DELETE = "meetings.delete"
    TRANSITION = "meetings.transition"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("schedule")
class SchedulePermissionName(StrEnum):
    READ = "schedule.read"
    CREATE = "schedule.create"
    UPDATE = "schedule.update"
    DELETE = "schedule.delete"
    IMPORT = "schedule.import"
    EXPORT = "schedule.export"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("tasks")
class TaskPermissionName(StrEnum):
    READ = "tasks.read"
    CREATE = "tasks.create"
    UPDATE = "tasks.update"
    DELETE = "tasks.delete"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("rfi")
class RfiPermissionName(StrEnum):
    READ = "rfi.read"
    CREATE = "rfi.create"
    UPDATE = "rfi.update"
    DELETE = "rfi.delete"
    RESPOND = "rfi.respond"
    TRANSITION = "rfi.transition"
    EXPORT = "rfi.export"

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("correspondence")
class CorrespondencePermissionName(StrEnum):
    READ = "correspondence.read"
    CREATE = "correspondence.create"
    UPDATE = "correspondence.update"
    DELETE = "correspondence.delete"
    EXPORT = "correspondence.export"

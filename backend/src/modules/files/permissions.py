from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("files")
class FilePermissionName(StrEnum):
    READ = "files.read"
    UPLOAD = "files.upload"
    DELETE = "files.delete"

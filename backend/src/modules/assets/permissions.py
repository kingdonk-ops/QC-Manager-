from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("assets")
class AssetPermissionName(StrEnum):
    READ = "assets.read"
    CREATE = "assets.create"
    UPDATE = "assets.update"
    DELETE = "assets.delete"
    IMPORT = "assets.import"
    EXPORT = "assets.export"

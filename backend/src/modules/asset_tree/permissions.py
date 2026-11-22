from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("asset_tree")
class AssetTreePermissionName(StrEnum):
    READ = "asset_tree.read"
    CREATE = "asset_tree.create"
    UPDATE = "asset_tree.update"
    DELETE = "asset_tree.delete"
    IMPORT = "asset_tree.import"
    CONFIGURE = "asset_tree.configure"
    """Edit levels, item types and apply packs."""

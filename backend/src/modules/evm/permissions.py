from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("evm")
class EvmPermissionName(StrEnum):
    READ = "evm.read"
    CREATE = "evm.create"
    UPDATE = "evm.update"
    DELETE = "evm.delete"
    IMPORT = "evm.import"
    EXPORT = "evm.export"

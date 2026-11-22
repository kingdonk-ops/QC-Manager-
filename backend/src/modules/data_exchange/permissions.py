from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("data_exchange")
class DataExchangePermissionName(StrEnum):
    EXPORT = "data_exchange.export"
    """Export the datasets you may read. Each dataset also needs its own module's permission."""
    IMPORT = "data_exchange.import"
    """Use the import wizard. Each importer also needs its own module's permission (e.g. ``cvr.edit``)."""

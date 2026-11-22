from enum import StrEnum


class ComponentStatus(StrEnum):
    PLANNED = "planned"
    INSTALLED = "installed"
    COMMISSIONED = "commissioned"
    IN_SERVICE = "in_service"
    DECOMMISSIONED = "decommissioned"


COMPONENT_FLOW: dict[str, set[str]] = {
    "planned": {"installed", "decommissioned"},
    "installed": {"planned", "commissioned", "decommissioned"},
    "commissioned": {"installed", "in_service", "decommissioned"},
    "in_service": {"commissioned", "decommissioned"},
    "decommissioned": {"in_service"},
}


class AssetKind(StrEnum):
    """COBie AssetType: whether a product is built in or can be moved."""

    FIXED = "Fixed"
    MOVEABLE = "Moveable"


ENTITY_COMPONENT = "asset"
"""Files attached to a component use this ``entity_type``."""
ENTITY_TYPE = "asset_type"
"""Files attached to a product type use this ``entity_type``."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"


class ClassificationStandard(StrEnum):
    DIN_276 = "din276"
    NRM = "nrm"
    MASTERFORMAT = "masterformat"
    UNIFORMAT = "uniformat"
    UNICLASS = "uniclass"
    CUSTOM = "custom"


REGIONS: dict[str, dict[str, str]] = {
    "AU": {"name": "Australia", "currency": "AUD", "classification": "nrm"},
    "NZ": {"name": "New Zealand", "currency": "NZD", "classification": "nrm"},
    "UK": {"name": "United Kingdom", "currency": "GBP", "classification": "nrm"},
    "DACH": {"name": "Germany / Austria / Switzerland", "currency": "EUR", "classification": "din276"},
    "EU": {"name": "Europe (other)", "currency": "EUR", "classification": "uniclass"},
    "US": {"name": "United States", "currency": "USD", "classification": "masterformat"},
    "CA": {"name": "Canada", "currency": "CAD", "classification": "masterformat"},
    "GULF": {"name": "Gulf states", "currency": "AED", "classification": "nrm"},
    "SEA": {"name": "South-East Asia", "currency": "SGD", "classification": "nrm"},
}
"""What a region implies by default: its currency and classification standard."""

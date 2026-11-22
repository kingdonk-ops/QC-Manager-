from enum import StrEnum


class CdeState(StrEnum):
    WIP = "wip"
    SHARED = "shared"
    PUBLISHED = "published"
    ARCHIVED = "archived"


SUITABILITY: dict[str, dict[str, str]] = {
    CdeState.WIP: {"S0": "Initial status (work in progress)"},
    CdeState.SHARED: {
        "S1": "Suitable for coordination",
        "S2": "Suitable for information",
        "S3": "Suitable for review and comment",
        "S4": "Suitable for stage approval",
    },
    CdeState.PUBLISHED: {
        **{f"A{n}": f"Authorised and accepted, stage {n}" for n in range(1, 10)},
        "CR": "As constructed record",
    },
}
"""The suitability codes each state accepts. Archived keeps the code it had."""

FLOW: dict[str, set[str]] = {
    CdeState.WIP: {CdeState.SHARED.value, CdeState.ARCHIVED.value},
    CdeState.SHARED: {CdeState.WIP.value, CdeState.PUBLISHED.value, CdeState.ARCHIVED.value},
    CdeState.PUBLISHED: {CdeState.ARCHIVED.value},
    CdeState.ARCHIVED: set(),
}

ENTITY = "cde_document"

CHARSETS = {"alnum": str.isalnum, "alpha": str.isalpha, "numeric": str.isdigit}

ISO_TYPES = {
    "AF": "Animation file",
    "BQ": "Bill of quantities",
    "CA": "Calculations",
    "CM": "Combined model",
    "CO": "Correspondence",
    "CP": "Cost plan",
    "CR": "Clash rendition",
    "DB": "Database",
    "DR": "Drawing",
    "FN": "File note",
    "HS": "Health and safety",
    "IE": "Information exchange file",
    "M2": "2D model",
    "M3": "3D model",
    "MI": "Minutes / action notes",
    "MR": "Model rendition",
    "MS": "Method statement",
    "PP": "Presentation",
    "PR": "Programme",
    "RD": "Room data sheet",
    "RI": "Request for information",
    "RP": "Report",
    "SA": "Schedule of accommodation",
    "SH": "Schedule",
    "SN": "Snagging list",
    "SP": "Specification",
    "SU": "Survey",
    "VS": "Visualisation",
}

ISO_ROLES = {
    "A": "Architect",
    "B": "Building surveyor",
    "C": "Civil engineer",
    "D": "Drainage, highways engineer",
    "E": "Electrical engineer",
    "F": "Facilities manager",
    "G": "Geographical and land surveyor",
    "H": "Heating and ventilation designer",
    "I": "Interior designer",
    "K": "Client",
    "L": "Landscape architect",
    "M": "Mechanical engineer",
    "P": "Public health engineer",
    "Q": "Quantity surveyor",
    "S": "Structural engineer",
    "T": "Town and country planner",
    "W": "Contractor",
    "X": "Subcontractor",
    "Y": "Specialist designer",
    "Z": "General (non-disciplinary)",
}


def _codes(table: dict[str, str]) -> list[dict[str, str]]:
    return [{"code": c, "description": d} for c, d in table.items()]


DEFAULT_CONVENTION: dict = {
    "separator": "-",
    "require_share_approval": True,
    "fields": [
        {"key": "project", "label": "Project", "codes": [], "min_length": 2, "max_length": 6, "charset": "alnum"},
        {"key": "originator", "label": "Originator", "codes": [], "min_length": 3, "max_length": 6, "charset": "alnum"},
        {"key": "volume", "label": "Volume / system", "codes": [], "min_length": 2, "max_length": 2, "charset": "alnum"},
        {"key": "level", "label": "Level / location", "codes": [], "min_length": 2, "max_length": 2, "charset": "alnum"},
        {"key": "type", "label": "Type", "codes": _codes(ISO_TYPES), "min_length": 2, "max_length": 2, "charset": "alnum"},
        {"key": "role", "label": "Role", "codes": _codes(ISO_ROLES), "min_length": 1, "max_length": 2, "charset": "alpha"},
        {"key": "number", "label": "Number", "codes": [], "min_length": 4, "max_length": 6, "charset": "numeric"},
    ],
}
"""BS EN ISO 19650-2 UK annex style: ``PRJ-ORG-ZZ-XX-DR-A-0001``."""

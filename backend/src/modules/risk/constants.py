from decimal import Decimal
from enum import StrEnum


class RiskCategory(StrEnum):
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    SCHEDULE = "schedule"
    REGULATORY = "regulatory"
    ENVIRONMENTAL = "environmental"
    SAFETY = "safety"
    COMMERCIAL = "commercial"


class Impact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResponseType(StrEnum):
    AVOID = "avoid"
    MITIGATE = "mitigate"
    TRANSFER = "transfer"
    ACCEPT = "accept"


class RiskStatus(StrEnum):
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    MITIGATING = "mitigating"
    CLOSED = "closed"
    OCCURRED = "occurred"


FLOW: dict[str, set[str]] = {
    RiskStatus.IDENTIFIED: {RiskStatus.ASSESSED, RiskStatus.MITIGATING, RiskStatus.CLOSED, RiskStatus.OCCURRED},
    RiskStatus.ASSESSED: {RiskStatus.IDENTIFIED, RiskStatus.MITIGATING, RiskStatus.CLOSED, RiskStatus.OCCURRED},
    RiskStatus.MITIGATING: {RiskStatus.ASSESSED, RiskStatus.CLOSED, RiskStatus.OCCURRED},
    RiskStatus.OCCURRED: {RiskStatus.MITIGATING, RiskStatus.CLOSED},
    RiskStatus.CLOSED: {RiskStatus.IDENTIFIED},
}
"""Closed reopens to identified; a risk that occurred is managed (mitigating) or closed."""

OPEN_STATUSES = (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED, RiskStatus.MITIGATING, RiskStatus.OCCURRED)


class Band(StrEnum):
    RARE = "rare"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    ALMOST_CERTAIN = "almost_certain"


BANDS: list[tuple[Band, str, Decimal, Decimal]] = [
    (Band.RARE, "Rare", Decimal("0.1"), Decimal("0.2")),
    (Band.UNLIKELY, "Unlikely", Decimal("0.3"), Decimal("0.4")),
    (Band.POSSIBLE, "Possible", Decimal("0.5"), Decimal("0.5")),
    (Band.LIKELY, "Likely", Decimal("0.6"), Decimal("0.7")),
    (Band.ALMOST_CERTAIN, "Almost certain", Decimal("0.8"), Decimal("0.9")),
]
"""Probability bands of the matrix, lowest first: (key, label, min, max), both inclusive."""


def band_of(probability: Decimal) -> Band:
    for key, _, low, high in BANDS:
        if low <= probability <= high:
            return key
    return Band.ALMOST_CERTAIN if probability > Decimal("0.9") else Band.RARE

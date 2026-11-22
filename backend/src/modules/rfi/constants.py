from enum import StrEnum


class RfiStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"
    VOID = "void"


class Party(StrEnum):
    CONTRACTOR = "contractor"
    DESIGNER = "designer"
    CLIENT = "client"
    CONSULTANT = "consultant"
    SUBCONTRACTOR = "subcontractor"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


FLOW: dict[str, set[str]] = {
    RfiStatus.DRAFT: {RfiStatus.OPEN, RfiStatus.VOID},
    RfiStatus.OPEN: {RfiStatus.ANSWERED, RfiStatus.VOID},
    RfiStatus.ANSWERED: {RfiStatus.CLOSED, RfiStatus.OPEN, RfiStatus.VOID},
    RfiStatus.CLOSED: {RfiStatus.VOID},
    RfiStatus.VOID: set(),
}
"""Answered goes back to open for a follow-up question; anything but void can be voided."""

DEFAULT_DUE_DAYS = 7
ENTITY = "rfi"
RESPONSE_ENTITY = "rfi_response"

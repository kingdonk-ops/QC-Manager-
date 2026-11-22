from enum import StrEnum


class CorrespondenceType(StrEnum):
    LETTER = "letter"
    EMAIL = "email"
    NOTICE = "notice"
    INSTRUCTION = "instruction"
    CLAIM = "claim"
    EXTENSION_OF_TIME = "extension_of_time"
    OTHER = "other"
    """A custom type, named in ``custom_type``."""


class Direction(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class CorrespondenceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    RECEIVED = "received"
    RESPONSE_REQUIRED = "response_required"
    RESPONDED = "responded"
    CLOSED = "closed"


S = CorrespondenceStatus
FLOW: dict[str, set[str]] = {
    S.DRAFT: {S.SENT, S.RECEIVED, S.RESPONSE_REQUIRED, S.CLOSED},
    S.SENT: {S.RESPONSE_REQUIRED, S.RESPONDED, S.CLOSED},
    S.RECEIVED: {S.RESPONSE_REQUIRED, S.RESPONDED, S.CLOSED},
    S.RESPONSE_REQUIRED: {S.RESPONDED, S.CLOSED},
    S.RESPONDED: {S.RESPONSE_REQUIRED, S.CLOSED},
    S.CLOSED: {S.RESPONSE_REQUIRED},
}

ENTITY = "correspondence"

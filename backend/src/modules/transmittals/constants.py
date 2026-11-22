from enum import StrEnum


class Purpose(StrEnum):
    FOR_INFORMATION = "for_information"
    FOR_REVIEW = "for_review"
    FOR_APPROVAL = "for_approval"
    FOR_CONSTRUCTION = "for_construction"
    AS_REQUESTED = "as_requested"


class TransmittalStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_ACKNOWLEDGED = "partially_acknowledged"
    ACKNOWLEDGED = "acknowledged"


PURPOSE_LABELS = {
    Purpose.FOR_INFORMATION: "For information",
    Purpose.FOR_REVIEW: "For review",
    Purpose.FOR_APPROVAL: "For approval",
    Purpose.FOR_CONSTRUCTION: "For construction",
    Purpose.AS_REQUESTED: "As requested",
}

ENTITY = "transmittal"

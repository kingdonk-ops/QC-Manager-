from enum import StrEnum


class PoStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CLOSED = "closed"
    CANCELLED = "cancelled"


FLOW: dict[str, set[str]] = {
    PoStatus.DRAFT: {PoStatus.SENT, PoStatus.CANCELLED},
    PoStatus.SENT: {PoStatus.PARTIALLY_RECEIVED, PoStatus.FULLY_RECEIVED, PoStatus.CLOSED, PoStatus.CANCELLED},
    PoStatus.PARTIALLY_RECEIVED: {PoStatus.FULLY_RECEIVED, PoStatus.CLOSED},
    PoStatus.FULLY_RECEIVED: {PoStatus.PARTIALLY_RECEIVED, PoStatus.CLOSED},
    PoStatus.CLOSED: set(),
    PoStatus.CANCELLED: set(),
}

MANUAL_TARGETS = {PoStatus.CLOSED, PoStatus.CANCELLED}
"""Sending and receiving set the other statuses."""

COMMITTED = (PoStatus.SENT, PoStatus.PARTIALLY_RECEIVED, PoStatus.FULLY_RECEIVED, PoStatus.CLOSED)
"""Statuses whose value counts as committed."""

AWAITING = (PoStatus.SENT, PoStatus.PARTIALLY_RECEIVED)
"""Statuses with deliveries still to come."""

RECEIVABLE = (PoStatus.SENT, PoStatus.PARTIALLY_RECEIVED, PoStatus.FULLY_RECEIVED)

RECEIPT_ENTITY = "goods_receipt"
"""The ``files`` entity type of a goods receipt's photos."""

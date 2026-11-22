from enum import StrEnum


class CardStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class Source(StrEnum):
    SITE_INSTRUCTION = "site_instruction"
    CLIENT_DIRECTION = "client_direction"
    FIELD_FINDING = "field_finding"
    OTHER = "other"


class ChangeType(StrEnum):
    SCOPE_INCREASE = "scope_increase"
    DESCOPE = "descope"
    SCOPE_CHANGE = "scope_change"
    ALREADY_DONE = "already_done"
    NOT_FOUND = "not_found"
    NEEDS_ASSESSMENT = "needs_assessment"
    CLIENT_TO_CONFIRM = "client_to_confirm"


FLOW: dict[str, set[str]] = {
    CardStatus.DRAFT: {CardStatus.SUBMITTED, CardStatus.WITHDRAWN},
    CardStatus.SUBMITTED: {
        CardStatus.ACKNOWLEDGED,
        CardStatus.APPROVED,
        CardStatus.REJECTED,
        CardStatus.WITHDRAWN,
        CardStatus.DRAFT,
    },
    CardStatus.ACKNOWLEDGED: {CardStatus.APPROVED, CardStatus.REJECTED, CardStatus.WITHDRAWN},
    CardStatus.APPROVED: set(),
    CardStatus.REJECTED: {CardStatus.DRAFT},
    CardStatus.EXPIRED: {CardStatus.SUBMITTED, CardStatus.WITHDRAWN},
    CardStatus.WITHDRAWN: {CardStatus.DRAFT},
    CardStatus.CONVERTED: set(),
}
"""Moves through ``PATCH /status``. ``expired`` is set only by the daily expiry and ``converted`` only by
``/convert``; resubmitting an expired card starts a new 14 days."""

WAITING = (CardStatus.SUBMITTED, CardStatus.ACKNOWLEDGED)
"""Waiting for the client: these expire."""
DECISIONS = {CardStatus.APPROVED, CardStatus.REJECTED}
EDITABLE = {CardStatus.DRAFT}
EXPIRES_AFTER_DAYS = 14
REMIND_BEFORE_DAYS = 3

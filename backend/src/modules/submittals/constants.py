from enum import StrEnum


class SubmittalType(StrEnum):
    SHOP_DRAWING = "shop_drawing"
    PRODUCT_DATA = "product_data"
    SAMPLE = "sample"
    METHOD_STATEMENT = "method_statement"
    TEST_REPORT = "test_report"
    OM_MANUAL = "om_manual"


class SubmittalStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    APPROVED_AS_NOTED = "approved_as_noted"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    REJECTED = "rejected"
    CLOSED = "closed"


class Decision(StrEnum):
    APPROVED = "approved"
    APPROVED_AS_NOTED = "approved_as_noted"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    REJECTED = "rejected"


class ReviewState(StrEnum):
    PENDING = "pending"
    """Its step hasn't opened yet."""
    OPEN = "open"
    DECIDED = "decided"
    SKIPPED = "skipped"
    """The review ended before this reviewer decided."""


SEVERITY: dict[str, int] = {
    Decision.APPROVED: 0,
    Decision.APPROVED_AS_NOTED: 1,
    Decision.REVISE_AND_RESUBMIT: 2,
    Decision.REJECTED: 3,
}
"""Higher is more severe; the outcome of a step is its most severe decision."""

ENDS_REVIEW = {Decision.REVISE_AND_RESUBMIT.value, Decision.REJECTED.value}

IN_REVIEW = {SubmittalStatus.SUBMITTED.value, SubmittalStatus.UNDER_REVIEW.value}
OPEN_STATUSES = {
    SubmittalStatus.DRAFT.value,
    SubmittalStatus.SUBMITTED.value,
    SubmittalStatus.UNDER_REVIEW.value,
    SubmittalStatus.REVISE_AND_RESUBMIT.value,
}
"""Statuses that still need something to happen; only these can be overdue."""

_OUTCOMES = {d.value for d in Decision}

FLOW: dict[str, set[str]] = {
    SubmittalStatus.DRAFT: {SubmittalStatus.SUBMITTED.value},
    SubmittalStatus.SUBMITTED: {SubmittalStatus.UNDER_REVIEW.value, *_OUTCOMES},
    SubmittalStatus.UNDER_REVIEW: set(_OUTCOMES),
    SubmittalStatus.APPROVED: {SubmittalStatus.CLOSED.value},
    SubmittalStatus.APPROVED_AS_NOTED: {
        SubmittalStatus.CLOSED.value,
        SubmittalStatus.DRAFT.value,
        SubmittalStatus.SUBMITTED.value,
    },
    SubmittalStatus.REVISE_AND_RESUBMIT: {SubmittalStatus.DRAFT.value, SubmittalStatus.SUBMITTED.value},
    SubmittalStatus.REJECTED: {
        SubmittalStatus.CLOSED.value,
        SubmittalStatus.DRAFT.value,
        SubmittalStatus.SUBMITTED.value,
    },
    SubmittalStatus.CLOSED: set(),
}
"""Allowed status changes. Revising goes back to draft, or straight to submitted."""

REVISABLE = {
    SubmittalStatus.APPROVED_AS_NOTED.value,
    SubmittalStatus.REVISE_AND_RESUBMIT.value,
    SubmittalStatus.REJECTED.value,
}


def revision_letter(number: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, like spreadsheet columns."""
    letters = ""
    n = number + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters

from enum import StrEnum


class Reason(StrEnum):
    CLIENT_REQUEST = "client_request"
    DESIGN_CHANGE = "design_change"
    UNFORESEEN_CONDITION = "unforeseen_condition"
    REGULATORY = "regulatory"
    ERROR_OMISSION = "error_omission"
    OTHER = "other"


class CoStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class CvrApply(StrEnum):
    """Which forecast of the linked cost heads an approved change order moves."""

    NONE = "none"
    VALUE = "value"
    COST = "cost"
    BOTH = "both"


FLOW: dict[str, set[str]] = {
    CoStatus.DRAFT: {CoStatus.SUBMITTED, CoStatus.WITHDRAWN},
    CoStatus.SUBMITTED: {CoStatus.UNDER_REVIEW, CoStatus.APPROVED, CoStatus.REJECTED, CoStatus.WITHDRAWN},
    CoStatus.UNDER_REVIEW: {CoStatus.APPROVED, CoStatus.REJECTED, CoStatus.WITHDRAWN},
    CoStatus.REJECTED: {CoStatus.DRAFT},
    CoStatus.WITHDRAWN: {CoStatus.DRAFT},
    CoStatus.APPROVED: set(),
}
"""A rejected or withdrawn change order goes back to draft to be revised; approval is final."""

DECISIONS = {CoStatus.UNDER_REVIEW, CoStatus.APPROVED, CoStatus.REJECTED}
"""Targets only holders of ``change_orders.approve`` may set."""

EDITABLE = {CoStatus.DRAFT}
"""Lines and header change only while drafting."""

PENDING = (CoStatus.SUBMITTED, CoStatus.UNDER_REVIEW)

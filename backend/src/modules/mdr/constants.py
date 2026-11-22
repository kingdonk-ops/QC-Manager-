from enum import StrEnum

ENTITY = "mdr_dossier"
"""Files attached to a dossier with this entity type are its custom uploads."""
OUTPUT_ENTITY = "mdr_output"
"""Compiled outputs, stored as one file revision chain per dossier."""
INTENT_STATEMENT = (
    "I confirm that this dossier revision is complete and correct to the best of my knowledge, "
    "and I sign it on behalf of the contractor."
)
INTENT_VERSION = "1"


class DossierStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    """A review revision (A, B ...) is with the client."""
    RETURNED = "returned"
    """The client rejected the latest review revision."""
    ACCEPTED = "accepted"
    """The client accepted the latest review revision: Rev 0 may be issued."""
    FINAL = "final"


class IssuePurpose(StrEnum):
    REVIEW = "review"
    FINAL = "final"


class RevisionKind(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    FINAL = "final"


class RevisionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_SIGNATURE = "pending_signature"
    ISSUED = "issued"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MdrDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


CAN_ISSUE: dict[str, set[str]] = {
    IssuePurpose.REVIEW: {DossierStatus.DRAFT, DossierStatus.IN_REVIEW, DossierStatus.RETURNED},
    IssuePurpose.FINAL: {DossierStatus.ACCEPTED, DossierStatus.FINAL},
}
"""Which dossier statuses each issue purpose starts from."""


def revision_label(kind: str, index: int) -> str:
    """The ``index``-th (0-based) revision of a kind: review A, B ... Z, AA ...; final 0, 1, 2 ..."""
    if kind == RevisionKind.FINAL:
        return str(index)
    label = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        label = chr(65 + rem) + label
    return label

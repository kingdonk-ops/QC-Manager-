"""Pure signatory rules: how many distinct people have signed a line, the bound on the required count and the wording
of a refusal.

The unit of counting is the signing person, never the signature: one person signing twice, in the same or in
different roles, counts once. Only a valid signature that still covers the record's current content counts; a
provisional, void or rejected one and the hold release signature never do. Plain values in, plain values out: this
file imports neither the web framework nor the database layer."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .constants import SignatureRole, SignatureStatus

MIN_REQUIRED = 1
MAX_REQUIRED = 10
DEFAULT_REQUIRED = 1
RANGE_MESSAGE = f"The required signatory count is a whole number from {MIN_REQUIRED} to {MAX_REQUIRED}."


@dataclass(frozen=True)
class SignatureFact:
    """What the counting needs to know about one stored signature."""

    signer_user_id: int | None
    role: str
    status: str
    covers_current: bool
    """True when the signature's content digest equals the record's current content digest."""


def counts_toward_total(fact: SignatureFact) -> bool:
    """Valid, over current content, by a known person, and not the hold release."""
    return (
        fact.signer_user_id is not None
        and fact.status == SignatureStatus.VALID.value
        and fact.covers_current
        and fact.role != SignatureRole.HOLD_RELEASE.value
    )


def distinct_signers(facts: list[SignatureFact]) -> list[int]:
    """The distinct signing people, in the order they first signed."""
    seen: dict[int, None] = {}
    for fact in facts:
        if fact.signer_user_id is not None and counts_toward_total(fact):
            seen.setdefault(fact.signer_user_id, None)
    return list(seen)


def collected_count(facts: list[SignatureFact], *, extra_signer: int | None = None) -> int:
    """Distinct counted people, plus a prospective signer who is not already counted."""
    people = set(distinct_signers(facts))
    if extra_signer is not None:
        people.add(extra_signer)
    return len(people)


def collected_from_rows(rows: Iterable[Any], current_hash: str) -> int:
    """Distinct counted people from objects that carry the signature fields (a stored row or a read model)."""
    return collected_count([SignatureFact(r.signer_user_id, r.role, r.status, r.content_sha256 == current_hash) for r in rows])


def signer_roles(facts: list[SignatureFact]) -> list[dict[str, Any]]:
    """Each counted person with the roles they signed in, both in order of first appearance."""
    roles: dict[int, list[str]] = {}
    for fact in facts:
        if fact.signer_user_id is not None and counts_toward_total(fact):
            held = roles.setdefault(fact.signer_user_id, [])
            if fact.role not in held:
                held.append(fact.role)
    return [{"user_id": user_id, "roles": held} for user_id, held in roles.items()]


def is_met(collected: int, required: int) -> bool:
    return collected >= required


def shortfall_message(collected: int, required: int) -> str:
    """The refusal wording: collected over required."""
    return f"Not enough distinct signers: {collected} collected of {required} required."


def required_count_error(value: Any) -> str | None:
    """Why a required count is unacceptable (None when it is fine). Omitted means the default; a boolean, a
    non-integer or a number outside one to ten is refused."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return RANGE_MESSAGE
    if value < MIN_REQUIRED or value > MAX_REQUIRED:
        return RANGE_MESSAGE
    return None


def normalise_required(value: Any) -> int:
    """The bounded required count, the default when omitted; raises ``ValueError`` when it is out of range."""
    error = required_count_error(value)
    if error:
        raise ValueError(error)
    return DEFAULT_REQUIRED if value is None else int(value)

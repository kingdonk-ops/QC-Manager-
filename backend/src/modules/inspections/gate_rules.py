"""Pure gate rules: the default blocking flag, the attachment pair check, authority ranking, which kinds may be
waived, and the canonical release snapshot with its SHA-256 digest.

The digest uses the destination's canonical JSON hashing helper (the one inspection signatures use), so it does not
depend on key order. This file otherwise imports neither the web framework nor the database layer."""

from typing import Any

from .constants import Authority, GateKind
from .signing import sha256_of

AUTHORITY_ORDER: tuple[str, ...] = (
    Authority.QUALITY_CONTROL.value,
    Authority.QUALITY_ASSURANCE.value,
    Authority.CLIENT.value,
    Authority.THIRD_PARTY_INSPECTOR.value,
    Authority.JURISDICTION.value,
)
"""Ascending: a later level may release anything an earlier level may."""
WAIVABLE_KINDS = frozenset({GateKind.WITNESS.value, GateKind.SURVEILLANCE.value, GateKind.REVIEW.value})
PAIR_MESSAGE = "Give the attachment kind and the attachment identifier together, or neither."


def default_blocks_progress(kind: str | None) -> bool:
    """A hold blocks; witness, surveillance and review only advise."""
    return kind == GateKind.HOLD.value


def blocks_progress(kind: str | None, explicit: bool | None) -> bool:
    """An explicit flag wins on any kind; otherwise the kind decides."""
    return default_blocks_progress(kind) if explicit is None else explicit


def attachment_pair_error(kind: Any, identifier: Any) -> str | None:
    """A gate with only half of its attachment could never be found by the can-proceed query."""
    if (kind is None) != (identifier is None):
        return PAIR_MESSAGE
    return None


def authority_rank(level: str | None) -> int:
    """Position in the ascending order; an unknown level ranks below every real one."""
    return AUTHORITY_ORDER.index(level) if level in AUTHORITY_ORDER else -1


def authority_satisfies(asserted: str | None, required: str | None) -> bool:
    """An asserted level meets a requirement when it is equal or higher; an unknown level never does."""
    return authority_rank(asserted) >= 0 and authority_rank(asserted) >= authority_rank(required)


def is_waivable(kind: str | None) -> bool:
    """Hold is the only kind that is never waived."""
    return kind in WAIVABLE_KINDS


def release_snapshot(
    number: str,
    kind: str,
    inspection_id: int | None,
    attachment_kind: str | None,
    attachment_id: int | None,
    level: str,
) -> dict[str, Any]:
    """What a release digest covers: the gate's identity and the level it was released at."""
    return {
        "number": number,
        "kind": kind,
        "inspection_id": inspection_id,
        "attachment": [attachment_kind, attachment_id],
        "level": level,
    }


def release_digest(snapshot: dict[str, Any]) -> str:
    """64 hexadecimal characters; the same content gives the same digest whatever the key order."""
    return sha256_of(snapshot)

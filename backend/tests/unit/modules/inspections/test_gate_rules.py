"""Gate rules: default blocking flag, attachment pair, authority ranking, waivable kinds and the release digest."""

import re

import pytest

from src.modules.inspections.constants import Authority, GateKind
from src.modules.inspections.gate_rules import (
    AUTHORITY_ORDER,
    PAIR_MESSAGE,
    attachment_pair_error,
    authority_rank,
    authority_satisfies,
    blocks_progress,
    default_blocks_progress,
    is_waivable,
    release_digest,
    release_snapshot,
)

QC = Authority.QUALITY_CONTROL.value
QA = Authority.QUALITY_ASSURANCE.value
CLIENT = Authority.CLIENT.value
THIRD_PARTY = Authority.THIRD_PARTY_INSPECTOR.value
AHJ = Authority.JURISDICTION.value


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("hold", True), ("witness", False), ("surveillance", False), ("review", False)],
)
def test_only_a_hold_blocks_when_no_flag_is_given(kind: str, expected: bool):
    assert default_blocks_progress(kind) is expected
    assert blocks_progress(kind, None) is expected


def test_an_explicit_flag_wins_on_any_kind():
    assert blocks_progress("witness", True) is True
    assert blocks_progress("surveillance", True) is True
    assert blocks_progress("hold", False) is False


@pytest.mark.parametrize(("kind", "identifier"), [("node", None), (None, 7)])
def test_half_an_attachment_is_rejected(kind: str | None, identifier: int | None):
    assert attachment_pair_error(kind, identifier) == PAIR_MESSAGE


@pytest.mark.parametrize(("kind", "identifier"), [("node", 7), (None, None), ("dossier", 1)])
def test_both_or_neither_of_the_attachment_pass(kind: str | None, identifier: int | None):
    assert attachment_pair_error(kind, identifier) is None


def test_the_authority_order_is_ascending_and_complete():
    assert AUTHORITY_ORDER == (QC, QA, CLIENT, THIRD_PARTY, AHJ)
    assert [authority_rank(level) for level in AUTHORITY_ORDER] == [0, 1, 2, 3, 4]
    assert set(AUTHORITY_ORDER) == {a.value for a in Authority}


@pytest.mark.parametrize(
    ("asserted", "required", "expected"),
    [
        (QC, AHJ, False),  # quality control cannot release an authority gate
        (AHJ, QA, True),  # a higher level releases a lower gate
        (QA, THIRD_PARTY, False),
        (AHJ, THIRD_PARTY, True),
        (THIRD_PARTY, THIRD_PARTY, True),  # equal is enough
        (QA, QA, True),
        (QC, QA, False),
        (CLIENT, QA, True),
        (QA, CLIENT, False),
    ],
)
def test_an_asserted_level_satisfies_an_equal_or_lower_requirement(asserted: str, required: str, expected: bool):
    assert authority_satisfies(asserted, required) is expected


def test_an_unknown_level_never_satisfies_anything():
    assert authority_rank("site manager") == -1
    assert authority_satisfies("site manager", QC) is False
    assert authority_satisfies(None, QC) is False


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("witness", True), ("surveillance", True), ("review", True), ("hold", False), ("other", False), (None, False)],
)
def test_every_kind_but_hold_is_waivable(kind: str | None, expected: bool):
    assert is_waivable(kind) is expected


def test_the_waivable_kinds_are_the_vocabulary_without_the_hold():
    assert {k.value for k in GateKind if is_waivable(k.value)} == {"witness", "surveillance", "review"}


def _snapshot(level: str = QA) -> dict:
    return release_snapshot("GATE-001", "hold", 12, "node", 5, level)


def test_the_digest_is_64_hexadecimal_characters():
    assert re.fullmatch(r"[0-9a-f]{64}", release_digest(_snapshot()))


def test_the_digest_does_not_depend_on_key_order():
    snapshot = _snapshot()
    reordered = dict(reversed(list(snapshot.items())))
    assert list(reordered) != list(snapshot)
    assert release_digest(reordered) == release_digest(snapshot)


def test_the_digest_changes_with_the_released_level_and_with_every_other_field():
    base = release_digest(_snapshot())
    assert release_digest(_snapshot(AHJ)) != base
    assert release_digest(release_snapshot("GATE-002", "hold", 12, "node", 5, QA)) != base
    assert release_digest(release_snapshot("GATE-001", "witness", 12, "node", 5, QA)) != base
    assert release_digest(release_snapshot("GATE-001", "hold", 13, "node", 5, QA)) != base
    assert release_digest(release_snapshot("GATE-001", "hold", 12, "item", 5, QA)) != base
    assert release_digest(release_snapshot("GATE-001", "hold", 12, "node", 6, QA)) != base


def test_the_snapshot_holds_the_identity_and_the_released_level():
    assert _snapshot() == {
        "number": "GATE-001",
        "kind": "hold",
        "inspection_id": 12,
        "attachment": ["node", 5],
        "level": QA,
    }

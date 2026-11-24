"""Signatory rules: distinct people are counted, never signatures; only valid signatures over current content count;
the required count is bounded; the refusal wording shows collected over required."""

import pytest

from src.modules.inspections.constants import SignatureRole, SignatureStatus
from src.modules.inspections.signatory_rules import (
    DEFAULT_REQUIRED,
    MAX_REQUIRED,
    MIN_REQUIRED,
    RANGE_MESSAGE,
    SignatureFact,
    collected_count,
    counts_toward_total,
    distinct_signers,
    is_met,
    normalise_required,
    required_count_error,
    shortfall_message,
    signer_roles,
)

INSPECTOR = SignatureRole.INSPECTOR.value
REVIEWER = SignatureRole.REVIEWER.value
ADDITIONAL = SignatureRole.ADDITIONAL_SIGNATORY.value
HOLD_RELEASE = SignatureRole.HOLD_RELEASE.value
CLIENT = SignatureRole.CLIENT.value
VALID = SignatureStatus.VALID.value


def fact(user: int | None, role: str = INSPECTOR, status: str = VALID, covers: bool = True) -> SignatureFact:
    return SignatureFact(signer_user_id=user, role=role, status=status, covers_current=covers)


def test_one_person_signing_in_two_roles_counts_once():
    facts = [fact(7, INSPECTOR), fact(7, ADDITIONAL)]
    assert distinct_signers(facts) == [7]
    assert collected_count(facts) == 1


def test_one_person_signing_twice_in_the_same_role_counts_once():
    assert collected_count([fact(7, ADDITIONAL), fact(7, ADDITIONAL)]) == 1


def test_a_second_different_person_makes_two():
    facts = [fact(7, INSPECTOR), fact(7, ADDITIONAL), fact(8, ADDITIONAL)]
    assert distinct_signers(facts) == [7, 8]
    assert collected_count(facts) == 2


def test_the_order_of_first_signing_is_kept():
    assert distinct_signers([fact(9), fact(3), fact(9), fact(5)]) == [9, 3, 5]


@pytest.mark.parametrize("status", ["provisional", "void", "rejected"])
def test_signatures_that_are_not_valid_add_nothing(status: str):
    assert counts_toward_total(fact(7, CLIENT, status=status)) is False
    assert collected_count([fact(7, CLIENT, status=status)]) == 0


def test_the_hold_release_signature_never_counts():
    assert counts_toward_total(fact(7, HOLD_RELEASE)) is False
    assert collected_count([fact(7, HOLD_RELEASE), fact(8, INSPECTOR)]) == 1


def test_a_signature_over_content_that_has_changed_adds_nothing():
    assert counts_toward_total(fact(7, INSPECTOR, covers=False)) is False
    assert collected_count([fact(7, INSPECTOR, covers=False), fact(8, REVIEWER)]) == 1


def test_a_signature_without_a_known_person_adds_nothing():
    assert collected_count([fact(None, INSPECTOR)]) == 0


def test_a_prospective_signer_counts_once_and_not_twice():
    facts = [fact(7, INSPECTOR)]
    assert collected_count(facts, extra_signer=8) == 2
    assert collected_count(facts, extra_signer=7) == 1
    assert collected_count([], extra_signer=7) == 1


def test_signer_roles_lists_each_person_once_with_all_their_roles():
    facts = [fact(7, INSPECTOR), fact(8, ADDITIONAL), fact(7, ADDITIONAL), fact(7, ADDITIONAL), fact(9, HOLD_RELEASE)]
    assert signer_roles(facts) == [
        {"user_id": 7, "roles": [INSPECTOR, ADDITIONAL]},
        {"user_id": 8, "roles": [ADDITIONAL]},
    ]


def test_is_met_compares_collected_with_required():
    assert is_met(2, 2) is True
    assert is_met(3, 2) is True
    assert is_met(1, 2) is False


def test_the_refusal_wording_shows_collected_over_required():
    message = shortfall_message(1, 2)
    assert "1 collected of 2 required" in message


@pytest.mark.parametrize("value", list(range(MIN_REQUIRED, MAX_REQUIRED + 1)))
def test_one_through_ten_are_accepted(value: int):
    assert required_count_error(value) is None
    assert normalise_required(value) == value


def test_an_omitted_count_means_one():
    assert required_count_error(None) is None
    assert normalise_required(None) == DEFAULT_REQUIRED == 1


@pytest.mark.parametrize("value", [0, 11, -1, 100, 2.5, 2.0, "3", True, False, [2]])
def test_zero_eleven_and_non_integers_are_rejected(value: object):
    assert required_count_error(value) == RANGE_MESSAGE
    with pytest.raises(ValueError, match="whole number"):
        normalise_required(value)

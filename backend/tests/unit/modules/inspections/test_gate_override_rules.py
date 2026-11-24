"""Gate override rules: splitting pending gates into overridden and plain, and the can-proceed verdict, which lets
overridden gates through only for a dossier attachment. The annotation never changes the release digest."""

from types import SimpleNamespace

import pytest

from src.modules.inspections.constants import AttachmentKind
from src.modules.inspections.gate_rules import (
    is_overridden,
    proceed_allowed,
    release_digest,
    release_snapshot,
    split_overridden,
)

DOSSIER = AttachmentKind.DOSSIER.value
OTHER_KINDS = [k.value for k in AttachmentKind if k != AttachmentKind.DOSSIER]


def gate(number: str, override_id: int | None = None) -> SimpleNamespace:
    ref = None if override_id is None else f"OVR-{override_id}"
    return SimpleNamespace(number=number, override_id=override_id, override_ref=ref)


def test_a_gate_is_overridden_only_when_it_carries_an_override_identifier():
    assert is_overridden(gate("G-1", 7)) is True
    assert is_overridden(gate("G-2")) is False
    assert is_overridden(SimpleNamespace(number="G-3")) is False  # an old row without the column reads as plain


def test_pending_gates_split_into_overridden_and_plain_in_the_order_given():
    first, second, third = gate("G-1", 7), gate("G-2", 7), gate("G-3")
    overridden, plain = split_overridden([first, third, second])
    assert [g.number for g in overridden] == ["G-1", "G-2"]
    assert [g.number for g in plain] == ["G-3"]


def test_an_empty_list_splits_into_two_empty_lists():
    assert split_overridden([]) == ([], [])


def test_a_dossier_attachment_proceeds_when_only_overridden_gates_remain():
    assert proceed_allowed(DOSSIER, plain=0, overridden=1) is True
    assert proceed_allowed(DOSSIER, plain=0, overridden=3) is True


def test_a_plain_pending_gate_still_stops_a_dossier():
    assert proceed_allowed(DOSSIER, plain=1, overridden=2) is False  # a gate created after the override is plain


@pytest.mark.parametrize("kind", OTHER_KINDS)
def test_every_other_attachment_kind_still_stops_on_an_overridden_gate(kind: str):
    assert proceed_allowed(kind, plain=0, overridden=1) is False
    assert proceed_allowed(kind, plain=0, overridden=0) is True


def test_hold_points_stop_progress_whatever_the_overrides():
    assert proceed_allowed(DOSSIER, plain=0, overridden=1, holds=1) is False
    assert proceed_allowed("inspection", plain=0, overridden=0, holds=2) is False
    assert proceed_allowed("inspection", plain=0, overridden=0, holds=0) is True


def test_without_any_gate_every_kind_proceeds():
    for kind in (DOSSIER, *OTHER_KINDS, None):
        assert proceed_allowed(kind, 0, 0) is True


def test_the_release_digest_does_not_depend_on_an_annotation():
    snapshot = release_snapshot("GATE-001", "hold", None, "dossier", 5, "contractor_qa")
    assert "override_id" not in snapshot and "override_ref" not in snapshot
    again = release_snapshot("GATE-001", "hold", None, "dossier", 5, "contractor_qa")
    assert release_digest(snapshot) == release_digest(again)

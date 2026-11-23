"""The pure rules of the recycle bin and the hidden Deleted folder: what 'no history beyond creation' means, where a
deleted draft goes, retention bounds, when the purge may remove a record, and when a restore is refused. The pinned
moments below are fixed; nothing reads the clock and no database is needed."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.modules.temporary_works.constants import (
    BIN,
    DEFAULT_RETENTION_DAYS,
    FOLDER,
    MAX_RETENTION_DAYS,
    MIN_RETENTION_DAYS,
)
from src.modules.temporary_works.deletion_rules import (
    BAD_RETENTION,
    ITEM_DELETED,
    ITEM_LINK_FIELDS,
    NOT_DELETED,
    PERMIT_LINK_FIELDS,
    RecordHistory,
    count_links,
    deletion_destination,
    has_history_beyond_creation,
    in_bin,
    purge_due,
    purge_on,
    restore_refusal,
    retention_days,
    retention_refusal,
)

DELETED = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)


def history(actions: Any = (), changes: Any = 0, permits: Any = 0, links: Any = 0) -> RecordHistory:
    return RecordHistory(actions, changes, permits, links)


# --- what counts as history beyond creation -----------------------------------------------------------------------


def test_a_record_with_nothing_but_its_creation_has_no_history_beyond_it():
    assert not has_history_beyond_creation(history())
    assert not has_history_beyond_creation(history(["temporary_works.item.created"]))
    assert deletion_destination(history()) == BIN


@pytest.mark.parametrize("verb", ["deleted", "restored", "purged", "created"])
def test_the_bins_own_steps_and_the_creation_are_not_history(verb: str):
    assert not has_history_beyond_creation(history([f"temporary_works.item.{verb}"]))
    assert not has_history_beyond_creation(history(["temporary_works.permit.deleted", "temporary_works.permit.restored"]))


@pytest.mark.parametrize(
    "verb", ["returned_to_draft", "loaded", "in_use", "on_hold", "issued", "active", "closed", "expired", "breach", "updated"]
)
def test_any_other_audit_entry_is_history_and_sends_the_record_to_the_folder(verb: str):
    assert has_history_beyond_creation(history([f"temporary_works.item.{verb}"]))
    assert has_history_beyond_creation(history(["temporary_works.item.created", f"temporary_works.item.{verb}"]))
    assert deletion_destination(history([f"temporary_works.item.{verb}"])) == FOLDER


def test_a_status_change_a_permit_or_a_link_is_history():
    assert has_history_beyond_creation(history(changes=1))
    assert has_history_beyond_creation(history(changes=4))
    assert has_history_beyond_creation(history(permits=1))  # a deleted permit counts too: the caller counts every row
    assert has_history_beyond_creation(history(links=1))
    assert deletion_destination(history(permits=2)) == FOLDER


def test_a_fact_that_is_missing_malformed_or_negative_reads_as_history():
    for bad in (None, -1, "0", 0.0, True, [], object()):
        assert has_history_beyond_creation(history(changes=bad)), bad
        assert has_history_beyond_creation(history(permits=bad)), bad
        assert has_history_beyond_creation(history(links=bad)), bad
    assert has_history_beyond_creation(history(actions=None))  # not a list of actions at all
    assert has_history_beyond_creation(history(actions=[None]))
    assert has_history_beyond_creation(history(actions=[42]))
    assert deletion_destination(history(changes=None)) == FOLDER


def test_the_history_has_no_default_so_a_missing_fact_cannot_read_as_none():
    with pytest.raises(TypeError):
        RecordHistory()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RecordHistory(audit_actions=[], status_changes=0, permits=0)  # type: ignore[call-arg]


def test_the_history_can_be_fed_any_iterable_of_actions():
    assert not has_history_beyond_creation(history(iter(["temporary_works.item.deleted"])))
    assert has_history_beyond_creation(history(a for a in ["temporary_works.item.loaded"]))
    assert has_history_beyond_creation(history(("temporary_works.item.loaded",)))


# --- links ---------------------------------------------------------------------------------------------------------


def test_the_item_links_are_the_scaffold_and_the_cross_references_and_the_permit_link_is_the_inspection():
    assert ITEM_LINK_FIELDS == ("scaffold_id", "related_refs")
    assert PERMIT_LINK_FIELDS == ("inspection_id",)


def test_a_link_counts_only_when_it_is_set():
    bare = SimpleNamespace(scaffold_id=None, related_refs={})
    assert count_links(bare, ITEM_LINK_FIELDS) == 0
    assert count_links(SimpleNamespace(scaffold_id=4, related_refs={}), ITEM_LINK_FIELDS) == 1
    assert count_links(SimpleNamespace(scaffold_id=4, related_refs={"drawing": "D-1"}), ITEM_LINK_FIELDS) == 2
    assert count_links(SimpleNamespace(scaffold_id=None, related_refs={"drawing": "D-1"}), ITEM_LINK_FIELDS) == 1
    assert count_links(SimpleNamespace(inspection_id=None), PERMIT_LINK_FIELDS) == 0
    assert count_links(SimpleNamespace(inspection_id=9), PERMIT_LINK_FIELDS) == 1
    assert count_links(SimpleNamespace(), ITEM_LINK_FIELDS) == 0  # a field the record does not have is not set
    assert count_links(SimpleNamespace(scaffold_id="", related_refs=[]), ITEM_LINK_FIELDS) == 0


# --- retention -----------------------------------------------------------------------------------------------------


def test_the_retention_defaults_to_thirty_days_with_a_maximum_of_sixty():
    assert (DEFAULT_RETENTION_DAYS, MAX_RETENTION_DAYS, MIN_RETENTION_DAYS) == (30, 60, 1)
    assert retention_days(None) == 30


@pytest.mark.parametrize("days", [1, 7, 30, 59, 60])
def test_a_retention_inside_the_range_is_kept_and_accepted(days: int):
    assert retention_days(days) == days
    assert retention_refusal(days) is None


@pytest.mark.parametrize("bad", [0, -5, 61, 365, None, "30", 30.0, True, [30]])
def test_a_retention_outside_the_range_or_not_a_whole_number_is_refused_and_reads_as_the_default(bad: Any):
    refusal = retention_refusal(bad)
    assert refusal is not None
    assert refusal.rule == BAD_RETENTION
    assert retention_days(bad) == DEFAULT_RETENTION_DAYS


# --- the purge -----------------------------------------------------------------------------------------------------


def test_a_bin_record_becomes_due_exactly_when_its_retention_has_passed():
    due = DELETED + timedelta(days=30)
    assert purge_on(DELETED, 30) == due
    assert not purge_due(BIN, DELETED, 30, due - timedelta(seconds=1))
    assert purge_due(BIN, DELETED, 30, due)  # the moment itself is due
    assert purge_due(BIN, DELETED, 30, due + timedelta(days=400))


def test_the_retention_in_force_decides_not_a_fixed_thirty_days():
    now = DELETED + timedelta(days=10)
    assert not purge_due(BIN, DELETED, 30, now)
    assert purge_due(BIN, DELETED, 7, now)
    assert not purge_due(BIN, DELETED, 60, DELETED + timedelta(days=59))
    assert purge_due(BIN, DELETED, 60, DELETED + timedelta(days=60))
    assert not purge_due(BIN, DELETED, 999, DELETED + timedelta(days=29))  # a bad value is the default, not forever


def test_the_deleted_folder_and_anything_of_unknown_kind_is_never_due():
    forever = DELETED + timedelta(days=5000)
    assert not purge_due(FOLDER, DELETED, 30, forever)
    for kind in (None, "", "BIN", "trash", 0):
        assert not purge_due(kind, DELETED, 30, forever), kind
    assert in_bin(BIN)
    assert not any(in_bin(kind) for kind in (FOLDER, None, "", "Bin"))


def test_a_record_with_no_deletion_time_is_never_due():
    for missing in (None, "2026-03-01", 5):
        assert purge_on(missing, 30) is None
        assert not purge_due(BIN, missing, 30, DELETED + timedelta(days=500)), missing


def test_a_naive_time_is_read_as_utc():
    naive = datetime(2026, 3, 1, 9, 30)
    assert purge_on(naive, 30) == DELETED + timedelta(days=30)
    assert purge_due(BIN, naive, 30, datetime(2026, 3, 31, 9, 30))


# --- restore -------------------------------------------------------------------------------------------------------


def test_a_deleted_record_can_be_restored_and_a_live_one_cannot():
    assert restore_refusal(DELETED) is None
    refused = restore_refusal(None)
    assert refused is not None
    assert refused.rule == NOT_DELETED


def test_a_permit_cannot_be_restored_while_its_item_is_still_deleted():
    assert restore_refusal(DELETED, parent_deleted=False) is None
    refused = restore_refusal(DELETED, parent_deleted=True)
    assert refused is not None
    assert refused.rule == ITEM_DELETED
    both = restore_refusal(None, parent_deleted=True)  # not deleted is named first
    assert both is not None
    assert both.rule == NOT_DELETED

"""The draft-only delete and the return-to-draft rules of the user decision that replaced the earlier delete guard: the pure
rules, the soft-delete columns and the migration chained after the register revision, the dedicated permissions and the
purity of the rule files. The recycle bin rules are in their own test file. No database is needed."""

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from src.modules.temporary_works import service
from src.modules.temporary_works.constants import DRAFT_ITEM_STATUS, ITEM_STATUSES, PERMIT_STATUSES
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from src.modules.temporary_works.permissions import TemporaryWorksPermissionName
from src.modules.temporary_works.transitions import (
    ALREADY_DRAFT,
    HAS_PERMITS,
    NOT_DRAFT,
    REASON_REQUIRED,
    UNKNOWN_STATUS,
    item_delete_refusal,
    item_return_to_draft,
    permit_delete_refusal,
    permit_return_to_draft,
)

BACKEND = Path(__file__).resolve().parents[4]
VERSIONS = BACKEND / "migrations" / "versions"
MODULE = BACKEND / "src" / "modules" / "temporary_works"
REVISION = "d8c3f1a6e925"
PARENT = "c4a7e1d9b352"
NEXT = "e7b4d2a9c150"


def rule(finding: Any) -> str | None:
    return finding.rule if finding is not None else None


# --- return to draft ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [s for s in ITEM_STATUSES if s != DRAFT_ITEM_STATUS])
def test_an_item_in_any_other_status_can_be_returned_to_draft_with_a_reason(status: str):
    assert item_return_to_draft(status, "Design withdrawn") is None


def test_an_item_cannot_be_returned_to_draft_without_a_reason_or_when_it_already_is_one_or_is_unknown():
    for reason in (None, "", "   ", 5):
        assert rule(item_return_to_draft("loaded", reason)) == REASON_REQUIRED, reason
    assert rule(item_return_to_draft(DRAFT_ITEM_STATUS, "Because")) == ALREADY_DRAFT
    for status in ("bogus", None, 3):
        assert rule(item_return_to_draft(status, "Because")) == UNKNOWN_STATUS, status


@pytest.mark.parametrize("status", [s for s in PERMIT_STATUSES if s != "draft"])
def test_a_permit_in_any_other_status_can_be_returned_to_draft_with_a_reason(status: str):
    assert permit_return_to_draft(status, "Dates were wrong") is None


def test_a_permit_cannot_be_returned_to_draft_without_a_reason_or_when_it_already_is_one_or_is_unknown():
    for reason in (None, "", "  "):
        assert rule(permit_return_to_draft("issued", reason)) == REASON_REQUIRED, reason
    assert rule(permit_return_to_draft("draft", "Because")) == ALREADY_DRAFT
    assert rule(permit_return_to_draft("bogus", "Because")) == UNKNOWN_STATUS


# --- delete ---------------------------------------------------------------------------------------------------


def test_only_an_item_in_draft_with_no_remaining_permit_can_be_deleted():
    assert item_delete_refusal(DRAFT_ITEM_STATUS, 0) is None
    assert rule(item_delete_refusal(DRAFT_ITEM_STATUS, 1)) == HAS_PERMITS
    assert rule(item_delete_refusal(DRAFT_ITEM_STATUS, 3)) == HAS_PERMITS


@pytest.mark.parametrize("status", [s for s in ITEM_STATUSES if s != DRAFT_ITEM_STATUS])
def test_an_item_that_is_not_in_draft_is_never_deleted_not_even_an_early_one(status: str):
    assert rule(item_delete_refusal(status, 0)) == NOT_DRAFT  # design brief included: the earlier default is replaced


def test_an_unknown_item_status_reads_as_not_draft_and_refuses_the_delete():
    for status in ("bogus", None, ""):
        assert rule(item_delete_refusal(status, 0)) == NOT_DRAFT, status


def test_only_a_draft_permit_can_be_deleted():
    assert permit_delete_refusal("draft") is None
    for status in (*[s for s in PERMIT_STATUSES if s != "draft"], "bogus", None):
        assert rule(permit_delete_refusal(status)) == NOT_DRAFT, status


# --- the permission -------------------------------------------------------------------------------------------


def test_return_to_draft_is_its_own_permission_in_lower_snake_case_separate_from_edit():
    name = TemporaryWorksPermissionName("temporary_works.return_to_draft")
    assert re.fullmatch(r"[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*", name.value)
    assert name is not TemporaryWorksPermissionName.UPDATE


def test_restore_is_its_own_permission_separate_from_delete_and_return_to_draft():
    name = TemporaryWorksPermissionName("temporary_works.restore")
    assert re.fullmatch(r"[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*", name.value)
    assert name not in (TemporaryWorksPermissionName.DELETE, TemporaryWorksPermissionName.RETURN_TO_DRAFT)


# --- the tombstone columns and the migration --------------------------------------------------------------------


@pytest.mark.parametrize("model", [TemporaryWorksItem, TemporaryWorksPermit])
def test_each_table_carries_a_nullable_tombstone_marker_and_the_deleting_user(model: Any):
    columns = model.__table__.columns
    assert columns["deleted_at"].nullable
    assert columns["deleted_by_id"].nullable
    assert "deleted_by_id" not in {c.name for fk in model.__table__.foreign_keys for c in [fk.parent]}


def test_a_new_row_is_not_deleted():
    item = TemporaryWorksItem(project_id=1, reference="TW-1", title="Props", family="propping")
    permit = TemporaryWorksPermit(project_id=1, item_id=2, number="P-1", kind="load")
    assert (item.deleted_at, item.deleted_by_id) == (None, None)
    assert (permit.deleted_at, permit.deleted_by_id) == (None, None)


def _revisions() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in VERSIONS.glob("*.py"):
        values: dict[str, Any] = {}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                if node.target.id in ("revision", "down_revision"):
                    values[node.target.id] = ast.literal_eval(node.value)
        parent = values.get("down_revision")
        found[str(values["revision"])] = {parent} if isinstance(parent, str) else set(parent or ())
    return found


def test_the_soft_delete_revision_is_chained_after_the_register_revision_and_the_recycle_bin_revision_follows_it():
    revisions = _revisions()
    assert revisions[REVISION] == {PARENT}
    assert [r for r, parents in revisions.items() if PARENT in parents] == [REVISION]
    assert [r for r, parents in revisions.items() if REVISION in parents] == [NEXT]
    heads = set(revisions) - set().union(*revisions.values())
    assert len(heads) == 1, heads  # the repository invariant: exactly one head
    ancestors: set[str] = set()
    pending = list(heads)
    while pending:
        for parent in revisions[pending.pop()]:
            if parent not in ancestors:
                ancestors.add(parent)
                pending.append(parent)
    assert NEXT in ancestors or heads == {NEXT}  # the recycle bin revision is at or below the head


def test_the_downgrade_drops_exactly_the_columns_the_upgrade_adds():
    source = (VERSIONS / f"{REVISION}_temporary_works_soft_delete.py").read_text()
    functions = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    assert set(functions) == {"upgrade", "downgrade"}
    text = {name: ast.unparse(node) for name, node in functions.items()}
    for attribute in ("create_table", "drop_table", "create_index", "drop_index"):
        assert attribute not in text["upgrade"] + text["downgrade"], attribute  # additive columns only
    assert "add_column" in text["upgrade"]
    assert "drop_column" in text["downgrade"]
    assert "add_column" not in text["downgrade"]
    assert "drop_column" not in text["upgrade"]
    for column in ("deleted_at", "deleted_by_id"):
        assert column in text["upgrade"]
        assert column in text["downgrade"]


# --- helpers and purity -----------------------------------------------------------------------------------------


def test_a_creator_that_is_not_a_well_formed_identifier_is_stored_as_absent():
    assert service.creator_of(7) == 7
    for bad in (0, -3, None, True, "5", 4.0):
        assert service.creator_of(bad) is None, bad


@pytest.mark.parametrize("name", ["rules.py", "validation.py", "transitions.py", "constants.py", "deletion_rules.py"])
def test_the_pure_rule_files_import_neither_the_web_framework_nor_the_database_layer(name: str):
    banned = {"fastapi", "starlette", "sqlalchemy", "pydantic", "fastcrud"}
    imported: set[str] = set()
    for node in ast.walk(ast.parse((MODULE / name).read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert "infrastructure" not in (node.module or ""), name  # no relative reach into the database layer
            elif node.module:
                imported.add(node.module.split(".")[0])
    assert not imported & banned, (name, imported & banned)


@pytest.mark.parametrize("name", [p.name for p in sorted(MODULE.glob("*.py"))])
def test_no_module_file_grows_past_the_code_line_limit(name: str):
    assert len((MODULE / name).read_text().splitlines()) <= 500, name

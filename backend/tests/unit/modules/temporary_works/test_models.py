"""Temporary works tables: constraints, cascade, no stored derived values, defaults, the migration chain and the
module's manifest and permission names. No database is needed."""

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Integer, UniqueConstraint

from src.infrastructure.database.session import Base
from src.infrastructure.modules.loader import installed_modules
from src.modules.temporary_works.manifest import manifest
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from src.modules.temporary_works.permissions import TemporaryWorksPermissionName

BACKEND = Path(__file__).resolve().parents[4]
VERSIONS = BACKEND / "migrations" / "versions"
REVISION = "c4a7e1d9b352"
PARENT = "b2e6a8c4f017"

ITEM_COLUMNS = set(
    """id project_id reference title family description design_check_category designer checker coordinator_name
    coordinator_user_id status held_from required_load_on required_strike_on design_due_on location asset_node_id
    sort_order notes scaffold_id related_refs created_by_id breach_notified_on deleted_at deleted_by_id deleted_kind
    created_at updated_at""".split()
)
PERMIT_COLUMNS = set(
    """id project_id item_id number kind status issued_by_name issued_on valid_from valid_to closed_on closed_by_id
    inspection_id design_check_accepted inspection_passed conditions created_by_id expiry_notified_on deleted_at
    deleted_by_id deleted_kind created_at updated_at""".split()
)


def table(model: type) -> Any:
    return model.__table__  # type: ignore[attr-defined]


def column_names(model: type) -> set[str]:
    return {c.name for c in table(model).columns}


def unique_sets(model: type) -> set[tuple[str, ...]]:
    return {tuple(c.name for c in u.columns) for u in table(model).constraints if isinstance(u, UniqueConstraint)}


def foreign_keys(model: type) -> dict[str, str | None]:
    """Column name to the ondelete rule of its foreign key."""
    out: dict[str, str | None] = {}
    for constraint in table(model).constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            for element in constraint.elements:
                out[element.parent.name] = constraint.ondelete
    return out


# --- the tables ---------------------------------------------------------------------------------------------


def test_the_two_tables_are_registered_with_the_database_registry():
    assert TemporaryWorksItem.__tablename__ == "temporary_works_items"
    assert TemporaryWorksPermit.__tablename__ == "temporary_works_permits"
    assert {"temporary_works_items", "temporary_works_permits", "temporary_works_settings"} <= set(Base.metadata.tables)


def test_every_stored_field_of_the_spec_exists_and_nothing_else():
    assert column_names(TemporaryWorksItem) == ITEM_COLUMNS
    assert column_names(TemporaryWorksPermit) == PERMIT_COLUMNS


def test_an_item_reference_is_unique_within_its_project():
    assert ("project_id", "reference") in unique_sets(TemporaryWorksItem)


def test_a_permit_number_is_unique_within_its_project():
    assert ("project_id", "number") in unique_sets(TemporaryWorksPermit)


def test_a_permit_belongs_to_its_item_and_is_removed_with_it():
    keys = foreign_keys(TemporaryWorksPermit)
    assert keys["item_id"] == "CASCADE"
    assert keys["project_id"] == "CASCADE"
    assert foreign_keys(TemporaryWorksItem)["project_id"] == "CASCADE"


def test_the_scaffold_link_and_the_inspection_reference_are_plain_identifiers_without_a_foreign_key():
    assert "scaffold_id" not in foreign_keys(TemporaryWorksItem)
    assert "inspection_id" not in foreign_keys(TemporaryWorksPermit)
    assert "created_by_id" not in foreign_keys(TemporaryWorksItem)


def test_no_gate_breach_overdue_or_percentage_value_is_stored():
    derived = re.compile(r"gate|breach|overdue|percent|clearance|cleared|compliant|valid_now|is_valid|expired")
    stored = column_names(TemporaryWorksItem) | column_names(TemporaryWorksPermit)
    # the one name that mentions a breach is the once-per-breach notice marker, a day and not a result
    assert {c for c in stored if derived.search(c)} == {"breach_notified_on"}
    assert isinstance(table(TemporaryWorksItem).columns["breach_notified_on"].type, Date)


def test_dates_are_calendar_days_without_a_time():
    items = table(TemporaryWorksItem).columns
    permits = table(TemporaryWorksPermit).columns
    for name in ("required_load_on", "required_strike_on", "design_due_on", "breach_notified_on"):
        assert isinstance(items[name].type, Date), name
    for name in ("issued_on", "valid_from", "valid_to", "closed_on", "expiry_notified_on"):
        assert isinstance(permits[name].type, Date), name
    assert isinstance(items["created_at"].type, DateTime)


def test_the_category_and_sort_order_are_whole_numbers_and_the_category_may_be_empty():
    items = table(TemporaryWorksItem).columns
    assert isinstance(items["design_check_category"].type, Integer)
    assert items["design_check_category"].nullable
    assert isinstance(items["sort_order"].type, Integer)
    assert not items["sort_order"].nullable


def test_the_required_fields_are_not_nullable_and_the_optional_ones_are():
    items = table(TemporaryWorksItem).columns
    permits = table(TemporaryWorksPermit).columns
    for name in ("project_id", "reference", "title", "family", "status"):
        assert not items[name].nullable, name
    for name in ("project_id", "item_id", "number", "kind", "status", "design_check_accepted", "inspection_passed"):
        assert not permits[name].nullable, name
    for name in ("coordinator_name", "coordinator_user_id", "required_load_on", "scaffold_id", "asset_node_id", "held_from"):
        assert items[name].nullable, name
    for name in ("issued_on", "valid_from", "valid_to", "closed_on", "closed_by_id", "inspection_id", "conditions"):
        assert permits[name].nullable, name


def test_the_expected_indexes_exist():
    item_indexes = {tuple(c.name for c in i.columns) for i in table(TemporaryWorksItem).indexes}
    permit_indexes = {tuple(c.name for c in i.columns) for i in table(TemporaryWorksPermit).indexes}
    assert ("project_id", "status") in item_indexes
    assert ("scaffold_id",) in item_indexes
    assert ("item_id",) in permit_indexes


# --- defaults -----------------------------------------------------------------------------------------------


def test_a_new_item_starts_identified_with_empty_optional_fields():
    item = TemporaryWorksItem(project_id=1, reference="TW-1", title="Slab props", family="propping")
    assert item.status == "identified"
    assert item.sort_order == 0
    assert item.design_check_category is None
    assert item.held_from is None
    assert item.scaffold_id is None
    assert item.related_refs == {}
    assert item.breach_notified_on is None


def test_a_new_permit_is_a_draft_with_both_prerequisites_unrecorded():
    permit = TemporaryWorksPermit(project_id=1, item_id=2, number="P-1", kind="load")
    assert permit.status == "draft"
    assert permit.design_check_accepted is False
    assert permit.inspection_passed is False
    assert permit.valid_from is None
    assert permit.valid_to is None
    assert permit.expiry_notified_on is None


def test_each_new_item_gets_its_own_related_refs_map():
    first = TemporaryWorksItem(project_id=1, reference="A", title="a", family="other")
    second = TemporaryWorksItem(project_id=1, reference="B", title="b", family="other")
    first.related_refs["drawing"] = "D-1"
    assert second.related_refs == {}


# --- the revision -------------------------------------------------------------------------------------------


def _revisions() -> dict[str, set[str]]:
    """Every revision under the versions folder and the revisions it chains after."""
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


def test_the_new_revision_chains_after_the_previous_head_and_one_head_remains():
    revisions = _revisions()
    assert revisions[REVISION] == {PARENT}
    heads = set(revisions) - set().union(*revisions.values())
    assert len(heads) == 1, heads


def test_no_other_revision_shares_the_new_revisions_parent():
    others = [r for r, parents in _revisions().items() if PARENT in parents and r != REVISION]
    assert others == []


def test_the_revision_creates_the_two_tables_and_the_downgrade_drops_exactly_them():
    source = (VERSIONS / f"{REVISION}_temporary_works.py").read_text()
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def calls(function: str, attribute: str) -> list[str]:
        out = []
        for node in ast.walk(functions[function]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute:
                first = node.args[0]
                out.append(first.value if isinstance(first, ast.Constant) else "")
        return out

    assert sorted(calls("upgrade", "create_table")) == ["temporary_works_items", "temporary_works_permits"]
    assert sorted(calls("downgrade", "drop_table")) == ["temporary_works_items", "temporary_works_permits"]
    assert calls("upgrade", "drop_table") == []
    assert calls("downgrade", "create_table") == []
    assert len(calls("upgrade", "create_index")) == len(calls("downgrade", "drop_index")) == 4


# --- the module ----------------------------------------------------------------------------------------------


def test_the_manifest_names_the_folder_and_keeps_scaffolds_optional():
    assert manifest.name == "temporary_works"
    assert set(manifest.depends) == {"projects", "asset_tree", "notifications", "tasks"}
    assert "scaffolds" not in manifest.depends
    assert manifest.optional_depends == ("scaffolds",)


def test_the_module_loader_orders_the_module_after_its_dependencies_without_a_cycle():
    order = [m.manifest.name for m in installed_modules()]
    assert "temporary_works" in order
    position = order.index("temporary_works")
    for name in ("projects", "asset_tree", "notifications", "tasks", "scaffolds"):
        assert order.index(name) < position, name


ACTIONS = ("read", "create", "update", "delete", "transition", "issue", "export", "return_to_draft", "restore")


@pytest.mark.parametrize("action", ACTIONS)
def test_each_permission_is_registered_in_lower_snake_case(action: str):
    name = TemporaryWorksPermissionName(f"temporary_works.{action}")
    assert re.fullmatch(r"[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*", name.value)


def test_there_are_exactly_the_nine_planned_permissions():
    """The seven planned first, then the return-to-draft permission and the restore permission of the user decisions."""
    assert {p.value for p in TemporaryWorksPermissionName} == {f"temporary_works.{a}" for a in ACTIONS}

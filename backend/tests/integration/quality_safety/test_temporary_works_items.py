"""Temporary works items API: create, uniqueness, validation, list and filters, edit, the guarded transitions and their
entry preconditions, history and audit, permissions, project visibility, and the draft-only soft delete with the
return-to-draft permission. Permits are seeded through the models, because the guarded API cannot reach some states."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.modules.temporary_works.constants import site_today
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/temporary-works"
VIEWER = ("projects.read", "temporary_works.read")
EDITOR = (*VIEWER, *(f"temporary_works.{a}" for a in ("create", "update", "delete", "transition")))
MANAGER = (*EDITOR, "temporary_works.issue", "temporary_works.return_to_draft")
OUTSIDER = ("temporary_works.read", "temporary_works.update", "temporary_works.delete", "temporary_works.transition")
SCAFFOLD_ACTIONS = ("read", "create", "update", "transition", "approve", "inspect", "delete")
SCAFFOLDS = ("tasks.read", *(f"scaffolds.{a}" for a in SCAFFOLD_ACTIONS))
TODAY = site_today()


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session)


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict[str, str]:
    await _grant(db, user["id"], f"tw-{uuid4().hex[:8]}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _item(
    client: AsyncClient, headers: dict, site: Tree, reference: str = "TW-1", expect: int = 201, **extra: Any
) -> dict:
    body = {"project_id": site.project.id, "reference": reference, "title": "Slab props", "family": "propping", **extra}
    made = await client.post(f"{API}/", json=body, headers=headers)
    assert made.status_code == expect, made.text
    return made.json()


async def _move(
    client: AsyncClient, headers: dict, item_id: int, status: str, expect: int = 200, note: str | None = None
) -> Any:
    body = {"status": status, **({"note": note} if note else {})}
    moved = await client.post(f"{API}/{item_id}/transition", json=body, headers=headers)
    assert moved.status_code == expect, moved.text
    return moved.json()


async def _walk(client: AsyncClient, headers: dict, item_id: int, *steps: str) -> None:
    for step in steps:
        await _move(client, headers, item_id, step)


async def _seed_item(db: AsyncSession, site: Tree, status: str, reference: str = "TW-S", **extra: Any) -> TemporaryWorksItem:
    values: dict[str, Any] = {"coordinator_name": "Kim Ng", "design_check_category": 1, **extra}
    item = TemporaryWorksItem(project_id=site.project.id, reference=reference, title="Seeded", family="propping", **values)
    item.status = status
    db.add(item)
    await db.commit()
    return item


async def _seed_permit(db: AsyncSession, item: TemporaryWorksItem, number: str = "P-1", **extra: Any) -> TemporaryWorksPermit:
    values: dict[str, Any] = {
        "kind": "load",
        "status": "issued",
        "valid_from": TODAY - timedelta(days=1),
        "valid_to": TODAY + timedelta(days=10),
        "design_check_accepted": True,
        "inspection_passed": True,
        **extra,
    }
    permit = TemporaryWorksPermit(project_id=item.project_id, item_id=item.id, number=number, kind=values.pop("kind"), **values)
    db.add(permit)
    await db.commit()
    return permit


async def _audit(db: AsyncSession, action: str, entity_id: int) -> list[AuditEntry]:
    rows = await db.execute(
        select(AuditEntry).where(AuditEntry.action == action, AuditEntry.entity_id == str(entity_id)).order_by(AuditEntry.seq)
    )
    return list(rows.scalars())


async def _stored(db: AsyncSession, item_id: int) -> TemporaryWorksItem:
    query = select(TemporaryWorksItem).where(TemporaryWorksItem.id == item_id).execution_options(populate_existing=True)
    row = await db.scalar(query)
    assert row is not None
    return row


# --- create, echo, uniqueness ---------------------------------------------------------------------------------


async def test_a_created_item_starts_identified_and_echoes_every_stored_field(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    body = await _item(
        client,
        headers,
        site,
        "TW-100",
        description="Props under the slab",
        design_check_category=1,
        designer="Ann Lee",
        checker="Bo Chan",
        coordinator_name="Kim Ng",
        required_load_on="2026-03-10",
        required_strike_on="2026-04-10",
        design_due_on="2026-03-01",
        location="Level 2",
        sort_order=3,
        notes="First pour",
        related_refs={"drawing": "D-12"},
        asset_node_id=site.rsw,
    )
    assert body["status"] == "identified"
    assert body["held_from"] is None
    echoed = (body["reference"], body["family"], body["design_check_category"], body["sort_order"])
    assert echoed == ("TW-100", "propping", 1, 3)
    assert (body["designer"], body["checker"], body["coordinator_name"]) == ("Ann Lee", "Bo Chan", "Kim Ng")
    dates = (body["required_load_on"], body["required_strike_on"], body["design_due_on"])
    assert dates == ("2026-03-10", "2026-04-10", "2026-03-01")
    assert (body["location"], body["notes"], body["asset_node_id"]) == ("Level 2", "First pour", site.rsw)
    assert body["related_refs"] == {"drawing": "D-12"}
    assert body["created_by_id"] == test_user["id"]
    assert body["created_at"] is not None
    assert body["warnings"] == []
    assert (await client.get(f"{API}/{body['id']}")).json()["reference"] == "TW-100"


async def test_a_duplicate_reference_conflicts_before_the_rules_run_and_only_within_a_project(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    first = await _item(client, headers, site, "TW-1")
    # the second would also break the date rule, but the conflict is answered first
    await _item(client, headers, site, "TW-1", expect=409, required_load_on="2026-03-10", required_strike_on="2026-03-01")

    other = await build_tree(db_session, "SC-2")
    await _item(client, headers, other, "TW-1")  # another project: accepted

    keep = await client.patch(f"{API}/{first['id']}", json={"reference": "TW-1", "title": "Renamed"}, headers=headers)
    assert keep.status_code == 200, keep.text
    second = await _item(client, headers, site, "TW-2")
    clash = await client.patch(f"{API}/{second['id']}", json={"reference": "TW-1"}, headers=headers)
    assert clash.status_code == 409


async def test_out_of_vocabulary_values_and_bad_lengths_are_invalid_input(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    for extra in (
        {"family": "bogus"},
        {"design_check_category": 4},
        {"design_check_category": -1},
        {"title": "x" * 301},
        {"reference": ""},
        {"sort_order": -1},
        {"status": "loaded"},  # the status is never part of a body
        {"unknown_field": 1},
    ):
        await _item(client, headers, site, expect=422, **{"reference": "TW-X", **extra})
    for query in ("family=bogus", "status=bogus", "category=9"):
        listed = await client.get(f"{API}/?project_id={site.project.id}&{query}")
        assert listed.status_code == 422, query


async def test_the_date_order_is_refused_and_a_late_design_due_date_is_only_a_warning(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    clashing = {"required_load_on": "2026-03-10", "required_strike_on": "2026-03-01"}
    refused = await _item(client, headers, site, "TW-1", expect=422, **clashing)
    assert "strike-before-load" in refused["detail"]

    saved = await _item(client, headers, site, "TW-2", required_load_on="2026-03-10", design_due_on="2026-03-15")
    assert [w["rule"] for w in saved["warnings"]] == ["late-design-due"]
    assert (await client.get(f"{API}/{saved['id']}")).status_code == 200


# --- list ---------------------------------------------------------------------------------------------------


async def test_the_list_orders_by_sort_order_then_creation_and_filters(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    await _item(client, headers, site, "B", sort_order=5, family="scaffold")
    await _item(client, headers, site, "A", sort_order=1, design_check_category=2)
    await _item(client, headers, site, "C", sort_order=1, design_check_category=2, family="formwork")
    listed = await client.get(f"{API}/?project_id={site.project.id}")
    assert listed.status_code == 200
    assert [i["reference"] for i in listed.json()["data"]] == ["A", "C", "B"]
    assert listed.json()["total_count"] == 3

    async def by(query: str) -> list[str]:
        r = await client.get(f"{API}/?project_id={site.project.id}&{query}")
        assert r.status_code == 200, r.text
        return [i["reference"] for i in r.json()["data"]]

    assert await by("family=scaffold") == ["B"]
    assert await by("category=2") == ["A", "C"]
    assert await by("status=identified") == ["A", "C", "B"]
    assert await by("status=loaded") == []
    paged = await client.get(f"{API}/?project_id={site.project.id}&items_per_page=2&page=2")
    assert [i["reference"] for i in paged.json()["data"]] == ["B"]


# --- edit ---------------------------------------------------------------------------------------------------


async def test_an_edit_leaves_omitted_fields_alone_and_an_explicit_null_clears_an_optional_one(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site, notes="keep", location="Level 2", designer="Ann Lee")
    edited = await client.patch(f"{API}/{item['id']}", json={"location": None, "title": "New title"}, headers=headers)
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["location"], body["title"], body["notes"], body["designer"]) == (None, "New title", "keep", "Ann Lee")
    for bad in ({"title": None}, {"family": None}, {"status": "loaded"}):
        assert (await client.patch(f"{API}/{item['id']}", json=bad, headers=headers)).status_code == 422, bad


async def test_an_update_of_notes_alone_runs_no_rules_but_a_rule_relevant_field_judges_the_merged_record(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    # stored in a state that would now fail the coordinator rule
    stored = await _seed_item(db_session, site, "approved_to_load", coordinator_name=None)
    notes = await client.patch(f"{API}/{stored.id}", json={"notes": "site note"}, headers=headers)
    assert notes.status_code == 200, notes.text
    changes = {"location": "L3", "required_load_on": "2026-05-01"}
    judged = await client.patch(f"{API}/{stored.id}", json=changes, headers=headers)
    assert judged.status_code == 422
    assert "coordinator" in judged.json()["detail"]
    assert (await _stored(db_session, stored.id)).location is None


# --- guarded transitions ----------------------------------------------------------------------------------


async def test_a_category_two_item_needs_an_independent_checker_to_reach_design_checked(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    same = await _item(client, headers, site, "TW-2", design_check_category=2, designer="Ann Lee", checker=" ANN lee ")
    blank = await _item(client, headers, site, "TW-3", design_check_category=2, designer="Ann Lee")
    one = await _item(client, headers, site, "TW-1", design_check_category=1, designer="Ann Lee", checker="ann lee")
    for item in (same, blank, one):
        await _walk(client, headers, item["id"], "design_brief", "design_submitted")

    refused = await _move(client, headers, same["id"], "design_checked", expect=422)
    assert "independent-check" in refused["detail"]
    assert "independent-check" in (await _move(client, headers, blank["id"], "design_checked", expect=422))["detail"]
    # category one: no such rule
    assert (await _move(client, headers, one["id"], "design_checked"))["status"] == "design_checked"

    fixed = await client.patch(f"{API}/{same['id']}", json={"checker": "Bo Chan"}, headers=headers)
    assert fixed.status_code == 200, fixed.text
    assert (await _move(client, headers, same["id"], "design_checked"))["status"] == "design_checked"


async def test_approval_to_load_needs_a_category_and_a_named_coordinator(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    bare = await _item(client, headers, site, "TW-1")
    await _walk(client, headers, bare["id"], "design_brief", "design_submitted", "design_checked")
    assert "category-required" in (await _move(client, headers, bare["id"], "approved_to_load", expect=422))["detail"]

    patched = await client.patch(f"{API}/{bare['id']}", json={"design_check_category": 1}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert "coordinator-required" in (await _move(client, headers, bare["id"], "approved_to_load", expect=422))["detail"]

    await client.patch(f"{API}/{bare['id']}", json={"coordinator_name": "Kim Ng"}, headers=headers)
    assert (await _move(client, headers, bare["id"], "approved_to_load"))["status"] == "approved_to_load"
    assert (await _stored(db_session, bare["id"])).status == "approved_to_load"


async def test_an_item_moves_one_step_at_a_time_and_a_step_back_needs_a_note(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    assert "one-step" in (await _move(client, headers, item["id"], "design_submitted", expect=422))["detail"]
    await _move(client, headers, item["id"], "design_brief")
    # a repeated move sees the status the first one set
    assert "no-change" in (await _move(client, headers, item["id"], "design_brief", expect=422))["detail"]
    assert "note-required" in (await _move(client, headers, item["id"], "identified", expect=422))["detail"]
    assert (await _move(client, headers, item["id"], "identified", note="Wrong item"))["status"] == "identified"
    history = (await client.get(f"{API}/{item['id']}/history")).json()
    moves = [(h["from_status"], h["to_status"]) for h in history]
    assert moves == [("identified", "design_brief"), ("design_brief", "identified")]
    assert history[1]["note"] == "Wrong item"
    assert history[0]["changed_by_id"] == test_user["id"]


async def test_loading_needs_the_load_gate_open_and_is_recorded_in_history_and_audit(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _seed_item(db_session, site, "approved_to_load")
    assert "load-gate" in (await _move(client, headers, item.id, "loaded", expect=422))["detail"]
    await _seed_permit(db_session, item, "P-1", status="draft")
    await _seed_permit(db_session, item, "P-2", design_check_accepted=False)  # one prerequisite missing
    await _seed_permit(db_session, item, "P-3", valid_to=TODAY - timedelta(days=1))  # ended yesterday
    await _seed_permit(db_session, item, "P-4", kind="dismantle")
    assert "load-gate" in (await _move(client, headers, item.id, "loaded", expect=422))["detail"]
    assert (await _stored(db_session, item.id)).status == "approved_to_load"

    await _seed_permit(db_session, item, "P-5")
    assert (await _move(client, headers, item.id, "loaded"))["status"] == "loaded"
    history = (await client.get(f"{API}/{item.id}/history")).json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [("approved_to_load", "loaded")]
    entries = await _audit(db_session, "temporary_works.item.loaded", item.id)
    assert len(entries) == 1
    assert entries[0].actor_id == test_user["id"]


async def test_in_use_only_from_loaded_and_struck_needs_a_permit_to_strike(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    approved = await _seed_item(db_session, site, "approved_to_load", "TW-A")
    await _seed_permit(db_session, approved, "P-A")
    assert "one-step" in (await _move(client, headers, approved.id, "in_use", expect=422))["detail"]

    loaded = await _seed_item(db_session, site, "loaded", "TW-B")
    await _seed_permit(db_session, loaded, "P-B")
    assert (await _move(client, headers, loaded.id, "in_use"))["status"] == "in_use"
    assert len(await _audit(db_session, "temporary_works.item.in_use", loaded.id)) == 1

    unpermitted = await _seed_item(db_session, site, "loaded", "TW-C")  # bearing load with no permit: cannot go into use
    assert "no-valid-load-permit" in (await _move(client, headers, unpermitted.id, "in_use", expect=422))["detail"]

    striking = await _seed_item(db_session, site, "approved_to_strike", "TW-D")
    assert "strike-gate" in (await _move(client, headers, striking.id, "struck", expect=422))["detail"]
    await _seed_permit(db_session, striking, "P-D1", kind="dismantle")
    assert "strike-gate" in (await _move(client, headers, striking.id, "struck", expect=422))["detail"]
    await _seed_permit(db_session, striking, "P-D2", kind="strike", design_check_accepted=False, inspection_passed=False)
    # the prerequisite flags have no effect on the strike gate
    assert (await _move(client, headers, striking.id, "struck"))["status"] == "struck"
    assert (await _move(client, headers, striking.id, "removed"))["status"] == "removed"
    assert "terminal" in (await _move(client, headers, striking.id, "struck", expect=422))["detail"]


async def test_on_hold_resumes_only_to_the_status_it_was_held_from(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _seed_item(db_session, site, "loaded")
    await _seed_permit(db_session, item)
    held = await _move(client, headers, item.id, "on_hold")
    assert (held["status"], held["held_from"]) == ("on_hold", "loaded")
    assert len(await _audit(db_session, "temporary_works.item.on_hold", item.id)) == 1
    assert "held-from" in (await _move(client, headers, item.id, "approved_to_load", expect=422))["detail"]
    resumed = await _move(client, headers, item.id, "loaded")
    assert (resumed["status"], resumed["held_from"]) == ("loaded", None)


async def test_a_linked_scaffold_must_be_tagged_green_or_yellow_to_load(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR, *SCAFFOLDS)

    async def scaffold(tag: str) -> int:
        body = {"project_id": site.project.id, "node_id": site.rsw, "purpose": "Access"}
        made = await client.post("/api/v1/scaffolds/", json=body, headers=headers)
        assert made.status_code == 201, made.text
        sid = int(made.json()["id"])
        for step in ("approved", "erecting", "erected"):
            moved = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
            assert moved.status_code == 200, moved.text
        tagged = await client.post(
            f"/api/v1/scaffolds/{sid}/inspections", json={"kind": "handover", "tag": tag}, headers=headers
        )
        assert tagged.status_code == 201, tagged.text
        return sid

    red, green = await scaffold("red"), await scaffold("green")
    blocked = await _seed_item(db_session, site, "approved_to_load", "TW-R", scaffold_id=red)
    await _seed_permit(db_session, blocked, "P-R")
    assert "scaffold-not-usable" in (await _move(client, headers, blocked.id, "loaded", expect=422))["detail"]
    clear = await _seed_item(db_session, site, "approved_to_load", "TW-G", scaffold_id=green)
    await _seed_permit(db_session, clear, "P-G")
    assert (await _move(client, headers, clear.id, "loaded"))["status"] == "loaded"

    # a scaffold that is missing, or of another project, is not found when the link is made
    await _item(client, headers, site, "TW-M", expect=404, scaffold_id=green + 1000)
    other = await build_tree(db_session, "SC-2")
    await _item(client, headers, other, "TW-O", expect=404, scaffold_id=green)


# --- permissions and visibility -------------------------------------------------------------------------------


async def test_a_viewer_reads_but_cannot_write_and_an_editor_can(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    viewer = await _as(client, db_session, test_user_2, *VIEWER)
    assert (await client.get(f"{API}/?project_id={site.project.id}")).status_code == 200
    assert (await client.get(f"{API}/{item['id']}")).status_code == 200
    assert (await client.get(f"{API}/{item['id']}/history")).status_code == 200
    await _item(client, viewer, site, "TW-V", expect=403)
    assert (await client.patch(f"{API}/{item['id']}", json={"notes": "x"}, headers=viewer)).status_code == 403
    to_brief = await client.post(f"{API}/{item['id']}/transition", json={"status": "design_brief"}, headers=viewer)
    assert to_brief.status_code == 403
    assert (await client.delete(f"{API}/{item['id']}", headers=viewer)).status_code == 403
    assert (await client.post(f"{API}/{item['id']}/return-to-draft", json={"reason": "x"}, headers=viewer)).status_code == 403


async def test_items_of_a_project_the_caller_cannot_see_answer_the_same_not_found_as_a_missing_item(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    outsider = await _as(client, db_session, test_user_2, *OUTSIDER)  # no access to the project
    missing = item["id"] + 1000
    for target in (item["id"], missing):
        assert (await client.get(f"{API}/{target}")).status_code == 404
        assert (await client.patch(f"{API}/{target}", json={"notes": "x"}, headers=outsider)).status_code == 404
        assert (await client.delete(f"{API}/{target}", headers=outsider)).status_code == 404
        moved = await client.post(f"{API}/{target}/transition", json={"status": "design_brief"}, headers=outsider)
        assert moved.status_code == 404
    assert (await client.get(f"{API}/?project_id={site.project.id}")).status_code == 404
    assert (await _stored(db_session, item["id"])).status == "identified"


# --- delete and return to draft -------------------------------------------------------------------------------


async def test_only_a_draft_item_is_deleted_and_the_delete_is_a_soft_audited_tombstone(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site, "TW-1")
    gone = await client.delete(f"{API}/{item['id']}", headers=headers)
    assert gone.status_code == 200, gone.text

    assert (await client.get(f"{API}/{item['id']}")).status_code == 404
    assert (await client.get(f"{API}/?project_id={site.project.id}")).json()["data"] == []
    row = await _stored(db_session, item["id"])  # never physically removed
    assert row.deleted_at is not None
    assert row.deleted_by_id == test_user["id"]
    entries = await _audit(db_session, "temporary_works.item.deleted", item["id"])
    assert len(entries) == 1
    assert entries[0].actor_id == test_user["id"]
    await _item(client, headers, site, "TW-1", expect=409)  # the tombstone keeps its reference

    started = await _item(client, headers, site, "TW-2")
    await _move(client, headers, started["id"], "design_brief")
    refused = await client.delete(f"{API}/{started['id']}", headers=headers)
    assert refused.status_code == 409
    assert "not-draft" in refused.json()["detail"]
    assert (await client.get(f"{API}/{started['id']}")).status_code == 200


async def test_an_item_with_permits_is_deleted_only_after_each_permit_has_been_deleted(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    permit = await _seed_permit(db_session, await _stored(db_session, item["id"]), "P-1", status="draft")
    blocked = await client.delete(f"{API}/{item['id']}", headers=headers)
    assert blocked.status_code == 409
    assert "has-permits" in blocked.json()["detail"]

    assert (await client.delete(f"{API}/permits/{permit.id}", headers=headers)).status_code == 200
    assert (await client.delete(f"{API}/{item['id']}", headers=headers)).status_code == 200
    # the permit was never removed either: it is a tombstone that still resolves for the audit
    assert (await _audit(db_session, "temporary_works.permit.deleted", permit.id))[0].project_id == site.project.id


async def test_returning_an_item_to_draft_needs_its_own_permission_and_a_reason_and_is_audited(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    await _walk(client, editor, item["id"], "design_brief", "design_submitted")
    denied = await client.post(f"{API}/{item['id']}/return-to-draft", json={"reason": "Wrong design"}, headers=editor)
    assert denied.status_code == 403  # edit rights are not enough

    manager = await _as(client, db_session, test_user_2, *MANAGER)
    for bad in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "ok", "extra": 1}):
        assert (await client.post(f"{API}/{item['id']}/return-to-draft", json=bad, headers=manager)).status_code == 422, bad
    back = await client.post(f"{API}/{item['id']}/return-to-draft", json={"reason": "Wrong design"}, headers=manager)
    assert back.status_code == 200, back.text
    assert (back.json()["status"], back.json()["held_from"]) == ("identified", None)
    again = await client.post(f"{API}/{item['id']}/return-to-draft", json={"reason": "Twice"}, headers=manager)
    assert again.status_code == 422
    assert "already-draft" in again.json()["detail"]

    history = (await client.get(f"{API}/{item['id']}/history")).json()
    assert history[-1]["to_status"] == "identified"
    assert "Wrong design" in history[-1]["note"]
    entries = await _audit(db_session, "temporary_works.item.returned_to_draft", item["id"])
    assert len(entries) == 1
    assert entries[0].after == {"status": "identified", "reason": "Wrong design"}
    assert entries[0].actor_id == test_user_2["id"]
    assert (await client.delete(f"{API}/{item['id']}", headers=manager)).status_code == 200  # draft again, so deletable

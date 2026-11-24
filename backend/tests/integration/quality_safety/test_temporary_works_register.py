"""Temporary works register views over the API: the rollup and the load-status view for an as-of day, computed from seeded
rows (some states are unreachable through the guarded API), the default site day, malformed days, deleted items left out,
scaffold advice, and read-only access."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.temporary_works.constants import site_today
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/temporary-works"
VIEWER = ("projects.read", "temporary_works.read")
EDITOR = (*VIEWER, *(f"temporary_works.{a}" for a in ("create", "update", "delete", "transition")))
OUTSIDER = ("temporary_works.read",)
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


async def _seed_item(db: AsyncSession, site: Tree, reference: str, status: str, **extra: Any) -> TemporaryWorksItem:
    fields: dict[str, Any] = {"family": "propping", "title": f"Item {reference}", **extra}
    item = TemporaryWorksItem(project_id=site.project.id, reference=reference, **fields)
    item.status = status
    db.add(item)
    await db.commit()
    return item


async def _seed_permit(db: AsyncSession, item: TemporaryWorksItem, number: str, **extra: Any) -> TemporaryWorksPermit:
    values: dict[str, Any] = {
        "status": "issued",
        "valid_from": TODAY - timedelta(days=7),
        "valid_to": TODAY + timedelta(days=7),
        "design_check_accepted": True,
        "inspection_passed": True,
        **extra,
    }
    kind = values.pop("kind", "load")
    permit = TemporaryWorksPermit(project_id=item.project_id, item_id=item.id, number=number, kind=kind, **values)
    db.add(permit)
    await db.commit()
    return permit


async def _rollup(client: AsyncClient, site: Tree, query: str = "") -> dict[str, Any]:
    r = await client.get(f"{API}/register?project_id={site.project.id}{query}")
    assert r.status_code == 200, r.text
    return r.json()


async def _status(client: AsyncClient, site: Tree, query: str = "") -> dict[str, Any]:
    r = await client.get(f"{API}/load-status?project_id={site.project.id}{query}")
    assert r.status_code == 200, r.text
    return r.json()


# --- the empty register and the as-of day ---------------------------------------------------------------------


async def test_an_empty_register_is_compliant_and_zero_filled(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    body = await _rollup(client, site)
    assert (body["total"], body["compliant"], body["design_clearance"]) == (0, True, None)
    assert body["as_of"] == TODAY.isoformat()  # the default is the current day at the site
    assert len(body["status_counts"]) == 11
    assert set(body["category_counts"]) == {"0", "1", "2", "3", "unassigned"}
    assert all(v == 0 for v in {**body["status_counts"], **body["category_counts"]}.values())
    for key in ("gates", "breaches", "overdue_to_load", "overdue_to_strike", "warnings"):
        assert body[key] == [], key
    status = await _status(client, site)
    assert (status["total"], status["compliant"], status["gates"], status["breaches"]) == (0, True, [], [])


async def test_a_malformed_as_of_day_is_invalid_input_and_a_given_day_is_echoed(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    for bad in ("tomorrow", "2026-13-01", "2026-3-1x"):
        assert (await client.get(f"{API}/register?project_id={site.project.id}&as_of={bad}")).status_code == 422, bad
        assert (await client.get(f"{API}/load-status?project_id={site.project.id}&as_of={bad}")).status_code == 422, bad
    assert (await _rollup(client, site, "&as_of=2026-03-10"))["as_of"] == "2026-03-10"
    assert (await _status(client, site, "&as_of=2026-03-10"))["as_of"] == "2026-03-10"


# --- gates and breach -----------------------------------------------------------------------------------------


async def test_the_load_gate_needs_both_prerequisites_in_a_valid_permit_and_only_a_strike_permit_opens_strike(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    cleared = await _seed_item(db_session, site, "TW-1", "approved_to_load")
    await _seed_permit(db_session, cleared, "P-1")
    short = await _seed_item(db_session, site, "TW-2", "approved_to_load")
    await _seed_permit(db_session, short, "P-2", inspection_passed=False)
    drafted = await _seed_item(db_session, site, "TW-3", "approved_to_load")
    await _seed_permit(db_session, drafted, "P-3", status="draft")
    ended = await _seed_item(db_session, site, "TW-4", "approved_to_load")
    await _seed_permit(db_session, ended, "P-4", valid_to=TODAY - timedelta(days=1))
    open_ended = await _seed_item(db_session, site, "TW-5", "approved_to_load")
    await _seed_permit(db_session, open_ended, "P-5", valid_from=TODAY - timedelta(days=30), valid_to=None)
    not_yet = await _seed_item(db_session, site, "TW-6", "approved_to_load")
    await _seed_permit(db_session, not_yet, "P-6", valid_from=TODAY + timedelta(days=1), valid_to=None)
    striking = await _seed_item(db_session, site, "TW-7", "approved_to_strike")
    await _seed_permit(db_session, striking, "P-7", kind="dismantle")
    striking_ok = await _seed_item(db_session, site, "TW-8", "approved_to_strike")
    await _seed_permit(db_session, striking_ok, "P-8", kind="strike")

    status = await _status(client, site)
    gates = {g["reference"]: (g["load_gate_open"], g["strike_gate_open"]) for g in status["gates"]}
    assert [gates[f"TW-{n}"][0] for n in range(1, 7)] == [True, False, False, False, True, False]
    assert gates["TW-7"][1] is False
    assert gates["TW-8"][1] is True
    assert (await _rollup(client, site))["gates"] == status["gates"]  # both views judge the same way


async def test_an_item_in_use_with_only_a_draft_permit_is_a_breach_until_a_permit_is_valid(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    item = await _seed_item(db_session, site, "TW-1", "in_use")
    permit = await _seed_permit(db_session, item, "P-1", status="draft")

    body = await _rollup(client, site)
    assert body["compliant"] is False
    assert [(b["reference"], b["item_id"]) for b in body["breaches"]] == [("TW-1", item.id)]
    assert "in use" in body["breaches"][0]["reason"]
    assert TODAY.isoformat() in body["breaches"][0]["reason"]
    assert (await _status(client, site))["compliant"] is False

    permit.status = "issued"  # the permit is issued within its window
    await db_session.commit()
    assert (await _rollup(client, site))["breaches"] == []
    assert (await _status(client, site))["compliant"] is True


async def test_an_item_approved_to_load_with_no_permit_is_shut_but_not_a_breach_and_a_loaded_item_with_a_valid_permit_is_clear(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    waiting = await _seed_item(db_session, site, "TW-1", "approved_to_load")
    loaded = await _seed_item(db_session, site, "TW-2", "loaded")
    await _seed_permit(db_session, loaded, "P-2")
    body = await _status(client, site)
    assert body["breaches"] == []
    assert body["compliant"] is True
    gate = {g["item_id"]: g["load_gate_open"] for g in body["gates"]}
    assert gate[waiting.id] is False
    assert gate[loaded.id] is True


async def test_a_later_as_of_day_judges_the_same_rows_afresh_without_storing_anything(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    item = await _seed_item(db_session, site, "TW-1", "loaded")
    await _seed_permit(db_session, item, "P-1", valid_to=TODAY + timedelta(days=2))
    assert (await _rollup(client, site))["breaches"] == []
    later = (TODAY + timedelta(days=3)).isoformat()
    body = await _rollup(client, site, f"&as_of={later}")
    assert [b["reference"] for b in body["breaches"]] == ["TW-1"]
    assert later in body["breaches"][0]["reason"]
    assert [g["load_gate_open"] for g in body["gates"]] == [False]
    await db_session.refresh(item)
    assert item.status == "loaded"  # nothing stored changed
    assert (await _rollup(client, site))["breaches"] == []  # and today is judged as before


# --- counts, overdue, warnings ----------------------------------------------------------------------------------


async def test_counts_clearance_and_overdue_lists_agree_with_the_rows(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    yesterday = TODAY - timedelta(days=1)
    await _seed_item(db_session, site, "TW-1", "identified", design_check_category=1, required_load_on=yesterday)
    await _seed_item(db_session, site, "TW-2", "design_checked", design_check_category=3)
    await _seed_item(db_session, site, "TW-3", "approved_to_load", required_load_on=yesterday)
    held = await _seed_item(db_session, site, "TW-4", "on_hold", required_load_on=yesterday, required_strike_on=yesterday)
    using = await _seed_item(db_session, site, "TW-5", "in_use", required_strike_on=yesterday)
    await _seed_permit(db_session, using, "P-5")
    await _seed_item(db_session, site, "TW-6", "struck", required_strike_on=yesterday, required_load_on=TODAY)

    body = await _rollup(client, site)
    assert body["total"] == 6
    assert body["design_clearance"] == "66.67"  # design checked, approved to load, in use and struck: four of six
    counts = body["status_counts"]
    assert [counts[s] for s in ("identified", "design_checked", "approved_to_load", "on_hold", "in_use", "struck")] == [1] * 6
    assert counts["loaded"] == 0
    assert {k: v for k, v in body["category_counts"].items() if v} == {"1": 1, "3": 1, "unassigned": 4}
    # approved to load still counts as overdue; loaded, later and on-hold items are not
    assert [i["reference"] for i in body["overdue_to_load"]] == ["TW-1", "TW-3"]
    assert body["overdue_to_load"][0]["required_load_on"] == yesterday.isoformat()
    assert [i["reference"] for i in body["overdue_to_strike"]] == ["TW-5"]  # not before loaded, not on hold
    assert body["overdue_to_strike"][0]["id"] == using.id
    assert body["breaches"] == []
    assert held.status == "on_hold"


async def test_a_live_permit_missing_a_prerequisite_on_an_item_bearing_load_is_a_warning_and_not_a_breach(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    item = await _seed_item(db_session, site, "TW-1", "loaded")
    await _seed_permit(db_session, item, "P-1", inspection_passed=False, valid_to=TODAY + timedelta(days=2))
    body = await _rollup(client, site)
    assert body["breaches"] == []
    assert body["compliant"] is True  # warnings never change the flag
    assert {w["rule"] for w in body["warnings"]} == {"prerequisites-missing", "permit-lapsing"}
    assert all(w["item_id"] == item.id and w["reference"] == "TW-1" for w in body["warnings"])
    assert "warnings" not in await _status(client, site)


async def test_a_linked_scaffold_with_a_red_tag_is_advised_on_and_an_unlinked_item_has_no_such_advice(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR, *SCAFFOLDS)
    made = await client.post(
        "/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw, "purpose": "Access"}, headers=headers
    )
    assert made.status_code == 201, made.text
    sid = int(made.json()["id"])
    for step in ("approved", "erecting", "erected"):
        moved = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    tagged = await client.post(f"/api/v1/scaffolds/{sid}/inspections", json={"kind": "handover", "tag": "red"}, headers=headers)
    assert tagged.status_code == 201, tagged.text

    linked = await _seed_item(db_session, site, "TW-1", "design_checked", scaffold_id=sid, family="scaffold")
    await _seed_item(db_session, site, "TW-2", "design_checked")
    body = await _rollup(client, site)
    assert [(w["item_id"], w["rule"]) for w in body["warnings"]] == [(linked.id, "scaffold-not-usable")]
    assert "red" in body["warnings"][0]["message"]
    assert body["compliant"] is True
    assert body["breaches"] == []


# --- deleted items, strays, access ------------------------------------------------------------------------------


async def test_a_deleted_item_is_hidden_from_every_count(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    body = {"project_id": site.project.id, "reference": "TW-1", "title": "Props", "family": "propping"}
    made = await client.post(f"{API}/", json=body, headers=headers)
    assert made.status_code == 201, made.text
    assert (await _rollup(client, site))["total"] == 1
    assert (await client.delete(f"{API}/{made.json()['id']}", headers=headers)).status_code == 200
    gone = await _rollup(client, site)
    assert gone["total"] == 0
    assert gone["status_counts"]["identified"] == 0
    assert gone["gates"] == []


async def test_a_stray_out_of_vocabulary_status_or_kind_does_not_break_the_rollup(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    await _seed_item(db_session, site, "TW-1", "mystery")
    loaded = await _seed_item(db_session, site, "TW-2", "loaded")
    await _seed_permit(db_session, loaded, "P-2", kind="mystery", status="odd")
    body = await _rollup(client, site)
    assert body["total"] == 2
    assert body["status_counts"]["mystery"] == 1
    assert sum(body["status_counts"].values()) == 2
    assert [b["reference"] for b in body["breaches"]] == ["TW-2"]  # a permit that is not clearly valid clears nothing
    assert (await _status(client, site))["compliant"] is False


async def test_a_viewer_reads_both_views_and_a_caller_who_cannot_see_the_project_gets_not_found(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    await _as(client, db_session, test_user, *VIEWER)
    await _seed_item(db_session, site, "TW-1", "design_checked")
    assert (await _rollup(client, site))["total"] == 1
    assert (await _status(client, site))["total"] == 1

    await _as(client, db_session, test_user_2, *OUTSIDER)
    assert (await client.get(f"{API}/register?project_id={site.project.id}")).status_code == 404
    assert (await client.get(f"{API}/load-status?project_id={site.project.id}")).status_code == 404
    other = await build_tree(db_session, "SC-2")
    assert (await client.get(f"{API}/register?project_id={other.project.id}")).status_code == 404
    assert (await client.get(f"{API}/register")).status_code == 422  # the project is required

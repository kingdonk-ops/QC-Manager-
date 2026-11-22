"""Scaffolds: request to dismantle, tags, overdue inspections turning red, weather events, hire days, readiness."""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.scaffolds.models import Scaffold
from src.modules.scaffolds.service import mark_overdue, scaffold_ready
from src.modules.tasks.models import Task
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

ALL = (
    "projects.read",
    "tasks.read",
    *(f"scaffolds.{a}" for a in ("read", "create", "update", "transition", "approve", "inspect", "delete", "export")),
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session)


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}-{len(permissions)}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _standing(client: AsyncClient, headers: dict, site: Tree, **extra) -> dict:
    """Request, approve, erect: a scaffold awaiting its handover inspection."""
    body = {
        "project_id": site.project.id,
        "node_id": site.rsw,
        "purpose": "Access to tail pulley",
        "scaffold_type": "independent",
        "duty_class": "medium",
        "dimensions": {"length_m": 6, "width_m": 1.2, "height_m": 8, "lifts": 4},
        "required_by": date.today().isoformat(),
        **extra,
    }
    made = await client.post("/api/v1/scaffolds/", json=body, headers=headers)
    assert made.status_code == 201, made.text
    sid = made.json()["id"]
    for step in ("approved", "erecting", "erected"):
        moved = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    return moved.json()


async def test_the_lifecycle_and_a_handover_tag(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree):
    headers = await _as(client, db_session, test_user, *ALL)
    s = await _standing(client, headers, site)
    assert s["code"] == "SCF-001"
    assert s["status"] == "erected"
    assert s["effective_tag"] == "none"
    assert s["node_path"] == "KAR / A1 / 101 / 101.1"

    # in_use only comes from an inspection
    refused = await client.post(f"/api/v1/scaffolds/{s['id']}/transition", json={"status": "in_use"}, headers=headers)
    assert refused.status_code == 422

    tagged = await client.post(
        f"/api/v1/scaffolds/{s['id']}/inspections",
        json={
            "kind": "handover",
            "tag": "green",
            "tag_no": "T-0042",
            "checklist": [{"item": "Base plates and sole boards", "ok": True}, {"item": "Toe boards", "ok": True}],
        },
        headers=headers,
    )
    assert tagged.status_code == 201, tagged.text
    assert tagged.json()["next_due_at"] is not None

    s = (await client.get(f"/api/v1/scaffolds/{s['id']}")).json()
    assert (s["status"], s["effective_tag"], s["tag_no"]) == ("in_use", "green", "T-0042")
    due = datetime.fromisoformat(s["next_inspection_due"])
    assert timedelta(days=6, hours=23) < due - datetime.now(UTC) <= timedelta(days=7)

    board = (await client.get("/api/v1/scaffolds/tag-board", params={"project_id": site.project.id})).json()
    assert [r["code"] for r in board["green"]] == ["SCF-001"]

    history = (await client.get(f"/api/v1/scaffolds/{s['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["requested", "approved", "erecting", "erected", "in_use"]

    # modification: approval takes it out of use, completion needs a fresh handover inspection
    mod = await client.post(f"/api/v1/scaffolds/{s['id']}/modifications", json={"description": "Add a lift"}, headers=headers)
    assert mod.status_code == 201, mod.text
    path = f"/api/v1/scaffolds/{s['id']}/modifications/{mod.json()['id']}/decision"
    assert (await client.post(path, json={"status": "approved"}, headers=headers)).status_code == 200
    s = (await client.get(f"/api/v1/scaffolds/{s['id']}")).json()
    assert (s["status"], s["effective_tag"]) == ("modifying", "red")
    assert (await client.post(path, json={"status": "completed"}, headers=headers)).status_code == 200
    s = (await client.get(f"/api/v1/scaffolds/{s['id']}")).json()
    assert (s["status"], s["effective_tag"]) == ("erected", "none")

    # dismantle request, go-ahead, completion
    for step in ("dismantle_requested", "dismantling", "dismantled"):
        moved = await client.post(f"/api/v1/scaffolds/{s['id']}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    assert moved.json()["dismantled_on"] == date.today().isoformat()
    assert moved.json()["effective_tag"] == "none"


async def test_steps_need_their_permission(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    requester = await _as(client, db_session, test_user, "projects.read", "scaffolds.read", "scaffolds.create")
    made = await client.post("/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw}, headers=requester)
    sid = made.json()["id"]
    approve = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": "approved"}, headers=requester)
    assert approve.status_code == 403
    inspect = await client.post(
        f"/api/v1/scaffolds/{sid}/inspections", json={"kind": "handover", "tag": "green"}, headers=requester
    )
    assert inspect.status_code == 403
    # the requester may cancel their own request
    cancel = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": "cancelled"}, headers=requester)
    assert cancel.status_code == 200, cancel.text

    # a node of another project is refused
    other = await build_tree(db_session, "SC-2")
    wrong = await client.post(
        "/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": other.rsw}, headers=requester
    )
    assert wrong.status_code == 404


async def test_an_overdue_inspection_turns_the_tag_red(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *ALL)
    s = await _standing(client, headers, site)
    eight_days_ago = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    tagged = await client.post(
        f"/api/v1/scaffolds/{s['id']}/inspections",
        json={"kind": "handover", "tag": "yellow", "restrictions": "No loading above lift 3", "inspected_at": eight_days_ago},
        headers=headers,
    )
    assert tagged.status_code == 201, tagged.text

    s = (await client.get(f"/api/v1/scaffolds/{s['id']}")).json()
    assert s["tag_status"] == "yellow"
    assert s["effective_tag"] == "red"
    assert s["inspection_overdue"] is True
    red = (await client.get("/api/v1/scaffolds/", params={"project_id": site.project.id, "tag": "red"})).json()
    assert [r["code"] for r in red["data"]] == ["SCF-001"]
    assert not await scaffold_ready(db_session, site.rsw, date.today())

    # the hourly job writes the red tag back
    assert await mark_overdue(db_session) == 1
    row = await db_session.scalar(select(Scaffold).where(Scaffold.id == s["id"]))
    assert row is not None
    await db_session.refresh(row)
    assert row.tag_status == "red"
    assert await mark_overdue(db_session) == 0

    # a periodic inspection clears it
    again = await client.post(
        f"/api/v1/scaffolds/{s['id']}/inspections", json={"kind": "periodic", "tag": "green"}, headers=headers
    )
    assert again.status_code == 201
    s = (await client.get(f"/api/v1/scaffolds/{s['id']}")).json()
    assert (s["effective_tag"], s["inspection_overdue"]) == ("green", False)
    assert await scaffold_ready(db_session, site.rsw, date.today())


async def test_a_weather_event_makes_inspections_due_now(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *ALL)
    s = await _standing(client, headers, site, custodian_id=test_user["id"])
    await client.post(f"/api/v1/scaffolds/{s['id']}/inspections", json={"kind": "handover", "tag": "green"}, headers=headers)

    hit = await client.post(
        "/api/v1/scaffolds/weather-events",
        json={"project_id": site.project.id, "node_id": site.area, "description": "Gusts over 60 km/h overnight"},
        headers=headers,
    )
    assert hit.status_code == 200, hit.text
    assert [(r["code"], r["effective_tag"]) for r in hit.json()] == [("SCF-001", "red")]
    tasks = (await db_session.execute(select(Task).where(Task.entity_type == "scaffold", Task.entity_id == s["id"]))).scalars()
    assert [(t.assignee_id, "weather" in t.title) for t in tasks] == [(test_user["id"], True)]


async def test_hire_days_and_cost(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree):
    headers = await _as(client, db_session, test_user, *ALL)
    made = await client.post("/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw}, headers=headers)
    sid = made.json()["id"]
    ten_days_ago = date.today() - timedelta(days=10)
    for step in ("approved", "erecting"):
        await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
    await client.post(
        f"/api/v1/scaffolds/{sid}/transition", json={"status": "erected", "on": ten_days_ago.isoformat()}, headers=headers
    )
    await client.patch(f"/api/v1/scaffolds/{sid}", json={"hire_rate": "45.50"}, headers=headers)

    s = (await client.get(f"/api/v1/scaffolds/{sid}")).json()
    assert s["days_erected"] == 11
    assert s["hire_cost"] == "500.50"

    week = await client.get(
        "/api/v1/scaffolds/hire",
        params={"project_id": site.project.id, "start": (date.today() - timedelta(days=6)).isoformat()},
    )
    body = week.json()
    assert (body["total_days"], body["total_cost"], body["currency"]) == (7, "318.50", "AUD")

    # dismantled three days ago: hire stops counting then
    for step in ("dismantle_requested", "dismantling"):
        await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    await client.post(
        f"/api/v1/scaffolds/{sid}/transition", json={"status": "dismantled", "on": three_days_ago}, headers=headers
    )
    s = (await client.get(f"/api/v1/scaffolds/{sid}")).json()
    assert s["days_erected"] == 8

    export = await client.get("/api/v1/scaffolds/export", params={"project_id": site.project.id, "format": "csv"})
    assert export.status_code == 200
    assert "SCF-001" in export.text


async def test_readiness_for_the_planner(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree):
    headers = await _as(client, db_session, test_user, *ALL)
    today = date.today()
    # nothing serves RSW 101.2 yet: nothing to wait for
    assert await scaffold_ready(db_session, site.rsw2, today)

    made = await client.post(
        "/api/v1/scaffolds/",
        json={"project_id": site.project.id, "node_id": site.rsw, "linked_node_ids": [site.rsw2]},
        headers=headers,
    )
    sid = made.json()["id"]
    assert not await scaffold_ready(db_session, site.rsw2, today)  # linked, only requested
    answer = (await client.get("/api/v1/scaffolds/readiness", params={"node_id": site.asset})).json()
    assert answer["ready"] is False
    assert answer["blockers"][0]["reason"] == "not erected yet"

    for step in ("approved", "erecting", "erected"):
        await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
    assert not await scaffold_ready(db_session, site.rsw, today)  # erected, not tagged
    await client.post(f"/api/v1/scaffolds/{sid}/inspections", json={"kind": "handover", "tag": "green"}, headers=headers)

    assert await scaffold_ready(db_session, site.rsw, today)
    assert await scaffold_ready(db_session, site.rsw2, today)
    assert await scaffold_ready(db_session, site.area, today)
    assert not await scaffold_ready(db_session, site.rsw, today + timedelta(days=8))  # due again before then
    later = (
        await client.get("/api/v1/scaffolds/readiness", params={"node_id": site.rsw, "on_date": str(today + timedelta(days=8))})
    ).json()
    assert later["blockers"][0]["reason"] == "inspection overdue by then"

    # a red tag blocks
    await client.post(f"/api/v1/scaffolds/{sid}/inspections", json={"kind": "ad_hoc", "tag": "red"}, headers=headers)
    assert not await scaffold_ready(db_session, site.rsw, today)

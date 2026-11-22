"""Saved register views: round trip, private / project / team visibility, editing rights and defaults."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from tests.integration.modules.submittals_cde.helpers import client_team, make_project, make_user, sign_in

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

BASE = "/api/v1/saved-views/"
USER = ("projects.read", "saved_views.read", "saved_views.create")
SHARER = (*USER, "saved_views.share")
MANAGER = (*SHARER, "saved_views.manage")

CONFIG = {
    "columns": [{"colId": "code", "width": 90}, {"colId": "title", "flex": 1}, {"colId": "status", "hide": True}],
    "sort": [{"colId": "code", "sort": "desc"}],
    "filters": {"status": {"filterType": "text", "type": "equals", "filter": "open"}},
    "group_by": ["status"],
}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def people(db_session: AsyncSession):
    project = await make_project(db_session)
    return {
        "project": project.id,
        "alice": await make_user(db_session, "Alice", *SHARER),
        "bob": await make_user(db_session, "Bob", *USER),
        "carol": await make_user(db_session, "Carol", *USER),
        "mgr": await make_user(db_session, "Mgr", *MANAGER),
    }


async def as_(client: AsyncClient, user: dict) -> dict[str, str]:
    client.cookies.clear()
    return await sign_in(client, user)


async def names(client: AsyncClient, project_id: int, register: str = "rfi.register") -> list[str]:
    r = await client.get(BASE, params={"project_id": project_id, "register_key": register})
    assert r.status_code == 200, r.text
    return [v["name"] for v in r.json()["data"]]


async def save(client: AsyncClient, headers: dict, project_id: int, name: str, expect: int = 201, **extra) -> dict:
    r = await client.post(
        BASE, json={"project_id": project_id, "register_key": "rfi.register", "name": name, **extra}, headers=headers
    )
    assert r.status_code == expect, r.text
    return r.json()


async def test_round_trip_keeps_the_grid_state(client: AsyncClient, people):
    p = people["project"]
    h = await as_(client, people["bob"])
    made = await save(client, h, p, "Open by code", config=CONFIG)
    got = (await client.get(f"{BASE}{made['id']}")).json()
    assert got["config"] == CONFIG
    assert got["owner_name"] == "Bob" and got["can_edit"] is True and got["visibility"] == "private"

    changed = await client.patch(f"{BASE}{made['id']}", json={"config": {**CONFIG, "sort": []}, "name": "Open"}, headers=h)
    assert changed.status_code == 200, changed.text
    assert changed.json()["config"]["sort"] == [] and changed.json()["name"] == "Open"
    # A different register doesn't list it.
    assert await names(client, p, "ncr.register") == []


async def test_visibility_private_project_and_team(client: AsyncClient, db_session: AsyncSession, people):
    p = people["project"]
    team = await client_team(db_session, people["bob"]["id"])

    h = await as_(client, people["alice"])
    await save(client, h, p, "Mine")
    shared = await save(client, h, p, "Everyone", visibility="project")
    team_view = await save(client, h, p, "Bob's team", visibility="team", team_ids=[team.id])
    assert team_view["team_ids"] == [team.id]
    await save(client, h, p, "No teams", expect=422, visibility="team")
    assert await names(client, p) == ["Bob's team", "Everyone", "Mine"]

    await as_(client, people["bob"])
    assert await names(client, p) == ["Bob's team", "Everyone"]
    assert (await client.get(f"{BASE}{shared['id']}")).json()["can_edit"] is False

    hc = await as_(client, people["carol"])
    assert await names(client, p) == ["Everyone"]
    assert (await client.get(f"{BASE}{team_view['id']}")).status_code == 404
    # Bob and Carol can't share or change Alice's views.
    await save(client, hc, p, "Shared?", expect=403, visibility="project")
    assert (await client.patch(f"{BASE}{shared['id']}", json={"name": "x"}, headers=hc)).status_code == 403
    assert (await client.delete(f"{BASE}{shared['id']}", headers=hc)).status_code == 403

    # A manager sees and edits every shared view, never a private one.
    hm = await as_(client, people["mgr"])
    assert await names(client, p) == ["Bob's team", "Everyone"]
    assert (await client.patch(f"{BASE}{team_view['id']}", json={"name": "Team B"}, headers=hm)).status_code == 200

    # Making the team view private again hides it from Bob.
    h = await as_(client, people["alice"])
    assert (await client.patch(f"{BASE}{team_view['id']}", json={"visibility": "private"}, headers=h)).json()["team_ids"] == []
    await as_(client, people["bob"])
    assert await names(client, p) == ["Everyone"]


async def test_views_need_a_readable_project(client: AsyncClient, db_session: AsyncSession, people):
    outsider = await make_user(db_session, "Out", "saved_views.read", "saved_views.create")
    h = await as_(client, outsider)
    await save(client, h, people["project"], "Nope", expect=404)
    r = await client.get(BASE, params={"project_id": people["project"], "register_key": "rfi.register"})
    assert r.status_code == 404


async def test_defaults_personal_then_project(client: AsyncClient, people):
    p = people["project"]
    params = {"project_id": p, "register_key": "rfi.register"}

    hm = await as_(client, people["mgr"])
    project_default = await save(client, hm, p, "Team standard", visibility="project", is_default=True)
    other = await save(client, hm, p, "Alt standard", visibility="project", is_default=True)
    listed = {v["name"]: v["is_default"] for v in (await client.get(BASE, params=params)).json()["data"]}
    assert listed == {"Alt standard": True, "Team standard": False}  # one project default per register
    await client.patch(f"{BASE}{project_default['id']}", json={"is_default": True}, headers=hm)

    hb = await as_(client, people["bob"])
    assert (await client.get(f"{BASE}default", params=params)).json()["name"] == "Team standard"
    mine = await save(client, hb, p, "My way", is_default=True)
    assert (await client.get(f"{BASE}default", params=params)).json()["id"] == mine["id"]
    second = await save(client, hb, p, "My other way", is_default=True)
    assert (await client.get(f"{BASE}{mine['id']}")).json()["is_default"] is False
    assert (await client.get(f"{BASE}default", params=params)).json()["id"] == second["id"]

    # Bob can't set or clear the project default, and team views can't be defaults.
    assert (await client.patch(f"{BASE}{other['id']}", json={"is_default": True}, headers=hb)).status_code == 403
    await save(client, hb, p, "Bad", expect=403, visibility="project", is_default=True)
    ha = await as_(client, people["alice"])
    await save(client, ha, p, "Team default", expect=422, visibility="team", team_ids=[1], is_default=True)

    await as_(client, people["carol"])
    assert (await client.get(f"{BASE}default", params=params)).json()["name"] == "Team standard"


async def test_deleting_own_view(client: AsyncClient, people):
    p = people["project"]
    h = await as_(client, people["bob"])
    made = await save(client, h, p, "Temp")
    assert (await client.delete(f"{BASE}{made['id']}", headers=h)).status_code == 200
    assert await names(client, p) == []

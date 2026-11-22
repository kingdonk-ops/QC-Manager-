"""The asset breakdown: packs, parent rules, code scopes, work anchors, restructure with lineage, items, scan lookup."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = ("projects.read", *(f"asset_tree.{a}" for a in ("read", "create", "update", "delete", "import", "configure")))


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def setup(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="P-1", name="Plant")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "assets", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    applied = await client.post(
        "/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers
    )
    assert applied.json() == {"levels_added": 4, "item_types_added": 6}, applied.text

    async def node(level: str, code: str, parent: int | None = None, expect: int = 201) -> dict:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=headers,
        )
        assert r.status_code == expect, r.text
        return r.json()

    return project, headers, node


async def test_a_pack_applies_once(client: AsyncClient, setup):
    project, headers, _ = setup
    again = await client.post(
        "/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers
    )
    assert again.json() == {"levels_added": 0, "item_types_added": 0}
    levels = [lv["key"] for lv in (await client.get("/api/v1/asset-tree/levels", params={"project_id": project.id})).json()]
    assert levels == ["site", "area", "asset", "rsw"]


async def test_parents_codes_and_display_paths(client: AsyncClient, setup):
    _, _, node = setup
    site = await node("site", "KAR")
    area = await node("area", "A1", site["id"])
    asset = await node("asset", "101", area["id"])
    rsw = await node("rsw", "101.1", asset["id"])
    assert rsw["display_path"] == "KAR / A1 / 101 / 101.1"
    assert rsw["display_code"] == "101 / 101.1"

    await node("rsw", "X", site["id"], expect=422)  # an RSW can't sit under a site
    await node("rsw", "101.1", asset["id"], expect=409)  # per-parent code clash
    other = await node("asset", "102", area["id"])
    await node("rsw", "101.1", other["id"])  # fine under another parent
    await node("site", "KAR", expect=409)  # sites are unique per project


async def test_work_anchors_are_found_and_never_nested(client: AsyncClient, setup):
    _, headers, node = setup
    site = await node("site", "S")
    asset = await node("asset", "101", site["id"])
    rsw = await node("rsw", "101.1", asset["id"])

    found = await client.get(f"/api/v1/asset-tree/nodes/{rsw['id']}/work-anchor")
    assert found.json()["id"] == rsw["id"]
    none = await client.get(f"/api/v1/asset-tree/nodes/{asset['id']}/work-anchor")
    assert none.status_code == 422
    assert "work anchor" in none.text


async def test_moving_a_subtree_rewrites_paths(client: AsyncClient, setup):
    _, headers, node = setup
    site = await node("site", "S")
    a1, a2 = await node("area", "A1", site["id"]), await node("area", "A2", site["id"])
    asset = await node("asset", "101", a1["id"])
    rsw = await node("rsw", "101.1", asset["id"])

    moved = await client.post(f"/api/v1/asset-tree/nodes/{asset['id']}/move", json={"parent_id": a2["id"]}, headers=headers)
    assert moved.status_code == 200, moved.text
    child = (await client.get(f"/api/v1/asset-tree/nodes/{rsw['id']}")).json()
    assert child["display_path"] == "S / A2 / 101 / 101.1"
    assert child["path"].startswith(f"/{site['id']}/{a2['id']}/{asset['id']}/")
    assert (
        await client.post(f"/api/v1/asset-tree/nodes/{a2['id']}/move", json={"parent_id": rsw["id"]}, headers=headers)
    ).status_code == 422


async def test_split_and_merge_keep_lineage(client: AsyncClient, setup):
    project, headers, node = setup
    site = await node("site", "S")
    asset = await node("asset", "101", site["id"])
    rsw = await node("rsw", "R1", asset["id"])

    parts = (
        await client.post(
            f"/api/v1/asset-tree/nodes/{rsw['id']}/split", json={"parts": [{"code": "R1a"}, {"code": "R1b"}]}, headers=headers
        )
    ).json()
    source = (await client.get(f"/api/v1/asset-tree/nodes/{rsw['id']}")).json()
    assert source["status"] == "retired"
    assert source["superseded_by"] == [p["id"] for p in parts]
    assert all(p["derived_from"] == [rsw["id"]] for p in parts)

    merged = (
        await client.post(
            f"/api/v1/asset-tree/nodes/{parts[0]['id']}/merge", json={"source_ids": [parts[1]["id"]]}, headers=headers
        )
    ).json()
    assert merged["derived_from"] == sorted([rsw["id"], parts[1]["id"]])
    active = (
        await client.get("/api/v1/asset-tree/nodes/", params={"project_id": project.id, "parent_id": asset["id"]})
    ).json()["data"]
    assert [n["code"] for n in active] == ["R1a"]


async def test_items_take_their_work_anchor_and_scan_tags(client: AsyncClient, setup):
    project, headers, node = setup
    site = await node("site", "S")
    asset = await node("asset", "101", site["id"])
    rsw = await node("rsw", "101.1", asset["id"])

    created = await client.post(
        "/api/v1/asset-tree/items/",
        json={
            "project_id": project.id,
            "node_id": rsw["id"],
            "item_type_key": "pipe_spool",
            "tag": "SP-0001",
            "custom_fields": {"nps": '4"'},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["work_anchor_id"] == rsw["id"]

    tagged = await client.post(
        f"/api/v1/asset-tree/items/{item['id']}/identifiers", json={"kind": "nfc", "value": "04:a2:3b:ff"}, headers=headers
    )
    assert tagged.json()["identifiers"][0]["value"] == "04A23BFF"
    hit = await client.get(
        "/api/v1/asset-tree/items/lookup", params={"project_id": project.id, "value": "04a23bff", "kind": "nfc"}
    )
    assert hit.json()["id"] == item["id"]
    by_tag = await client.get("/api/v1/asset-tree/items/lookup", params={"project_id": project.id, "value": "sp-0001"})
    assert by_tag.json()["id"] == item["id"]
    assert (
        await client.get("/api/v1/asset-tree/items/lookup", params={"project_id": project.id, "value": "nothing"})
    ).status_code == 404

    under_site = (
        await client.get("/api/v1/asset-tree/items/", params={"project_id": project.id, "node_id": site["id"]})
    ).json()
    assert under_site["total_count"] == 1

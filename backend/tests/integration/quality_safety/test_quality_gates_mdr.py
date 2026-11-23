"""The MDR gate hook: a pending blocking quality gate in a dossier's scope (or without any attachment) blocks dossier
issue; released, voided, non-blocking and out-of-scope gates do not."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.config.settings import settings
from src.infrastructure.modules import state
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
STAFF = (
    "projects.read",
    "files.read",
    "ncr.read",
    "audit.read",
    "asset_tree.read",
    *(f"mdr.{a}" for a in ("read", "create", "update", "delete", "submit", "sign")),
    *(f"inspections.{a}" for a in ("read", "create", "update", "delete", "approve")),
)
ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]
QA = "contractor_qa"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


class World:
    def __init__(self, client: AsyncClient, tree: Tree, headers: dict[str, str]):
        self.client, self.tree, self.headers = client, tree, headers
        self.project = tree.project

    async def gate(self, **values: Any) -> dict[str, Any]:
        body = {"project_id": self.project.id, "title": "Pre-issue hold", **values}
        r = await self.client.post(f"{API}/gates/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def release(self, gate_id: int) -> None:
        r = await self.client.post(f"{API}/gates/{gate_id}/release", json={"authority": QA}, headers=self.headers)
        assert r.status_code == 200, r.text

    async def void(self, gate_id: int) -> None:
        r = await self.client.post(f"{API}/gates/{gate_id}/void", json={}, headers=self.headers)
        assert r.status_code == 200, r.text

    async def dossier(self, *scope: int) -> str:
        body = {"project_id": self.project.id, "title": "Piping turnover", "scope_node_ids": list(scope)}
        r = await self.client.post("/api/v1/mdr/dossiers/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return f"/api/v1/mdr/dossiers/{r.json()['id']}"

    async def check(self, base: str) -> dict[str, Any]:
        """The quality-gates row of the dossier gate, with the overall readiness."""
        gate = (await self.client.get(f"{base}/gate")).json()
        row = next(c for c in gate["checks"] if c["key"] == "quality_gates")
        return {**row, "ready": gate["ready"]}


@pytest_asyncio.fixture
async def world(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> World:
    monkeypatch.setattr(settings, "FILE_STORAGE_DIR", str(tmp_path))
    tree = await build_tree(db_session, "LM-1")
    await _grant(db_session, test_user["id"], "gate_mdr_staff", *STAFF)
    return World(client, tree, {"X-CSRF-Token": await _login(client, test_user)})


async def test_a_pending_hold_in_scope_stops_the_issue_until_it_is_released(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    held = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)

    row = await w.check(base)
    assert row["status"] == "fail" and row["blocking"] is True and row["ready"] is False
    assert [f["reference"] for f in row["findings"]] == [held["number"]]
    blocked = await w.client.post(f"{base}/issue", json={"purpose": "review"}, headers=w.headers)
    assert blocked.status_code == 422 and held["number"] in blocked.text

    await w.release(held["id"])
    row = await w.check(base)
    assert row["status"] == "pass" and row["findings"] == [] and row["ready"] is True
    issued = await w.client.post(f"{base}/issue", json={"purpose": "review"}, headers=w.headers)
    assert issued.status_code == 201, issued.text


async def test_an_unattached_blocking_gate_counts_project_wide(world: World):
    w = world
    base = await w.dossier(w.tree.rsw2)
    loose = await w.gate()
    row = await w.check(base)
    assert row["status"] == "fail" and [f["reference"] for f in row["findings"]] == [loose["number"]]
    assert (await w.client.post(f"{base}/issue", json={"purpose": "review"}, headers=w.headers)).status_code == 422

    await w.void(loose["id"])
    row = await w.check(base)
    assert row["status"] == "pass" and row["ready"] is True


async def test_gates_outside_the_scope_or_not_blocking_do_not_count(world: World):
    w = world
    base = await w.dossier(w.tree.rsw)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw2)  # another RSW, outside the scope
    await w.gate(kind="surveillance", attachment_kind="node", attachment_id=w.tree.rsw)  # advisory
    await w.gate(kind="review")
    row = await w.check(base)
    assert row["status"] == "pass" and row["findings"] == []

    whole = await w.dossier()
    assert (await w.check(whole))["status"] == "fail"  # no scope nodes: the whole project counts


async def test_a_gate_on_an_inspection_anchored_in_scope_blocks(world: World):
    w = world
    pid = w.project.id
    body = {"project_id": pid, "name": "Anchored check", "area": "qa_itp", "sections": ONE_CHECK}
    template = (await w.client.post(f"{API}/templates/", json=body, headers=w.headers)).json()
    made = await w.client.post(
        f"{API}/", json={"project_id": pid, "template_id": template["id"], "node_id": w.tree.rsw}, headers=w.headers
    )
    assert made.status_code == 201, made.text
    held = await w.gate(attachment_kind="inspection", attachment_id=made.json()["id"])

    inside = await w.dossier(w.tree.rsw)
    assert [f["reference"] for f in (await w.check(inside))["findings"]] == [held["number"]]
    outside = await w.dossier(w.tree.rsw2)
    assert (await w.check(outside))["status"] == "pass"

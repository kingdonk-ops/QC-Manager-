"""ITP line gate state: review, pending, blocked, passed and released, with the satisfied flag and the reason."""

from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.inspections.eligibility import line_gate_state
from src.modules.inspections.models import Inspection
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
INSPECTOR = (
    "projects.read",
    "asset_tree.read",
    "tasks.read",
    "files.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "transition", "submit")),
)
REVIEWER = (
    "projects.read",
    "files.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "review", "approve")),
)
ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


class World:
    def __init__(self, client: AsyncClient, tree: Tree, users: dict[str, dict[str, Any]]):
        self.client, self.tree, self.users = client, tree, users
        self.project = tree.project
        self.headers: dict[str, str] = {}
        self.current: str | None = None

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def post(self, path: str, body: dict[str, Any], expect: int = 200) -> dict[str, Any]:
        r = await self.client.post(f"{API}{path}", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def instance(self, points: list[dict[str, str]]) -> dict[str, Any]:
        pid = self.project.id
        form_body = {"project_id": pid, "name": "ITR", "area": "qa_itp", "is_formal": True, "sections": ONE_CHECK}
        form = await self.post("/templates/", form_body, expect=201)
        activities = [
            {"title": f"Activity {n}", "form_template_id": form["id"], "points": p} for n, p in enumerate(points, start=1)
        ]
        plan = await self.post("/templates/", {"project_id": pid, "name": "Plan", "kind": "itp", "activities": activities}, 201)
        return await self.post("/itp/instances", {"template_id": plan["id"], "node_id": self.tree.rsw}, expect=201)

    async def lines(self, instance_id: int) -> list[dict[str, Any]]:
        r = await self.client.get(f"{API}/itp/instances/{instance_id}")
        assert r.status_code == 200, r.text
        return r.json()["lines"]

    async def pass_line(self, line_id: int) -> None:
        """Inspector answers and submits, the reviewer approves: the line is completed as passed."""
        await self.as_("inspector")
        record = (await self.client.get(f"{API}/{line_id}")).json()
        answer = {"id": record["items"][0]["id"], "result": "pass"}
        r = await self.client.patch(f"{API}/{line_id}/items", json={"items": [answer]}, headers=self.headers)
        assert r.status_code == 200, r.text
        await self.post(f"/{line_id}/submit", {"proposed_result": "pass", "accept_intent": True})
        await self.as_("reviewer")
        await self.post(f"/{line_id}/review", {"decision": "approve", "accept_intent": True})


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    tree = await build_tree(db_session, "LS-1")
    await _grant(db_session, test_user["id"], "line_inspector", *INSPECTOR)
    await _grant(db_session, test_user_2["id"], "line_reviewer", *REVIEWER)
    w = World(client, tree, {"inspector": test_user, "reviewer": test_user_2})
    return await w.as_("inspector")


def _states(lines: list[dict[str, Any]]) -> list[tuple[str, bool]]:
    return [(ln["gate_state"], ln["gate_satisfied"]) for ln in lines]


async def test_a_passed_hold_is_satisfied_only_once_released_and_a_passed_witness_without_release(world: World):
    w = world
    instance = await w.instance([{"contractor": "H"}, {"contractor": "W"}, {"contractor": "R"}])
    line1, line2, line3 = instance["lines"]
    assert [ln["position"] for ln in instance["lines"]] == [1, 2, 3]
    assert _states(instance["lines"]) == [("pending", False), ("blocked", False), ("review", True)]
    assert line1["gate_reason"] and line3["gate_reason"] is None

    await w.pass_line(line1["id"])
    lines = await w.lines(instance["id"])
    assert _states(lines)[0] == ("passed", False)
    assert "passed" in lines[0]["gate_reason"] and "not been released" in lines[0]["gate_reason"]
    assert lines[1]["gate_state"] == "blocked"  # line 2 still waits for line 1's hold release

    await w.as_("reviewer")
    await w.post(f"/{line1['id']}/hold-release", {"accept_intent": True})
    lines = await w.lines(instance["id"])
    assert _states(lines) == [("released", True), ("pending", False), ("review", True)]
    assert lines[0]["gate_reason"] is None

    await w.pass_line(line2["id"])
    lines = await w.lines(instance["id"])
    assert _states(lines) == [("released", True), ("passed", True), ("review", True)]  # a witness needs no release
    assert [ln["position"] for ln in lines] == [1, 2, 3]  # ascending, each with its state


async def test_a_line_behind_an_unreleased_hold_names_it_until_it_is_released(world: World):
    w = world
    instance = await w.instance([{"contractor": "H"}, {"client": "W"}])
    line1, line2 = instance["lines"]
    assert line2["gate_state"] == "blocked" and line1["code"] in line2["gate_reason"]

    await w.pass_line(line1["id"])
    await w.post(f"/{line1['id']}/hold-release", {"accept_intent": True})
    after = (await w.lines(instance["id"]))[1]
    assert (after["gate_state"], after["gate_satisfied"]) == ("pending", False)
    assert after["blocked"] is False  # the existing blocked flag keeps working beside the new state


def _line(points: dict[str, str], status: str, result: str | None, released: bool = False) -> Inspection:
    record = Inspection(project_id=1, code="ITP-001/01", title="Activity", points=points, status=status, result=result)
    record.hold_released_at = datetime.now(UTC) if released else None
    return record


async def test_a_failed_line_is_never_satisfied_and_only_hold_or_witness_points_make_a_gate():
    failed = line_gate_state(_line({"contractor": "H"}, "completed", "fail"), [])
    assert failed == {"gate_state": "pending", "gate_satisfied": False, "gate_reason": "The inspection failed."}
    assert line_gate_state(_line({"client": "W"}, "completed", "fail"), [])["gate_satisfied"] is False
    assert line_gate_state(_line({"client": "W"}, "closed", "pass"), [])["gate_state"] == "passed"
    assert line_gate_state(_line({"contractor": "H"}, "closed", "pass", released=True), [])["gate_state"] == "released"
    reopened = line_gate_state(_line({"contractor": "H"}, "in_progress", "pass"), [])
    assert (reopened["gate_state"], reopened["gate_satisfied"]) == ("pending", False)  # the latest result decides
    for points in ({"contractor": "R"}, {"contractor": "S"}, {"contractor": "none"}, {}):
        assert line_gate_state(_line(points, "planned", None), []) == {
            "gate_state": "review",
            "gate_satisfied": True,
            "gate_reason": None,
        }

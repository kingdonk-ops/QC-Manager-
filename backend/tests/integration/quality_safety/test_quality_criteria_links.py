"""Criterion links: template items and ITP activities reference a criterion, limits are snapshotted onto the
record, the record carries a criterion and measured value, and a standing result freezes the reference."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
PERMS = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "tasks.read",
    "files.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "delete", "transition")),
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


class World:
    def __init__(self, client: AsyncClient, tree: Tree, headers: dict[str, str]):
        self.client, self.tree, self.headers = client, tree, headers
        self.project = tree.project

    async def criterion(self, code: str, project_id: int | None = None, **extra: Any) -> dict[str, Any]:
        body = {"project_id": project_id or self.project.id, "code": code, "title": f"Criterion {code}", **extra}
        r = await self.client.post(f"{API}/criteria/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def template(self, expect: int = 201, **values: Any) -> Any:
        r = await self.client.post(f"{API}/templates/", json={"project_id": self.project.id, **values}, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def inspection(self, template_id: int, expect: int = 201, **values: Any) -> Any:
        body = {"project_id": self.project.id, "template_id": template_id, **values}
        r = await self.client.post(f"{API}/", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict) -> World:
    tree = await build_tree(db_session, "QL-1")
    await _grant(db_session, test_user["id"], "quality_links", *PERMS)
    return World(client, tree, {"X-CSRF-Token": await _login(client, test_user)})


def _section(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"title": "Checks", "items": list(items)}]


async def test_numeric_criterion_limits_are_snapshotted_onto_the_item(world: World):
    w = world
    crit = await w.criterion(
        "THK", rule_type="range", lower_limit="50", upper_limit="55", unit="mm", title="Insulation thickness"
    )
    linked = {"text": "Thickness", "criterion_id": crit["id"]}
    tpl = await w.template(name="Thickness", sections=_section(linked, {"text": "Plain"}))
    record = await w.inspection(tpl["id"])
    first, plain = record["items"]
    assert (first["criterion_id"], first["response_type"], first["min_value"], first["max_value"], first["unit"]) == (
        crit["id"],
        "numeric",
        50.0,
        55.0,
        "mm",
    )
    assert plain["criterion_id"] is None and plain["response_type"] == "pass_fail"
    assert (record["criterion_id"], record["measured_value"], record["conditional"], record["report_id"]) == (
        None,
        None,
        False,
        None,
    )

    # a title change leaves the snapshot alone; a limit change is refused once a record is judged against it
    renamed = await w.client.patch(f"{API}/criteria/{crit['id']}", json={"title": "Thickness (revised)"}, headers=w.headers)
    assert renamed.status_code == 200
    refused = await w.client.patch(f"{API}/criteria/{crit['id']}", json={"lower_limit": "40"}, headers=w.headers)
    assert refused.status_code == 409
    again = (await w.client.get(f"{API}/{record['id']}")).json()["items"][0]
    assert (again["min_value"], again["max_value"]) == (50.0, 55.0)


async def test_a_non_numeric_criterion_leaves_a_pass_fail_item_with_the_clause_in_its_guidance(world: World):
    w = world
    crit = await w.criterion("VIS", rule_type="free_text", title="Surface finish", standards_ref="ISO 8501")
    tpl = await w.template(
        name="Finish", sections=_section({"text": "Surface clean", "guidance": "Look closely", "criterion_id": crit["id"]})
    )
    item = (await w.inspection(tpl["id"]))["items"][0]
    assert item["response_type"] == "pass_fail" and item["criterion_id"] == crit["id"]
    assert (item["min_value"], item["max_value"]) == (None, None)
    assert "Criterion VIS - Surface finish (ISO 8501)." in item["guidance"] and item["guidance"].startswith("Look closely")

    half = await w.criterion("HALF", rule_type="range", lower_limit="5", upper_limit="n/a", unit="mm")
    tpl2 = await w.template(name="Half", sections=_section({"text": "Gap", "criterion_id": half["id"]}))
    assert (await w.inspection(tpl2["id"]))["items"][0]["response_type"] == "pass_fail"


async def test_a_foreign_or_missing_criterion_answers_not_found(world: World, db_session: AsyncSession):
    w = world
    other = Project(code="QL-X", name="Another project")
    db_session.add(other)
    await db_session.commit()
    foreign = await w.criterion("FOR", project_id=other.id)
    item = {"text": "Thickness", "criterion_id": foreign["id"]}
    await w.template(expect=404, name="Foreign", sections=_section(item))
    await w.template(expect=404, name="Missing", sections=_section({"text": "x", "criterion_id": 999999}))

    plain = await w.template(name="Plain", sections=_section({"text": "x"}))
    await w.inspection(plain["id"], expect=404, criterion_id=foreign["id"])
    await w.inspection(plain["id"], expect=404, criterion_id=999999)


async def test_the_record_criterion_cannot_change_while_a_result_stands(world: World):
    w = world
    crit = await w.criterion("REC", rule_type="maximum", upper_limit="50")
    other = await w.criterion("REC2", rule_type="maximum", upper_limit="60")
    tpl = await w.template(name="One check", sections=_section({"text": "Checked"}))
    record = await w.inspection(tpl["id"], criterion_id=crit["id"], measured_value="42")
    assert (record["criterion_id"], record["measured_value"]) == (crit["id"], "42")
    url = f"{API}/{record['id']}"

    swapped = await w.client.patch(url, json={"criterion_id": other["id"]}, headers=w.headers)
    assert swapped.status_code == 200 and swapped.json()["criterion_id"] == other["id"]

    item_id = record["items"][0]["id"]
    filled = await w.client.patch(f"{url}/items", json={"items": [{"id": item_id, "result": "pass"}]}, headers=w.headers)
    assert filled.status_code == 200, filled.text
    done = await w.client.post(f"{url}/complete", json={}, headers=w.headers)
    assert done.status_code == 200, done.text

    refused = await w.client.patch(url, json={"criterion_id": crit["id"]}, headers=w.headers)
    assert refused.status_code == 422 and "reopen" in refused.text
    assert (await w.client.patch(url, json={"measured_value": "43"}, headers=w.headers)).status_code == 422
    assert (await w.client.get(url)).json()["criterion_id"] == other["id"]
    assert (await w.client.patch(url, json={"notes": "still editable"}, headers=w.headers)).status_code == 200

    reopened = await w.client.patch(f"{url}/status", json={"status": "in_progress"}, headers=w.headers)
    assert reopened.status_code == 200, reopened.text
    changed = await w.client.patch(url, json={"criterion_id": crit["id"]}, headers=w.headers)
    assert changed.status_code == 200 and changed.json()["criterion_id"] == crit["id"]


async def test_an_itp_line_keeps_its_wording_and_carries_the_activity_criterion(world: World):
    w = world
    crit = await w.criterion("DFT", rule_type="range", lower_limit="60", upper_limit="100", unit="um")
    itp = await w.template(
        name="Coating ITP",
        kind="itp",
        activities=[
            {
                "title": "Primer",
                "acceptance_criteria": "DFT 60-100 um as specified",
                "criterion_id": crit["id"],
                "points": {"contractor": "S"},
            },
            {"title": "Final review", "points": {"contractor": "R"}},
        ],
    )
    instance = {"template_id": itp["id"], "node_id": w.tree.rsw}
    made = await w.client.post(f"{API}/itp/instances", json=instance, headers=w.headers)
    assert made.status_code == 201, made.text
    first, second = made.json()["lines"]
    assert first["criterion_id"] == crit["id"] and second["criterion_id"] is None
    line = (await w.client.get(f"{API}/{first['id']}")).json()
    assert line["criterion_id"] == crit["id"] and line["acceptance_criteria"] == "DFT 60-100 um as specified"

    await w.template(expect=404, name="Bad ITP", kind="itp", activities=[{"title": "x", "criterion_id": 999999}])


async def test_a_criterion_named_by_a_template_cannot_be_deleted(world: World):
    w = world
    crit = await w.criterion("TPL", rule_type="minimum", lower_limit="3")
    tpl = await w.template(name="Holder", sections=_section({"text": "Checked", "criterion_id": crit["id"]}))
    refused = await w.client.delete(f"{API}/criteria/{crit['id']}", headers=w.headers)
    assert refused.status_code == 409 and "1 templates" in refused.text
    assert (await w.client.delete(f"{API}/templates/{tpl['id']}", headers=w.headers)).status_code == 200
    assert (await w.client.delete(f"{API}/criteria/{crit['id']}", headers=w.headers)).status_code == 200

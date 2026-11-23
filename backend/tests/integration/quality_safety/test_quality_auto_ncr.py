"""Automatic non-conformance reports raised when inspection results are recorded."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.inspections import completion
from src.modules.ncr.models import Ncr
from src.modules.ncr.templates import IssueRuleError
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
INSPECTOR = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "tasks.read",
    "files.read",
    "ncr.read",
    "ncr.transition",
    *(f"inspections.{a}" for a in ("read", "create", "update", "delete", "transition", "submit", "manage")),
)
REVIEWER = ("projects.read", "inspections.read", "inspections.review")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


class World:
    def __init__(self, client: AsyncClient, db: AsyncSession, tree: Tree, headers: dict[str, str]):
        self.client, self.db, self.tree, self.headers = client, db, tree, headers
        self.project = tree.project

    async def criterion(self, code: str, **extra: Any) -> dict[str, Any]:
        body = {"project_id": self.project.id, "code": code, "title": f"Title {code}", **extra}
        r = await self.client.post(f"{API}/criteria/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def template(self, *items: dict[str, Any], **extra: Any) -> dict[str, Any]:
        sections = [{"title": "Checks", "items": list(items) or [{"text": "Checked"}]}]
        body = {"project_id": self.project.id, "name": "Auto report", "sections": sections, **extra}
        r = await self.client.post(f"{API}/templates/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def record(self, template_id: int, **extra: Any) -> dict[str, Any]:
        body = {"project_id": self.project.id, "template_id": template_id, **extra}
        r = await self.client.post(f"{API}/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def fill(self, record_id: int, *answers: dict[str, Any]) -> None:
        r = await self.client.patch(f"{API}/{record_id}/items", json={"items": list(answers)}, headers=self.headers)
        assert r.status_code == 200, r.text

    async def complete(self, record_id: int, expect: int = 200, **body: Any) -> dict[str, Any]:
        r = await self.client.post(f"{API}/{record_id}/complete", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def reopen(self, record_id: int) -> None:
        r = await self.client.patch(f"{API}/{record_id}/status", json={"status": "in_progress"}, headers=self.headers)
        assert r.status_code == 200, r.text

    async def get(self, record_id: int) -> dict[str, Any]:
        return (await self.client.get(f"{API}/{record_id}")).json()

    async def ncr(self, ncr_id: int) -> Ncr:
        found = await self.db.scalar(select(Ncr).where(Ncr.id == ncr_id).execution_options(populate_existing=True))
        assert found is not None
        return found

    async def report_count(self, record_id: int) -> int:
        return await self.db.scalar(select(func.count()).select_from(Ncr).where(Ncr.inspection_id == record_id)) or 0


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict) -> World:
    tree = await build_tree(db_session, "QA-1")
    await _grant(db_session, test_user["id"], "quality_auto", *INSPECTOR)
    return World(client, db_session, tree, {"X-CSRF-Token": await _login(client, test_user)})


async def test_a_failed_record_with_a_criterion_raises_a_major_report_that_quotes_it(world: World):
    w = world
    crit = await w.criterion("WT-1", title="Wall thickness", rule_type="maximum", upper_limit="50", unit="mm")
    record = await w.record((await w.template())["id"], criterion_id=crit["id"])
    await w.fill(record["id"], {"id": record["items"][0]["id"], "result": "fail"})

    done = await w.complete(record["id"], measured_value="60")
    assert done["status"] == "completed" and done["result"] == "fail"
    assert done["report_id"] is not None and done["measured_value"] == "60"
    report = await w.ncr(done["report_id"])
    assert (report.severity, report.status, report.inspection_id) == ("major", "open", record["id"])
    assert report.issue_type == "ncr" and report.source == "inspection"
    text = report.description or ""
    assert "Raised automatically from inspection" in text and "WT-1" in text and "Wall thickness" in text
    assert "inclusive upper bound 50" in text and "Measured value: 60." in text
    assert report.source_data and report.source_data["outcome"] == "fail" and report.source_data["measured_value"] == "60"
    assert report.source_data["criterion_id"] == crit["id"]
    # the plain failed item keeps the task-by-default follow-up
    assert (await w.get(record["id"]))["items"][0]["task_id"] is not None


async def test_a_plain_pass_raises_nothing(world: World):
    w = world
    record = await w.record((await w.template())["id"])
    await w.fill(record["id"], {"id": record["items"][0]["id"], "result": "pass"})
    done = await w.complete(record["id"])
    assert done["result"] == "pass" and done["report_id"] is None and done["conditional"] is False
    assert await w.report_count(record["id"]) == 0


async def test_a_conditional_acceptance_keeps_pass_and_raises_a_minor_report(world: World):
    w = world
    template = await w.template(issue_category="materials")
    first = await w.record(template["id"])
    await w.fill(first["id"], {"id": first["items"][0]["id"], "result": "pass"})
    done = await w.complete(first["id"], conditional=True, report_severity="minor")
    assert done["result"] == "pass" and done["conditional"] is True and done["report_id"] is not None
    report = await w.ncr(done["report_id"])
    assert report.severity == "minor" and report.source_data["outcome"] == "conditional"
    assert report.source_data["conditional"] is True

    second = await w.record(template["id"])
    await w.fill(second["id"], {"id": second["items"][0]["id"], "result": "pass"})
    defaulted = await w.complete(second["id"], conditional=True)
    assert (await w.ncr(defaulted["report_id"])).severity == "minor"
    third = await w.record(template["id"])
    await w.fill(third["id"], {"id": third["items"][0]["id"], "result": "pass"})
    overridden = await w.complete(third["id"], conditional=True, report_severity="critical")
    assert (await w.ncr(overridden["report_id"])).severity == "critical"


async def test_completing_twice_or_by_status_edit_is_refused_and_changes_nothing(world: World):
    w = world
    crit = await w.criterion("TW-1", rule_type="maximum", upper_limit="5")
    record = await w.record((await w.template())["id"], criterion_id=crit["id"])
    await w.fill(record["id"], {"id": record["items"][0]["id"], "result": "fail"})
    done = await w.complete(record["id"], measured_value="9")

    await w.complete(record["id"], expect=422)
    edited = await w.client.patch(f"{API}/{record['id']}/status", json={"status": "completed"}, headers=w.headers)
    assert edited.status_code == 422
    again = await w.get(record["id"])
    assert (again["status"], again["result"], again["report_id"]) == ("completed", "fail", done["report_id"])
    assert await w.report_count(record["id"]) == 1


async def test_the_project_setting_raises_a_report_for_a_failure_without_a_criterion(world: World):
    w = world
    template = await w.template()
    off = await w.record(template["id"])
    await w.fill(off["id"], {"id": off["items"][0]["id"], "result": "fail"})
    assert (await w.complete(off["id"], measured_value="7"))["report_id"] is None

    switched = await w.client.patch(
        f"{API}/settings", params={"project_id": w.project.id}, json={"auto_report_on_failure": True}, headers=w.headers
    )
    assert switched.status_code == 200 and switched.json()["auto_report_on_failure"] is True
    on = await w.record(template["id"])
    await w.fill(on["id"], {"id": on["items"][0]["id"], "result": "fail"})
    done = await w.complete(on["id"], measured_value="7")
    report = await w.ncr(done["report_id"])
    text = report.description or ""
    assert "Criterion" not in text and "Tolerance" not in text and "Measured value" not in text
    assert report.source_data["measured_value"] == "7" and report.source_data["criterion_id"] is None


async def test_a_failed_item_linked_to_a_criterion_gets_its_own_report_and_a_plain_one_a_task(world: World):
    w = world
    crit = await w.criterion(
        "THK", title="Insulation thickness", rule_type="range", lower_limit="50", upper_limit="55", unit="mm"
    )
    template = await w.template({"text": "Thickness", "criterion_id": crit["id"]}, {"text": "Plain check"})
    record = await w.record(template["id"])
    linked, plain = record["items"]
    await w.fill(record["id"], {"id": linked["id"], "reading": 48}, {"id": plain["id"], "result": "fail"})

    done = await w.complete(record["id"])
    assert done["report_id"] is None  # no record-level criterion and the setting is off
    after = {i["id"]: i for i in (await w.get(record["id"]))["items"]}
    assert after[linked["id"]]["ncr_id"] is not None and after[linked["id"]]["task_id"] is None
    assert after[plain["id"]]["task_id"] is not None and after[plain["id"]]["ncr_id"] is None
    report = await w.ncr(after[linked["id"]]["ncr_id"])
    assert report.severity == "major" and report.inspection_item_id == linked["id"]
    text = report.description or ""
    assert "inclusive lower bound 50" in text and "Measured value: 48." in text and "Insulation thickness" in text


async def test_a_reopened_record_raises_a_further_report_only_when_it_fails_again(world: World):
    w = world
    crit = await w.criterion("RE-1", rule_type="maximum", upper_limit="10")
    record = await w.record((await w.template())["id"], criterion_id=crit["id"])
    item_id = record["items"][0]["id"]
    await w.fill(record["id"], {"id": item_id, "result": "fail"})
    first = (await w.complete(record["id"], measured_value="12"))["report_id"]

    await w.reopen(record["id"])
    await w.fill(record["id"], {"id": item_id, "result": "pass"})
    passed = await w.complete(record["id"], measured_value="8")
    assert passed["result"] == "pass" and passed["report_id"] == first
    assert await w.report_count(record["id"]) == 1
    assert (await w.ncr(first)).status == "open"

    await w.reopen(record["id"])
    await w.fill(record["id"], {"id": item_id, "result": "fail"})
    second = (await w.complete(record["id"], measured_value="13"))["report_id"]
    assert second not in (None, first) and await w.report_count(record["id"]) == 2
    assert (await w.ncr(first)).status == "open"

    # a report raised from a failure cannot be closed straight from open
    closed = await w.client.patch(f"/api/v1/ncr/{first}/status", json={"status": "closed"}, headers=w.headers)
    assert closed.status_code == 422


async def test_a_failed_formal_itp_line_without_a_criterion_raises_no_automatic_report(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    tree = await build_tree(db_session, "QA-2")
    await _grant(db_session, test_user["id"], "line_inspector", *INSPECTOR)
    await _grant(db_session, test_user_2["id"], "line_reviewer", *REVIEWER)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    itp = await client.post(
        f"{API}/templates/",
        json={
            "project_id": tree.project.id,
            "name": "Wording only",
            "kind": "itp",
            "activities": [{"title": "Primer", "acceptance_criteria": "DFT at least 60 um", "points": {"contractor": "S"}}],
        },
        headers=headers,
    )
    assert itp.status_code == 201, itp.text
    instance = {"template_id": itp.json()["id"], "node_id": tree.rsw}
    made = await client.post(f"{API}/itp/instances", json=instance, headers=headers)
    assert made.status_code == 201, made.text
    line_id = made.json()["lines"][0]["id"]
    submitted = await client.post(
        f"{API}/{line_id}/submit", json={"proposed_result": "fail", "accept_intent": True}, headers=headers
    )
    assert submitted.status_code == 200, submitted.text

    reviewer_headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    approved = await client.post(
        f"{API}/{line_id}/review", json={"decision": "approve", "accept_intent": True}, headers=reviewer_headers
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["result"] == "fail" and body["report_id"] is None
    count = await db_session.scalar(select(func.count()).select_from(Ncr).where(Ncr.inspection_id == line_id))
    assert count == 0


async def test_if_the_report_cannot_be_created_the_whole_completion_fails(world: World, monkeypatch: pytest.MonkeyPatch):
    w = world
    crit = await w.criterion("ER-1", rule_type="maximum", upper_limit="10")
    record = await w.record((await w.template())["id"], criterion_id=crit["id"])
    await w.fill(record["id"], {"id": record["items"][0]["id"], "result": "fail"})

    async def refuse(*args: Any, **kwargs: Any) -> Ncr:
        raise IssueRuleError("There is no ncr template for this category.")

    monkeypatch.setattr(completion, "raise_automatic", refuse)
    await w.complete(record["id"], expect=422, measured_value="12")
    after = await w.get(record["id"])
    assert after["status"] == "in_progress" and after["result"] is None and after["report_id"] is None
    assert await w.report_count(record["id"]) == 0

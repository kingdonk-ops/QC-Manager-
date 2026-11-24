"""Distinct-signer counting on ITP lines: the additional-signatory action, the signatory status read, approval refused
until enough different people have signed, the required count carried from the template activity, and permissions."""

import asyncio
from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.inspections.eligibility import settings_of
from src.modules.inspections.models import InspectionSignature
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
BASE = ("projects.read", "asset_tree.read", "tasks.read", "files.read")
INSPECTOR = (*BASE, *(f"inspections.{a}" for a in ("read", "create", "update", "transition", "submit")))
REVIEWER = ("projects.read", "files.read", *(f"inspections.{a}" for a in ("read", "create", "update", "review", "approve")))
SOLO = (*INSPECTOR, "inspections.review", "inspections.approve")
READER = ("projects.read", "inspections.read")
OUTSIDER = ("inspections.read", "inspections.submit")
ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]
ADDITIONAL = "additional_signatory"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _user(db: AsyncSession, username: str) -> dict[str, Any]:
    u = User(
        name=username.capitalize(),
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        profile_image_url="https://example.com/x.jpg",
    )
    db.add(u)
    await db.commit()
    await reset_password_budget(u.id)
    return {"id": u.id, "name": u.name, "username": username, "password": "Password123!"}


class World:
    def __init__(self, client: AsyncClient, db: AsyncSession, tree: Tree, users: dict[str, dict[str, Any]]):
        self.client, self.db, self.tree, self.users = client, db, tree, users
        self.project = tree.project
        self.headers: dict[str, str] = {}
        self.current: str | None = None
        self.made = 0

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def post(self, path: str, body: dict[str, Any], expect: int = 200) -> Any:
        r = await self.client.post(f"{API}{path}", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def get(self, path: str, expect: int = 200, **params: Any) -> Any:
        r = await self.client.get(f"{API}{path}", params=params)
        assert r.status_code == expect, r.text
        return r.json()

    async def template(self, activities: list[dict[str, Any]], expect: int = 201) -> Any:
        pid = self.project.id
        self.made += 1
        form_body = {"project_id": pid, "name": f"ITR {self.made}", "area": "qa_itp", "is_formal": True, "sections": ONE_CHECK}
        form = await self.post("/templates/", form_body, 201)
        for activity in activities:
            activity.setdefault("form_template_id", form["id"])
        body = {"project_id": pid, "name": f"Plan {self.made}", "kind": "itp", "activities": activities}
        return await self.post("/templates/", body, expect)

    async def instance(self, *required: int | None) -> dict[str, Any]:
        """An ITP applied to a node, one line per entry (``None``: no count given on the activity)."""
        activities = [
            {"title": f"Activity {n}", **({} if count is None else {"required_signatories": count})}
            for n, count in enumerate(required or (2,), start=1)
        ]
        plan = await self.template(activities)
        return await self.post("/itp/instances", {"template_id": plan["id"], "node_id": self.tree.rsw}, 201)

    async def answer(self, line_id: int, result: str = "pass") -> None:
        record = await self.get(f"/{line_id}")
        r = await self.client.patch(
            f"{API}/{line_id}/items", json={"items": [{"id": record["items"][0]["id"], "result": result}]}, headers=self.headers
        )
        assert r.status_code == 200, r.text

    async def sign(self, line_id: int) -> None:
        await self.post(f"/{line_id}/sign", {"accept_intent": True}, 201)

    async def additional(self, line_id: int, expect: int = 201, **body: Any) -> Any:
        return await self.post(f"/{line_id}/signatories/additional", {"accept_intent": True, **body}, expect)

    async def submit(self, line_id: int) -> None:
        await self.post(f"/{line_id}/submit", {"proposed_result": "pass", "accept_intent": True})

    async def approve(self, line_id: int, expect: int = 200) -> Any:
        return await self.post(f"/{line_id}/review", {"decision": "approve", "accept_intent": True}, expect)

    async def status(self, line_id: int) -> dict[str, Any]:
        return await self.get(f"/{line_id}/signatories")

    async def ready(self, line_id: int) -> None:
        """The inspector answers and signs the line (as the inspector user)."""
        await self.as_("inspector")
        await self.answer(line_id)
        await self.sign(line_id)


async def make_world(client: AsyncClient, db: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    tree = await build_tree(db, "SG-1")
    users = {"inspector": test_user, "reviewer": test_user_2}
    await _grant(db, test_user["id"], "sig_inspector", *INSPECTOR)
    await _grant(db, test_user_2["id"], "sig_reviewer", *REVIEWER)
    for name, perms in (("second", INSPECTOR), ("solo", SOLO), ("reader", READER), ("outsider", OUTSIDER)):
        users[name] = await _user(db, f"sig{name}")
        await _grant(db, users[name]["id"], f"sig_{name}", *perms)
    return await World(client, db, tree, users).as_("inspector")


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    return await make_world(client, db_session, test_user, test_user_2)


# --- counting people, not signatures -------------------------------------------------------------------


async def test_one_person_counts_once_and_approval_waits_for_a_second_person(world: World, db_session: AsyncSession):
    w = world
    settings = await settings_of(db_session, w.project.id)
    settings.allow_self_approval = True  # one person performs, signs again and approves
    await db_session.commit()
    instance = await w.instance(2)
    line = instance["lines"][0]
    assert (line["required_signatories"], line["signatories_collected"]) == (2, 0)

    await w.as_("solo")
    await w.answer(line["id"])
    await w.sign(line["id"])
    first = await w.status(line["id"])
    assert (first["required"], first["collected"], first["met"]) == (2, 1, False)
    assert [p["roles"] for p in first["signers"]] == [["inspector"]]

    again = await w.additional(line["id"])  # same person, different role: accepted, still one person
    assert (again["collected"], again["met"], len(again["signers"])) == (1, False, 1)
    assert again["signers"][0]["roles"] == ["inspector", ADDITIONAL]
    await w.additional(line["id"], expect=409)  # same person and role twice

    await w.submit(line["id"])
    refused = await w.approve(line["id"], expect=422)
    assert "1 collected of 2 required" in str(refused)
    assert (await w.get(f"/{line['id']}"))["status"] == "submitted"  # nothing was stored by the refused approval
    stateless = await w.get(f"/{line['id']}/eligibility", action="approve")
    assert stateless["eligible"] is False
    assert "SIGNATORIES_SHORT" in [f["code"] for f in stateless["findings"]]

    await w.as_("second")
    met = await w.additional(line["id"])
    assert (met["collected"], met["met"], len(met["signers"])) == (2, True, 2)
    record = await w.get(f"/{line['id']}")
    assert (record["required_signatories"], record["signatories_collected"]) == (2, 2)
    shown = (await w.get(f"/itp/instances/{instance['id']}"))["lines"][0]
    assert (shown["required_signatories"], shown["signatories_collected"]) == (2, 2)

    await w.as_("solo")
    approved = await w.approve(line["id"])
    assert (approved["status"], approved["result"]) == ("completed", "pass")


async def test_the_approver_counts_toward_the_total_and_a_count_of_one_changes_nothing(world: World):
    w = world
    instance = await w.instance(2, None)
    two, one = instance["lines"]
    assert one["required_signatories"] == 1  # an activity with no count requires one

    await w.ready(two["id"])
    await w.submit(two["id"])
    await w.as_("reviewer")
    assert (await w.get(f"/{two['id']}/eligibility", action="approve"))["eligible"] is True
    assert (await w.approve(two["id"]))["result"] == "pass"  # the inspector plus the approving reviewer make two

    await w.ready(one["id"])
    await w.submit(one["id"])
    await w.as_("reviewer")
    findings = (await w.get(f"/{one['id']}/eligibility", action="approve"))["findings"]
    assert all(f["code"] != "SIGNATORIES_SHORT" for f in findings)
    assert (await w.approve(one["id"]))["result"] == "pass"


async def test_a_line_needing_three_counts_the_approver_as_the_last_person(world: World):
    w = world
    line = (await w.instance(3))["lines"][0]
    await w.ready(line["id"])
    await w.submit(line["id"])
    await w.as_("reviewer")
    refused = await w.approve(line["id"], expect=422)  # the inspector and the approver make two
    assert "2 collected of 3 required" in str(refused)

    await w.as_("second")
    assert (await w.additional(line["id"]))["collected"] == 2
    await w.as_("reviewer")
    assert (await w.approve(line["id"]))["status"] == "completed"  # three different people


async def test_two_simultaneous_submissions_by_one_person_and_role_store_one(
    a_session_per_request: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    w = await make_world(a_session_per_request, db_session, test_user, test_user_2)
    line = (await w.instance(2))["lines"][0]
    await w.ready(line["id"])
    await w.as_("second")
    path = f"{API}/{line['id']}/signatories/additional"
    answers = await asyncio.gather(
        *(a_session_per_request.post(path, json={"accept_intent": True}, headers=w.headers) for _ in range(2))
    )
    assert sorted(a.status_code for a in answers) == [201, 409]
    stored = await db_session.scalar(
        select(func.count())
        .select_from(InspectionSignature)
        .where(InspectionSignature.inspection_id == line["id"], InspectionSignature.role == ADDITIONAL)
    )
    assert stored == 1


async def test_signatures_over_changed_content_stop_counting_and_signing_again_is_allowed(world: World):
    w = world
    line = (await w.instance(2))["lines"][0]
    await w.ready(line["id"])
    await w.as_("second")
    assert (await w.additional(line["id"]))["collected"] == 2

    await w.as_("inspector")
    await w.answer(line["id"], "fail")  # the content changed: every earlier signature is void
    after = await w.status(line["id"])
    assert (after["collected"], after["signers"], after["met"]) == (0, [], False)
    assert (await w.get(f"/{line['id']}"))["signatories_collected"] == 0

    await w.sign(line["id"])
    await w.as_("second")
    renewed = await w.additional(line["id"])  # the earlier signature is void, so this is not a duplicate
    assert (renewed["collected"], renewed["met"]) == (2, True)


# --- refusals and permissions -----------------------------------------------------------------------------


async def test_the_additional_signatory_action_refuses_unsuitable_lines_and_incomplete_requests(world: World):
    w = world
    line = (await w.instance(2))["lines"][0]
    await w.as_("second")
    planned = await w.additional(line["id"], expect=422)
    assert "planned" in str(planned)

    await w.ready(line["id"])
    await w.as_("second")
    await w.additional(line["id"], expect=422, accept_intent=False)  # the statement must be accepted
    await w.post(f"/{line['id']}/signatories/additional", {"accept_intent": True, "extra": 1}, 422)
    await w.post("/999999/signatories/additional", {"accept_intent": True}, 404)
    await w.get("/999999/signatories", expect=404)
    assert (await w.status(line["id"]))["collected"] == 1  # nothing was stored by the refusals

    pid = w.project.id
    template = await w.post("/templates/", {"project_id": pid, "name": "Plain", "sections": ONE_CHECK}, 201)
    plain = await w.post("/", {"project_id": pid, "template_id": template["id"]}, 201)
    assert "ITP line" in str(await w.additional(plain["id"], expect=422))
    assert (await w.status(plain["id"]))["required"] == 1


async def test_a_passed_line_takes_no_more_signatures(world: World):
    w = world
    line = (await w.instance(None))["lines"][0]
    await w.ready(line["id"])
    await w.submit(line["id"])
    await w.as_("reviewer")
    await w.approve(line["id"])
    await w.as_("second")
    assert "completed" in str(await w.additional(line["id"], expect=422))


async def test_a_read_only_user_reads_the_status_but_cannot_sign_and_a_foreign_project_is_not_found(world: World):
    w = world
    line = (await w.instance(2))["lines"][0]
    await w.ready(line["id"])

    await w.as_("reader")
    await w.additional(line["id"], expect=403)
    assert (await w.status(line["id"]))["required"] == 2

    await w.as_("outsider")  # holds inspection permissions but cannot see the project
    await w.additional(line["id"], expect=404)
    await w.get(f"/{line['id']}/signatories", expect=404)


# --- the required count on the template activity --------------------------------------------------------


async def test_the_required_count_is_bounded_and_copied_from_the_activity_to_each_line(world: World):
    w = world
    instance = await w.instance(3, 1, 10, None)
    assert [ln["required_signatories"] for ln in instance["lines"]] == [3, 1, 10, 1]
    assert all(ln["signatories_collected"] == 0 for ln in instance["lines"])

    plans = {"project_id": w.project.id, "kind": "itp"}
    stored = (await w.get("/templates/", **plans))["total_count"]
    for bad in (0, 11, -1, 2.5, "3", True):
        # The validation handler answers generically, so only the refusal and the unchanged state are asserted.
        await w.template([{"title": "Bad", "required_signatories": bad}], expect=422)
        assert (await w.get("/templates/", **plans))["total_count"] == stored


async def test_an_instance_reads_its_collected_counts_in_one_grouped_query(world: World, test_db_engine):
    w = world
    instance = await w.instance(2, 2, 2)
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "inspections_signatures" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(test_db_engine.sync_engine, "before_cursor_execute", record)
    try:
        lines = (await w.get(f"/itp/instances/{instance['id']}"))["lines"]
    finally:
        event.remove(test_db_engine.sync_engine, "before_cursor_execute", record)
    assert len(lines) == 3
    assert len(seen) == 1

"""Quality gates: lifecycle, authority-ranked release, waiver rules, can-proceed, references, permissions, listing and
the inspection delete guard."""

import re
from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.modules.inspections.gate_rules import release_digest, release_snapshot
from src.modules.ncr.models import Ncr
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
EDITOR = (
    "projects.read",
    "asset_tree.read",
    "tasks.read",
    "files.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "transition")),
)
MANAGER = (*EDITOR, "inspections.delete", "inspections.approve")
READER = ("projects.read", "inspections.read")
ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]
QA = "contractor_qa"
AHJ = "authority_having_jurisdiction"


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

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def gate(self, expect: int = 201, **values: Any) -> dict[str, Any]:
        body = {"project_id": self.project.id, "title": "Pre-pour hold", **values}
        r = await self.client.post(f"{API}/gates/", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def act(self, gate_id: int, action: str, body: dict[str, Any] | None = None, expect: int = 200) -> Any:
        r = await self.client.post(f"{API}/gates/{gate_id}/{action}", json=body or {}, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def read(self, gate_id: int, expect: int = 200) -> dict[str, Any]:
        r = await self.client.get(f"{API}/gates/{gate_id}")
        assert r.status_code == expect, r.text
        return r.json()

    async def proceed(self, kind: str, target: int) -> dict[str, Any]:
        params = {"project_id": self.project.id, "attachment_kind": kind, "attachment_id": target}
        r = await self.client.get(f"{API}/gates/can-proceed", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    async def listed(self, **params: Any) -> dict[str, Any]:
        r = await self.client.get(f"{API}/gates/", params={"project_id": self.project.id, **params})
        assert r.status_code == 200, r.text
        return r.json()

    async def post(self, path: str, body: dict[str, Any], expect: int = 201) -> dict[str, Any]:
        r = await self.client.post(f"{API}{path}", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def record(self, project_id: int | None = None) -> dict[str, Any]:
        pid = project_id or self.project.id
        template = await self.post("/templates/", {"project_id": pid, "name": "Gate check", "sections": ONE_CHECK})
        return await self.post("/", {"project_id": pid, "template_id": template["id"]})

    async def pass_record(self, record: dict[str, Any]) -> None:
        answer = {"id": record["items"][0]["id"], "result": "pass"}
        r = await self.client.patch(f"{API}/{record['id']}/items", json={"items": [answer]}, headers=self.headers)
        assert r.status_code == 200, r.text
        await self.post(f"/{record['id']}/complete", {}, expect=200)


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    tree = await build_tree(db_session, "LG-1")
    await _grant(db_session, test_user["id"], "gate_editor", *EDITOR)
    await _grant(db_session, test_user_2["id"], "gate_manager", *MANAGER)
    reader = await _user(db_session, "gatereader")
    await _grant(db_session, reader["id"], "gate_reader", *READER)
    w = World(client, db_session, tree, {"editor": test_user, "manager": test_user_2, "reader": reader})
    return await w.as_("manager")


# --- release and can-proceed ---------------------------------------------------------------------------


async def test_a_pending_hold_blocks_until_a_quality_assurance_party_releases_it(world: World, db_session: AsyncSession):
    w, node = world, world.tree.rsw
    made = await w.gate(attachment_kind="node", attachment_id=node)
    assert (made["number"], made["kind"], made["status"], made["blocks_progress"], made["authority"]) == (
        "GATE-001",
        "hold",
        "pending",
        True,
        QA,
    )
    before = await w.proceed("node", node)
    assert before["can_proceed"] is False
    assert before["gate_numbers"] == ["GATE-001"] and before["gate_ids"] == [made["id"]] and before["hold_points"] == []

    released = await w.act(made["id"], "release", {"authority": QA, "justification": "Surface accepted"})
    assert (released["status"], released["released_level"], released["release_justification"]) == (
        "released",
        QA,
        "Surface accepted",
    )
    assert released["released_by_id"] == w.users["manager"]["id"] and released["released_at"] and released["release_ip"]
    expected = release_digest(release_snapshot("GATE-001", "hold", None, "node", node, QA))
    assert re.fullmatch(r"[0-9a-f]{64}", released["release_digest"]) and released["release_digest"] == expected
    after = await w.proceed("node", node)
    assert after["can_proceed"] is True and after["gate_numbers"] == [] and after["gate_ids"] == []

    entry = await db_session.scalar(
        select(AuditEntry).where(AuditEntry.action == "inspections.gate.released", AuditEntry.entity_id == str(made["id"]))
    )
    assert entry is not None and entry.after["level"] == QA and entry.after["digest"] == expected


async def test_release_needs_an_asserted_level_at_or_above_the_requirement(world: World):
    w = world
    cases = [
        (AHJ, "contractor_qc", 403),
        (QA, AHJ, 200),
        ("third_party_inspector", QA, 403),
        ("third_party_inspector", AHJ, 200),
        ("client", "third_party_inspector", 200),
        ("client", QA, 403),
    ]
    for required, asserted, expect in cases:
        made = await w.gate(authority=required)
        done = await w.act(made["id"], "release", {"authority": asserted}, expect=expect)
        stored = await w.read(made["id"])
        if expect == 200:
            assert (done["status"], done["released_level"]) == ("released", asserted)  # the asserted level, not the required
            assert stored["release_digest"]
        else:
            assert stored["status"] == "pending" and stored["release_digest"] is None


async def test_a_linked_inspection_must_have_passed_before_release(world: World):
    w = world
    record = await w.record()
    made = await w.gate(inspection_id=record["id"])
    refused = await w.act(made["id"], "release", {"authority": QA}, expect=422)
    assert record["code"] in str(refused) and "planned" in str(refused)
    assert (await w.read(made["id"]))["status"] == "pending"

    await w.pass_record(record)
    released = await w.act(made["id"], "release", {"authority": QA})
    assert released["status"] == "released" and released["inspection_id"] == record["id"]


# --- waiver, void ----------------------------------------------------------------------------------------


async def test_non_hold_kinds_do_not_block_unless_flagged_and_a_waiver_clears_them(world: World):
    w, node = world, world.tree.rsw
    surveillance = await w.gate(kind="surveillance", title="Spot check", attachment_kind="node", attachment_id=node)
    assert surveillance["blocks_progress"] is False
    assert (await w.proceed("node", node))["can_proceed"] is True

    witness = await w.gate(kind="witness", blocks_progress=True, attachment_kind="node", attachment_id=node)
    assert (await w.proceed("node", node))["gate_numbers"] == [witness["number"]]
    waived = await w.act(witness["id"], "waive", {"reason": "Client declined to attend"})
    assert (waived["status"], waived["waived_by_id"], waived["waiver_reason"]) == (
        "waived",
        w.users["manager"]["id"],
        "Client declined to attend",
    )
    assert waived["release_digest"] is None and waived["release_ip"] is None and waived["released_level"] is None
    assert (await w.proceed("node", node))["can_proceed"] is True


async def test_a_hold_is_never_waived_and_a_waiver_needs_a_reason(world: World):
    w = world
    hold = await w.gate()
    refused = await w.act(hold["id"], "waive", {"reason": "Programme pressure"}, expect=409)
    assert "hold" in str(refused)
    assert (await w.read(hold["id"]))["status"] == "pending"

    witness = await w.gate(kind="witness")
    await w.act(witness["id"], "waive", {"reason": ""}, expect=422)
    await w.act(witness["id"], "waive", {"reason": "   "}, expect=422)
    await w.act(witness["id"], "waive", {}, expect=422)
    assert (await w.read(witness["id"]))["status"] == "pending"

    for kind in ("surveillance", "review"):
        other = await w.gate(kind=kind)
        assert (await w.act(other["id"], "waive", {"reason": "Not needed"}))["status"] == "waived"


async def test_a_pending_gate_can_be_edited_voided_or_deleted_and_status_is_not_editable(world: World):
    w, node = world, world.tree.rsw
    made = await w.gate()
    edited = await w.client.patch(
        f"{API}/gates/{made['id']}", json={"title": "Pre-pour hold (revised)", "description": "Rebar"}, headers=w.headers
    )
    assert edited.status_code == 200 and edited.json()["title"] == "Pre-pour hold (revised)"
    status_edit = await w.client.patch(f"{API}/gates/{made['id']}", json={"status": "released"}, headers=w.headers)
    assert status_edit.status_code == 422
    half = await w.client.patch(f"{API}/gates/{made['id']}", json={"attachment_kind": "node"}, headers=w.headers)
    assert half.status_code == 422
    both = {"attachment_kind": "node", "attachment_id": node}
    assert (await w.client.patch(f"{API}/gates/{made['id']}", json=both, headers=w.headers)).status_code == 200
    assert (await w.proceed("node", node))["gate_numbers"] == [made["number"]]

    voided = await w.act(made["id"], "void")
    assert voided["status"] == "void"
    assert (await w.proceed("node", node))["can_proceed"] is True
    await w.act(made["id"], "void", expect=422)

    spare = await w.gate()
    removed = await w.client.delete(f"{API}/gates/{spare['id']}", headers=w.headers)
    assert removed.status_code == 200
    await w.read(spare["id"], expect=404)


async def test_a_decided_gate_is_permanent(world: World):
    w = world
    made = await w.gate(title="Weld hold")
    await w.act(made["id"], "release", {"authority": QA})
    edit = await w.client.patch(f"{API}/gates/{made['id']}", json={"title": "Changed"}, headers=w.headers)
    assert edit.status_code == 422 and "released" in edit.text
    await w.act(made["id"], "void", expect=422)
    await w.act(made["id"], "release", {"authority": AHJ}, expect=422)
    assert (await w.client.delete(f"{API}/gates/{made['id']}", headers=w.headers)).status_code == 409
    stored = await w.read(made["id"])
    assert (stored["title"], stored["status"], stored["released_level"]) == ("Weld hold", "released", QA)


# --- permissions, references ------------------------------------------------------------------------------


async def test_permissions_separate_reading_editing_and_deciding(world: World):
    w = world
    await w.as_("reader")
    await w.gate(expect=403)
    assert (await w.listed())["total_count"] == 0
    await w.as_("editor")
    made = await w.gate()
    await w.act(made["id"], "release", {"authority": QA}, expect=403)
    await w.act(made["id"], "waive", {"reason": "No"}, expect=403)
    await w.act(made["id"], "void", expect=403)
    assert (await w.client.delete(f"{API}/gates/{made['id']}", headers=w.headers)).status_code == 403
    assert (await w.client.patch(f"{API}/gates/{made['id']}", json={"title": "Edited"}, headers=w.headers)).status_code == 200
    await w.as_("reader")
    assert (await w.read(made["id"]))["title"] == "Edited"
    assert (await w.proceed("node", w.tree.rsw))["can_proceed"] is True
    await w.as_("manager")
    assert (await w.act(made["id"], "release", {"authority": QA}))["status"] == "released"


async def test_the_attachment_comes_as_a_pair_and_foreign_references_answer_not_found(world: World, db_session: AsyncSession):
    w = world
    await w.gate(expect=422, attachment_kind="node")
    await w.gate(expect=422, attachment_id=5)
    await w.gate(expect=422, attachment_kind="wall", attachment_id=5)
    assert (await w.gate(attachment_kind="node", attachment_id=w.tree.rsw))["attachment_kind"] == "node"
    assert (await w.gate())["attachment_kind"] is None

    other = await build_tree(db_session, "LG-2")
    await w.gate(expect=404, attachment_kind="node", attachment_id=other.rsw)
    await w.gate(expect=404, attachment_kind="inspection", attachment_id=999999)
    await w.gate(expect=404, attachment_kind="task", attachment_id=999999)
    await w.gate(expect=404, attachment_kind="dossier", attachment_id=999999)
    await w.gate(expect=404, inspection_id=999999)
    foreign = await w.post("/criteria/", {"project_id": other.project.id, "code": "F-1", "title": "Foreign"})
    await w.gate(expect=404, criterion_id=foreign["id"])
    mine = await w.post("/criteria/", {"project_id": w.project.id, "code": "M-1", "title": "Mine"})
    assert (await w.gate(criterion_id=mine["id"]))["criterion_id"] == mine["id"]
    refused = await w.client.delete(f"{API}/criteria/{mine['id']}", headers=w.headers)
    assert refused.status_code == 409 and "gates" in refused.text


# --- listing, ordering, ITP holds, eligibility --------------------------------------------------------------


async def test_lists_are_newest_first_and_can_proceed_is_oldest_first(world: World):
    w, node = world, world.tree.rsw
    first = await w.gate(title="A", attachment_kind="node", attachment_id=node)
    second = await w.gate(title="B", attachment_kind="node", attachment_id=node)
    await w.gate(title="C", kind="witness", attachment_kind="node", attachment_id=node)
    await w.gate(title="D", kind="review")
    listed = await w.listed()
    assert [g["number"] for g in listed["data"]] == ["GATE-004", "GATE-003", "GATE-002", "GATE-001"]
    assert listed["total_count"] == 4
    assert (await w.listed(kind="hold"))["total_count"] == 2
    assert (await w.listed(attachment_kind="node", attachment_id=node))["total_count"] == 3
    assert (await w.proceed("node", node))["gate_numbers"] == [first["number"], second["number"]]

    await w.act(first["id"], "release", {"authority": QA})
    released = await w.listed(status="released")
    assert released["total_count"] == 1 and released["data"][0]["released_level"] == QA
    assert (await w.proceed("node", node))["gate_ids"] == [second["id"]]


async def test_an_itp_line_behind_an_unreleased_hold_cannot_proceed_and_pending_gates_only_advise(world: World):
    w = world
    pid = w.project.id
    body = {"project_id": pid, "name": "ITR", "area": "qa_itp", "is_formal": True, "sections": ONE_CHECK}
    form = await w.post("/templates/", body)
    activities = [
        {"title": "Surface prep", "form_template_id": form["id"], "points": {"contractor": "H"}},
        {"title": "Primer", "form_template_id": form["id"], "points": {"contractor": "W"}},
    ]
    plan = await w.post("/templates/", {"project_id": pid, "name": "Coating ITP", "kind": "itp", "activities": activities})
    instance = await w.post("/itp/instances", {"template_id": plan["id"], "node_id": w.tree.rsw})
    line1, line2 = instance["lines"]

    behind = await w.proceed("inspection", line2["id"])
    assert behind["can_proceed"] is False and behind["gate_numbers"] == []
    assert behind["hold_points"] == [{"id": line1["id"], "code": line1["code"], "title": "Surface prep"}]
    assert (await w.proceed("inspection", line1["id"]))["can_proceed"] is True

    made = await w.gate(attachment_kind="inspection", attachment_id=line1["id"])
    assert (await w.proceed("inspection", line1["id"]))["gate_numbers"] == [made["number"]]
    found = await w.client.get(f"{API}/{line1['id']}/eligibility", params={"action": "fill"})
    advice = [f for f in found.json()["findings"] if f["code"] == "GATE_PENDING"]
    assert found.json()["eligible"] is True and len(advice) == 1 and advice[0]["blocking"] is False
    assert made["number"] in advice[0]["message"]


# --- inspection delete guard -------------------------------------------------------------------------------


async def test_a_judged_or_referenced_inspection_is_kept_and_a_planned_one_is_deleted(world: World):
    w = world
    done = await w.record()
    await w.pass_record(done)
    refused = await w.client.delete(f"{API}/{done['id']}", headers=w.headers)
    assert refused.status_code == 409 and "result pass" in refused.text

    free = await w.record()
    assert (await w.client.delete(f"{API}/{free['id']}", headers=w.headers)).status_code == 200
    assert (await w.client.get(f"{API}/{free['id']}")).status_code == 404

    linked = await w.record()
    gate = await w.gate(inspection_id=linked["id"])
    held = await w.client.delete(f"{API}/{linked['id']}", headers=w.headers)
    assert held.status_code == 409 and "gate" in held.text
    assert (await w.client.delete(f"{API}/gates/{gate['id']}", headers=w.headers)).status_code == 200

    attached = await w.record()
    note = await w.gate(attachment_kind="inspection", attachment_id=attached["id"])
    assert (await w.client.delete(f"{API}/{attached['id']}", headers=w.headers)).status_code == 409
    await w.client.delete(f"{API}/gates/{note['id']}", headers=w.headers)

    reported = await w.record()
    w.db.add(Ncr(project_id=w.project.id, code="NCR-T1", title="Raised earlier", inspection_id=reported["id"]))
    await w.db.commit()
    blocked = await w.client.delete(f"{API}/{reported['id']}", headers=w.headers)
    assert blocked.status_code == 409 and "non-conformance" in blocked.text
    assert (await w.client.delete(f"{API}/{linked['id']}", headers=w.headers)).status_code == 200


# --- a gate that names an inspection by its linked-inspection field -----------------------------------------


async def test_a_gate_linked_to_an_inspection_by_reference_is_listed_and_blocks_that_record(world: World):
    w = world
    record = await w.record()
    other = await w.record()
    linked = await w.gate(inspection_id=record["id"])
    attached = await w.gate(attachment_kind="inspection", attachment_id=record["id"], title="Attached hold")
    await w.gate(inspection_id=other["id"], title="Someone else's hold")

    listed = await w.listed(inspection_id=record["id"])
    assert [g["id"] for g in listed["data"]] == [attached["id"], linked["id"]] and listed["total_count"] == 2
    assert (await w.listed(attachment_kind="inspection", attachment_id=record["id"]))["total_count"] == 1

    answer = await w.proceed("inspection", record["id"])
    assert answer["can_proceed"] is False and answer["gate_ids"] == [linked["id"], attached["id"]]
    found = await w.client.get(f"{API}/{record['id']}/eligibility", params={"action": "fill"})
    assert [f["code"] for f in found.json()["findings"] if f["code"] == "GATE_PENDING"] == ["GATE_PENDING"]

    await w.act(linked["id"], "release", {"authority": QA}, expect=422)  # the linked record has not passed yet
    await w.pass_record(record)
    await w.act(linked["id"], "release", {"authority": QA})
    await w.act(attached["id"], "release", {"authority": QA})
    cleared = await w.proceed("inspection", record["id"])
    assert cleared["can_proceed"] is True and cleared["gate_ids"] == []
    assert (await w.proceed("inspection", other["id"]))["can_proceed"] is False


# --- project scoping ----------------------------------------------------------------------------------------


async def test_gates_of_another_project_stay_out_of_this_projects_list_and_can_proceed(world: World, db_session: AsyncSession):
    w = world
    other = await build_tree(db_session, "LG-3")
    mine = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    foreign = await w.client.post(
        f"{API}/gates/",
        json={
            "project_id": other.project.id,
            "title": "Other site hold",
            "attachment_kind": "node",
            "attachment_id": other.rsw,
        },
        headers=w.headers,
    )
    assert foreign.status_code == 201, foreign.text

    assert [g["id"] for g in (await w.listed())["data"]] == [mine["id"]]
    answer = await w.proceed("node", other.rsw)  # a node of the other project, asked about under this project
    assert answer["can_proceed"] is True and answer["gate_ids"] == []
    assert (await w.proceed("node", w.tree.rsw))["gate_ids"] == [mine["id"]]

"""The one-engine inspection model from KERP: anchoring, ITPs and Hold points, inspection requests and notice,
signing with competency and content hash, client co-sign modes, review and return, delegation."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.assets.models import AssetComponent
from src.modules.notifications.models import Notification, NotificationPreference
from src.modules.projects.models import Project
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
INSPECTOR = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "asset_tree.configure",
    "files.read",
    "files.upload",
    "tasks.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "delete", "transition", "submit")),
)
REVIEWER = (
    "projects.read",
    "files.read",
    *(f"inspections.{a}" for a in ("read", "create", "update", "review", "approve", "manage")),
)
CLIENT = ("projects.read", "inspections.read", "inspections.respond")


def iso(dt: datetime) -> str:
    return dt.isoformat()


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


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


class World:
    def __init__(self, client: AsyncClient, project: Project, users: dict[str, dict[str, Any]], tree: dict[str, int]):
        self.client, self.project, self.users, self.tree = client, project, users, tree
        self.headers: dict[str, str] = {}
        self.current: str | None = None

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def post(self, path: str, body: Any = None, expect: int | None = 200, **kw: Any) -> Any:
        r = await self.client.post(path, json=body if body is not None else {}, headers=self.headers, **kw)
        if expect is not None:
            assert r.status_code == expect, r.text
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    async def patch(self, path: str, body: Any, expect: int = 200, **kw: Any) -> Any:
        r = await self.client.patch(path, json=body, headers=self.headers, **kw)
        assert r.status_code == expect, r.text
        return r.json()

    async def get(self, path: str, expect: int = 200, **params: Any) -> Any:
        r = await self.client.get(path, params=params)
        assert r.status_code == expect, r.text
        return r.json()

    async def template(self, **values: Any) -> dict[str, Any]:
        return await self.post(f"{API}/templates/", {"project_id": self.project.id, **values}, expect=201)

    async def inspection(self, template_id: int, expect: int = 201, **values: Any) -> Any:
        return await self.post(f"{API}/", {"project_id": self.project.id, "template_id": template_id, **values}, expect=expect)


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    project = Project(code="K-2", name="Coastal remediation")
    other = Project(code="K-X", name="Elsewhere")
    db_session.add_all([project, other])
    await db_session.commit()
    client_user = await _user(db_session, "clientrep")
    delegate = await _user(db_session, "deputy")
    await _grant(db_session, test_user["id"], "inspector", *INSPECTOR)
    await _grant(db_session, test_user_2["id"], "qa_lead", *REVIEWER)
    await _grant(db_session, client_user["id"], "client_rep", *CLIENT)
    await _grant(db_session, delegate["id"], "client_deputy", *CLIENT)
    w = World(
        client,
        project,
        {"inspector": test_user, "reviewer": test_user_2, "client": client_user, "deputy": delegate},
        {"other_project": other.id},
    )
    await w.as_("inspector")
    pack = await w.post("/api/v1/asset-tree/packs/remediation-rsw/apply?project_id=" + str(project.id))
    assert pack["levels_added"] == 4

    async def node(level: str, code: str, parent: int | None = None, project_id: int = project.id) -> int:
        made = await w.post(
            "/api/v1/asset-tree/nodes/",
            {"project_id": project_id, "level_key": level, "code": code, "parent_id": parent},
            expect=201,
        )
        return int(made["id"])

    site = await node("site", "KAR")
    area = await node("area", "A1", site)
    asset = await node("asset", "101", area)
    rsw = await node("rsw", "101.1", asset)
    item = await w.post(
        "/api/v1/asset-tree/items/",
        {"project_id": project.id, "node_id": rsw, "item_type_key": "support", "tag": "PS-1"},
        expect=201,
    )
    w.tree.update(site=site, area=area, asset=asset, rsw=rsw, item=item["id"])
    await w.post(f"/api/v1/asset-tree/packs/remediation-rsw/apply?project_id={other.id}")
    w.tree["foreign_area"] = await node("area", "Z", await node("site", "Z", project_id=other.id), project_id=other.id)
    return w


ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]


async def _formal_form(w: World, **extra: Any) -> dict[str, Any]:
    return await w.template(name="ITR coating", area="qa_itp", is_formal=True, sections=ONE_CHECK, **extra)


async def _itp(w: World, form_id: int) -> dict[str, Any]:
    return await w.template(
        name="Coating ITP",
        kind="itp",
        work_type="Blast & paint",
        activities=[
            {
                "title": "Surface preparation",
                "form_template_id": form_id,
                "acceptance_criteria": "Sa 2½",
                "points": {"contractor": "H", "client": "W"},
            },
            {"title": "Primer", "acceptance_criteria": "DFT 60-100 µm", "points": {"contractor": "S", "client": "H"}},
            {"title": "Final review", "points": {"contractor": "R"}},
        ],
    )


# --- anchoring -----------------------------------------------------------------------------------------


async def test_qa_itp_records_anchor_to_inspection_anchors_and_others_stay_project_level(
    world: World, db_session: AsyncSession
):
    w, t = world, world.tree
    qa = await w.template(name="QA check", area="qa_itp", sections=ONE_CHECK)
    await w.inspection(qa["id"], expect=422)  # a QA/ITP record needs an anchor
    await w.inspection(qa["id"], node_id=t["site"], expect=422)  # a site isn't an inspection anchor
    await w.inspection(qa["id"], node_id=t["area"], item_id=t["item"], expect=422)  # exactly one
    await w.inspection(qa["id"], node_id=t["foreign_area"], expect=404)  # another project's node
    on_node = await w.inspection(qa["id"], node_id=t["rsw"])
    assert on_node["category"] == "qa_itp" and on_node["anchor_label"] == "KAR / A1 / 101 / 101.1"
    on_item = await w.inspection(qa["id"], item_id=t["item"])
    assert on_item["anchor_label"].startswith("PS-1")
    await w.inspection(qa["id"], node_id=t["rsw"], location_node_id=t["area"], expect=422)

    prestart = await w.template(name="Vehicle pre-start", area="safety_prestart", sections=ONE_CHECK)
    await w.inspection(prestart["id"], node_id=t["rsw"], expect=422)  # project-level: no anchor
    pump = AssetComponent(project_id=w.project.id, name="Pump P-101", tag_number="P-101")
    crane = AssetComponent(project_id=w.project.id, name="Crane", tag_number="CR-1")
    db_session.add_all([pump, crane])
    await db_session.commit()
    two = [{"kind": "equipment", "id": pump.id}, {"kind": "equipment", "id": crane.id}]
    await w.inspection(prestart["id"], links=two, expect=422)  # at most one equipment link
    linked = await w.inspection(
        prestart["id"],
        location_node_id=t["area"],
        links=[{"kind": "node", "id": t["asset"]}, {"kind": "item", "id": t["item"]}, {"kind": "equipment", "id": pump.id}],
    )
    assert linked["node_id"] is None and linked["location_node_id"] == t["area"]
    assert {(link["kind"], link["label"]) for link in linked["links"]} == {
        ("node", "KAR / A1 / 101"),
        ("item", "PS-1 (KAR / A1 / 101 / 101.1)"),
        ("equipment", "P-101"),
    }

    # Links are searchable but never roll up: the anchor-subtree filter finds only anchored records.
    by_link = await w.get(f"{API}/", project_id=w.project.id, linked=f"equipment:{pump.id}")
    assert [r["id"] for r in by_link["data"]] == [linked["id"]]
    under_area = await w.get(f"{API}/", project_id=w.project.id, node_id=t["area"])
    assert {r["id"] for r in under_area["data"]} == {on_node["id"], on_item["id"]}


async def test_itp_instances_validate_their_anchor(world: World):
    w, t = world, world.tree
    form = await _formal_form(w)
    itp = await _itp(w, form["id"])
    assert itp["is_formal"] and itp["area"] == "qa_itp" and itp["item_count"] == 3
    await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["site"]}, expect=422)
    typed = await w.template(
        name="Spool ITP", kind="itp", item_type_key="pipe_spool", activities=[{"title": "Visual", "points": {"client": "W"}}]
    )
    await w.post(f"{API}/itp/instances", {"template_id": typed["id"], "item_id": t["item"]}, expect=422)  # a support
    informal = await w.template(name="Informal form", sections=ONE_CHECK)
    bad = {
        "project_id": w.project.id,
        "name": "x",
        "kind": "itp",
        "activities": [{"title": "a", "form_template_id": informal["id"]}],
    }
    assert (await w.client.post(f"{API}/templates/", json=bad, headers=w.headers)).status_code == 422

    instance = await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["rsw"]}, expect=201)
    assert instance["code"] == "ITP-001" and instance["lines_total"] == 3 and instance["holds_open"] == 2
    lines = instance["lines"]
    assert [ln["code"] for ln in lines] == ["ITP-001/01", "ITP-001/02", "ITP-001/03"]
    assert lines[0]["points"] == {"contractor": "H", "client": "W", "third_party": "none"}
    assert lines[0]["item_count"] == 1 and lines[0]["verifying_document"] == "ITR coating"
    assert [ln["blocked"] for ln in lines] == [False, True, True]
    await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["rsw"]}, expect=422)  # applied already
    listed = await w.get(f"{API}/itp/instances/", project_id=w.project.id, node_id=t["area"])
    assert listed["total_count"] == 1


# --- ITP: hold points, call-outs, review, release ------------------------------------------------------


async def test_a_hold_point_blocks_the_next_activity_until_released(world: World, db_session: AsyncSession):
    w, t = world, world.tree
    users = w.users
    form = await _formal_form(w)
    itp = await _itp(w, form["id"])
    instance = await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["rsw"]}, expect=201)
    line1, line2 = instance["lines"][0], instance["lines"][1]

    blocked = await w.get(f"{API}/{line2['id']}/eligibility", action="submit")
    assert not blocked["eligible"] and blocked["findings"][0]["code"] == "HOLD_NOT_RELEASED"
    draft2 = await w.post(
        f"{API}/requests/",
        {
            "project_id": w.project.id,
            "title": "Primer",
            "scheduled_start": iso(datetime.now(UTC) + timedelta(days=3)),
            "inspection_ids": [line2["id"]],
        },
        expect=201,
    )
    refused = await w.post(f"{API}/requests/{draft2['id']}/issue", expect=422)
    assert "HOLD_NOT_RELEASED" in str(refused)
    await w.post(f"{API}/requests/{draft2['id']}/cancel", {})

    # Line 1 has a client Witness point: it can't be submitted before a call-out.
    first = await w.get(f"{API}/{line1['id']}/eligibility", action="submit")
    assert [f["code"] for f in first["findings"]] == ["RFI_REQUIRED"]

    # The client opted out of approval notifications; call-outs are transactional and reach them anyway.
    db_session.add(NotificationPreference(user_id=users["client"]["id"], category="approval", in_app=False, email=False))
    await db_session.commit()
    start = datetime.now(UTC) + timedelta(days=2)
    draft = await w.post(
        f"{API}/requests/",
        {
            "project_id": w.project.id,
            "title": "Blast inspection",
            "discipline": "C",
            "scheduled_start": iso(start),
            "location_ref": "Batch 7",
            "inspection_ids": [line1["id"]],
            "parties": [{"party": "client", "witness_user_id": users["client"]["id"]}],
        },
        expect=201,
    )
    assert draft["status"] == "draft" and draft["code"] is None
    assert {p["party"]: p["point"] for p in draft["parties"]} == {"contractor": "H", "client": "W"}
    issued = await w.post(f"{API}/requests/{draft['id']}/issue")
    assert (issued["code"], issued["status"], issued["notice_met"], issued["required_notice_hours"]) == (
        "IR-001",
        "requested",
        True,
        24,
    )
    assert issued["findings"] == []
    client_party = next(p for p in issued["parties"] if p["party"] == "client")
    assert client_party["notice_delivery"] == "delivered" and client_party["acknowledged"] is False
    notes = (await db_session.execute(select(Notification).where(Notification.user_id == users["client"]["id"]))).scalars()
    assert any("IR-001 issued" in n.title for n in notes)
    assert (await w.get(f"{API}/{line1['id']}"))["status"] == "requested"
    pending = await w.get(f"{API}/{line1['id']}/eligibility", action="submit")
    assert [f["code"] for f in pending["findings"]] == ["WITNESS_PENDING"]

    await w.as_("client")
    await w.post(f"{API}/requests/{draft['id']}/acknowledge", {})
    confirmed = await w.post(f"{API}/requests/{draft['id']}/confirm", {})
    assert confirmed["status"] == "confirmed"
    assert next(p for p in confirmed["parties"] if p["party"] == "client")["acknowledged"] is True
    await w.post(f"{API}/requests/{draft['id']}/attendance", {"party": "client", "attendance": "attended"})
    await w.post(f"{API}/requests/{draft['id']}/outcome", {"outcome": "witnessed"}, expect=403)  # reviewers only

    await w.as_("reviewer")
    done = await w.post(f"{API}/requests/{draft['id']}/outcome", {"outcome": "witnessed"})
    assert done["status"] == "witnessed"

    await w.as_("inspector")
    record = await w.get(f"{API}/{line1['id']}")
    await w.patch(f"{API}/{line1['id']}/items", {"items": [{"id": record["items"][0]["id"], "result": "pass"}]})
    await w.post(f"{API}/{line1['id']}/submit", {"proposed_result": "pass"}, expect=422)  # statement not accepted
    submitted = await w.post(f"{API}/{line1['id']}/submit", {"proposed_result": "pass", "accept_intent": True})
    assert submitted["status"] == "submitted" and submitted["review_round"] == 1
    assert [s["role"] for s in submitted["signatures"]] == ["inspector"]
    await w.post(f"{API}/{line1['id']}/hold-release", {"accept_intent": True}, expect=403)  # no approve permission

    await w.as_("reviewer")
    early = await w.post(f"{API}/{line1['id']}/hold-release", {"accept_intent": True}, expect=422)
    assert "LINE_NOT_ACCEPTED" in str(early)
    approved = await w.post(f"{API}/{line1['id']}/review", {"decision": "approve", "accept_intent": True})
    assert (approved["status"], approved["result"]) == ("completed", "pass")
    tiles = await w.get(f"{API}/dashboard", project_id=w.project.id)
    assert (tiles["holds_awaiting_release"], tiles["holds_open"], tiles["pass_rate"]) == (1, 2, 100.0)
    released = await w.post(f"{API}/{line1['id']}/hold-release", {"accept_intent": True})
    assert released["hold_released_at"] and [s["role"] for s in released["signatures"]] == [
        "inspector",
        "reviewer",
        "hold_release",
    ]

    after = await w.get(f"{API}/itp/instances/{instance['id']}")
    assert (after["lines_done"], after["progress"], after["holds_open"]) == (1, 33.3, 1)
    assert [ln["blocked"] for ln in after["lines"]] == [False, False, True]  # line 3 waits for line 2's hold
    nxt = await w.get(f"{API}/{line2['id']}/eligibility", action="submit")
    assert [f["code"] for f in nxt["findings"]] == ["RFI_REQUIRED"]  # the client's Hold needs a call-out now
    pdf = await w.client.get(f"{API}/{line1['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_notice_rules_decide_whether_a_no_show_lets_work_proceed(world: World):
    w, t = world, world.tree
    users = w.users
    itp = await w.template(
        name="Bolting ITP",
        kind="itp",
        activities=[{"title": "Torque check", "points": {"client": "W"}}, {"title": "Flange", "points": {"client": "H"}}],
    )
    instance = await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "item_id": t["item"]}, expect=201)
    witness_line, hold_line = instance["lines"]

    async def request(line_id: int, start: datetime, **extra: Any) -> dict[str, Any]:
        draft = await w.post(
            f"{API}/requests/",
            {
                "project_id": w.project.id,
                "title": "Call-out",
                "scheduled_start": iso(start),
                "inspection_ids": [line_id],
                "parties": [{"party": "client", "recipient_user_ids": [users["client"]["id"]]}],
                **extra,
            },
            expect=201,
        )
        return draft

    # Short notice is a warning; a client absent after short notice never lets the work proceed.
    soon = datetime.now(UTC) + timedelta(hours=2)
    r = await request(witness_line["id"], soon)
    issued = await w.post(f"{API}/requests/{r['id']}/issue")
    assert issued["notice_met"] is False and [f["code"] for f in issued["findings"]] == ["NOTICE_SHORT"]
    await w.as_("reviewer")
    await w.post(f"{API}/requests/{r['id']}/attendance", {"party": "client", "attendance": "absent"})
    await w.post(f"{API}/requests/{r['id']}/outcome", {"outcome": "no_show"}, expect=422)  # before the grace period
    no_show = await w.post(
        f"{API}/requests/{r['id']}/outcome", {"outcome": "no_show", "occurred_at": iso(soon + timedelta(hours=1))}
    )
    assert next(p for p in no_show["parties"] if p["party"] == "client")["notice_valid_at_outcome"] is False
    unmet = await w.get(f"{API}/{witness_line['id']}/eligibility", action="submit")
    assert [f["code"] for f in unmet["findings"]] == ["WITNESS_NOT_SATISFIED"]

    # Rescheduled with proper notice: an absent Witness party after valid notice lets the work proceed.
    later = datetime.now(UTC) + timedelta(days=3)
    await w.as_("inspector")
    again = await w.post(f"{API}/requests/{r['id']}/reschedule", {"scheduled_start": iso(later), "reason": "Client asked"})
    assert (again["status"], again["notice_met"], again["reschedule_count"]) == ("requested", True, 1)
    assert next(p for p in again["parties"] if p["party"] == "client")["attendance"] == "pending"
    await w.as_("reviewer")
    await w.post(f"{API}/requests/{r['id']}/attendance", {"party": "client", "attendance": "absent"})
    await w.post(f"{API}/requests/{r['id']}/outcome", {"outcome": "no_show", "occurred_at": iso(later + timedelta(hours=1))})
    ok = await w.get(f"{API}/{witness_line['id']}/eligibility", action="submit")
    assert ok["findings"] == []

    # A Hold point is never passed by a no-show, however good the notice.
    await w.as_("inspector")
    h = await request(hold_line["id"], later)
    await w.post(f"{API}/requests/{h['id']}/issue")
    await w.as_("reviewer")
    await w.post(f"{API}/requests/{h['id']}/attendance", {"party": "client", "attendance": "absent"})
    await w.post(f"{API}/requests/{h['id']}/outcome", {"outcome": "no_show", "occurred_at": iso(later + timedelta(hours=1))})
    held = await w.get(f"{API}/{hold_line['id']}/eligibility", action="submit")
    assert [f["code"] for f in held["findings"]] == ["WITNESS_NOT_SATISFIED"]


async def test_undelivered_notice_and_blocking_short_notice(world: World):
    w, t = world, world.tree
    itp = await w.template(name="W ITP", kind="itp", activities=[{"title": "Visual", "points": {"client": "W"}}])
    instance = await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["asset"]}, expect=201)
    line = instance["lines"][0]
    await w.as_("reviewer")
    settings = await w.patch(f"{API}/settings", {"block_short_notice": True}, params={"project_id": w.project.id})
    assert settings["block_short_notice"] is True
    await w.as_("inspector")
    soon = datetime.now(UTC) + timedelta(hours=1)
    body = {
        "project_id": w.project.id,
        "title": "Visual",
        "scheduled_start": iso(soon),
        "inspection_ids": [line["id"]],
        "parties": [{"party": "client", "contact_ids": [999999]}],
    }
    r = await w.post(f"{API}/requests/", body, expect=201)
    refused = await w.post(f"{API}/requests/{r['id']}/issue", expect=422)
    assert "Short notice" in str(refused)
    later = datetime.now(UTC) + timedelta(days=2)
    await w.patch(f"{API}/requests/{r['id']}", {"scheduled_start": iso(later)})
    issued = await w.post(f"{API}/requests/{r['id']}/issue")
    party = next(p for p in issued["parties"] if p["party"] == "client")
    assert party["notice_delivery"] == "failed" and party["notice_delivery_reason"] == "no_channel"  # unknown contact
    await w.as_("reviewer")
    await w.post(f"{API}/requests/{r['id']}/attendance", {"party": "client", "attendance": "absent"})
    out = await w.post(
        f"{API}/requests/{r['id']}/outcome", {"outcome": "no_show", "occurred_at": iso(later + timedelta(hours=1))}
    )
    assert next(p for p in out["parties"] if p["party"] == "client")["notice_valid_at_outcome"] is False
    assert [f["code"] for f in (await w.get(f"{API}/{line['id']}/eligibility", action="submit"))["findings"]] == [
        "WITNESS_NOT_SATISFIED"
    ]
    cal = await w.get(
        f"{API}/requests/calendar",
        project_id=w.project.id,
        **{"from": iso(later - timedelta(days=1)), "to": iso(later + timedelta(days=1))},
    )
    assert [e["code"] for e in cal] == ["IR-001"] and cal[0]["parties"][0]["notice_delivery"] == "failed"
    await w.get(
        f"{API}/requests/calendar",
        expect=422,
        project_id=w.project.id,
        **{"from": iso(later), "to": iso(later + timedelta(days=90))},
    )


# --- signing -------------------------------------------------------------------------------------------


async def test_any_change_voids_the_signatures(world: World):
    w, t = world, world.tree
    form = await _formal_form(w)
    made = await w.inspection(form["id"], node_id=t["rsw"])
    item = made["items"][0]["id"]
    await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": item, "result": "pass"}]})
    signed = await w.post(f"{API}/{made['id']}/sign", {"accept_intent": True}, expect=201)
    assert signed["status"] == "valid" and signed["signer_snapshot"]["name"] == w.users["inspector"]["name"]
    assert "performed inspection INS-001" in signed["intent_text"] and len(signed["content_sha256"]) == 64
    record = await w.get(f"{API}/{made['id']}")
    assert record["content_sha256"] == signed["content_sha256"]

    changed = await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": item, "notes": "Rust bloom at weld"}]})
    sig = changed["signatures"][0]
    assert (sig["status"], sig["void_reason"]) == ("void", "The record changed after signing")
    resigned = await w.post(f"{API}/{made['id']}/sign", {"accept_intent": True}, expect=201)
    assert resigned["content_sha256"] != signed["content_sha256"]
    header = await w.patch(f"{API}/{made['id']}", {"notes": "Second coat pending"})
    assert [s["status"] for s in header["signatures"]] == ["void", "void"]


async def test_competency_expiry_blocks_signing(world: World):
    w, t = world, world.tree
    form = await _formal_form(w, required_qualification="Coating inspector")
    made = await w.inspection(form["id"], node_id=t["rsw"])
    await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": made["items"][0]["id"], "result": "pass"}]})
    missing = await w.post(f"{API}/{made['id']}/sign", {"accept_intent": True}, expect=422)
    assert "COMPETENCY_MISSING" in str(missing)
    me = w.users["inspector"]["id"]
    await w.post(f"{API}/competencies/", {"user_id": me, "qualification": "Coating inspector"}, expect=403)

    await w.as_("reviewer")
    expired = await w.post(
        f"{API}/competencies/",
        {
            "user_id": me,
            "qualification": "Coating inspector",
            "level": "NACE 2",
            "issued_on": "2023-01-01",
            "expires_on": (date.today() - timedelta(days=1)).isoformat(),
        },
        expect=201,
    )
    assert expired["valid_today"] is False and expired["expires_in_days"] == -1
    await w.as_("inspector")
    blocked = await w.post(f"{API}/{made['id']}/sign", {"accept_intent": True}, expect=422)
    assert "COMPETENCY_EXPIRED" in str(blocked)
    elig = await w.get(f"{API}/{made['id']}/eligibility", action="sign")
    assert [f["code"] for f in elig["findings"]] == ["COMPETENCY_EXPIRED"]
    mine = await w.get(f"{API}/competencies/")
    assert mine["total_count"] == 1

    await w.as_("reviewer")
    renewed = (date.today() + timedelta(days=365)).isoformat()
    await w.patch(f"{API}/competencies/{expired['id']}", {"expires_on": renewed})
    await w.as_("inspector")
    signed = await w.post(f"{API}/{made['id']}/sign", {"accept_intent": True}, expect=201)
    snap = signed["competency_snapshot"][0]
    assert (snap["qualification"], snap["expires_on"], snap["valid_at_signing"]) == ("Coating inspector", renewed, True)


async def test_client_cosign_modes(world: World):
    w, t = world, world.tree
    users = w.users
    form = await _formal_form(w, requires_client_signature=True)

    async def filled() -> dict[str, Any]:
        made = await w.inspection(form["id"], node_id=t["rsw"])
        await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": made["items"][0]["id"], "result": "pass"}]})
        return made

    # On the inspector's device: provisional until the client confirms in their own account.
    one = await filled()
    drawn = {
        "mode": "on_device",
        "client_user_id": users["client"]["id"],
        "signer_name": "C. Rep",
        "signature_image": "data:image/png;base64,iVBORw0KGgo=",
    }
    await w.post(f"{API}/{one['id']}/cosign", drawn, expect=422)  # the inspector signs first
    missing = await w.post(f"{API}/{one['id']}/submit", {"proposed_result": "pass", "accept_intent": True}, expect=422)
    assert "CLIENT_SIGNATURE_MISSING" in str(missing)
    await w.post(f"{API}/{one['id']}/sign", {"accept_intent": True}, expect=201)
    provisional = await w.post(f"{API}/{one['id']}/cosign", drawn, expect=201)
    assert (provisional["status"], provisional["mode"], provisional["has_image"]) == ("provisional", "on_device", True)
    await w.post(f"{API}/{one['id']}/cosign", drawn, expect=409)
    await w.post(f"{API}/{one['id']}/submit", {"proposed_result": "pass"})
    await w.as_("reviewer")
    held = await w.post(f"{API}/{one['id']}/review", {"decision": "approve", "accept_intent": True}, expect=422)
    assert "CLIENT_SIGNATURE_PROVISIONAL" in str(held)
    await w.as_("client")
    waiting = await w.get(f"{API}/cosigns/pending")
    assert [p["inspection_id"] for p in waiting] == [one["id"]]
    await w.post(f"{API}/{one['id']}/cosign/{provisional['id']}", {"decision": "confirm"}, expect=422)  # no statement
    confirmed = await w.post(f"{API}/{one['id']}/cosign/{provisional['id']}", {"decision": "confirm", "accept_intent": True})
    client_sig = next(s for s in confirmed["signatures"] if s["role"] == "client")
    assert client_sig["status"] == "valid" and client_sig["confirmed_at"]
    await w.as_("reviewer")
    approved = await w.post(f"{API}/{one['id']}/review", {"decision": "approve", "accept_intent": True})
    assert approved["status"] == "completed"

    # A scanned paper signature: the client rejects it, which returns the submitted record.
    await w.as_("inspector")
    two = await filled()
    await w.post(f"{API}/{two['id']}/sign", {"accept_intent": True}, expect=201)
    scan = await w.client.post(
        "/api/v1/files/",
        data={"project_id": str(w.project.id), "entity_type": "inspection", "entity_id": str(two["id"])},
        files={"file": ("signed.pdf", b"%PDF-1.4 signed page", "application/pdf")},
        headers=w.headers,
    )
    assert scan.status_code == 201, scan.text
    scanned = await w.post(
        f"{API}/{two['id']}/cosign",
        {"mode": "scan", "client_user_id": users["client"]["id"], "scan_file_id": scan.json()["id"]},
        expect=201,
    )
    await w.post(f"{API}/{two['id']}/submit", {"proposed_result": "pass"})
    await w.as_("client")
    await w.post(f"{API}/{two['id']}/cosign/{scanned['id']}", {"decision": "reject"}, expect=422)  # needs a reason
    rejected = await w.post(f"{API}/{two['id']}/cosign/{scanned['id']}", {"decision": "reject", "reason": "Not my signature"})
    assert rejected["status"] == "returned" and "Not my signature" in rejected["return_reason"]

    # In the client's own account: a full co-signature at once; the inspector can't use this mode.
    await w.as_("inspector")
    three = await filled()
    await w.post(f"{API}/{three['id']}/sign", {"accept_intent": True}, expect=201)
    await w.post(f"{API}/{three['id']}/cosign", {"mode": "portal", "accept_intent": True}, expect=403)
    await w.as_("client")
    portal = await w.post(f"{API}/{three['id']}/cosign", {"mode": "portal", "accept_intent": True}, expect=201)
    assert (portal["status"], portal["signer_user_id"]) == ("valid", users["client"]["id"])
    await w.as_("deputy")
    await w.post(f"{API}/{two['id']}/cosign/{scanned['id']}", {"decision": "confirm", "accept_intent": True}, expect=403)


# --- review --------------------------------------------------------------------------------------------


async def test_review_returns_with_answer_comments_and_refuses_self_approval(world: World):
    w, t = world, world.tree
    form = await _formal_form(w)
    made = await w.inspection(form["id"], node_id=t["rsw"])
    item = made["items"][0]["id"]
    await w.post(f"{API}/{made['id']}/complete", {}, expect=422)  # formal: reviewed, not completed directly
    await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": item, "result": "pass"}]})
    await w.post(f"{API}/{made['id']}/submit", {"proposed_result": "pass", "accept_intent": True})
    locked = await w.client.patch(
        f"{API}/{made['id']}/items", json={"items": [{"id": item, "result": "fail"}]}, headers=w.headers
    )
    assert locked.status_code == 422

    await w.as_("reviewer")
    await w.post(f"{API}/{made['id']}/review", {"decision": "return"}, expect=422)  # a reason is required
    returned = await w.post(
        f"{API}/{made['id']}/review",
        {"decision": "return", "reason": "Photo missing", "comments": [{"item_id": item, "body": "Add the profile reading"}]},
    )
    assert returned["status"] == "returned" and returned["return_reason"] == "Photo missing"
    assert [(c["body"], c["review_round"]) for c in returned["comments"]] == [("Add the profile reading", 1)]

    await w.as_("inspector")
    await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": item, "notes": "Profile 65 µm"}]})
    await w.post(f"{API}/{made['id']}/comments/{returned['comments'][0]['id']}/resolve")
    again = await w.post(f"{API}/{made['id']}/submit", {"proposed_result": "pass", "accept_intent": True})
    assert again["review_round"] == 2 and again["comments"][0]["resolved_at"]
    assert [s["status"] for s in again["signatures"]] == ["void", "valid"]

    # The reviewer who submitted their own inspection may not approve it.
    await w.as_("reviewer")
    own = await w.inspection(form["id"], node_id=t["rsw"])
    await w.patch(f"{API}/{own['id']}/items", {"items": [{"id": own["items"][0]["id"], "result": "fail"}]})
    await w.post(f"{API}/{own['id']}/submit", {"proposed_result": "fail", "accept_intent": True}, expect=403)  # no submit
    await w.post(f"{API}/{own['id']}/review", {"decision": "approve", "accept_intent": True}, expect=422)  # not submitted

    approved = await w.post(f"{API}/{made['id']}/review", {"decision": "approve", "accept_intent": True})
    assert (approved["status"], approved["result"], approved["self_approved"]) == ("completed", "pass", False)
    history = [h["to_status"] for h in await w.get(f"{API}/{made['id']}/history")]
    assert history == ["planned", "in_progress", "submitted", "returned", "submitted", "completed"]


async def test_self_approval_follows_the_project_setting(world: World):
    w, t = world, world.tree
    form = await _formal_form(w)
    made = await w.inspection(form["id"], node_id=t["rsw"], inspector_id=w.users["reviewer"]["id"])
    await w.patch(f"{API}/{made['id']}/items", {"items": [{"id": made["items"][0]["id"], "result": "pass"}]})
    await w.post(f"{API}/{made['id']}/submit", {"proposed_result": "pass", "accept_intent": True})
    await w.as_("reviewer")
    refused = await w.post(f"{API}/{made['id']}/review", {"decision": "approve", "accept_intent": True}, expect=422)
    assert "SELF_APPROVAL" in str(refused)
    await w.patch(f"{API}/settings", {"allow_self_approval": True}, params={"project_id": w.project.id})
    approved = await w.post(f"{API}/{made['id']}/review", {"decision": "approve", "accept_intent": True})
    assert approved["self_approved"] is True


# --- templates and delegation --------------------------------------------------------------------------


async def test_template_settings_are_locked_and_revised(world: World):
    w = world
    t = await w.template(name="H&S walk", area="health_safety", sections=ONE_CHECK, linked_issue_types=["punch"])
    assert (t["version"], t["is_formal"], t["linked_issue_types"]) == (1, False, ["punch"])
    await w.patch(f"{API}/templates/{t['id']}", {"is_formal": True}, expect=403)  # needs manage
    renamed = await w.patch(f"{API}/templates/{t['id']}", {"name": "H&S site walk"})
    assert renamed["version"] == 1
    await w.as_("reviewer")
    audit = await w.patch(f"{API}/templates/{t['id']}", {"is_formal": True, "audit_scope": "external"})
    assert (audit["version"], audit["audit_scope"]) == (2, "external")
    revisions = await w.get(f"{API}/templates/{t['id']}/revisions")
    assert [r["version"] for r in revisions] == [2, 1]
    assert (
        revisions[0]["snapshot"]["audit_scope"] == "external"
        and revisions[0]["content_sha256"] != revisions[1]["content_sha256"]
    )
    filtered = await w.get(f"{API}/templates/", project_id=w.project.id, audit=True)
    assert [x["id"] for x in filtered["data"]] == [t["id"]]


async def test_delegation_is_narrow_and_routes_callouts(world: World):
    w, t = world, world.tree
    users = w.users
    now = datetime.now(UTC)
    await w.as_("client")
    await w.post(
        f"{API}/delegations/",
        {
            "project_id": w.project.id,
            "delegate_id": users["client"]["id"],
            "kind": "hold_point",
            "ends_at": iso(now + timedelta(days=5)),
        },
        expect=422,
    )
    await w.post(
        f"{API}/delegations/",
        {
            "project_id": w.project.id,
            "delegate_id": users["deputy"]["id"],
            "kind": "hold_point",
            "ends_at": iso(now + timedelta(days=120)),
        },
        expect=422,
    )
    d = await w.post(
        f"{API}/delegations/",
        {
            "project_id": w.project.id,
            "delegate_id": users["deputy"]["id"],
            "kind": "hold_point",
            "ends_at": iso(now + timedelta(days=5)),
            "reason": "Leave",
        },
        expect=201,
    )
    assert d["active"] and d["delegator_id"] == users["client"]["id"]
    await w.post(
        f"{API}/delegations/",
        {
            "project_id": w.project.id,
            "delegate_id": users["inspector"]["id"],
            "kind": "hold_point",
            "ends_at": iso(now + timedelta(days=2)),
        },
        expect=409,
    )
    await w.post(
        f"{API}/delegations/",
        {
            "project_id": w.project.id,
            "delegator_id": users["inspector"]["id"],
            "delegate_id": users["deputy"]["id"],
            "kind": "review",
            "ends_at": iso(now + timedelta(days=2)),
        },
        expect=403,
    )

    await w.as_("inspector")
    itp = await w.template(name="Hold ITP", kind="itp", activities=[{"title": "Hydrotest", "points": {"client": "H"}}])
    instance = await w.post(f"{API}/itp/instances", {"template_id": itp["id"], "node_id": t["rsw"]}, expect=201)
    r = await w.post(
        f"{API}/requests/",
        {
            "project_id": w.project.id,
            "title": "Hydrotest",
            "scheduled_start": iso(now + timedelta(days=2)),
            "inspection_ids": [instance["lines"][0]["id"]],
            "parties": [{"party": "client", "witness_user_id": users["client"]["id"]}],
        },
        expect=201,
    )
    issued = await w.post(f"{API}/requests/{r['id']}/issue")
    recipients = next(p for p in issued["parties"] if p["party"] == "client")["recipients"]
    assert {(x["user_id"], x["on_behalf_of_user_id"]) for x in recipients} == {
        (users["client"]["id"], None),
        (users["deputy"]["id"], users["client"]["id"]),
    }
    await w.as_("deputy")
    await w.post(
        f"{API}/requests/{r['id']}/attendance", {"party": "client", "attendance": "attended"}
    )  # as the witness's delegate
    await w.as_("client")
    revoked = await w.post(f"{API}/delegations/{d['id']}/revoke")
    assert revoked["active"] is False and revoked["revoked_at"]
    listed = await w.get(f"{API}/delegations/", project_id=w.project.id)
    assert listed["total_count"] == 1

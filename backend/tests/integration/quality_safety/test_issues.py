"""The issues engine: punch and NCR workflows, Cat A/B/C rules, verifier != rectifier, client visibility,
flag overrides and guardrails, punch -> NCR upgrade and external NCRs, templates and revisions, MDR gate facts."""

from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.files.models import StoredFile
from src.modules.ncr import service
from src.modules.ncr.events import raise_requested
from src.modules.ncr.reporting import loosening_overrides, open_cat_a
from src.modules.notifications.models import Notification
from src.modules.projects.models import Project
from src.modules.team.models import Team, TeamMembership
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

STAFF = (
    "projects.read",
    *(f"ncr.{a}" for a in ("read", "create", "update", "transition", "verify", "manage", "export")),
    *(f"asset_tree.{a}" for a in ("read", "create", "configure")),
    "files.read",
    "files.upload",
    "comments.read",
    "comments.create",
)
CLIENT = ("ncr.read", "ncr.create", "ncr.verify", "files.read", "comments.read", "comments.create")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _user(db: AsyncSession, name: str) -> dict[str, Any]:
    user = User(
        name=name,
        username=name.lower().replace(" ", ""),
        email=f"{name.lower().replace(' ', '.')}@example.com",
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await reset_password_budget(user.id)
    return {"id": user.id, "name": name, "username": user.username, "password": "Password123!"}


@pytest_asyncio.fixture
async def site(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict):
    """A project with a breakdown (site / area / asset / RSW), two staff users and a portal user."""
    team = Team(name="Client team")
    db_session.add(team)
    await db_session.flush()
    project = Project(code="K-1", name="Refinery", client_team_id=team.id)
    db_session.add(project)
    await db_session.commit()
    client_user = await _user(db_session, "Clara Client")
    third = await _user(db_session, "Quinn Lead")
    db_session.add(TeamMembership(team_id=team.id, user_id=client_user["id"]))
    await db_session.commit()
    await _grant(db_session, test_user["id"], "qa-a", *STAFF)
    await _grant(db_session, test_user_2["id"], "qa-b", *STAFF)
    await _grant(db_session, client_user["id"], "client", *CLIENT)
    await _grant(db_session, third["id"], "qa-c", *STAFF)

    users = {"a": test_user, "b": test_user_2, "c": third, "client": client_user}

    async def as_(who: str) -> dict[str, str]:
        return {"X-CSRF-Token": await _login(client, users[who])}

    headers = await as_("a")
    await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers)

    async def node(level: str, code: str, parent: int | None = None) -> dict:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        return r.json()

    s = await node("site", "KAR")
    area1 = await node("area", "A1", s["id"])
    area2 = await node("area", "A2", s["id"])
    asset1 = await node("asset", "101", area1["id"])
    rsw1 = await node("rsw", "101.1", asset1["id"])
    asset2 = await node("asset", "201", area2["id"])
    rsw2 = await node("rsw", "201.1", asset2["id"])
    nodes = {"site": s, "area1": area1, "area2": area2, "asset1": asset1, "rsw1": rsw1, "rsw2": rsw2}
    return project, users, as_, nodes


async def _raise(client: AsyncClient, headers: dict, expect: int = 201, **body: Any) -> dict:
    r = await client.post("/api/v1/issues/", json=body, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


async def _move(client: AsyncClient, headers: dict, issue_id: int, to: str, expect: int = 200, **extra: Any) -> dict:
    r = await client.post(f"/api/v1/issues/{issue_id}/transition", json={"to": to, **extra}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


async def _patch(client: AsyncClient, headers: dict, issue_id: int, expect: int = 200, **body: Any) -> dict:
    r = await client.patch(f"/api/v1/issues/{issue_id}", json=body, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


async def test_punch_workflow_and_verifier_is_never_the_rectifier(client: AsyncClient, site):
    project, users, as_, nodes = site
    a = await as_("a")
    punch = await _raise(
        client,
        a,
        project_id=project.id,
        issue_type="punch",
        category="insulation",
        title="Open joint on line 12",
        punch_category="A",
        anchor_node_id=nodes["rsw1"]["id"],
        answers={"defect": "Gaps / joints open"},
    )
    assert (punch["code"], punch["status"], punch["issue_type"], punch["punch_category"]) == ("PL-001", "open", "punch", "A")
    assert punch["template_name"] == "Insulation punch" and punch["anchor_role"] == "work_anchor"
    assert punch["work_anchor_node_id"] == nodes["rsw1"]["id"] and punch["anchor_label"].endswith("101.1")
    assert (punch["visibility"], punch["mdr_effect"]) == ("internal", "blocks")
    pid = punch["id"]

    assert "What was done" in (await _move(client, a, pid, "rectified", 422))["detail"]
    await _patch(client, a, pid, answers={"rectification": "Joint re-butted and taped"})
    rectified = await _move(client, a, pid, "rectified")
    assert rectified["rectified_by_id"] == users["a"]["id"]
    assert "rectified" in (await _move(client, a, pid, "verified", 403))["detail"]
    # rectify-step fields are read-only once rectified
    await _patch(client, a, pid, 422, answers={"rectification": "changed"})

    b = await as_("b")
    await _move(client, b, pid, "open", 422)  # rejecting needs a reason
    await _move(client, b, pid, "open", note="Tape missing at the bottom")
    a = await as_("a")
    await _move(client, a, pid, "rectified")
    b = await as_("b")
    closed = await _move(client, b, pid, "verified")
    assert (closed["status"], closed["verified_by_id"]) == ("closed", users["b"]["id"])
    history = (await client.get(f"/api/v1/issues/{pid}/history")).json()
    assert [h["to_status"] for h in history] == ["open", "rectified", "open", "rectified", "verified", "closed"]


async def test_a_separate_close_is_never_by_the_rectifier(client: AsyncClient, site):
    project, _, as_, nodes = site
    a = await as_("a")
    template = (
        await client.post(
            "/api/v1/issues/templates/",
            json={
                "project_id": project.id,
                "name": "Walkdown snag",
                "issue_type": "punch",
                "category": "general",
                "separate_close": True,
                "default_punch_category": "B",
                "fields": [],
            },
            headers=a,
        )
    ).json()
    await client.post(f"/api/v1/issues/templates/{template['id']}/publish", headers=a)
    pid = (
        await _raise(
            client, a, project_id=project.id, template_id=template["id"], title="Label", anchor_node_id=nodes["rsw2"]["id"]
        )
    )["id"]
    await _move(client, a, pid, "rectified")
    b = await as_("b")
    assert (await _move(client, b, pid, "verified"))["status"] == "verified"
    a = await as_("a")
    await _move(client, a, pid, "closed", 403)
    b = await as_("b")
    assert (await _move(client, b, pid, "closed"))["status"] == "closed"


async def test_cat_rules_anchors_and_the_completion_gate(client: AsyncClient, db_session: AsyncSession, site):
    project, _, as_, nodes = site
    a = await as_("a")
    base = {"project_id": project.id, "issue_type": "punch", "category": "cladding"}
    await _raise(client, a, 422, **base, title="Bad cat", punch_category="D", anchor_node_id=nodes["rsw1"]["id"])
    b_cat = await _raise(client, a, **base, title="Dent", anchor_node_id=nodes["rsw1"]["id"])
    assert b_cat["punch_category"] == "B"  # the template default
    cat_a = await _raise(client, a, **base, title="Laps open", punch_category="A", anchor_node_id=nodes["rsw1"]["id"])
    ncr = await _raise(
        client, a, project_id=project.id, issue_type="ncr", category="cladding", title="Wrong sheet", punch_category="A",
        anchor_node_id=nodes["rsw1"]["id"],
    )  # fmt: skip
    assert ncr["punch_category"] is None and ncr["severity"] == "minor"

    # cladding needs an anchor in a project with a breakdown; an area has no work anchor on its path
    await _raise(client, a, 422, **base, title="Nowhere")
    assert "work anchor" in (await _raise(client, a, 422, **base, title="Area", anchor_node_id=nodes["area1"]["id"]))["detail"]
    hs = await _raise(
        client, a, project_id=project.id, issue_type="punch", category="health_safety", title="Trip hazard",
        punch_category="A", location_node_id=nodes["area2"]["id"],
    )  # fmt: skip
    assert hs["anchor_node_id"] is None and hs["location_label"].endswith("A2")

    blockers = await service.completion_blockers(db_session, project.id, nodes["rsw1"]["id"])
    assert sorted(b["id"] for b in blockers) == sorted([cat_a["id"], ncr["id"]])  # Cat B and project-level never block
    assert await open_cat_a(db_session, project.id) == 2

    summary = (await client.get("/api/v1/issues/summary", params={"project_id": project.id, "level_key": "area"})).json()
    assert summary["totals"]["cat_a_open"] == 2 and summary["totals"]["open"] == 3
    areas = {x["label"].split(" / ")[-1]: x for x in summary["by_area"]}
    assert areas["A1"]["cat_a_open"] == 1 and areas["A1"]["cat_b_open"] == 1
    assert areas["Project level"]["cat_a_open"] == 1

    scoped = (await client.get("/api/v1/issues/", params={"project_id": project.id, "node_id": nodes["area1"]["id"]})).json()
    assert scoped["total_count"] == 3
    xlsx = await client.get("/api/v1/issues/export", params={"project_id": project.id, "register": "punch"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    pdf = await client.get("/api/v1/issues/export", params={"project_id": project.id, "register": "ncr", "format": "pdf"})
    assert pdf.content.startswith(b"%PDF")


async def test_ncr_workflow_through_the_issues_api(client: AsyncClient, site):
    project, users, as_, nodes = site
    a = await as_("a")
    ncr = await _raise(
        client, a, project_id=project.id, issue_type="ncr", category="coatings", title="Low DFT", severity="major",
        anchor_node_id=nodes["rsw2"]["id"],
        answers={"coating_system": "EP-2", "requirement": "SPEC-PNT §4", "containment_action": "Area barricaded"},
    )  # fmt: skip
    nid = ncr["id"]
    await _move(client, a, nid, "root_cause", 422)  # steps are never skipped
    await _move(client, a, nid, "disposition")
    await _patch(client, a, nid, disposition="use_as_is")
    assert "concession" in (await _move(client, a, nid, "root_cause", 422))["detail"]
    await _patch(client, a, nid, concession_reference="CON-7")
    await _move(client, a, nid, "root_cause")
    await _patch(client, a, nid, root_cause_category="procedure", root_cause_description="Wrong DFT gauge setting")
    await _move(client, a, nid, "corrective_action")
    action = (await client.post(f"/api/v1/ncr/{nid}/actions", json={"description": "Recalibrate gauges"}, headers=a)).json()
    b = await as_("b")
    await client.patch(f"/api/v1/ncr/{nid}/actions/{action['actions'][0]['id']}", json={"status": "done"}, headers=b)
    await _move(client, b, nid, "effectiveness")
    a = await as_("a")
    await _patch(client, a, nid, answers={"effectiveness_evidence": "Re-measured 3 areas"})
    await _move(client, a, nid, "closed", 422)  # the sign-off needs the attestation
    await _move(client, a, nid, "closed", 403, attest=True)  # recorded the disposition
    b = await as_("b")
    await _move(client, b, nid, "closed", 403, attest=True)  # completed an action
    c = await as_("c")
    closed = await _move(client, c, nid, "closed", attest=True)
    assert (closed["status"], closed["verified_by_id"]) == ("closed", users["c"]["id"])
    assert "NCR-001" in closed["effectiveness_statement"]
    pdf = await client.get(f"/api/v1/ncr/{nid}/report.pdf")
    assert pdf.content.startswith(b"%PDF")


async def test_clients_never_see_internal_issues(client: AsyncClient, db_session: AsyncSession, site):
    project, users, as_, nodes = site
    a = await as_("a")
    internal = await _raise(
        client, a, project_id=project.id, issue_type="punch", category="welding", title="Spatter",
        anchor_node_id=nodes["rsw1"]["id"],
    )  # fmt: skip
    # an internal issue is never assigned to a portal account
    await _patch(client, a, internal["id"], 422, responsible_user_id=users["client"]["id"])

    c = await as_("client")
    raised = await _raise(
        client, c, project_id=project.id, issue_type="punch", category="welding", title="Weld cap rough",
        punch_category="A", anchor_node_id=nodes["rsw1"]["id"],
    )  # fmt: skip
    assert (raised["origin"], raised["visibility"]) == ("client", "client")
    assert raised["client_seen_at"]  # the client read it back
    listed = (await client.get("/api/v1/issues/", params={"project_id": project.id})).json()
    assert [i["id"] for i in listed["data"]] == [raised["id"]]
    assert (await client.get(f"/api/v1/issues/{internal['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/ncr/{internal['id']}/report.pdf")).status_code == 404
    summary = (await client.get("/api/v1/issues/summary", params={"project_id": project.id})).json()
    assert summary["totals"]["open"] == 1
    assert (await client.get("/api/v1/issues/blocking", params={"project_id": project.id})).status_code == 404

    # staff rectify; the client verifies the punch they raised, but works no other step
    a = await as_("a")
    await _patch(client, a, raised["id"], answers={"rectification": "Ground smooth"})
    await _move(client, a, raised["id"], "rectified")
    await _patch(client, a, internal["id"], answers={"rectification": "Cleaned"})
    await _move(client, a, internal["id"], "rectified")
    c = await as_("client")
    assert (await _move(client, c, raised["id"], "verified"))["status"] == "closed"
    await _move(client, c, internal["id"], "verified", 404)


async def test_files_and_comments_on_internal_issues_stay_internal(client: AsyncClient, site):
    project, _, as_, nodes = site
    anchor = nodes["rsw1"]["id"]
    c = await as_("client")
    shared = await _raise(
        client, c, project_id=project.id, issue_type="punch", category="welding", title="Seen", anchor_node_id=anchor
    )
    a = await as_("a")
    internal = await _raise(
        client, a, project_id=project.id, issue_type="punch", category="welding", title="Hidden", anchor_node_id=anchor
    )
    files: dict[str, int] = {}
    for key, issue in (("internal", internal), ("shared", shared)):
        up = await client.post(
            "/api/v1/files/",
            data={"project_id": str(project.id), "entity_type": "ncr", "entity_id": str(issue["id"])},
            files={"file": (f"{key}.txt", b"photo", "text/plain")},
            headers=a,
        )
        assert up.status_code == 201, up.text
        files[key] = up.json()["id"]
        made = await client.post(
            "/api/v1/comments/",
            json={"project_id": project.id, "entity_type": "ncr", "entity_id": issue["id"], "body": key},
            headers=a,
        )
        assert made.status_code == 201, made.text
    listing = {"project_id": project.id, "entity_type": "ncr"}
    assert set(files.values()) <= {f["id"] for f in (await client.get("/api/v1/files/", params=listing)).json()["data"]}

    c = await as_("client")
    seen = {f["id"] for f in (await client.get("/api/v1/files/", params=listing)).json()["data"]}
    assert files["shared"] in seen and files["internal"] not in seen
    assert (await client.get(f"/api/v1/files/{files['shared']}")).status_code == 200
    assert (await client.get(f"/api/v1/files/{files['internal']}")).status_code == 404
    assert (await client.get(f"/api/v1/files/{files['internal']}/download")).status_code == 404
    thread = {"project_id": project.id, "entity_type": "ncr", "entity_id": internal["id"]}
    assert (await client.get("/api/v1/comments/", params=thread)).status_code == 404
    assert (await client.post("/api/v1/comments/", json={**thread, "body": "hi"}, headers=c)).status_code == 404
    own = {**thread, "entity_id": shared["id"]}
    assert [t["body"] for t in (await client.get("/api/v1/comments/", params=own)).json()] == ["shared"]


async def test_flag_overrides_and_their_guardrails(client: AsyncClient, db_session: AsyncSession, site):
    project, users, as_, nodes = site
    a = await as_("a")
    ncr = await _raise(
        client, a, project_id=project.id, issue_type="ncr", category="welding", title="Porosity",
        anchor_node_id=nodes["rsw1"]["id"], answers={"weld_id": "W-12"},
    )  # fmt: skip
    nid = ncr["id"]

    async def flag(name: str, value: str, expect: int = 200, issue: int = nid) -> dict:
        r = await client.post(
            f"/api/v1/issues/{issue}/flags", json={"flag": name, "value": value, "reason": "QA decision"}, headers=a
        )
        assert r.status_code == expect, r.text
        return r.json()

    assert "Raise external" in (await flag("visibility", "client", 422))["detail"]
    assert (await flag("mdr_effect", "register_only"))["mdr_effect"] == "register_only"
    assert (await flag("mdr_effect", "blocks"))["mdr_effect"] == "blocks"  # tightening
    await flag("completion_effect", "none")
    await flag("mdr_effect", "blocks", 422)  # already
    await flag("mdr_effect", "sometimes", 422)
    ledger = (await client.get(f"/api/v1/issues/{nid}/flags")).json()
    assert [(e["flag"], e["new_value"], e["loosening"]) for e in ledger] == [
        ("mdr_effect", "register_only", True),
        ("mdr_effect", "blocks", False),
        ("completion_effect", "none", True),
    ]
    assert ledger[0]["actor_name"] == users["a"]["name"] and ledger[0]["reason"] == "QA decision"
    assert await loosening_overrides(db_session, project.id) == 2
    # the QA authority (the other ncr.manage holders) hears about every loosening
    notes = list(
        (await db_session.execute(select(Notification.title).where(Notification.user_id == users["b"]["id"]))).scalars()
    )
    assert sum("loosened" in t for t in notes) == 2

    # client-origin issues are locked: never internal, never excluded
    c = await as_("client")
    client_ncr = await _raise(
        client,
        c,
        project_id=project.id,
        issue_type="ncr",
        category="welding",
        title="Crack",
        anchor_node_id=nodes["rsw1"]["id"],
    )
    a = await as_("a")
    await flag("visibility", "internal", 422, client_ncr["id"])
    await flag("mdr_effect", "excluded", 422, client_ncr["id"])
    await flag("mdr_effect", "register_only", 200, client_ncr["id"])

    # external-audit origin forces client and lifts excluded to register_only at raise
    audit = await _raise(
        client, a, project_id=project.id, issue_type="ncr", category="audit", title="Audit finding",
        origin="external_audit", answers={"audit_reference": "EXT-1"},
    )  # fmt: skip
    assert (audit["visibility"], audit["mdr_effect"]) == ("client", "register_only")
    internal_audit = await _raise(
        client, a, project_id=project.id, issue_type="punch", category="audit", title="Housekeeping",
        answers={"audit_reference": "INT-1"},
    )  # fmt: skip
    assert (internal_audit["origin"], internal_audit["visibility"], internal_audit["mdr_effect"]) == (
        "internal_audit",
        "internal",
        "excluded",
    )


async def test_client_seen_issues_never_go_back_to_internal(client: AsyncClient, site):
    project, _, as_, nodes = site
    a = await as_("a")
    template = (
        await client.post(
            "/api/v1/issues/templates/",
            json={"project_id": project.id, "name": "Client snag", "issue_type": "punch", "category": "general",
                  "default_visibility": "client", "default_punch_category": "B", "fields": []},
            headers=a,
        )
    ).json()  # fmt: skip
    await client.post(f"/api/v1/issues/templates/{template['id']}/publish", headers=a)
    anchor = nodes["rsw1"]["id"]
    unseen = await _raise(client, a, project_id=project.id, template_id=template["id"], title="One", anchor_node_id=anchor)
    seen = await _raise(client, a, project_id=project.id, template_id=template["id"], title="Two", anchor_node_id=anchor)
    await as_("client")
    assert (await client.get(f"/api/v1/issues/{seen['id']}")).status_code == 200
    a = await as_("a")
    body = {"flag": "visibility", "value": "internal", "reason": "Raised on the wrong template"}
    refused = await client.post(f"/api/v1/issues/{seen['id']}/flags", json=body, headers=a)
    assert refused.status_code == 422 and "seen" in refused.json()["detail"]
    allowed = await client.post(f"/api/v1/issues/{unseen['id']}/flags", json=body, headers=a)
    assert allowed.json()["visibility"] == "internal"


async def test_upgrade_punch_to_ncr_and_raise_external(client: AsyncClient, db_session: AsyncSession, site):
    project, users, as_, nodes = site
    other = Project(code="K-2", name="Elsewhere")
    db_session.add(other)
    await db_session.flush()
    photo = StoredFile(
        name="joint.jpg", content_type="image/jpeg", size=10, sha256="0" * 64, storage_key="k",
        uploaded_by_id=users["a"]["id"], project_id=project.id,
    )  # fmt: skip
    foreign = StoredFile(
        name="x.jpg", content_type="image/jpeg", size=1, sha256="1" * 64, storage_key="x", uploaded_by_id=None,
        project_id=other.id,
    )  # fmt: skip
    db_session.add_all([photo, foreign])
    await db_session.commit()
    a = await as_("a")
    base = {"project_id": project.id, "issue_type": "punch", "category": "welding", "anchor_node_id": nodes["rsw1"]["id"]}
    await _raise(client, a, 422, **base, title="Foreign photo", answers={"photos": [foreign.id]})
    punch = await _raise(client, a, **base, title="Undercut on W-3", answers={"weld_id": "W-3", "photos": [photo.id]})

    upgraded = await client.post(f"/api/v1/issues/{punch['id']}/upgrade", json={"note": "Repeat defect"}, headers=a)
    assert upgraded.status_code == 201, upgraded.text
    ncr = upgraded.json()
    assert (ncr["code"], ncr["issue_type"], ncr["upgraded_from_id"]) == ("NCR-001", "ncr", punch["id"])
    assert ncr["answers"] == {"weld_id": "W-3", "photos": [photo.id]}  # same file ids
    assert ncr["visibility"] == "internal" and ncr["anchor_node_id"] == nodes["rsw1"]["id"]
    source = (await client.get(f"/api/v1/issues/{punch['id']}")).json()
    assert (source["status"], source["successor_id"]) == ("upgraded", ncr["id"])
    assert (await client.post(f"/api/v1/issues/{ncr['id']}/upgrade", json={}, headers=a)).status_code == 422  # no downgrade

    await client.post(f"/api/v1/ncr/{ncr['id']}/actions", json={"description": "Internal RCA note"}, headers=a)
    external = await client.post(
        f"/api/v1/issues/{ncr['id']}/raise-external",
        json={"carry_description": False, "carry_answers": ["weld_id", "photos"], "carry_photos": [photo.id]},
        headers=a,
    )
    assert external.status_code == 201, external.text
    ext = external.json()
    assert (ext["visibility"], ext["escalated_from_id"], ext["actions"]) == ("client", ncr["id"], [])
    assert ext["answers"] == {"weld_id": "W-3", "photos": [photo.id]}
    assert (await client.get(f"/api/v1/issues/{ncr['id']}")).json()["status"] == "escalated"
    again = await client.post(f"/api/v1/issues/{ext['id']}/raise-external", json={}, headers=a)
    assert again.status_code == 422  # already client-visible

    await as_("client")
    seen = (await client.get(f"/api/v1/issues/{ext['id']}")).json()
    assert seen["escalated_from_id"] is None  # an internal-only link

    a = await as_("a")
    void = await client.post(f"/api/v1/issues/{ext['id']}/void", json={"reason": "Duplicate"}, headers=a)
    assert (void.json()["status"], void.json()["code"], void.json()["void_reason"]) == ("void", ext["code"], "Duplicate")


async def test_templates_are_layered_and_revisioned(client: AsyncClient, site):
    project, _, as_, nodes = site
    a = await as_("a")
    library = (await client.get("/api/v1/issues/templates/", params={"issue_type": "punch"})).json()
    keys = {t["key"] for t in library["data"]}
    assert {"insulation-punch", "cladding-punch", "coatings-punch", "refractory-punch", "scaffolding-punch"} <= keys
    assert {"welding-punch", "health_safety-punch", "audit-internal-punch"} <= keys
    assert library["data"][0]["published"]["json_schema"]["type"] == "object"

    # library edits need ncr.configure
    lib_id = next(t["id"] for t in library["data"] if t["key"] == "coatings-punch")
    assert (await client.put(f"/api/v1/issues/templates/{lib_id}/draft", json={"name": "x"}, headers=a)).status_code == 403

    def fields(*extra: dict) -> list[dict]:
        return [
            {"key": "defect", "label": "Defect", "type": "select", "options": ["Holiday", "Runs"], "required": True},
            *extra,
        ]

    body = {"project_id": project.id, "name": "Coatings snag", "issue_type": "punch", "category": "coatings"}
    bad = [
        [{"key": "x", "label": "X", "step": "containment"}],  # an NCR step on a punch template
        [{"key": "x", "label": "X", "type": "select"}],  # no options
        [{"key": "x", "label": "X"}, {"key": "x", "label": "Y"}],  # duplicate key
    ]
    for f in bad:
        assert (await client.post("/api/v1/issues/templates/", json={**body, "fields": f}, headers=a)).status_code == 422
    made = (await client.post("/api/v1/issues/templates/", json={**body, "fields": fields()}, headers=a)).json()
    tid = made["id"]
    assert made["published"] is None and made["draft"]["number"] == 1
    anchor = nodes["rsw1"]["id"]
    await _raise(client, a, 422, project_id=project.id, template_id=tid, title="Unpublished", anchor_node_id=anchor)
    await client.post(f"/api/v1/issues/templates/{tid}/publish", headers=a)
    default = await client.put(
        "/api/v1/issues/defaults",
        json={"project_id": project.id, "category": "coatings", "issue_type": "punch", "template_id": tid},
        headers=a,
    )
    assert {"category": "coatings", "issue_type": "punch", "template_id": tid, "layer": "project"} in default.json()

    first = await _raise(
        client, a, project_id=project.id, issue_type="punch", category="coatings", title="Runs", punch_category="C",
        anchor_node_id=anchor, answers={"defect": "Runs"},
    )  # fmt: skip
    assert first["template_id"] == tid
    for answers in ({"defect": "Dust"}, {"colour": "red"}):
        await _raise(
            client, a, 422, project_id=project.id, template_id=tid, title="Bad", anchor_node_id=anchor, answers=answers
        )

    edited = await client.put(
        f"/api/v1/issues/templates/{tid}/draft",
        json={"fields": fields({"key": "dft", "label": "DFT", "type": "number", "unit": "µm", "min": 0})},
        headers=a,
    )
    assert edited.json()["draft"]["number"] == 2 and len(edited.json()["published"]["fields"]) == 1
    await client.post(f"/api/v1/issues/templates/{tid}/publish", headers=a)
    second = await _raise(
        client, a, project_id=project.id, template_id=tid, title="Thin", punch_category="C",
        anchor_node_id=anchor, answers={"defect": "Holiday", "dft": 80},
    )  # fmt: skip
    assert second["template_revision_id"] != first["template_revision_id"]
    assert (await client.get(f"/api/v1/issues/{first['id']}")).json()["template_revision_id"] == first["template_revision_id"]
    await _patch(client, a, first["id"], 422, answers={"dft": 80})  # not a field of its pinned revision
    revisions = (await client.get(f"/api/v1/issues/templates/{tid}")).json()["revisions"]
    assert [(r["number"], r["status"]) for r in revisions] == [(1, "published"), (2, "published")]

    # copying a library template hides the library one from the project's lists
    copy = (await client.post(f"/api/v1/issues/templates/{lib_id}/copy", params={"project_id": project.id}, headers=a)).json()
    assert copy["derived_from_id"] == lib_id and copy["published"]["number"] == 1
    listed = (await client.get("/api/v1/issues/templates/", params={"project_id": project.id, "category": "coatings"})).json()
    ids = {t["id"] for t in listed["data"]}
    assert lib_id not in ids and copy["id"] in ids

    # categories: project-editable, deactivated rather than deleted
    cats = await client.put(
        "/api/v1/issues/categories/vehicle", params={"project_id": project.id}, json={"is_active": False}, headers=a
    )
    vehicle = next(c for c in cats.json() if c["key"] == "vehicle")
    assert (vehicle["is_active"], vehicle["layer"]) == (False, "project")
    await _raise(
        client, a, 422, project_id=project.id, issue_type="punch", category="vehicle", title="Tyre", punch_category="A"
    )
    library_cats = (await client.get("/api/v1/issues/categories")).json()
    assert next(c for c in library_cats if c["key"] == "vehicle")["is_active"] is True


async def test_mdr_gate_and_register(client: AsyncClient, db_session: AsyncSession, site):
    project, _, as_, nodes = site
    a = await as_("a")
    punch = {"project_id": project.id, "issue_type": "punch", "category": "insulation", "punch_category": "A"}
    hs = {"project_id": project.id, "issue_type": "ncr", "category": "health_safety"}
    anchored = await _raise(client, a, **punch, title="In scope", anchor_node_id=nodes["rsw1"]["id"])
    await _raise(client, a, **punch, title="Other area", anchor_node_id=nodes["rsw2"]["id"])
    everywhere = await _raise(client, a, **hs, title="Project wide", answers={"hazard": "Fall"})
    at_site = await _raise(
        client, a, **hs, title="At site (an ancestor)", location_node_id=nodes["site"]["id"], answers={"hazard": "Dust"}
    )
    await _raise(client, a, **hs, title="Elsewhere", location_node_id=nodes["area2"]["id"], answers={"hazard": "Noise"})

    blocking = await service.blocking_issues(db_session, project.id, [nodes["asset1"]["id"]])
    assert sorted(b["id"] for b in blocking) == sorted([anchored["id"], everywhere["id"], at_site["id"]])
    via_api = await client.get("/api/v1/issues/blocking", params={"project_id": project.id, "node_id": nodes["asset1"]["id"]})
    assert len(via_api.json()) == 3
    assert len(await service.blocking_issues(db_session, project.id, None)) == 5

    # the register prints client issues only, and marks them client-seen
    raised = await client.post(f"/api/v1/issues/{anchored['id']}/raise-external", json={}, headers=a)
    assert raised.status_code == 201, raised.text
    register = await service.mdr_register(db_session, project.id, [nodes["asset1"]["id"]])
    await db_session.commit()
    assert [r["title"] for r in register] == ["In scope"] and register[0]["issue_type"] == "ncr"
    ext = await service.get_ncr(db_session, register[0]["id"])
    await db_session.refresh(ext)
    assert ext.client_seen_channel == "mdr"


async def test_an_inspection_request_raises_an_issue(db_session: AsyncSession, test_user: dict):
    project = Project(code="K-9", name="Plant")
    db_session.add(project)
    await db_session.commit()
    payload = {
        "project_id": project.id,
        "inspection_id": 5,
        "item_id": 9,
        "ncr_id": None,
        "title": "INS-001 #2: Thickness",
        "raised_by_id": test_user["id"],
    }
    issue = await raise_requested(db_session, payload)
    assert issue is not None
    assert (issue.code, issue.issue_type, issue.source, issue.inspection_item_id) == ("NCR-001", "ncr", "inspection", 9)
    punch = await raise_requested(db_session, {**payload, "issue_type": "punch", "category": "insulation"})
    assert punch is not None and (punch.code, punch.punch_category) == ("PL-001", "A")
    assert await raise_requested(db_session, {**payload, "ncr_id": issue.id}) is None  # inspections raised it already

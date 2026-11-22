"""NCRs (issues engine, NCR type): workflow with reopen on ineffective verification, root cause, disposition, CAPA,
costs, PDF and export through the original /api/v1/ncr routes."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.contacts.models import Company, Contact
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    "ncr.read",
    "ncr.create",
    "ncr.update",
    "ncr.delete",
    "ncr.transition",
    "ncr.export",
    "ncr.verify",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def test_ncr_lifecycle_with_capa(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict):
    project = Project(code="N-1", name="Refinery revamp")
    company = Company(name="Acme Insulation")
    db_session.add_all([project, company])
    await db_session.flush()
    contact = Contact(first_name="Sam", last_name="Lee", company_id=company.id)
    db_session.add(contact)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "qa", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    made = await client.post(
        "/api/v1/ncr/",
        json={
            "project_id": project.id,
            "title": "Cladding laps facing weather",
            "description": "Laps on line 12 open upward; water ingress risk.",
            "location": "Pipe rack 2",
            "trade": "Insulation",
            "severity": "major",
            "source": "client",
            "spec_reference": "SPEC-INS-001 §7.3",
            "responsible_user_id": test_user_2["id"],
            "responsible_contact_id": contact.id,
            "responsible_company_id": company.id,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    ncr = made.json()
    assert (ncr["code"], ncr["status"], ncr["raised_by_id"]) == ("NCR-001", "open", test_user["id"])
    assert ncr["raised_on"] and ncr["responsible_contact_name"] == "Sam Lee (Acme Insulation)"
    assert ncr["responsible_company_name"] == "Acme Insulation"
    nid = ncr["id"]

    skipped = await client.patch(f"/api/v1/ncr/{nid}/status", json={"status": "closed"}, headers=headers)
    assert skipped.status_code == 422

    async def move(status: str, note: str | None = None, expect: int = 200) -> dict:
        r = await client.patch(f"/api/v1/ncr/{nid}/status", json={"status": status, "note": note}, headers=headers)
        assert r.status_code == expect, r.text
        return r.json()

    # containment is a required template field of the general NCR template
    assert "Containment" in (await move("disposition", expect=422))["detail"]
    contained = await client.patch(
        f"/api/v1/ncr/{nid}",
        json={"answers": {"requirement": "SPEC-INS-001 §7.3", "containment_action": "Line 12 tagged, laps taped"}},
        headers=headers,
    )
    assert contained.status_code == 200, contained.text
    await move("disposition")
    updated = await client.patch(
        f"/api/v1/ncr/{nid}",
        json={
            "disposition": "rework",
            "rework_cost": "1250.50",
            "delay_cost": "800",
            "other_cost": "49.50",
            "days_delay": 2,
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["total_cost"] == "2100.00"
    assert (await client.patch(f"/api/v1/ncr/{nid}", json={"rework_cost": -1}, headers=headers)).status_code == 422
    assert (await client.patch(f"/api/v1/ncr/{nid}", json={"title": None}, headers=headers)).status_code == 422
    assert (await move("root_cause"))["disposition_by_id"] == test_user["id"]
    locked = await client.patch(f"/api/v1/ncr/{nid}", json={"disposition": "scrap"}, headers=headers)
    assert locked.status_code == 422  # recorded at its step
    await move("corrective_action", expect=422)  # root cause first
    await client.patch(
        f"/api/v1/ncr/{nid}",
        json={"root_cause_category": "workmanship", "root_cause_description": "Installer not briefed on lap orientation."},
        headers=headers,
    )
    await move("corrective_action")
    await move("effectiveness", expect=422)  # no corrective action done yet

    corrective = await client.post(
        f"/api/v1/ncr/{nid}/actions",
        json={
            "description": "Re-lap cladding on line 12",
            "responsible_id": test_user_2["id"],
            "due_date": "2026-01-10",
            "verification_criteria": "QC walkdown, all laps shed water",
        },
        headers=headers,
    )
    assert corrective.status_code == 201, corrective.text
    preventive = await client.post(
        f"/api/v1/ncr/{nid}/actions",
        json={"description": "Toolbox talk on lap orientation", "kind": "preventive", "responsible_id": test_user_2["id"]},
        headers=headers,
    )
    actions = preventive.json()["actions"]
    assert [a["kind"] for a in actions] == ["corrective", "preventive"]
    assert preventive.json()["open_actions"] == 2
    assert actions[0]["overdue"] is True  # due in the past and still open

    first, second = actions[0]["id"], actions[1]["id"]
    done = await client.patch(f"/api/v1/ncr/{nid}/actions/{first}", json={"status": "done"}, headers=headers)
    assert done.json()["actions"][0]["completed_at"]
    verified = await client.patch(
        f"/api/v1/ncr/{nid}/actions/{first}", json={"status": "verified", "verification_notes": "Walkdown OK"}, headers=headers
    )
    action = verified.json()["actions"][0]
    assert (action["verified_by_id"], action["verified_by_name"]) == (test_user["id"], test_user["name"])
    assert action["verified_at"] and action["overdue"] is False
    assert verified.json()["open_actions"] == 1
    await move("effectiveness", expect=422)  # the preventive action is still open
    no_reason = await client.patch(f"/api/v1/ncr/{nid}/actions/{second}", json={"status": "cancelled"}, headers=headers)
    assert no_reason.status_code == 422
    await client.patch(
        f"/api/v1/ncr/{nid}/actions/{second}",
        json={"status": "cancelled", "cancel_reason": "Covered by the induction update"},
        headers=headers,
    )

    await move("effectiveness")
    await move("corrective_action", expect=422)  # sending it back needs a reason
    reopened = await move("corrective_action", "Verification failed")
    assert reopened["status"] == "corrective_action"
    await move("effectiveness")
    await client.patch(f"/api/v1/ncr/{nid}", json={"answers": {"effectiveness_evidence": "Walkdown 12 Jan"}}, headers=headers)
    # whoever recorded the disposition or completed an action never verifies effectiveness
    assert (await move("closed", expect=403))["detail"].startswith("Nobody who recorded")

    await _grant(db_session, test_user_2["id"], "qa-lead", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    closed = await move("closed", "All laps re-done")
    assert closed["closed_at"] and closed["verified_by_id"] == test_user_2["id"]
    assert "NCR-001" in closed["effectiveness_statement"]
    assert (await client.patch(f"/api/v1/ncr/{nid}/status", json={"status": "open"}, headers=headers)).status_code == 422

    history = (await client.get(f"/api/v1/ncr/{nid}/history")).json()
    assert [h["to_status"] for h in history] == [
        "open",
        "disposition",
        "root_cause",
        "corrective_action",
        "effectiveness",
        "corrective_action",
        "effectiveness",
        "closed",
    ]
    assert history[5]["note"] == "Verification failed" and history[-1]["changed_by_name"] == test_user_2["name"]
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    use_as_is = await client.post(
        "/api/v1/ncr/", json={"project_id": project.id, "title": "Minor dent", "source": "audit"}, headers=headers
    )
    assert use_as_is.json()["code"] == "NCR-002"
    await client.patch(
        f"/api/v1/ncr/{use_as_is.json()['id']}",
        json={"disposition": "use_as_is", "concession_reference": "CON-17"},
        headers=headers,
    )

    by_severity = (await client.get("/api/v1/ncr/", params={"project_id": project.id, "severity": "major"})).json()
    assert [n["code"] for n in by_severity["data"]] == ["NCR-001"]
    open_only = (await client.get("/api/v1/ncr/", params={"project_id": project.id, "open_only": True})).json()
    assert [n["code"] for n in open_only["data"]] == ["NCR-002"]
    searched = (await client.get("/api/v1/ncr/", params={"project_id": project.id, "search": "dent"})).json()
    assert searched["total_count"] == 1

    pdf = await client.get(f"/api/v1/ncr/{nid}/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")

    csv = await client.get("/api/v1/ncr/export", params={"project_id": project.id, "format": "csv"})
    assert csv.status_code == 200
    lines = csv.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("NCR,Title,Status")
    assert any("NCR-001" in line and "2100.0" in line for line in lines)
    xlsx = await client.get("/api/v1/ncr/export", params={"project_id": project.id})
    assert xlsx.content[:2] == b"PK"

    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    titles = [n["title"] for n in inbox]
    assert "NCR-001: Cladding laps facing weather" in titles
    assert "NCR-001: corrective action" in titles and "NCR-001: preventive action" in titles
    assert "NCR-001 is now effectiveness" in titles  # test_user_2 closed it themselves


async def test_ncr_actions_belong_to_their_ncr(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="N-2", name="Plant")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "qa", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    a = (await client.post("/api/v1/ncr/", json={"project_id": project.id, "title": "A"}, headers=headers)).json()
    b = (await client.post("/api/v1/ncr/", json={"project_id": project.id, "title": "B"}, headers=headers)).json()
    with_action = (await client.post(f"/api/v1/ncr/{a['id']}/actions", json={"description": "Fix"}, headers=headers)).json()
    action_id = with_action["actions"][0]["id"]
    wrong = await client.patch(f"/api/v1/ncr/{b['id']}/actions/{action_id}", json={"status": "done"}, headers=headers)
    assert wrong.status_code == 404
    removed = await client.delete(f"/api/v1/ncr/{a['id']}/actions/{action_id}", headers=headers)
    assert removed.json()["actions"] == []
    assert (await client.delete(f"/api/v1/ncr/{b['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/ncr/{b['id']}")).status_code == 404

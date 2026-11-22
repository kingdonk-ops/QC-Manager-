"""NCRs: lifecycle with reopen on failed verification, root cause, disposition, CAPA, costs, PDF and export."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.contacts.models import Company, Contact
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = ("projects.read", "ncr.read", "ncr.create", "ncr.update", "ncr.delete", "ncr.transition", "ncr.export")


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

    async def move(status: str, note: str | None = None) -> dict:
        r = await client.patch(f"/api/v1/ncr/{nid}/status", json={"status": status, "note": note}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    await move("under_investigation")
    updated = await client.patch(
        f"/api/v1/ncr/{nid}",
        json={
            "root_cause_category": "workmanship",
            "root_cause_description": "Installer not briefed on lap orientation.",
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
    await move("corrective_action_planned")

    first = actions[0]["id"]
    done = await client.patch(f"/api/v1/ncr/{nid}/actions/{first}", json={"status": "done"}, headers=headers)
    assert done.json()["actions"][0]["completed_at"]
    verified = await client.patch(
        f"/api/v1/ncr/{nid}/actions/{first}", json={"status": "verified", "verification_notes": "Walkdown OK"}, headers=headers
    )
    action = verified.json()["actions"][0]
    assert (action["verified_by_id"], action["verified_by_name"]) == (test_user["id"], test_user["name"])
    assert action["verified_at"] and action["overdue"] is False
    assert verified.json()["open_actions"] == 1

    await move("corrective_action_taken")
    await move("verified")
    reopened = await move("corrective_action_planned")  # verification failed
    assert reopened["status"] == "corrective_action_planned"
    await move("corrective_action_taken")
    await move("verified")
    closed = await move("closed", "All laps re-done")
    assert closed["closed_at"]
    assert (await client.patch(f"/api/v1/ncr/{nid}/status", json={"status": "open"}, headers=headers)).status_code == 422

    history = (await client.get(f"/api/v1/ncr/{nid}/history")).json()
    assert [h["to_status"] for h in history] == [
        "open",
        "under_investigation",
        "corrective_action_planned",
        "corrective_action_taken",
        "verified",
        "corrective_action_planned",
        "corrective_action_taken",
        "verified",
        "closed",
    ]
    assert history[5]["note"] == "Verification failed" and history[-1]["changed_by_name"] == test_user["name"]

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
    assert "NCR-001 is now closed" in titles


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

"""Correspondence: yearly references, threads, response tracking, search, filters and export."""

from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.contacts.models import Contact
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "correspondence.read",
    "correspondence.create",
    "correspondence.update",
    "correspondence.delete",
    "correspondence.export",
    "projects.read",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _world(db: AsyncSession) -> tuple[Project, Contact, Contact]:
    project = Project(code="P-1", name="Plant")
    client_rep = Contact(first_name="Cara", last_name="Client", email="cara@client.example")
    engineer = Contact(first_name="Eli", last_name="Engineer")
    db.add_all([project, client_rep, engineer])
    await db.commit()
    return project, client_rep, engineer


async def test_a_notice_is_answered_and_the_thread_reads_in_order(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    project, cara, eli = await _world(db_session)
    await _grant(db_session, test_user["id"], "cor", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    notice = await client.post(
        "/api/v1/correspondence/",
        json={
            "project_id": project.id,
            "subject": "Notice of delay: scaffold access",
            "type": "notice",
            "direction": "incoming",
            "status": "response_required",
            "body": "Access to level 4 blocked by others since Monday.",
            "sender_contact_id": cara.id,
            "recipient_user_ids": [test_user["id"]],
            "date_received": "2026-03-02",
            "response_required_by": "2026-03-09",
            "external_reference": "CL-L-0042",
        },
        headers=headers,
    )
    assert notice.status_code == 201, notice.text
    original = notice.json()
    assert original["reference"] == "COR-2026-001"
    assert original["sender_name"] == "Cara Client"
    assert original["recipients"] == [{"kind": "user", "id": test_user["id"], "name": test_user["name"]}]
    assert original["overdue"] is (date.today() > date(2026, 3, 9))

    reply = (
        await client.post(
            "/api/v1/correspondence/",
            json={
                "project_id": project.id,
                "subject": "Re: Notice of delay: scaffold access",
                "direction": "outgoing",
                "status": "sent",
                "recipient_contact_ids": [cara.id, eli.id],
                "date_sent": "2026-03-04",
                "in_reply_to_id": original["id"],
            },
            headers=headers,
        )
    ).json()
    assert reply["reference"] == "COR-2026-002"
    assert reply["in_reply_to_reference"] == "COR-2026-001"
    assert [r["name"] for r in reply["recipients"]] == ["Cara Client", "Eli Engineer"]

    answered = (await client.get(f"/api/v1/correspondence/{original['id']}")).json()
    assert (answered["status"], answered["reply_count"], answered["overdue"]) == ("responded", 1, False)

    follow_up = (
        await client.post(
            "/api/v1/correspondence/",
            json={
                "project_id": project.id,
                "subject": "Claim for delay costs",
                "type": "claim",
                "direction": "incoming",
                "status": "received",
                "date_received": "2027-01-10",
                "in_reply_to_id": reply["id"],
            },
            headers=headers,
        )
    ).json()
    assert follow_up["reference"] == "COR-2027-001"

    thread = (await client.get(f"/api/v1/correspondence/{reply['id']}/thread")).json()
    assert [(t["reference"], t["depth"]) for t in thread] == [
        ("COR-2026-001", 0),
        ("COR-2026-002", 1),
        ("COR-2027-001", 2),
    ]

    history = (await client.get(f"/api/v1/correspondence/{original['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["response_required", "responded"]

    closed = await client.patch(f"/api/v1/correspondence/{original['id']}", json={"status": "closed"}, headers=headers)
    assert closed.json()["status"] == "closed"
    refused = await client.patch(f"/api/v1/correspondence/{original['id']}", json={"status": "draft"}, headers=headers)
    assert refused.status_code == 422


async def test_register_search_filters_and_export(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project, cara, eli = await _world(db_session)
    await _grant(db_session, test_user["id"], "cor", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    async def make(subject: str, **kw):
        response = await client.post(
            "/api/v1/correspondence/", json={"project_id": project.id, "subject": subject, **kw}, headers=headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    eot = await make(
        "Extension of time request 3",
        type="extension_of_time",
        body="Rain stopped insulation works on the pipe rack.",
        recipient_contact_ids=[cara.id],
        status="response_required",
        response_required_by="2020-01-01",
    )
    await make("Site instruction 12", type="instruction", direction="incoming", sender_contact_id=eli.id)
    custom = await make("Toolbox minutes", type="other", custom_type="Minutes")
    assert custom["custom_type"] == "Minutes"

    def listing(**params):
        return client.get("/api/v1/correspondence/", params={"project_id": project.id, **params})

    def refs(response) -> list[str]:
        return [r["subject"] for r in response.json()["data"]]

    assert refs(await listing(search="rain pipe")) == ["Extension of time request 3"]
    assert refs(await listing(search="rain cladding")) == []
    assert refs(await listing(direction="incoming")) == ["Site instruction 12"]
    assert refs(await listing(type="extension_of_time")) == ["Extension of time request 3"]
    assert refs(await listing(contact_id=cara.id)) == ["Extension of time request 3"]
    assert refs(await listing(contact_id=eli.id)) == ["Site instruction 12"]
    assert refs(await listing(overdue=True)) == ["Extension of time request 3"]
    assert (await listing()).json()["total_count"] == 3
    assert eot["overdue"] is True

    for fmt in ("csv", "xlsx", "pdf"):
        exported = await client.get("/api/v1/correspondence/export", params={"project_id": project.id, "format": fmt})
        assert exported.status_code == 200, exported.text
    csv = (await client.get("/api/v1/correspondence/export", params={"project_id": project.id, "format": "csv"})).text
    assert "Extension of time request 3" in csv and "Cara Client" in csv and "Minutes" in csv

    other = Project(code="P-2", name="Other")
    db_session.add(other)
    await db_session.commit()
    cross = await client.post(
        "/api/v1/correspondence/",
        json={"project_id": other.id, "subject": "Re", "in_reply_to_id": eot["id"]},
        headers=headers,
    )
    assert cross.status_code == 422

    assert (await client.delete(f"/api/v1/correspondence/{eot['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/correspondence/{eot['id']}")).status_code == 404


async def test_correspondence_needs_a_visible_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project, _, _ = await _world(db_session)
    await _grant(db_session, test_user["id"], "cor-only", "correspondence.read")
    await _login(client, test_user)
    assert (await client.get("/api/v1/correspondence/", params={"project_id": project.id})).status_code == 404

"""Transmittals: building the bundle, revision warnings, sending with a cover sheet, acknowledgements."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mail import Mail
from src.infrastructure.modules import state
from src.modules.contacts.models import Company, Contact
from src.modules.files.models import StoredFile
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "transmittals.read",
    "transmittals.create",
    "transmittals.update",
    "transmittals.delete",
    "transmittals.submit",
    "projects.read",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture
def outbox(monkeypatch) -> list[Mail]:
    sent: list[Mail] = []

    async def capture(mail: Mail) -> None:
        sent.append(mail)

    monkeypatch.setattr("src.modules.transmittals.service.deliver", capture)
    return sent


def _file(
    project: Project, name: str, revision: int = 1, supersedes: StoredFile | None = None, category: str = "drawing"
) -> StoredFile:
    return StoredFile(
        name=name,
        content_type="application/pdf",
        size=100,
        sha256="0" * 64,
        storage_key=f"xx/{name}-{revision}",
        uploaded_by_id=None,
        project_id=project.id,
        category=category,
        revision=revision,
        supersedes_id=supersedes.id if supersedes else None,
    )


async def _world(db: AsyncSession):
    project = Project(code="P-24017", name="LNG Train 3")
    company = Company(name="Northwind Energy")
    db.add_all([project, company])
    await db.commit()
    ana = Contact(first_name="Ana", last_name="Approver", email="ana@northwind.example", company_id=company.id)
    bob = Contact(first_name="Bob", last_name="Builder", email="bob@site.example")
    nomail = Contact(first_name="Nora", last_name="Nomail")
    db.add_all([ana, bob, nomail])
    old = _file(project, "GA-100.pdf", 1)
    db.add(old)
    await db.commit()
    old.is_latest = False
    new = _file(project, "GA-100.pdf", 2, supersedes=old)
    spec = _file(project, "Spec-07.pdf", 1, category="specification")
    db.add_all([new, spec])
    await db.commit()
    return project, ana, bob, nomail, old, new, spec


async def test_build_warn_swap_send_and_acknowledge(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, outbox: list[Mail]
):
    project, ana, bob, nomail, old, new, spec = await _world(db_session)
    await _grant(db_session, test_user["id"], "tr", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    created = await client.post(
        "/api/v1/transmittals/",
        json={
            "project_id": project.id,
            "subject": "IFC drawings package 1",
            "purpose": "for_construction",
            "notes": "Supersedes all previous issues.",
            "file_ids": [old.id],
            "contact_ids": [ana.id],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    t = created.json()
    assert (t["code"], t["status"]) == ("TR-001", "draft")
    assert [(d["name"], d["revision"], d["is_latest"], d["latest_revision"]) for d in t["documents"]] == [
        ("GA-100.pdf", 1, False, 2)
    ]
    assert [w["latest_file_id"] for w in t["warnings"]] == [new.id]
    assert t["recipients"][0]["name"] == "Ana Approver (Northwind Energy)"

    # Adding the same stale file again is a no-op; swapping moves it to the latest revision
    added = await client.post(
        f"/api/v1/transmittals/{t['id']}/documents", json={"file_ids": [spec.id, old.id]}, headers=headers
    )
    assert [d["name"] for d in added.json()["documents"]] == ["GA-100.pdf", "Spec-07.pdf"]
    stale = added.json()["documents"][0]
    swapped = await client.post(f"/api/v1/transmittals/{t['id']}/documents/{stale['id']}/latest", headers=headers)
    body = swapped.json()
    assert body["warnings"] == []
    assert [(d["file_id"], d["revision"]) for d in body["documents"]] == [(new.id, 2), (spec.id, 1)]

    recipients = await client.post(
        f"/api/v1/transmittals/{t['id']}/recipients", json={"contact_ids": [bob.id, nomail.id, ana.id]}, headers=headers
    )
    assert len(recipients.json()["recipients"]) == 3
    nora = next(r for r in recipients.json()["recipients"] if r["contact_id"] == nomail.id)
    removed = await client.delete(f"/api/v1/transmittals/{t['id']}/recipients/{nora['id']}", headers=headers)
    assert removed.json()["recipient_count"] == 2
    await client.post(f"/api/v1/transmittals/{t['id']}/recipients", json={"contact_ids": [nomail.id]}, headers=headers)

    cover = await client.get(f"/api/v1/transmittals/{t['id']}/cover.pdf")
    assert cover.status_code == 200 and cover.content.startswith(b"%PDF")

    early = await client.patch(
        f"/api/v1/transmittals/{t['id']}/acknowledge", json={"recipient_id": nora["id"]}, headers=headers
    )
    assert early.status_code == 422

    sent = await client.post(f"/api/v1/transmittals/{t['id']}/send", json={"message": "Urgent."}, headers=headers)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "sent" and body["sent_at"]
    assert {r["delivery"] for r in body["recipients"]} == {"sent", "no_email"}
    assert sorted(m.to[0] for m in outbox) == ["ana@northwind.example", "bob@site.example"]
    mail = outbox[0]
    assert mail.subject == "Transmittal TR-001: IFC drawings package 1"
    assert "GA-100.pdf (rev 2)" in mail.text and "Urgent." in mail.text
    assert mail.attachments[0].filename == "TR-001.pdf"
    assert mail.attachments[0].content.startswith(b"%PDF")

    locked = await client.post(f"/api/v1/transmittals/{t['id']}/documents", json={"file_ids": [old.id]}, headers=headers)
    assert locked.status_code == 422
    again = await client.post(f"/api/v1/transmittals/{t['id']}/send", json={}, headers=headers)
    assert again.status_code == 422

    people = {r["contact_id"]: r for r in body["recipients"]}
    partial = await client.patch(
        f"/api/v1/transmittals/{t['id']}/acknowledge",
        json={"recipient_id": people[ana.id]["id"], "note": "Received in good order"},
        headers=headers,
    )
    body = partial.json()
    assert body["status"] == "partially_acknowledged"
    ana_row = next(r for r in body["recipients"] if r["contact_id"] == ana.id)
    assert ana_row["delivery"] == "acknowledged" and ana_row["acknowledgement_note"] == "Received in good order"

    received_only = await client.patch(
        f"/api/v1/transmittals/{t['id']}/acknowledge",
        json={"recipient_id": people[bob.id]["id"], "acknowledged": False, "received_at": "2026-11-20T09:00:00Z"},
        headers=headers,
    )
    bob_row = next(r for r in received_only.json()["recipients"] if r["contact_id"] == bob.id)
    assert bob_row["delivery"] == "received" and bob_row["received_at"].startswith("2026-11-20")
    for cid in (bob.id, nomail.id):
        done = await client.patch(
            f"/api/v1/transmittals/{t['id']}/acknowledge", json={"recipient_id": people[cid]["id"]}, headers=headers
        )
    assert done.json()["status"] == "acknowledged"
    assert done.json()["acknowledged_count"] == 3

    history = (await client.get(f"/api/v1/transmittals/{t['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "sent", "partially_acknowledged", "acknowledged"]

    register = (await client.get("/api/v1/transmittals/", params={"project_id": project.id})).json()
    assert register["total_count"] == 1
    assert register["data"][0]["document_count"] == 2 and len(register["data"][0]["recipients"]) == 3


async def test_sending_a_superseded_revision_warns_and_empty_ones_are_refused(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, outbox: list[Mail]
):
    project, ana, _, _, old, _, _ = await _world(db_session)
    await _grant(db_session, test_user["id"], "tr", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    empty = (
        await client.post("/api/v1/transmittals/", json={"project_id": project.id, "subject": "Empty"}, headers=headers)
    ).json()
    refused = await client.post(f"/api/v1/transmittals/{empty['id']}/send", json={}, headers=headers)
    assert refused.status_code == 422

    t = (
        await client.post(
            "/api/v1/transmittals/",
            json={"project_id": project.id, "subject": "Old drawing", "file_ids": [old.id], "contact_ids": [ana.id]},
            headers=headers,
        )
    ).json()
    assert t["code"] == "TR-002"
    sent = (await client.post(f"/api/v1/transmittals/{t['id']}/send", json={}, headers=headers)).json()
    assert sent["status"] == "sent"
    assert len(sent["warnings"]) == 1 and "superseded" in sent["warnings"][0]["message"]
    assert len(outbox) == 1

    renamed = await client.patch(f"/api/v1/transmittals/{empty['id']}", json={"subject": "Renamed"}, headers=headers)
    assert renamed.json()["subject"] == "Renamed"
    assert (await client.get("/api/v1/transmittals/", params={"project_id": project.id, "status": "draft"})).json()[
        "total_count"
    ] == 1

    other = Project(code="P-2", name="Other")
    db_session.add(other)
    await db_session.commit()
    foreign = _file(other, "Other.pdf")
    db_session.add(foreign)
    await db_session.commit()
    wrong = await client.post(f"/api/v1/transmittals/{empty['id']}/documents", json={"file_ids": [foreign.id]}, headers=headers)
    assert wrong.status_code == 422

    assert (await client.delete(f"/api/v1/transmittals/{empty['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/transmittals/{empty['id']}")).status_code == 404


async def test_transmittals_need_a_visible_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="P-9", name="Hidden")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "tr-only", "transmittals.read")
    await _login(client, test_user)
    assert (await client.get("/api/v1/transmittals/", params={"project_id": project.id})).status_code == 404

"""RFIs: numbering, ball in court, response rounds, lifecycle, overdue reminders, tasks and export."""

from datetime import date, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.files.models import StoredFile
from src.modules.projects.models import Project
from src.modules.rfi.service import overdue_reminders
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

RFI = (
    "rfi.read",
    "rfi.create",
    "rfi.update",
    "rfi.delete",
    "rfi.respond",
    "rfi.transition",
    "rfi.export",
    "projects.read",
    "tasks.read",
    "tasks.create",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture(autouse=True)
def mail(monkeypatch) -> list[Any]:
    sent: list[Any] = []

    async def capture(m: Any) -> None:
        sent.append(m)

    monkeypatch.setattr("src.modules.notifications.service.deliver", capture)
    return sent


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant")
    db.add(project)
    await db.commit()
    return project


async def _setup(client: AsyncClient, db: AsyncSession, *users: dict) -> None:
    for user in users:
        await _grant(db, user["id"], f"r{user['id']}", *RFI)


async def _inbox(client: AsyncClient, user: dict) -> list[dict]:
    await _login(client, user)
    return (await client.get("/api/v1/notifications/")).json()["data"]


async def test_an_rfi_is_raised_answered_followed_up_and_closed(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    await _setup(client, db_session, test_user, test_user_2)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    draft = await client.post(
        "/api/v1/rfis/",
        json={
            "project_id": project.id,
            "subject": "Insulation thickness on line 12",
            "question": "Drawing shows 50 mm, spec says 75 mm. Which applies?",
            "discipline": "Mechanical",
            "addressed_to_user_id": test_user_2["id"],
            "schedule_impact": True,
            "schedule_impact_days": 3,
        },
        headers=headers,
    )
    assert draft.status_code == 201, draft.text
    rfi = draft.json()
    assert (rfi["code"], rfi["status"], rfi["ball_in_court"]) == ("RFI-001", "draft", None)
    assert rfi["due_date"] == (date.today() + timedelta(days=7)).isoformat()
    assert rfi["raised_by_id"] == test_user["id"]

    opened = await client.patch(f"/api/v1/rfis/{rfi['id']}/status", json={"status": "open"}, headers=headers)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert (body["status"], body["ball_in_court"], body["bic_user_id"]) == ("open", "designer", test_user_2["id"])
    assert body["days_open"] == 0

    # Closing straight from open is not allowed
    refused = await client.patch(f"/api/v1/rfis/{rfi['id']}/status", json={"status": "closed"}, headers=headers)
    assert refused.status_code == 422

    assignment = [n for n in await _inbox(client, test_user_2) if n["category"] == "assignment"]
    assert assignment and "ball is in your court" in assignment[0]["title"]

    # The designer answers, attaching a sketch uploaded to the project
    sketch = StoredFile(
        name="sketch.pdf",
        content_type="application/pdf",
        size=10,
        sha256="0" * 64,
        storage_key="xx/sketch",
        uploaded_by_id=test_user_2["id"],
        project_id=project.id,
    )
    db_session.add(sketch)
    await db_session.commit()
    headers2 = {"X-CSRF-Token": await _login(client, test_user_2)}
    answered = await client.post(
        f"/api/v1/rfis/{rfi['id']}/respond",
        json={"body": "75 mm applies.", "attachment_ids": [sketch.id]},
        headers=headers2,
    )
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert (body["status"], body["ball_in_court"], body["bic_user_id"]) == ("answered", "contractor", test_user["id"])
    assert body["responses"][0]["author_name"] == test_user_2["name"]
    assert [a["name"] for a in body["responses"][0]["attachments"]] == ["sketch.pdf"]

    # Follow-up round: reopen, hand the ball back, answer again, close
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    reopened = await client.patch(
        f"/api/v1/rfis/{rfi['id']}/status",
        json={"status": "open", "ball_in_court": "consultant", "bic_user_id": test_user_2["id"], "note": "Which grade?"},
        headers=headers,
    )
    assert (reopened.json()["status"], reopened.json()["ball_in_court"]) == ("open", "consultant")
    comment = await client.post(
        f"/api/v1/rfis/{rfi['id']}/respond", json={"body": "Still checking.", "is_answer": False}, headers=headers
    )
    assert comment.json()["status"] == "open"
    headers2 = {"X-CSRF-Token": await _login(client, test_user_2)}
    await client.post(f"/api/v1/rfis/{rfi['id']}/respond", json={"body": "Grade 2."}, headers=headers2)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    closed = await client.patch(f"/api/v1/rfis/{rfi['id']}/status", json={"status": "closed"}, headers=headers)
    assert closed.json()["status"] == "closed"
    assert len(closed.json()["responses"]) == 3

    late = await client.post(f"/api/v1/rfis/{rfi['id']}/respond", json={"body": "x"}, headers=headers)
    assert late.status_code == 422

    history = (await client.get(f"/api/v1/rfis/{rfi['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "open", "answered", "open", "answered", "closed"]
    assert history[3]["note"] == "Which grade?"

    voided = await client.patch(f"/api/v1/rfis/{rfi['id']}/status", json={"status": "void"}, headers=headers)
    assert voided.json()["status"] == "void"

    raiser_inbox = await _inbox(client, test_user)
    assert any("answered" in n["title"] for n in raiser_inbox)


async def test_register_filters_overdue_reminders_and_project_settings(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    await _setup(client, db_session, test_user)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    settings = await client.put(f"/api/v1/rfis/settings/{project.id}", json={"default_due_days": 14}, headers=headers)
    assert settings.json()["default_due_days"] == 14

    def make(subject: str, **kw):
        return client.post(
            "/api/v1/rfis/",
            json={"project_id": project.id, "subject": subject, "question": "?", "status": "open", **kw},
            headers=headers,
        )

    late = (
        await make(
            "Pipe support spacing",
            discipline="Piping",
            due_date="2020-01-01",
            ball_in_court="client",
            bic_user_id=test_user_2["id"],
        )
    ).json()
    fresh = (await make("Cladding colour", discipline="Architectural")).json()
    assert fresh["due_date"] == (date.today() + timedelta(days=14)).isoformat()
    assert (late["overdue"], fresh["overdue"]) == (True, False)
    assert late["days_open"] == 0

    def listing(**params):
        return client.get("/api/v1/rfis/", params={"project_id": project.id, **params})

    assert [r["code"] for r in (await listing(overdue=True)).json()["data"]] == [late["code"]]
    assert [r["code"] for r in (await listing(ball_in_court="client")).json()["data"]] == [late["code"]]
    assert [r["code"] for r in (await listing(discipline="architectural")).json()["data"]] == [fresh["code"]]
    assert [r["code"] for r in (await listing(search="cladding")).json()["data"]] == [fresh["code"]]
    assert (await listing(status="open")).json()["total_count"] == 2

    assert await overdue_reminders(db_session) == 1
    due = [n for n in await _inbox(client, test_user_2) if n["category"] == "due"]
    assert len(due) == 1 and late["code"] in due[0]["title"]


async def test_export_and_task_from_rfi(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    await _setup(client, db_session, test_user)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    rfi = (
        await client.post(
            "/api/v1/rfis/",
            json={
                "project_id": project.id,
                "subject": "Fire stopping",
                "question": "Detail?",
                "cost_impact": True,
                "cost_impact_amount": "1250.50",
                "entity_type": "drawing",
                "entity_id": 3,
            },
            headers=headers,
        )
    ).json()
    assert rfi["cost_impact_amount"] == "1250.50"

    for fmt, media in (("csv", "text/csv"), ("xlsx", "spreadsheetml"), ("pdf", "application/pdf")):
        exported = await client.get("/api/v1/rfis/export", params={"project_id": project.id, "format": fmt})
        assert exported.status_code == 200, exported.text
        assert media in exported.headers["content-type"]
    csv = (await client.get("/api/v1/rfis/export", params={"project_id": project.id, "format": "csv"})).content
    assert b"Fire stopping" in csv and b"cost" in csv

    task = await client.post(f"/api/v1/rfis/{rfi['id']}/task", json={"assignee_id": test_user["id"]}, headers=headers)
    assert task.status_code == 201, task.text
    linked = (await client.get("/api/v1/tasks/", params={"project_id": project.id, "entity_type": "rfi"})).json()
    assert linked["data"][0]["entity_id"] == rfi["id"]

    patched = await client.patch(f"/api/v1/rfis/{rfi['id']}", json={"location": "Level 3"}, headers=headers)
    assert patched.json()["location"] == "Level 3"
    users = (await client.get("/api/v1/rfis/users")).json()
    assert test_user["id"] in [u["id"] for u in users]

    assert (await client.delete(f"/api/v1/rfis/{rfi['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/rfis/{rfi['id']}")).status_code == 404


async def test_rfis_need_a_visible_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    await _grant(db_session, test_user["id"], "rfi-only", "rfi.read", "rfi.create")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    assert (await client.get("/api/v1/rfis/", params={"project_id": project.id})).status_code == 404
    made = await client.post("/api/v1/rfis/", json={"project_id": project.id, "subject": "x", "question": "y"}, headers=headers)
    assert made.status_code == 404

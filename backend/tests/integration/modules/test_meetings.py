"""Meetings: series templates, agenda, attendance, actions that become tasks, minutes as PDF, issuing them."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mail import Mail
from src.infrastructure.modules import state
from src.modules.meetings import service as meetings_service
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

MEETINGS = (
    "meetings.read",
    "meetings.create",
    "meetings.update",
    "meetings.delete",
    "meetings.transition",
    "tasks.read",
    "tasks.create",
    "contacts.read",
    "contacts.create",
    "projects.read",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture
def sent(monkeypatch) -> list[Mail]:
    mails: list[Mail] = []

    async def keep(mail: Mail) -> None:
        mails.append(mail)

    monkeypatch.setattr(meetings_service, "deliver", keep)
    return mails


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant")
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _contact(client: AsyncClient, headers: dict, email: str | None = "site@acme.example") -> dict[str, Any]:
    response = await client.post(
        "/api/v1/contacts/", json={"first_name": "Sam", "last_name": "Site", "email": email}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_series_meeting_starts_from_its_template_and_shows_the_previous_one(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *MEETINGS)
    contact = await _contact(client, headers)

    created = await client.post(
        "/api/v1/meetings/series/",
        json={
            "project_id": project.id,
            "name": "Weekly site coordination",
            "cadence": "weekly",
            "location": "Site office",
            "agenda_template": [{"title": "Safety", "duration_minutes": 10}, {"title": "Programme"}],
            "default_attendees": [{"user_id": test_user_2["id"]}, {"contact_id": contact["id"]}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    series = created.json()

    first = (
        await client.post(
            "/api/v1/meetings/",
            json={"project_id": project.id, "series_id": series["id"], "starts_at": "2026-03-02T09:00:00Z"},
            headers=headers,
        )
    ).json()
    assert first["code"] == "MTG-001"
    assert first["title"] == "Weekly site coordination"
    assert first["location"] == "Site office"
    assert [(a["number"], a["title"]) for a in first["agenda"]] == [(1, "Safety"), (2, "Programme")]
    assert {a["name"] for a in first["attendees"]} == {test_user_2["name"], "Sam Site"}

    action = await client.post(
        f"/api/v1/meetings/{first['id']}/actions",
        json={"description": "Issue scaffold permit", "assignee_id": test_user_2["id"], "due_date": "2026-03-06"},
        headers=headers,
    )
    assert action.status_code == 201, action.text
    await client.patch(f"/api/v1/meetings/{first['id']}", json={"minutes": "Good progress."}, headers=headers)

    second = (
        await client.post(
            "/api/v1/meetings/",
            json={"project_id": project.id, "series_id": series["id"], "starts_at": "2026-03-09T09:00:00Z"},
            headers=headers,
        )
    ).json()
    assert second["code"] == "MTG-002"
    previous = (await client.get(f"/api/v1/meetings/{second['id']}/previous")).json()
    assert previous["meeting"]["code"] == "MTG-001"
    assert previous["meeting"]["minutes"] == "Good progress."
    assert [a["description"] for a in previous["open_actions"]] == ["Issue scaffold permit"]

    listed = (await client.get("/api/v1/meetings/", params={"project_id": project.id})).json()
    assert [m["code"] for m in listed["data"]] == ["MTG-002", "MTG-001"]
    assert listed["data"][1]["open_actions"] == 1
    assert (await client.get(f"/api/v1/meetings/series/{series['id']}")).json()["next_date"] == "2026-03-16"

    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert [n["category"] for n in inbox] == ["assignment"]
    assert inbox[0]["link"] == f"/meetings?project={project.id}&meeting={first['id']}"


async def test_agenda_attendance_and_actions_become_tasks(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *MEETINGS)
    contact = await _contact(client, headers)
    meeting = (
        await client.post(
            "/api/v1/meetings/",
            json={"project_id": project.id, "title": "Design review", "starts_at": "2026-04-01T14:00:00Z"},
            headers=headers,
        )
    ).json()
    base = f"/api/v1/meetings/{meeting['id']}"

    a = (await client.post(f"{base}/agenda", json={"title": "Drawings", "duration_minutes": 20}, headers=headers)).json()
    b = (
        await client.post(f"{base}/agenda", json={"title": "Risks", "presenter_contact_id": contact["id"]}, headers=headers)
    ).json()
    assert b["presenter_name"] == "Sam Site"
    order = (await client.put(f"{base}/agenda/order", json={"ids": [b["id"], a["id"]]}, headers=headers)).json()
    assert [(i["number"], i["title"]) for i in order] == [(1, "Risks"), (2, "Drawings")]
    updated = await client.patch(
        f"{base}/agenda/{a['id']}", json={"notes": "Rev C agreed", "decisions": "Issue for construction"}, headers=headers
    )
    assert updated.json()["decisions"] == "Issue for construction"

    me = (await client.post(f"{base}/attendees", json={"user_id": test_user["id"]}, headers=headers)).json()
    them = (await client.post(f"{base}/attendees", json={"contact_id": contact["id"]}, headers=headers)).json()
    duplicate = await client.post(f"{base}/attendees", json={"contact_id": contact["id"]}, headers=headers)
    assert duplicate.status_code == 422
    neither = await client.post(f"{base}/attendees", json={}, headers=headers)
    assert neither.status_code == 422
    marked = await client.patch(f"{base}/attendees/{me['id']}", json={"attended": True}, headers=headers)
    assert marked.json()["attended"] is True

    action = (
        await client.post(
            f"{base}/actions",
            json={"description": "Update drawing register", "assignee_id": test_user_2["id"], "due_date": "2026-04-08"},
            headers=headers,
        )
    ).json()
    converted = await client.post(f"{base}/actions/{action['id']}/task", headers=headers)
    assert converted.status_code == 201, converted.text
    assert converted.json()["task_code"] == "TASK-001"
    again = await client.post(f"{base}/actions/{action['id']}/task", headers=headers)
    assert again.status_code == 422

    task = (await client.get(f"/api/v1/tasks/{converted.json()['task_id']}")).json()
    assert (task["entity_type"], task["entity_id"]) == ("meeting", meeting["id"])
    assert (task["assignee_id"], task["due_date"]) == (test_user_2["id"], "2026-04-08")
    linked = (await client.get(f"{base}/tasks")).json()
    assert [t["code"] for t in linked] == ["TASK-001"]

    minutes = (await client.get(f"{base}/minutes")).json()
    assert [p["name"] for p in minutes["present"]] == [test_user["name"]]
    assert [p["name"] for p in minutes["apologies"]] == ["Sam Site"]
    assert minutes["agenda"][1]["decisions"] == "Issue for construction"
    assert minutes["actions"][0]["task_code"] == "TASK-001"
    assert them["invited"] is True


async def test_minutes_render_as_pdf_and_issue_to_attendees(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, sent: list[Mail]
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *MEETINGS)
    contact = await _contact(client, headers)
    silent = await _contact(client, headers, email=None)
    meeting = (
        await client.post(
            "/api/v1/meetings/",
            json={"project_id": project.id, "title": "Progress meeting", "starts_at": "2026-05-05T08:30:00Z"},
            headers=headers,
        )
    ).json()
    base = f"/api/v1/meetings/{meeting['id']}"
    await client.post(f"{base}/agenda", json={"title": "Programme", "notes": "Two days behind"}, headers=headers)
    await client.post(f"{base}/actions", json={"description": "Recovery plan"}, headers=headers)
    for body in ({"user_id": test_user_2["id"]}, {"contact_id": contact["id"]}, {"contact_id": silent["id"]}):
        await client.post(f"{base}/attendees", json=body, headers=headers)

    pdf = await client.get(f"{base}/minutes.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert "MTG-001-minutes.pdf" in pdf.headers["content-disposition"]

    too_early = await client.post(f"{base}/issue", headers=headers)
    assert too_early.status_code == 422
    held = await client.post(f"{base}/status", json={"status": "held"}, headers=headers)
    assert held.json()["status"] == "held"

    issued = await client.post(f"{base}/issue", headers=headers)
    assert issued.status_code == 200, issued.text
    result = issued.json()
    assert result["meeting"]["status"] == "minutes_issued"
    assert result["meeting"]["issued_at"]
    assert sorted(result["emailed"]) == sorted([test_user_2["email"], "site@acme.example"])
    assert result["no_email"] == ["Sam Site"]
    assert sorted(m.to[0] for m in sent) == sorted(result["emailed"])
    assert sent[0].subject == "Minutes MTG-001: Progress meeting"
    assert sent[0].attachments[0].filename == "MTG-001-minutes.pdf"
    assert sent[0].attachments[0].content.startswith(b"%PDF")

    history = (await client.get(f"{base}/history")).json()
    assert [h["to_status"] for h in history] == ["planned", "held", "minutes_issued"]
    cancelled = await client.post(f"{base}/status", json={"status": "cancelled"}, headers=headers)
    assert cancelled.status_code == 422


async def test_meetings_need_a_visible_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "meetings.read", "meetings.create")

    created = await client.post(
        "/api/v1/meetings/",
        json={"project_id": project.id, "title": "x", "starts_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    assert created.status_code == 404
    assert (await client.get("/api/v1/meetings/", params={"project_id": project.id})).status_code == 404

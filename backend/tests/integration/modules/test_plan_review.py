"""Client plan review: only the client team sees shared plans; per-document decisions; notifications both ways."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.notifications.models import Notification
from src.modules.projects.models import Project, ProjectMember
from src.modules.team.models import Team, TeamMembership
from tests.integration.modules.people import grant, login, make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

STAFF = ("projects.read", "portal.read", "portal.submit", "files.read", "files.upload")
CLIENT = ("portal.read", "portal.review")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def parties(db_session: AsyncSession):
    team = Team(name="Client - Port Authority")
    db_session.add(team)
    await db_session.flush()
    project = Project(code="PR-1", name="Berth 4 refurbishment", client_team_id=team.id)
    db_session.add(project)
    await db_session.commit()
    staff = await make_user(db_session, "Pat Planner")
    client = await make_user(db_session, "Casey Client")
    outsider = await make_user(db_session, "Oscar Outsider")
    db_session.add(TeamMembership(team_id=team.id, user_id=client["id"]))
    # The outsider can read the project (a direct member) but isn't on the client team.
    db_session.add(ProjectMember(project_id=project.id, user_id=outsider["id"], source="manual"))
    await db_session.commit()
    await grant(db_session, staff, *STAFF)
    await grant(db_session, client, *CLIENT)
    await grant(db_session, outsider, *CLIENT)
    return project, staff, client, outsider


async def _upload(client: AsyncClient, headers: dict, project_id: int, name: str) -> int:
    r = await client.post(
        "/api/v1/files/",
        data={"project_id": str(project_id)},
        files={"file": (name, b"%PDF-1.4 " + name.encode(), "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _notified(db: AsyncSession, user: dict) -> list[str]:
    rows = await db.execute(select(Notification.title).where(Notification.user_id == user["id"]).order_by(Notification.id))
    return list(rows.scalars())


async def test_a_shared_plan_reaches_only_the_client_team(client: AsyncClient, db_session: AsyncSession, parties):
    project, staff, customer, outsider = parties
    headers = await login(client, staff)
    itp = await _upload(client, headers, project.id, "ITP-101.pdf")
    plan = await _upload(client, headers, project.id, "Work plan rev A.pdf")
    made = await client.post(
        "/api/v1/portal/reviews/",
        json={
            "project_id": project.id,
            "title": "Berth 4 shutdown plan",
            "kind": "work_plan",
            "due_date": "2026-12-01",
            "documents": [{"file_id": plan}, {"file_id": itp, "title": "ITP 101"}],
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    review = made.json()
    assert (review["code"], review["status"], review["client_team_name"]) == ("PRV-001", "draft", "Client - Port Authority")
    rid = review["id"]

    # a draft is invisible to the client
    await login(client, customer)
    listed = (await client.get("/api/v1/portal/reviews/", params={"project_id": project.id})).json()
    assert listed["data"] == []
    assert (await client.get(f"/api/v1/portal/reviews/{rid}")).status_code == 404

    headers = await login(client, staff)
    shared = await client.post(f"/api/v1/portal/reviews/{rid}/share", json={"note": "Please review by Friday"}, headers=headers)
    assert shared.status_code == 200, shared.text
    assert "PRV-001: Berth 4 shutdown plan shared for your review by 2026-12-01" in await _notified(db_session, customer)
    assert await _notified(db_session, outsider) == []

    # the client sees it; the outsider, who can read the project but isn't on the client team, doesn't
    await login(client, customer)
    queue = (await client.get("/api/v1/portal/reviews/", params={"project_id": project.id, "status": "shared"})).json()
    assert [r["code"] for r in queue["data"]] == ["PRV-001"]
    detail = (await client.get(f"/api/v1/portal/reviews/{rid}")).json()
    assert detail["can_decide"] is True
    assert [d["title"] for d in detail["documents"]] == ["Work plan rev A.pdf", "ITP 101"]
    download = await client.get(f"/api/v1/portal/reviews/{rid}/documents/{detail['documents'][1]['id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 ITP-101.pdf"

    await login(client, outsider)
    assert (await client.get("/api/v1/portal/reviews/", params={"project_id": project.id})).json()["data"] == []
    assert (await client.get(f"/api/v1/portal/reviews/{rid}")).status_code == 404


async def test_the_client_decides_each_document(client: AsyncClient, db_session: AsyncSession, parties):
    project, staff, customer, outsider = parties
    headers = await login(client, staff)
    plan = await _upload(client, headers, project.id, "Method statement.pdf")
    itp = await _upload(client, headers, project.id, "ITP.pdf")
    rid = (
        await client.post(
            "/api/v1/portal/reviews/",
            json={
                "project_id": project.id,
                "title": "Method statement",
                "kind": "method_statement",
                "documents": [{"file_id": plan}, {"file_id": itp}],
            },
            headers=headers,
        )
    ).json()["id"]
    await client.post(f"/api/v1/portal/reviews/{rid}/share", json={}, headers=headers)
    docs = (await client.get(f"/api/v1/portal/reviews/{rid}")).json()["documents"]

    # staff can't decide for the client
    staff_try = await client.post(
        f"/api/v1/portal/reviews/{rid}/documents/{docs[0]['id']}/decision", json={"decision": "approved"}, headers=headers
    )
    assert staff_try.status_code in (403, 404)

    headers_c = await login(client, customer)
    no_reason = await client.post(
        f"/api/v1/portal/reviews/{rid}/documents/{docs[0]['id']}/decision", json={"decision": "rejected"}, headers=headers_c
    )
    assert no_reason.status_code == 422
    commented = await client.post(
        f"/api/v1/portal/reviews/{rid}/comments",
        json={"body": "Lifting plan for the gantry is missing", "document_id": docs[0]["id"]},
        headers=headers_c,
    )
    assert commented.status_code == 200, commented.text
    assert commented.json()["comments"][0]["from_client"] is True
    first = await client.post(
        f"/api/v1/portal/reviews/{rid}/documents/{docs[0]['id']}/decision",
        json={"decision": "approved_with_comments", "comment": "Add the lifting plan"},
        headers=headers_c,
    )
    assert first.json()["status"] == "shared"
    assert first.json()["documents_decided"] == 1
    done = await client.post(
        f"/api/v1/portal/reviews/{rid}/documents/{docs[1]['id']}/decision", json={"decision": "approved"}, headers=headers_c
    )
    body = done.json()
    assert (body["status"], body["outcome"], body["can_decide"]) == ("reviewed", "approved_with_comments", False)

    staff_heard = await _notified(db_session, staff)
    assert "PRV-001: new comment from Casey Client" in staff_heard
    assert "PRV-001: review complete, approved with comments" in staff_heard

    # staff see the status; a staff reply reaches the client
    headers = await login(client, staff)
    seen = (await client.get("/api/v1/portal/reviews/", params={"project_id": project.id})).json()["data"][0]
    assert (seen["status"], seen["outcome"], seen["documents_decided"]) == ("reviewed", "approved_with_comments", 2)
    await client.post(
        f"/api/v1/portal/reviews/{rid}/comments", json={"body": "Lifting plan attached as rev B"}, headers=headers
    )
    assert "PRV-001: new comment from Pat Planner" in await _notified(db_session, customer)

    # a revised document goes back to the client
    rev_b = await _upload(client, headers, project.id, "Method statement rev B.pdf")
    again = await client.post(f"/api/v1/portal/reviews/{rid}/documents", json={"file_id": rev_b}, headers=headers)
    assert (again.json()["status"], again.json()["outcome"]) == ("shared", None)

    history = (await client.get(f"/api/v1/portal/reviews/{rid}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "shared", "reviewed", "shared"]


async def test_sharing_needs_documents_and_the_permission(client: AsyncClient, db_session: AsyncSession, parties):
    project, staff, customer, _ = parties
    headers = await login(client, staff)
    rid = (
        await client.post("/api/v1/portal/reviews/", json={"project_id": project.id, "title": "Empty"}, headers=headers)
    ).json()["id"]
    assert (await client.post(f"/api/v1/portal/reviews/{rid}/share", json={}, headers=headers)).status_code == 422

    headers_c = await login(client, customer)
    assert (
        await client.post("/api/v1/portal/reviews/", json={"project_id": project.id, "title": "Mine"}, headers=headers_c)
    ).status_code == 403

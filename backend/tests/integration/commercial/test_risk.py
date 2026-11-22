"""Risk register: exposure, the probability × impact matrix, status workflow, review reminders, export."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.notifications.models import Notification
from src.modules.projects.models import Project
from src.modules.risk.tasks import send_review_reminders
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

RISK = ("risk.read", "risk.create", "risk.update", "risk.transition", "risk.delete", "risk.export", "projects.read")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession) -> Project:
    project = Project(code="R-P1", name="Refinery", currency="EUR")
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"risk{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def test_exposure_matrix_and_register_totals(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *RISK)

    async def raise_risk(title: str, **kw) -> dict:
        response = await client.post("/api/v1/risks/", json={"project_id": project.id, "title": title, **kw}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    crane = await raise_risk(
        "Crane failure",
        category="safety",
        probability=0.3,
        impact="critical",
        cost_impact="200000",
        schedule_impact_days=20,
        owner_id=test_user_2["id"],
        residual_probability=0.1,
        response="mitigate",
    )
    steel = await raise_risk("Steel price rise", category="financial", probability=0.7, impact="high", cost_impact="50000")
    permit = await raise_risk("Permit delay", category="regulatory", probability=0.5, impact="medium", cost_impact="10000")
    await raise_risk("Rain", category="schedule", probability=0.9, impact="low", cost_impact="1000")

    assert crane["code"] == "R-001" and permit["code"] == "R-003"
    assert crane["exposure"] == "60000.00" and crane["residual_exposure"] == "20000.00"
    assert crane["band"] == "unlikely" and steel["band"] == "likely"
    assert crane["owner_name"] == test_user_2["name"]

    bad = await client.post(
        "/api/v1/risks/", json={"project_id": project.id, "title": "x", "probability": 0.95}, headers=headers
    )
    assert bad.status_code == 422

    matrix = (await client.get("/api/v1/risks/matrix", params={"project_id": project.id})).json()
    assert matrix["currency"] == "EUR"
    assert len(matrix["cells"]) == 5 * 4
    cell = next(c for c in matrix["cells"] if c["band"] == "likely" and c["impact"] == "high")
    assert (cell["count"], cell["exposure"]) == (1, "35000.00")
    assert matrix["total_exposure"] == "100900.00"  # 60000 + 35000 + 5000 + 900
    assert (matrix["open_count"], matrix["high_critical_count"], matrix["total_schedule_days"]) == (4, 2, 20)
    assert [r["code"] for r in matrix["top"]] == ["R-001", "R-002", "R-003", "R-004"]
    assert matrix["by_category"][0] == {"category": "safety", "count": 1, "exposure": "60000.00"}

    # Clicking a cell filters the register by band and impact.
    filtered = (
        await client.get("/api/v1/risks/", params={"project_id": project.id, "band": "unlikely", "impact": "critical"})
    ).json()
    assert [r["id"] for r in filtered["data"]] == [crane["id"]]
    by_exposure = (await client.get("/api/v1/risks/", params={"project_id": project.id, "sort": "exposure"})).json()
    assert [r["code"] for r in by_exposure["data"]][:2] == ["R-001", "R-002"]

    # Closed risks leave the matrix.
    closed = await client.patch(f"/api/v1/risks/{steel['id']}/status", json={"status": "closed"}, headers=headers)
    assert closed.status_code == 200
    matrix = (await client.get("/api/v1/risks/matrix", params={"project_id": project.id})).json()
    assert matrix["total_exposure"] == "65900.00" and matrix["open_count"] == 3 and matrix["count"] == 4

    # The owner heard about it.
    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(n["title"].startswith("R-001") and n["category"] == "assignment" for n in inbox)


async def test_status_workflow_history_update_and_export(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *RISK)
    risk = (
        await client.post("/api/v1/risks/", json={"project_id": project.id, "title": "Ground contamination"}, headers=headers)
    ).json()

    assert (
        await client.patch(f"/api/v1/risks/{risk['id']}/status", json={"status": "assessed"}, headers=headers)
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/risks/{risk['id']}/status", json={"status": "mitigating", "note": "Survey"}, headers=headers
        )
    ).status_code == 200
    refused = await client.patch(f"/api/v1/risks/{risk['id']}/status", json={"status": "identified"}, headers=headers)
    assert refused.status_code == 422

    history = (await client.get(f"/api/v1/risks/{risk['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["identified", "assessed", "mitigating"]
    assert history[-1]["note"] == "Survey"

    updated = await client.patch(
        f"/api/v1/risks/{risk['id']}",
        json={"cost_impact": "1000", "probability": 0.4, "mitigation": "Test pits"},
        headers=headers,
    )
    assert updated.json()["exposure"] == "400.00" and updated.json()["mitigation"] == "Test pits"

    export = await client.get("/api/v1/risks/export", params={"project_id": project.id, "format": "csv"})
    assert export.status_code == 200
    lines = export.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Code,Title") and lines[1].startswith("R-001,Ground contamination")

    assert (await client.delete(f"/api/v1/risks/{risk['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/risks/{risk['id']}")).status_code == 404


async def test_review_reminders_reach_the_owner(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *RISK)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    later = (date.today() + timedelta(days=10)).isoformat()
    for title, when in (("Due", yesterday), ("Not yet", later)):
        await client.post(
            "/api/v1/risks/",
            json={"project_id": project.id, "title": title, "owner_id": test_user_2["id"], "review_date": when},
            headers=headers,
        )

    assert await send_review_reminders(db_session) == 1
    rows = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == test_user_2["id"], Notification.category == "due")
        )
    ).scalars()
    assert [n.title for n in rows] == ["R-001 is overdue for review"]


async def test_other_projects_risks_stay_hidden(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    await _grant(db_session, test_user["id"], "risk-only", "risk.read")
    await _login(client, test_user)
    assert (await client.get("/api/v1/risks/", params={"project_id": project.id})).status_code == 404

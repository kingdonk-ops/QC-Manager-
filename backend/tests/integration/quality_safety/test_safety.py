"""Safety: incidents and risk scores, observations, corrective actions, hours, TRIR/LTIFR and the 5×5 matrix."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = ("projects.read", "safety.read", "safety.create", "safety.update", "safety.delete", "safety.transition")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _setup(client: AsyncClient, db: AsyncSession, user: dict) -> tuple[Project, dict]:
    project = Project(code="S-1", name="Gas plant shutdown")
    db.add(project)
    await db.commit()
    await _grant(db, user["id"], "hse", *PERMS)
    return project, {"X-CSRF-Token": await _login(client, user)}


async def test_rates_risk_matrix_and_indicators(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project, headers = await _setup(client, db_session, test_user)
    pid = project.id

    for month, hours in (("2026-01", 100_000), ("2026-02", 60_000)):
        r = await client.put("/api/v1/safety/hours", json={"project_id": pid, "month": month, "hours": hours}, headers=headers)
        assert r.status_code == 200, r.text
    replaced = await client.put(
        "/api/v1/safety/hours", json={"project_id": pid, "month": "2026-02", "hours": 100_000, "headcount": 55}, headers=headers
    )
    assert replaced.json()["month"] == "2026-02-01"
    hours = (await client.get("/api/v1/safety/hours/", params={"project_id": pid})).json()
    assert [(h["month"], h["hours"]) for h in hours["data"]] == [("2026-02-01", 100_000), ("2026-01-01", 100_000)]

    async def report(**body) -> dict:
        r = await client.post("/api/v1/safety/incidents/", json={"project_id": pid, **body}, headers=headers)
        assert r.status_code == 201, r.text
        return r.json()

    lti = await report(
        title="Hand caught in cladding roller",
        type="injury",
        occurred_at="2026-01-14T09:30:00Z",
        severity=3,
        likelihood=4,
        recordable=True,
        lost_time=True,
        days_lost=3,
        people_involved=["Insulator A"],
    )
    assert (lti["code"], lti["risk_score"], lti["risk_band"], lti["status"]) == ("INC-001", 12, "high", "reported")
    for day in ("03", "17"):
        nm = await report(
            title="Dropped band clip", type="near_miss", occurred_at=f"2026-02-{day}T10:00:00Z", severity=2, likelihood=2
        )
        assert (nm["risk_score"], nm["risk_band"]) == (4, "low")
    mti = await report(
        title="Burn from refractory dry-out",
        type="injury",
        occurred_at="2026-02-20T14:00:00Z",
        severity=5,
        likelihood=3,
        recordable=True,
    )
    assert (mti["risk_score"], mti["risk_band"]) == (15, "extreme")
    bad = await client.post(
        "/api/v1/safety/incidents/",
        json={"project_id": pid, "title": "x", "type": "injury", "occurred_at": "2026-02-01T00:00:00Z", "days_lost": 2},
        headers=headers,
    )
    assert bad.status_code == 422

    rescored = await client.patch(f"/api/v1/safety/incidents/{nm['id']}", json={"likelihood": 3}, headers=headers)
    assert (rescored.json()["risk_score"], rescored.json()["risk_band"]) == (6, "medium")
    await client.patch(f"/api/v1/safety/incidents/{nm['id']}", json={"likelihood": 2}, headers=headers)

    for kind in ("positive", "positive", "positive"):
        o = await client.post(
            "/api/v1/safety/observations/",
            json={
                "project_id": pid,
                "kind": kind,
                "category": "ppe",
                "description": "Full PPE on the rack",
                "observed_at": "2026-02-05T08:00:00Z",
            },
            headers=headers,
        )
        assert o.json()["status"] == "closed"
    negative = (
        await client.post(
            "/api/v1/safety/observations/",
            json={
                "project_id": pid,
                "kind": "negative",
                "category": "working_at_height",
                "description": "Harness not clipped on",
                "observed_at": "2026-02-06T08:00:00Z",
                "severity": 2,
                "likelihood": 3,
            },
            headers=headers,
        )
    ).json()
    assert (negative["code"], negative["status"], negative["risk_score"], negative["risk_band"]) == (
        "OBS-004",
        "open",
        6,
        "medium",
    )
    quick = await client.post(
        "/api/v1/safety/observations/",
        json={"project_id": pid, "kind": "negative", "description": "Trip hazard"},
        headers=headers,
    )
    assert quick.status_code == 201 and quick.json()["observed_at"] and quick.json()["risk_score"] is None
    await client.delete(f"/api/v1/safety/observations/{quick.json()['id']}", headers=headers)

    board = (await client.get(f"/api/v1/safety/dashboard/{pid}")).json()
    assert board["hours_worked"] == 200_000
    assert (board["trir_base"], board["ltifr_base"]) == (200_000, 1_000_000)
    assert board["trir"] == 2.0  # 2 recordables × 200,000 / 200,000 h
    assert board["ltifr"] == 5.0  # 1 lost-time injury × 1,000,000 / 200,000 h
    assert board["near_miss_ratio"] == 1.0  # 2 near misses / 2 recordables
    assert board["by_type"] == {
        "injury": 2,
        "near_miss": 2,
        "property_damage": 0,
        "environmental": 0,
        "dangerous_occurrence": 0,
    }
    assert board["by_band"] == {"low": 2, "medium": 0, "high": 1, "extreme": 1}
    assert board["lagging"] == {
        "incidents": 4,
        "recordables": 2,
        "lost_time_injuries": 1,
        "days_lost": 3,
        "near_misses": 2,
        "trir": 2.0,
        "ltifr": 5.0,
    }
    assert board["leading"]["observations"] == 4
    assert (board["leading"]["positive_observations"], board["leading"]["positive_ratio"]) == (3, 0.75)

    jan, feb = board["monthly"]
    assert (jan["month"], jan["hours"], jan["recordables"], jan["trir"], jan["ltifr"]) == ("2026-01", 100_000, 1, 2.0, 10.0)
    assert (feb["month"], feb["incidents"], feb["near_misses"], feb["observations"], feb["trir"]) == ("2026-02", 3, 2, 4, 2.0)

    matrix = {(c["severity"], c["likelihood"]): c for c in board["risk_matrix"]}
    assert len(matrix) == 25
    assert matrix[(3, 4)]["incidents"] == 1 and matrix[(3, 4)]["band"] == "high"
    assert matrix[(2, 2)]["incidents"] == 2 and matrix[(2, 2)]["band"] == "low"
    assert matrix[(5, 3)]["incidents"] == 1 and matrix[(5, 3)]["band"] == "extreme"
    assert matrix[(2, 3)]["observations"] == 1 and matrix[(2, 3)]["score"] == 6
    assert matrix[(5, 5)]["band"] == "extreme" and matrix[(1, 1)]["band"] == "low"
    assert sum(c["incidents"] for c in board["risk_matrix"]) == 4

    million = (await client.get(f"/api/v1/safety/dashboard/{pid}", params={"base": 1_000_000})).json()
    assert (million["trir"], million["ltifr"], million["trir_base"]) == (10.0, 5.0, 1_000_000)
    assert (await client.get(f"/api/v1/safety/dashboard/{pid}", params={"base": 12345})).status_code == 422

    february = (
        await client.get(f"/api/v1/safety/dashboard/{pid}", params={"date_from": "2026-02-01", "date_to": "2026-02-28"})
    ).json()
    assert (february["hours_worked"], february["lagging"]["recordables"], february["trir"]) == (100_000, 1, 2.0)
    assert february["ltifr"] == 0.0

    everywhere = (await client.get("/api/v1/safety/dashboard")).json()
    assert pid in everywhere["project_ids"] and everywhere["lagging"]["incidents"] == 4

    filtered = (await client.get("/api/v1/safety/incidents/", params={"project_id": pid, "type": "near_miss"})).json()
    assert filtered["total_count"] == 2
    recordable = (await client.get("/api/v1/safety/incidents/", params={"project_id": pid, "recordable": True})).json()
    assert [i["code"] for i in recordable["data"]] == ["INC-004", "INC-001"]
    positives = (await client.get("/api/v1/safety/observations/", params={"project_id": pid, "kind": "positive"})).json()
    assert positives["total_count"] == 3

    pdf = await client.get("/api/v1/safety/summary.pdf", params={"project_id": pid, "month": "2026-02"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await client.get("/api/v1/safety/summary.pdf", params={"project_id": pid, "month": "2026-13"})).status_code == 422


async def test_incident_workflow_with_corrective_actions(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project, headers = await _setup(client, db_session, test_user)
    incident = (
        await client.post(
            "/api/v1/safety/incidents/",
            json={
                "project_id": project.id,
                "title": "Scaffold board slipped",
                "type": "dangerous_occurrence",
                "occurred_at": "2026-03-02T07:45:00Z",
                "severity": 4,
                "likelihood": 2,
            },
            headers=headers,
        )
    ).json()
    iid = incident["id"]
    investigating = await client.patch(
        f"/api/v1/safety/incidents/{iid}/status", json={"status": "investigating"}, headers=headers
    )
    assert investigating.json()["status"] == "investigating"

    action = await client.post(
        "/api/v1/safety/actions/",
        json={
            "parent_type": "incident",
            "parent_id": iid,
            "description": "Re-tag scaffold, toolbox talk on board ties",
            "assignee_id": test_user_2["id"],
            "due_date": "2026-03-09",
        },
        headers=headers,
    )
    assert action.status_code == 201, action.text
    aid = action.json()["id"]
    assert action.json()["parent_code"] == "INC-001"
    current = (await client.get(f"/api/v1/safety/incidents/{iid}")).json()
    assert (current["status"], current["open_actions"]) == ("actions_open", 1)

    blocked = await client.patch(f"/api/v1/safety/incidents/{iid}/status", json={"status": "closed"}, headers=headers)
    assert blocked.status_code == 422
    board = (await client.get(f"/api/v1/safety/dashboard/{project.id}")).json()
    assert (board["open_actions"], board["overdue_actions"]) == (1, 1)

    verified = await client.patch(f"/api/v1/safety/actions/{aid}", json={"status": "verified"}, headers=headers)
    assert verified.json()["verified_by_id"] == test_user["id"] and verified.json()["completed_at"]
    open_list = (await client.get("/api/v1/safety/actions/", params={"project_id": project.id, "open_only": True})).json()
    assert open_list["total_count"] == 0

    closed = await client.patch(
        f"/api/v1/safety/incidents/{iid}/status", json={"status": "closed", "note": "Actions verified"}, headers=headers
    )
    assert closed.json()["status"] == "closed" and closed.json()["closed_at"]
    history = (await client.get(f"/api/v1/safety/incidents/{iid}/history")).json()
    assert [h["to_status"] for h in history] == ["reported", "investigating", "actions_open", "closed"]
    reopen = await client.patch(f"/api/v1/safety/incidents/{iid}/status", json={"status": "reported"}, headers=headers)
    assert reopen.status_code == 422

    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert [n["title"] for n in inbox] == ["INC-001: safety action"]


async def test_safety_respects_project_visibility(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project, headers = await _setup(client, db_session, test_user)
    await client.post(
        "/api/v1/safety/incidents/",
        json={"project_id": project.id, "title": "x", "type": "near_miss", "occurred_at": "2026-03-02T07:45:00Z"},
        headers=headers,
    )
    await _grant(db_session, test_user_2["id"], "outsider", "safety.read")
    await _login(client, test_user_2)
    assert (await client.get(f"/api/v1/safety/dashboard/{project.id}")).status_code == 404
    assert (await client.get("/api/v1/safety/incidents/", params={"project_id": project.id})).status_code == 404
    everywhere = (await client.get("/api/v1/safety/dashboard")).json()
    assert everywhere["project_ids"] == [] and everywhere["lagging"]["incidents"] == 0

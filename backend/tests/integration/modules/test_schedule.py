"""4D Schedule: activities and links recalculating the critical path, progress, baselines, generation,
Monte Carlo, import and export."""

import io
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.cvr.models import CostHead
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

SCHEDULE = (
    "schedule.read",
    "schedule.create",
    "schedule.update",
    "schedule.delete",
    "schedule.import",
    "schedule.export",
    "projects.read",
)
FIXTURES = Path(__file__).parents[2] / "unit" / "modules" / "schedule" / "fixtures"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession, code: str = "S-1") -> Project:
    project = Project(code=code, name="Tower", start_date=date(2026, 1, 5))
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _gantt(client: AsyncClient, project_id: int) -> dict:
    response = await client.get(f"/api/v1/schedule/gantt/{project_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _by_code(gantt: dict) -> dict:
    return {a["code"]: a for a in gantt["activities"]}


async def test_activities_and_links_recalculate_the_critical_path(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, *SCHEDULE)

    async def add(name: str, **kw) -> dict:
        r = await client.post("/api/v1/schedule/activities/", json={"project_id": project.id, "name": name, **kw}, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    phase = await add("Substructure", code="P1")
    dig = await add("Excavate", code="A1", parent_id=phase["id"], duration=5, budget_hours="120")
    pour = await add("Pour", code="A2", parent_id=phase["id"], duration=3, predecessor_id=dig["id"])
    side = await add("Order steel", code="A3", duration=2)
    handover = await add("Handover", code="M1", type="milestone")
    assert (dig["wbs_code"], pour["wbs_code"], side["wbs_code"]) == ("1.1", "1.2", "2")

    link = await client.post(
        "/api/v1/schedule/dependencies/",
        json={"predecessor_id": pour["id"], "successor_id": handover["id"], "type": "FS", "lag": 2},
        headers=h,
    )
    assert link.status_code == 201, link.text
    await client.post(
        "/api/v1/schedule/dependencies/", json={"predecessor_id": side["id"], "successor_id": handover["id"]}, headers=h
    )

    g = _by_code(await _gantt(client, project.id))
    assert (g["A1"]["early_start"], g["A1"]["early_finish"]) == ("2026-01-05", "2026-01-09")
    assert (g["A2"]["early_start"], g["A2"]["early_finish"]) == ("2026-01-12", "2026-01-14")
    assert g["M1"]["early_start"] == "2026-01-19"
    assert g["A1"]["is_critical"] and g["A2"]["is_critical"] and g["M1"]["is_critical"]
    assert not g["A3"]["is_critical"] and g["A3"]["total_float"] == 8
    assert g["M1"]["driving_predecessor_ids"] == [pour["id"]]
    assert g["P1"]["type"] == "summary"
    assert (g["P1"]["planned_start"], g["P1"]["planned_finish"], g["P1"]["duration"]) == ("2026-01-05", "2026-01-14", 8)

    # A loop is refused with the loop named.
    loop = await client.post(
        "/api/v1/schedule/dependencies/", json={"predecessor_id": handover["id"], "successor_id": dig["id"]}, headers=h
    )
    assert loop.status_code == 422
    detail = loop.json()["detail"]
    assert detail["codes"][0] == detail["codes"][-1] and set(detail["codes"]) == {"A1", "A2", "M1"}

    # Dragging a bar sets a start-no-earlier-than; dragging its end changes the duration.
    moved = await client.patch(f"/api/v1/schedule/activities/{side['id']}", json={"planned_start": "2026-01-13"}, headers=h)
    assert moved.json()["constraint_type"] == "snet" and moved.json()["early_start"] == "2026-01-13"
    stretched = await client.patch(
        f"/api/v1/schedule/activities/{side['id']}", json={"planned_finish": "2026-01-20"}, headers=h
    )
    assert stretched.json()["duration"] == 6
    g = _by_code(await _gantt(client, project.id))
    assert g["M1"]["early_start"] == "2026-01-21" and g["A3"]["is_critical"] and not g["A1"]["is_critical"]

    listed = (await client.get("/api/v1/schedule/activities/", params={"project_id": project.id, "critical": True})).json()
    assert {a["code"] for a in listed["data"]} == {"A3", "M1"}
    assert (await client.post(f"/api/v1/schedule/{project.id}/calculate", headers=h)).json()["finish"] == "2026-01-21"

    deleted = await client.delete(f"/api/v1/schedule/dependencies/{link.json()['id']}", headers=h)
    assert deleted.status_code == 200
    assert (await client.delete(f"/api/v1/schedule/activities/{phase['id']}", headers=h)).status_code == 200
    remaining = (await client.get("/api/v1/schedule/activities/", params={"project_id": project.id})).json()
    assert {a["code"] for a in remaining["data"]} == {"A3", "M1"}


async def test_progress_baselines_and_variance(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, *SCHEDULE)
    a = (
        await client.post(
            "/api/v1/schedule/activities/", json={"project_id": project.id, "name": "Frame", "duration": 4}, headers=h
        )
    ).json()
    b = (
        await client.post(
            "/api/v1/schedule/activities/",
            json={"project_id": project.id, "name": "Roof", "duration": 2, "predecessor_id": a["id"]},
            headers=h,
        )
    ).json()

    base = await client.post(f"/api/v1/schedule/{project.id}/baselines", json={"name": "Contract"}, headers=h)
    assert base.status_code == 201 and base.json()[0]["is_current"] and base.json()[0]["finish_date"] == "2026-01-12"

    cal = await client.put(
        f"/api/v1/schedule/{project.id}/calendar", json={"data_date": "2026-01-07", "holidays": ["2026-01-09"]}, headers=h
    )
    assert cal.json()["holidays"] == ["2026-01-09"]

    started = await client.patch(
        f"/api/v1/schedule/activities/{a['id']}",
        json={"actual_start": "2026-01-06", "percent_complete": 25},
        headers=h,
    )
    body = started.json()
    assert body["status"] == "in_progress"
    assert body["early_finish"] == "2026-01-12"  # 3 days left from Wednesday 7th, over the holiday
    g = await _gantt(client, project.id)
    roof = _by_code(g)[b["code"]]
    assert roof["baseline_finish"] == "2026-01-12"
    assert roof["early_finish"] == "2026-01-14" and roof["baseline_variance"] == 2
    assert g["summary"]["baseline_finish"] == "2026-01-12" and g["summary"]["finish_variance"] == 2

    done = await client.patch(f"/api/v1/schedule/activities/{a['id']}", json={"status": "completed"}, headers=h)
    assert done.json()["percent_complete"] == 100 and done.json()["actual_finish"] == "2026-01-07"
    history = (await client.get(f"/api/v1/schedule/activities/{a['id']}/history")).json()
    assert [x["to_status"] for x in history] == ["pending", "in_progress", "completed"]

    second = (await client.post(f"/api/v1/schedule/{project.id}/baselines", json={"name": "Recovery"}, headers=h)).json()
    assert [x["is_current"] for x in second] == [False, True]
    current = await client.post(f"/api/v1/schedule/{project.id}/baselines/{second[0]['id']}/current", headers=h)
    assert [x["is_current"] for x in current.json()] == [True, False]
    assert len((await client.get(f"/api/v1/schedule/{project.id}/baselines")).json()) == 2


async def test_generate_from_sections_and_cvr(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, *SCHEDULE)
    sections = [
        {"code": "01", "name": "Preliminaries", "value": "10000"},
        {"code": "02", "name": "Insulation", "value": "60000"},
        {"code": "03", "name": "Cladding", "value": "30000"},
    ]
    r = await client.post(
        f"/api/v1/schedule/{project.id}/generate", json={"sections": sections, "total_duration": 20}, headers=h
    )
    assert r.status_code == 201, r.text
    acts = r.json()
    assert [(a["code"], a["duration"]) for a in acts] == [("01", 2), ("02", 12), ("03", 6)]
    assert acts[2]["early_finish"] == "2026-01-30" and all(a["is_critical"] for a in acts)
    assert acts[1]["budget_cost"] == "60000.00"

    db_session.add_all(
        [
            CostHead(project_id=project.id, code="C1", description="Labour", budget=3),
            CostHead(project_id=project.id, code="C2", description="Plant", budget=1),
        ]
    )
    await db_session.commit()
    r = await client.post(
        f"/api/v1/schedule/{project.id}/generate", json={"source": "cvr", "total_duration": 8, "replace": True}, headers=h
    )
    assert [(a["code"], a["duration"]) for a in r.json()] == [("C1", 6), ("C2", 2)]


async def test_monte_carlo(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, *SCHEDULE)
    empty = await client.post(f"/api/v1/schedule/{project.id}/monte-carlo", json={}, headers=h)
    assert empty.status_code == 422
    first = (
        await client.post(
            "/api/v1/schedule/activities/",
            json={"project_id": project.id, "name": "Piling", "duration": 10, "pessimistic_duration": 20},
            headers=h,
        )
    ).json()
    await client.post(
        "/api/v1/schedule/activities/",
        json={"project_id": project.id, "name": "Caps", "duration": 5, "predecessor_id": first["id"]},
        headers=h,
    )
    body = {"iterations": 500, "seed": 4}
    r1 = (await client.post(f"/api/v1/schedule/{project.id}/monte-carlo", json=body, headers=h)).json()
    r2 = (await client.post(f"/api/v1/schedule/{project.id}/monte-carlo", json=body, headers=h)).json()
    assert r1 == r2
    assert r1["planned_finish"] == "2026-01-23" and r1["p50"] <= r1["p80"] <= r1["p90"]
    assert r1["probability_on_time"] < 0.5
    assert {c["name"] for c in r1["criticality"]} == {"Piling", "Caps"}
    too_many = await client.post(f"/api/v1/schedule/{project.id}/monte-carlo", json={"iterations": 20001}, headers=h)
    assert too_many.status_code == 422


async def test_import_preview_import_and_export(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, *SCHEDULE)
    xer = {"file": ("demo.xer", (FIXTURES / "demo.xer").read_bytes(), "application/octet-stream")}

    preview = (
        await client.post(f"/api/v1/schedule/{project.id}/import", files=xer, data={"dry_run": "true"}, headers=h)
    ).json()
    assert (preview["format"], preview["activities"], preview["summaries"], preview["dependencies"]) == ("xer", 4, 2, 4)
    assert (await client.get("/api/v1/schedule/activities/", params={"project_id": project.id})).json()["total_count"] == 0

    done = await client.post(f"/api/v1/schedule/{project.id}/import", files=xer, data={"replace": "true"}, headers=h)
    assert done.status_code == 200, done.text
    assert done.json()["created"] == 6
    g = await _gantt(client, project.id)
    acts = _by_code(g)
    assert g["calendar"]["holidays"] == ["2026-01-09"]
    assert acts["A1000"]["status"] == "completed" and acts["A1010"]["status"] == "in_progress"
    assert acts["CIV"]["type"] == "summary" and acts["A1000"]["parent_id"] == acts["CIV"]["id"]
    assert {d["type"] for d in g["dependencies"]} == {"FS", "SS", "FF", "SF"}

    msp = {"file": ("demo.xml", (FIXTURES / "demo_msp.xml").read_bytes(), "application/xml")}
    appended = (await client.post(f"/api/v1/schedule/{project.id}/import", files=msp, headers=h)).json()
    assert appended["format"] == "msp_xml" and appended["created"] == 4
    p6 = {"file": ("p6.xml", (FIXTURES / "demo_p6.xml").read_bytes(), "application/xml")}
    p6_report = (await client.post(f"/api/v1/schedule/{project.id}/import", files=p6, data={"dry_run": "1"}, headers=h)).json()
    assert p6_report["format"] == "p6_xml" and p6_report["activities"] == 3

    bad = {"file": ("x.txt", b"not a schedule", "text/plain")}
    assert (await client.post(f"/api/v1/schedule/{project.id}/import", files=bad, headers=h)).status_code == 422

    xml = await client.get(f"/api/v1/schedule/{project.id}/export", params={"format": "msp_xml"})
    assert xml.status_code == 200 and b"<PredecessorLink>" in xml.content
    sheet = await client.get(f"/api/v1/schedule/{project.id}/export", params={"format": "xlsx"})
    rows = list(load_workbook(io.BytesIO(sheet.content)).active.iter_rows(values_only=True))
    assert rows[0][:3] == ("WBS", "Activity ID", "Name") and len(rows) == 11
    csv = await client.get(f"/api/v1/schedule/{project.id}/export", params={"format": "csv"})
    assert "A1010FS" not in csv.text and "A1000FS" in csv.text


async def test_permissions_and_project_visibility(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    h = await _as(client, db_session, test_user, "schedule.read")
    assert (await client.get(f"/api/v1/schedule/gantt/{project.id}")).status_code == 404  # no projects.read
    denied = await client.post("/api/v1/schedule/activities/", json={"project_id": project.id, "name": "x"}, headers=h)
    assert denied.status_code == 403

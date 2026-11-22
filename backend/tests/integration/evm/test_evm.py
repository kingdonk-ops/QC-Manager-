"""Earned value: packages -> progress -> metrics -> S-curve, import, snapshots, exports."""

import io
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

EVM = ("evm.read", "evm.create", "evm.update", "evm.delete", "evm.import", "evm.export", "projects.read")
BASE = "/api/v1/evm"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _packages(client: AsyncClient, headers: dict, project_id: int) -> dict[str, dict]:
    specs = [
        {
            "code": "A",
            "name": "Piping",
            "control_account": "CA-1",
            "discipline": "Mech",
            "budget_hours": "100",
            "budget_cost": "1000",
        },
        {"code": "B", "name": "Steel", "control_account": "CA-1", "discipline": "Civil", "budget_hours": "100"},
        {
            "code": "C",
            "name": "Cable",
            "control_account": "CA-2",
            "discipline": "Elec",
            "budget_hours": "200",
            "curve": "s_curve",
        },
    ]
    out = {}
    for spec in specs:
        response = await client.post(
            f"{BASE}/work-packages/",
            json={"project_id": project_id, "planned_start": "2026-01-01", "planned_finish": "2026-01-10", **spec},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        out[spec["code"]] = response.json()
    return out


async def test_progress_metrics_and_s_curve(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *EVM)
    wp = await _packages(client, headers, project.id)

    listed = (await client.get(f"{BASE}/work-packages/", params={"project_id": project.id})).json()
    assert listed["total_count"] == 3
    assert [p["code"] for p in listed["data"]] == ["A", "B", "C"]

    # nothing recorded yet: indices are null, not errors
    empty = (await client.get(f"{BASE}/{project.id}/metrics", params={"date": "2026-01-05"})).json()
    assert empty["total"]["ev"] == 0
    assert empty["total"]["cpi"] is None
    assert empty["total"]["eac"] is None
    assert empty["total"]["pv"] == 200  # A and B linear 50 each, C s-curve 50% of 200

    saved = await client.post(
        f"{BASE}/{project.id}/progress",
        json={
            "data_date": "2026-01-05",
            "entries": [
                {"work_package_id": wp["A"]["id"], "percent_complete": "40", "actual_hours": "50", "actual_cost": "450"},
                {"work_package_id": wp["C"]["id"], "earned_hours": "100", "actual_hours": "80", "comment": "Good week"},
            ],
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["saved"] == 2

    settings = (await client.get(f"{BASE}/{project.id}/settings")).json()
    assert settings["data_date"] == "2026-01-05"
    assert settings["cost_available"] is True

    sheet = (await client.get(f"{BASE}/{project.id}/progress", params={"date": "2026-01-06"})).json()
    by_code = {r["code"]: r for r in sheet["rows"]}
    assert float(by_code["C"]["percent_complete"]) == 50
    assert float(by_code["C"]["earned_hours"]) == 100
    assert by_code["C"]["recorded_on"] == "2026-01-05"
    assert by_code["B"]["recorded_on"] is None

    report = (await client.get(f"{BASE}/{project.id}/metrics")).json()  # defaults to the data date
    assert report["data_date"] == "2026-01-05"
    assert report["basis"] == "hours"
    total = report["total"]
    assert (total["bac"], total["pv"], total["ev"], total["ac"]) == (400, 200, 140, 130)
    assert total["spi"] == 0.7
    assert total["cpi"] == round(140 / 130, 4)
    assert total["eac"] == round(400 / (140 / 130), 2)
    assert total["vac"] == round(400 - 400 / (140 / 130), 2)
    assert total["tcpi"] == round(260 / 270, 4)
    b = next(r for r in report["rows"] if r["key"] == "B")
    assert b["cpi"] is None

    accounts = (await client.get(f"{BASE}/{project.id}/metrics", params={"group_by": "account"})).json()["rows"]
    assert [(r["key"], r["ev"]) for r in accounts] == [("CA-1", 40), ("CA-2", 100)]
    disciplines = (await client.get(f"{BASE}/{project.id}/metrics", params={"group_by": "discipline"})).json()["rows"]
    assert {r["key"] for r in disciplines} == {"Civil", "Elec", "Mech"}

    budget_rate = (await client.get(f"{BASE}/{project.id}/metrics", params={"eac_method": "budget_rate"})).json()
    assert budget_rate["total"]["eac"] == 130 + 260

    cost = (await client.get(f"{BASE}/{project.id}/metrics", params={"basis": "cost"})).json()
    assert [r["key"] for r in cost["rows"]] == ["A"]
    assert (cost["total"]["bac"], cost["total"]["ev"], cost["total"]["ac"]) == (1000, 400, 450)

    curve = (await client.get(f"{BASE}/{project.id}/s-curve", params={"interval": "week"})).json()
    points = curve["points"]
    assert points[0]["period_start"] == "2025-12-29"
    assert points[-1]["pv"] == 400
    assert points[1]["ev"] == 140
    assert points[1]["ac"] == 130
    assert points[-1]["ev"] is None
    assert points[-1]["forecast"] == curve["eac"]
    assert curve["baseline_id"] is None
    monthly = (await client.get(f"{BASE}/{project.id}/s-curve")).json()
    # SPI 0.7 stretches the 31-day project to 45 days, so the forecast runs into February
    assert monthly["forecast_finish"] == "2026-02-14"
    assert [p["label"] for p in monthly["points"]] == ["Jan 2026", "Feb 2026"]
    assert monthly["points"][1]["pv"] == 400
    assert monthly["points"][1]["forecast"] == monthly["eac"]

    # a later period: omitted values carry forward
    await client.post(
        f"{BASE}/{project.id}/progress",
        json={"data_date": "2026-01-08", "entries": [{"work_package_id": wp["A"]["id"], "percent_complete": "80"}]},
        headers=headers,
    )
    later = {r["code"]: r for r in (await client.get(f"{BASE}/{project.id}/progress")).json()["rows"]}
    assert float(later["A"]["percent_complete"]) == 80
    assert float(later["A"]["actual_hours"]) == 50

    cashflow = (await client.get(f"{BASE}/{project.id}/cashflow")).json()
    assert cashflow["months"][0]["planned_cost"] == 1000
    assert cashflow["months"][0]["actual_cost"] == 450


async def test_progress_validation(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    other = await _project(db_session, "P-2")
    headers = await _as(client, db_session, test_user, *EVM)
    wp = await _packages(client, headers, project.id)
    foreign = await _packages(client, headers, other.id)

    both = await client.post(
        f"{BASE}/{project.id}/progress",
        json={
            "data_date": "2026-01-05",
            "entries": [{"work_package_id": wp["A"]["id"], "percent_complete": 5, "earned_hours": 5}],
        },
        headers=headers,
    )
    assert both.status_code == 422
    over = await client.post(
        f"{BASE}/{project.id}/progress",
        json={"data_date": "2026-01-05", "entries": [{"work_package_id": wp["A"]["id"], "percent_complete": 101}]},
        headers=headers,
    )
    assert over.status_code == 422
    wrong_project = await client.post(
        f"{BASE}/{project.id}/progress",
        json={"data_date": "2026-01-05", "entries": [{"work_package_id": foreign["A"]["id"], "percent_complete": 5}]},
        headers=headers,
    )
    assert wrong_project.status_code == 422

    duplicate = await client.post(
        f"{BASE}/work-packages/", json={"project_id": project.id, "code": "A", "name": "Again"}, headers=headers
    )
    assert duplicate.status_code == 409
    backwards = await client.patch(
        f"{BASE}/work-packages/{wp['A']['id']}", json={"planned_finish": "2025-12-01"}, headers=headers
    )
    assert backwards.status_code == 422
    patched = await client.patch(
        f"{BASE}/work-packages/{wp['A']['id']}", json={"budget_hours": "120", "schedule_activity_id": 7}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert float(patched.json()["budget_hours"]) == 120
    assert patched.json()["schedule_activity_id"] == 7
    assert (await client.delete(f"{BASE}/work-packages/{wp['B']['id']}", headers=headers)).status_code == 200


async def test_import_from_excel(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *EVM)
    await _packages(client, headers, project.id)

    book = Workbook()
    sheet = book.active
    sheet.append(["Code", "% Complete", "Actual Hours"])
    sheet.append(["A", 25, 30])
    sheet.append(["c", 50, 90])
    sheet.append(["ZZ", 10, 1])
    buffer = io.BytesIO()
    book.save(buffer)
    upload = {"file": ("progress.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    dry = await client.post(
        f"{BASE}/{project.id}/import", files=upload, data={"data_date": "2026-01-05", "dry_run": "true"}, headers=headers
    )
    assert dry.status_code == 200, dry.text
    assert dry.json()["saved"] == 0
    assert dry.json()["issues"] == [{"row": 4, "message": "ZZ: no work package with that code"}]
    assert (await client.get(f"{BASE}/{project.id}/metrics", params={"date": "2026-01-05"})).json()["total"]["ev"] == 0

    done = (
        await client.post(f"{BASE}/{project.id}/import", files=upload, data={"data_date": "2026-01-05"}, headers=headers)
    ).json()
    assert done["saved"] == 2
    total = (await client.get(f"{BASE}/{project.id}/metrics")).json()["total"]
    assert (total["ev"], total["ac"]) == (125, 120)

    exported = await client.get(f"{BASE}/{project.id}/export")
    assert exported.status_code == 200
    rows = list(load_workbook(io.BytesIO(exported.content)).active.iter_rows(values_only=True))
    assert rows[0][:7] == ("code", "name", "control account", "discipline", "BAC", "percent", "actual hours")
    assert rows[1][:2] == ("A", "Piping")
    assert rows[1][5] == 25

    pdf = await client.get(f"{BASE}/{project.id}/report.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


async def test_snapshots_baselines_and_compare(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *EVM)
    wp = await _packages(client, headers, project.id)

    first = await client.post(
        f"{BASE}/{project.id}/snapshots/", json={"name": "Original", "set_as_baseline": True}, headers=headers
    )
    assert first.status_code == 201, first.text
    assert first.json()["budget_hours"] == 400
    assert first.json()["is_baseline"] is True

    await client.patch(f"{BASE}/work-packages/{wp['A']['id']}", json={"budget_hours": "150"}, headers=headers)
    await client.delete(f"{BASE}/work-packages/{wp['B']['id']}", headers=headers)
    await client.post(f"{BASE}/work-packages/", json={"project_id": project.id, "code": "D", "name": "Paint"}, headers=headers)

    compare = (
        await client.get(f"{BASE}/{project.id}/snapshots/{first.json()['id']}/compare", params={"date": "2026-01-05"})
    ).json()
    status = {r["code"]: r["status"] for r in compare["rows"]}
    assert status == {"A": "changed", "C": "same", "D": "added", "B": "removed"}
    assert (compare["snapshot_hours"], compare["current_hours"]) == (400, 350)
    a = next(r for r in compare["rows"] if r["code"] == "A")
    assert (a["delta_hours"], a["snapshot_pv"], a["current_pv"]) == (50, 50, 75)

    curve = (await client.get(f"{BASE}/{project.id}/s-curve", params={"date": "2026-01-05"})).json()
    assert curve["baseline_id"] == first.json()["id"]
    assert curve["points"][-1]["baseline_pv"] == 400
    assert curve["points"][-1]["pv"] == 350

    # re-baseline: the new snapshot takes over
    second = (
        await client.post(f"{BASE}/{project.id}/snapshots/", json={"name": "Rev 1", "set_as_baseline": True}, headers=headers)
    ).json()
    listed = (await client.get(f"{BASE}/{project.id}/snapshots/")).json()["data"]
    assert [(s["name"], s["is_baseline"]) for s in listed] == [("Rev 1", True), ("Original", False)]
    back = await client.patch(
        f"{BASE}/{project.id}/snapshots/{first.json()['id']}", json={"is_baseline": True}, headers=headers
    )
    assert back.json()["is_baseline"] is True
    listed = (await client.get(f"{BASE}/{project.id}/snapshots/")).json()["data"]
    assert [s["is_baseline"] for s in listed] == [False, True]
    assert (await client.delete(f"{BASE}/{project.id}/snapshots/{second['id']}", headers=headers)).status_code == 200


async def test_reading_needs_the_permission_and_the_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "evm.read")
    assert (await client.get(f"{BASE}/{project.id}/metrics")).status_code == 404  # no projects.read: can't see it
    assert (
        await client.post(f"{BASE}/work-packages/", json={"project_id": project.id, "code": "X", "name": "X"}, headers=headers)
    ).status_code == 403


async def test_cashflow_shows_cvr_alongside(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *EVM, "cvr.read", "cvr.edit")
    await _packages(client, headers, project.id)
    put = await client.put(
        f"/api/v1/cvr/projects/{project.id}/cashflow",
        json={"periods": [{"period": "2026-01-15", "planned_cost": "900", "actual_cost": "300"}]},
        headers=headers,
    )
    assert put.status_code == 200, put.text

    cashflow = (await client.get(f"{BASE}/{project.id}/cashflow")).json()
    assert cashflow["cvr_included"] is True
    january = cashflow["months"][0]
    assert january["month"] == "2026-01-01"
    assert (january["planned_cost"], january["cvr_planned_cost"], january["cvr_actual_cost"]) == (1000, 900, 300)

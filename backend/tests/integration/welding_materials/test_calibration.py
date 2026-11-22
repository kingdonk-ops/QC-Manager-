"""Calibration: register, certificates, activation, the hard gate, quarantine, due reminders."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.calibration.models import Equipment
from src.modules.calibration.reporting import equipment_rows, overdue
from src.modules.calibration.service import CalibrationGateError, assert_calibrated, due_reminders
from tests.integration.rbac.test_user_permissions import _login

from .helpers import world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

TODAY = date.today()
API = "/api/v1/calibration"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def test_equipment_goes_into_service_with_a_certificate(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    eq = await w.post(
        f"{API}/equipment/",
        {
            "project_id": w.project.id,
            "name": "Torque wrench 50-250 Nm",
            "equipment_type": "torque_wrench",
            "serial_number": "TW-9",
        },
    )
    assert eq["code"] == "EQ-001" and eq["status"] == "out_of_service" and not eq["usable"]
    refused = await w.client.post(f"{API}/equipment/{eq['id']}/status", json={"status": "in_service"}, headers=w.headers)
    assert refused.status_code == 422 and "certificate" in refused.text

    cert = await w.post(
        f"{API}/equipment/{eq['id']}/certificates",
        {"certificate_number": "C-1", "calibrated_on": (TODAY - timedelta(days=10)).isoformat()},
        expect=201,
    )
    assert cert["expires_on"] == (TODAY - timedelta(days=10) + timedelta(days=365)).isoformat()
    eq = await w.get(f"{API}/equipment/{eq['id']}")
    assert eq["status"] == "in_service" and eq["usable"] and eq["due_on"] == cert["expires_on"]

    second = await w.post(
        f"{API}/equipment/{eq['id']}/certificates",
        {"certificate_number": "C-2", "calibrated_on": TODAY.isoformat()},
        expect=201,
    )
    certs = await w.get(f"{API}/equipment/{eq['id']}/certificates")
    assert [c["is_active"] for c in certs] == [True, False] and certs[0]["id"] == second["id"]
    history = await w.get(f"{API}/equipment/{eq['id']}/history")
    assert [h["to_status"] for h in history] == ["out_of_service", "in_service"]


async def test_the_gate_names_overdue_and_quarantined_equipment(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)

    async def instrument(name: str) -> dict:
        eq = await w.post(f"{API}/equipment/", {"project_id": w.project.id, "name": name, "equipment_type": "dft_meter"})
        await w.post(
            f"{API}/equipment/{eq['id']}/certificates",
            {"certificate_number": f"C-{name}", "calibrated_on": (TODAY - timedelta(days=30)).isoformat()},
        )
        return eq

    good, late, held = await instrument("good"), await instrument("late"), await instrument("held")
    row = await db_session.get(Equipment, late["id"])
    assert row is not None
    row.due_on = TODAY - timedelta(days=1)
    await db_session.commit()
    await w.post(f"{API}/equipment/{held['id']}/status", {"status": "quarantined", "note": "Dropped"})

    listing = await w.get(f"{API}/equipment/", project_id=w.project.id, status="overdue")
    assert [e["code"] for e in listing["data"]] == [late["code"]]
    summary = await w.get(f"{API}/summary", project_id=w.project.id)
    assert (summary["in_service"], summary["overdue"], summary["quarantined"]) == (1, 1, 1)
    assert await overdue(db_session, w.project.id) == 1
    assert len(await equipment_rows(db_session, w.project.id, {})) == 3
    available = await w.get(f"{API}/available", project_id=w.project.id)
    assert [e["id"] for e in available] == [good["id"]]

    check = await w.post(f"{API}/gate", {"equipment_ids": [good["id"], late["id"], held["id"]]}, project_id=w.project.id)
    assert not check["ok"] and len(check["problems"]) == 2
    assert any("expired" in p and late["code"] in p for p in check["problems"])
    assert any("quarantined" in p for p in check["problems"])

    assert [e.id for e in await assert_calibrated(db_session, [good["id"]], TODAY)] == [good["id"]]
    with pytest.raises(CalibrationGateError) as caught:
        await assert_calibrated(db_session, [good["id"], late["id"]], TODAY)
    assert late["code"] in str(caught.value.public_detail)
    # A reading dated before the certificate lapsed still passes.
    await assert_calibrated(db_session, [late["id"]], TODAY - timedelta(days=2))
    with pytest.raises(CalibrationGateError):
        await assert_calibrated(db_session, [good["id"]], TODAY, project_id=w.project.id + 999)


async def test_custodians_are_reminded_once_a_week(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    w = await world(client, db_session, test_user)
    eq = await w.post(
        f"{API}/equipment/",
        {"project_id": w.project.id, "name": "Pressure gauge", "custodian_id": test_user_2["id"], "interval_days": 30},
    )
    await w.post(
        f"{API}/equipment/{eq['id']}/certificates",
        {"certificate_number": "PG-1", "calibrated_on": (TODAY - timedelta(days=25)).isoformat()},
    )
    far = await w.post(f"{API}/equipment/", {"project_id": w.project.id, "name": "Far", "custodian_id": test_user_2["id"]})
    await w.post(f"{API}/equipment/{far['id']}/certificates", {"certificate_number": "F-1", "calibrated_on": TODAY.isoformat()})

    assert (await w.get(f"{API}/equipment/{eq['id']}"))["status"] == "due"
    assert await due_reminders(db_session) == 1
    assert await due_reminders(db_session) == 0
    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(eq["code"] in n["title"] and "due in 5 days" in n["title"] for n in inbox)

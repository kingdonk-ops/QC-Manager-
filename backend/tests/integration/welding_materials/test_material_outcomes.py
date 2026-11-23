"""Materials: pass, fail and conditional outcomes on receipt review and PMI, with automatic material reports."""

from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.ncr.models import Ncr
from tests.integration.rbac.test_user_permissions import _grant

from .helpers import World
from .helpers import world as make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/materials"
TODAY = date.today()
EXTRA = ("inspections.read", "inspections.update", "inspections.delete", "ncr.read")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def w(client: AsyncClient, db_session: AsyncSession, test_user: dict) -> World:
    await _grant(db_session, test_user["id"], "q6-extra", *EXTRA)
    return await make_world(client, db_session, test_user, "MO-1")


async def _criterion(w: World, code: str = "MAT-1") -> dict[str, Any]:
    body = {
        "project_id": w.project.id,
        "code": code,
        "title": "Wall thickness",
        "rule_type": "range",
        "lower_limit": "10",
        "upper_limit": "20",
        "unit": "mm",
        "standards_ref": "ASTM A106",
    }
    return await w.post("/api/v1/inspections/criteria/", body, expect=201)


async def _receipt(w: World, supplier: str = "Mill") -> dict[str, Any]:
    body = {"project_id": w.project.id, "received_on": TODAY.isoformat(), "supplier": supplier}
    return await w.post(f"{API}/receipts/", body)


async def _heat(w: World, number: str, receipt_id: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project_id": w.project.id,
        "heat_number": number,
        "material_grade": "A106 Gr.B",
        "lot_number": f"LOT-{number}",
        "manufacturer": "Steelworks",
    }
    if receipt_id:
        body["receipt_id"] = receipt_id
    return await w.post(f"{API}/heats/", body, expect=201)


async def _report(w: World, report_id: int) -> Ncr:
    found = await w.db.scalar(select(Ncr).where(Ncr.id == report_id).execution_options(populate_existing=True))
    assert found is not None
    return found


async def _reports(w: World, kind: str) -> list[Ncr]:
    stmt = select(Ncr).where(Ncr.project_id == w.project.id).execution_options(populate_existing=True)
    rows = (await w.db.execute(stmt)).scalars()
    return [n for n in rows if (n.source_data or {}).get("source_kind") == kind]


async def test_a_failed_receipt_review_is_rejected_and_raises_a_material_report(w: World):
    crit = await _criterion(w)
    receipt = await _receipt(w)
    heat = await _heat(w, "H-100", receipt["id"])
    await w.post(f"{API}/heats/{heat['id']}/certificates", {"certificate_number": "MTC-100"}, expect=201)

    done = await w.post(
        f"{API}/receipts/{receipt['id']}/status",
        {"outcome": "fail", "criterion_id": crit["id"], "measured_value": "25", "note": "Walls thin"},
    )
    assert (done["status"], done["outcome"], done["conditional"]) == ("rejected", "fail", False)
    assert done["criterion_id"] == crit["id"] and done["measured_value"] == "25" and done["report_id"] is not None

    report = await _report(w, done["report_id"])
    assert (report.severity, report.status, report.source, report.issue_type) == ("major", "open", "supplier", "ncr")
    assert report.source_data["report_kind"] == "material" and report.source_data["source_kind"] == "material_receipt"
    text = report.description or ""
    assert "Raised automatically from material receipt" in text and "Supplier: Mill" in text
    assert "heat H-100" in text and "lot LOT-H-100" in text and "grade A106 Gr.B" in text and "manufacturer Steelworks" in text
    assert "Certificate: type 3.1, number MTC-100, status pending_verification." in text
    assert "MAT-1" in text and "ASTM A106" in text and "inclusive upper bound 20" in text and "Measured value: 25." in text

    # review is allowed only from received
    again = await w.client.post(f"{API}/receipts/{receipt['id']}/status", json={"outcome": "pass"}, headers=w.headers)
    assert again.status_code == 422


async def test_pass_and_conditional_review(w: World):
    passed = await w.post(f"{API}/receipts/{(await _receipt(w))['id']}/status", {"outcome": "pass"})
    assert (passed["status"], passed["outcome"], passed["report_id"]) == ("accepted", "pass", None)

    conditional = await w.post(f"{API}/receipts/{(await _receipt(w))['id']}/status", {"outcome": "conditional"})
    assert (conditional["status"], conditional["conditional"]) == ("accepted", True)
    assert (await _report(w, conditional["report_id"])).severity == "minor"

    critical = await w.post(
        f"{API}/receipts/{(await _receipt(w))['id']}/status", {"outcome": "conditional", "severity": "critical"}
    )
    assert (await _report(w, critical["report_id"])).severity == "critical"
    assert len(await _reports(w, "material_receipt")) == 2


async def test_existing_clients_sending_only_a_status_keep_working(w: World):
    accepted = await w.post(f"{API}/receipts/{(await _receipt(w))['id']}/status", {"status": "accepted"})
    assert accepted["status"] == "accepted" and accepted["report_id"] is None
    rejected = await w.post(f"{API}/receipts/{(await _receipt(w))['id']}/status", {"status": "rejected", "note": "Damaged"})
    assert rejected["status"] == "rejected" and rejected["report_id"] is not None
    assert (await _report(w, rejected["report_id"])).severity == "major"

    reopened = await w.post(f"{API}/receipts/{rejected['id']}/status", {"status": "received"})
    assert (reopened["status"], reopened["outcome"], reopened["report_id"]) == ("received", None, rejected["report_id"])
    assert len(await _reports(w, "material_receipt")) == 1

    fresh = await _receipt(w)
    url = f"{API}/receipts/{fresh['id']}/status"
    clash = await w.client.post(url, json={"status": "accepted", "outcome": "fail"}, headers=w.headers)
    assert clash.status_code == 422
    empty = await w.client.post(url, json={"note": "nothing"}, headers=w.headers)
    assert empty.status_code == 422


async def test_a_failed_pmi_is_rejected_quarantines_the_heat_and_raises_a_report(w: World):
    crit = await _criterion(w, "PMI-1")
    heat = await _heat(w, "H-200")
    body = {
        "tested_on": TODAY.isoformat(),
        "outcome": "fail",
        "criterion_id": crit["id"],
        "measured_value": "25",
        "grade_found": "304",
    }
    made = await w.post(f"{API}/heats/{heat['id']}/pmi", body, expect=201)
    assert (made["result"], made["outcome"], made["conditional"]) == ("rejected", "fail", False)
    assert made["report_id"] is not None and made["criterion_id"] == crit["id"]
    assert (await w.get(f"{API}/heats/{heat['id']}"))["status"] == "quarantined"

    report = await _report(w, made["report_id"])
    assert report.severity == "major" and report.source_data["report_kind"] == "material"
    assert report.source_data["source_kind"] == "pmi_test" and report.source_data["grade_found"] == "304"
    text = report.description or ""
    assert "heat H-200" in text and "lot LOT-H-200" in text and "PMI-1" in text
    assert "inclusive lower bound 10" in text and "Measured value: 25." in text

    # a PMI test is recorded once: there is no route that changes it
    edit = await w.client.patch(f"{API}/heats/{heat['id']}/pmi/{made['id']}", json={}, headers=w.headers)
    assert edit.status_code in (404, 405)


async def test_each_pmi_test_is_judged_and_reported_on_its_own(w: World):
    heat = await _heat(w, "H-300")
    url = f"{API}/heats/{heat['id']}/pmi"
    day = TODAY.isoformat()
    for outcome in ("fail", "pass", "fail"):
        await w.post(url, {"tested_on": day, "outcome": outcome}, expect=201)
    reports = [n for n in await _reports(w, "pmi_test") if n.source_data["heat_id"] == heat["id"]]
    assert len(reports) == 2

    legacy_ok = await w.post(url, {"tested_on": day, "result": "accepted"}, expect=201)
    assert legacy_ok["outcome"] == "pass" and legacy_ok["report_id"] is None
    legacy_bad = await w.post(url, {"tested_on": day, "result": "rejected"}, expect=201)
    assert legacy_bad["report_id"] is not None
    conditional = await w.post(url, {"tested_on": day, "outcome": "conditional"}, expect=201)
    assert (conditional["result"], conditional["conditional"]) == ("accepted", True)
    assert (await _report(w, conditional["report_id"])).severity == "minor"

    mismatch = await w.client.post(
        f"{API}/heats/{heat['id']}/pmi",
        json={"tested_on": TODAY.isoformat(), "result": "accepted", "outcome": "fail"},
        headers=w.headers,
    )
    assert mismatch.status_code == 422


async def test_a_criterion_held_by_a_pmi_test_cannot_be_deleted(w: World):
    crit = await _criterion(w, "HOLD-1")
    heat = await _heat(w, "H-400")
    await w.post(
        f"{API}/heats/{heat['id']}/pmi",
        {"tested_on": TODAY.isoformat(), "outcome": "pass", "criterion_id": crit["id"]},
        expect=201,
    )
    refused = await w.client.delete(f"/api/v1/inspections/criteria/{crit['id']}", headers=w.headers)
    assert refused.status_code == 409 and "1 PMI tests" in refused.text
    frozen = await w.client.patch(f"/api/v1/inspections/criteria/{crit['id']}", json={"upper_limit": "30"}, headers=w.headers)
    assert frozen.status_code == 409

    missing = await w.client.post(
        f"{API}/heats/{heat['id']}/pmi",
        json={"tested_on": TODAY.isoformat(), "outcome": "pass", "criterion_id": 999999},
        headers=w.headers,
    )
    assert missing.status_code == 404

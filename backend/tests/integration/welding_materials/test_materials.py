"""Materials: receipts, heats, certificate verification, issue to work, traceability both ways, quarantine, warnings."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.asset_tree.service import subtree_ids
from src.modules.calibration.models import Equipment
from src.modules.materials.reporting import heat_rows, uncertified
from src.modules.materials.service import certificates_for

from .helpers import World, world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/materials"
TODAY = date.today()


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _heat(w: World, number: str, **extra) -> dict:
    return await w.post(
        f"{API}/heats/", {"project_id": w.project.id, "heat_number": number, "material_grade": "A106 Gr.B", **extra}, expect=201
    )


async def test_traceability_both_ways_and_the_mdr_appendix(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    receipt = await w.post(
        f"{API}/receipts/", {"project_id": w.project.id, "received_on": TODAY.isoformat(), "supplier": "Mill"}
    )
    assert receipt["code"] == "MRIR-001"
    h1 = await _heat(w, "H-100", receipt_id=receipt["id"], quantity="12", uom="m")
    h2 = await _heat(w, "H-200", receipt_id=receipt["id"], product_form="flange")
    assert h1["status"] == "available" and h1["received_on"] == TODAY.isoformat() and h1["certificate_status"] == "none"

    cert = await w.post(
        f"{API}/heats/{h1['id']}/certificates", {"certificate_number": "MTC-1", "chemistry": {"C": 0.21}}, expect=201
    )
    assert cert["status"] == "pending_verification"
    no_file = await w.client.post(f"{API}/certificates/{cert['id']}/verify", json={"status": "verified"}, headers=w.headers)
    assert no_file.status_code == 422 and "Attach" in no_file.text
    with_file = await w.post(
        f"{API}/heats/{h2['id']}/certificates", {"certificate_number": "MTC-2", "file_id": await w.file()}, expect=201
    )
    verified = await w.post(f"{API}/certificates/{with_file['id']}/verify", {"status": "verified"})
    assert verified["status"] == "verified" and verified["verified_by_id"]
    rejected = await w.client.post(f"{API}/certificates/{cert['id']}/verify", json={"status": "rejected"}, headers=w.headers)
    assert rejected.status_code == 422  # needs a reason

    pipe = await w.post(
        "/api/v1/asset-tree/items/",
        {"project_id": w.project.id, "node_id": w.rsw["id"], "item_type_key": "pipe_spool", "tag": "SP-1"},
    )
    to_item = await w.post(
        f"{API}/issues/", {"project_id": w.project.id, "heat_id": h1["id"], "item_id": pipe["id"], "quantity": "5"}
    )
    assert to_item["node_id"] == w.rsw["id"] and to_item["item_tag"] == "SP-1"
    to_node = await w.post(f"{API}/issues/", {"project_id": w.project.id, "heat_id": h2["id"], "node_id": w.rsw["id"]})
    assert to_node["node_id"] == w.rsw["id"]
    too_much = await w.client.post(
        f"{API}/issues/",
        json={"project_id": w.project.id, "heat_id": h1["id"], "item_id": pipe["id"], "quantity": "8"},
        headers=w.headers,
    )
    assert too_much.status_code == 422 and "left to issue" in too_much.text
    no_anchor = await w.client.post(
        f"{API}/issues/", json={"project_id": w.project.id, "heat_id": h1["id"], "node_id": w.asset["id"]}, headers=w.headers
    )
    assert no_anchor.status_code == 422

    item_trace = await w.get(f"{API}/trace/items/{pipe['id']}")
    assert [t["heat"]["heat_number"] for t in item_trace["heats"]] == ["H-100", "H-200"]
    assert item_trace["heats"][0]["certificates"][0]["certificate_number"] == "MTC-1"
    node_trace = await w.get(f"{API}/trace/nodes/{w.asset['id']}")
    assert {t["heat"]["heat_number"] for t in node_trace["heats"]} == {"H-100", "H-200"}
    used = await w.get(f"{API}/trace/heats/{h1['id']}")
    assert [(i["node_path"], i["item_tag"]) for i in used["issues"]] == [("S / 101 / 101.1", "SP-1")]
    assert (await w.get(f"{API}/heats/{h1['id']}"))["issued_quantity"] == "5.0000"

    assert await uncertified(db_session, w.project.id) == 1
    assert [r["certificate_status"] for r in await heat_rows(db_session, w.project.id, {})] == [
        "pending_verification",
        "verified",
    ]
    rows = await certificates_for(db_session, await subtree_ids(db_session, w.site["id"]))
    assert [(r["heat_number"], r["certificate_number"], r["node_ids"]) for r in rows] == [
        ("H-100", "MTC-1", [w.rsw["id"]]),
        ("H-200", "MTC-2", [w.rsw["id"]]),
    ]
    strict = await w.get(f"{API}/appendix", project_id=w.project.id, verified_only="true")
    assert [r["certificate_number"] for r in strict] == ["MTC-2"]
    assert await certificates_for(db_session, [w.site["id"]]) == []  # node ids are taken as given


async def test_quarantine_pmi_and_release(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    heat = await _heat(w, "H-300", received_on=TODAY.isoformat(), material_grade="A182 F316L")
    hold = await w.post(f"{API}/heats/{heat['id']}/holds", {"reason": "Damaged bevels"}, expect=201)
    assert hold["code"] == "HOLD-001"
    assert (await w.get(f"{API}/heats/{heat['id']}"))["status"] == "quarantined"
    blocked = await w.client.post(
        f"{API}/issues/", json={"project_id": w.project.id, "heat_id": heat["id"], "node_id": w.rsw["id"]}, headers=w.headers
    )
    assert blocked.status_code == 422 and "quarantined" in blocked.text
    await w.post(f"{API}/holds/{hold['id']}/close", {"status": "released", "disposition": "Re-bevelled"})
    assert (await w.get(f"{API}/heats/{heat['id']}"))["status"] == "available"
    await w.post(f"{API}/issues/", {"project_id": w.project.id, "heat_id": heat["id"], "node_id": w.rsw["id"]})

    cal = "/api/v1/calibration"
    gun = await w.post(f"{cal}/equipment/", {"project_id": w.project.id, "name": "XRF", "equipment_type": "pmi_analyser"})
    await w.post(f"{cal}/equipment/{gun['id']}/certificates", {"certificate_number": "X1", "calibrated_on": TODAY.isoformat()})
    row = await db_session.get(Equipment, gun["id"])
    assert row is not None
    row.due_on = TODAY - timedelta(days=3)
    await db_session.commit()
    gate = await w.client.post(
        f"{API}/heats/{heat['id']}/pmi",
        json={"tested_on": TODAY.isoformat(), "result": "accepted", "equipment_id": gun["id"]},
        headers=w.headers,
    )
    assert gate.status_code == 422 and "Calibration gate" in gate.text

    await w.post(
        f"{API}/heats/{heat['id']}/pmi",
        {"tested_on": TODAY.isoformat(), "result": "rejected", "grade_found": "304"},
        expect=201,
    )
    detail = await w.get(f"{API}/heats/{heat['id']}")
    assert detail["status"] == "quarantined" and detail["open_holds"] == 1 and "PMI rejected" in detail["holds"][-1]["reason"]
    await w.post(f"{API}/holds/{detail['holds'][-1]['id']}/close", {"status": "rejected", "disposition": "Scrap"})
    assert (await w.get(f"{API}/heats/{heat['id']}"))["status"] == "rejected"
    holds = await w.get(f"{API}/holds/", project_id=w.project.id, status="open")
    assert holds["total_count"] == 0


async def test_client_supplied_material_late_for_its_work_anchor(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    w = await world(client, db_session, test_user)  # the RSW starts on 2030-01-10
    late = await _heat(w, "C-1", supplied_by="client", expected_delivery="2030-02-01", planned_node_id=w.rsw["id"])
    await _heat(w, "C-2", supplied_by="client", expected_delivery="2030-01-05", planned_node_id=w.rsw["id"])
    await _heat(w, "C-3", supplied_by="client", planned_node_id=w.rsw["id"])
    assert late["status"] == "expected"
    wrong = await w.client.post(
        f"{API}/heats/",
        json={"project_id": w.project.id, "heat_number": "C-9", "material_grade": "X", "planned_node_id": w.asset["id"]},
        headers=w.headers,
    )
    assert wrong.status_code == 422

    warnings = await w.get(f"{API}/warnings", project_id=w.project.id, node_id=w.site["id"])
    assert sorted(x["heat_number"] for x in warnings) == ["C-1", "C-3"]
    assert all(x["kind"] == "client_material_late" and x["node_id"] == w.rsw["id"] for x in warnings)
    expected = await w.client.post(
        f"{API}/issues/", json={"project_id": w.project.id, "heat_id": late["id"], "node_id": w.rsw["id"]}, headers=w.headers
    )
    assert expected.status_code == 422  # not received yet

    await w.post(f"{API}/heats/{late['id']}/receive", {"received_on": TODAY.isoformat()})
    assert [x["heat_number"] for x in await w.get(f"{API}/warnings", project_id=w.project.id)] == ["C-3"]


async def test_a_weld_on_uncertified_material_is_not_accepted(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    api = "/api/v1/welding"
    wps = await w.post(f"{api}/wps/", {"project_id": w.project.id, "code": "WPS-1", "process": "SMAW"}, expect=201)
    await w.post(f"{api}/wps/{wps['id']}/status", {"status": "approved"})
    welder = await w.post(f"{api}/welders/", {"project_id": w.project.id, "stamp": "W9", "name": "Nine"}, expect=201)
    await w.post(
        f"{api}/welders/{welder['id']}/qualifications",
        {"process": "SMAW", "qualified_on": (TODAY - timedelta(days=10)).isoformat()},
    )
    weld = await w.post(
        f"{api}/welds/",
        {
            "project_id": w.project.id,
            "node_id": w.rsw["id"],
            "weld_number": "FW-1",
            "wps_id": wps["id"],
            "weld_category": "category_d",
        },
        expect=201,
    )
    await w.post(f"{api}/welds/{weld['id']}/weld", {"welded_on": TODAY.isoformat(), "passes": [{"welder_id": welder["id"]}]})
    await w.post(f"{api}/welds/{weld['id']}/visual", {"result": "accepted"})
    heat = await _heat(w, "H-9", received_on=TODAY.isoformat())
    await w.post(f"{API}/issues/", {"project_id": w.project.id, "heat_id": heat["id"], "item_id": weld["item_id"]})

    refused = await w.post(f"{api}/welds/{weld['id']}/accept", {}, expect=422)
    assert "H-9" in refused["detail"]
    cert = await w.post(
        f"{API}/heats/{heat['id']}/certificates", {"certificate_number": "M9", "file_id": await w.file("m9.pdf")}
    )
    await w.post(f"{API}/certificates/{cert['id']}/verify", {"status": "verified"})
    assert (await w.post(f"{api}/welds/{weld['id']}/accept", {}))["status"] == "accepted"

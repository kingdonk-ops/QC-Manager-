"""Welding & NDE: qualification blocking, sampling, progressive examination, repairs, acceptance, rates, bolted joints."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.calibration.models import Equipment
from src.modules.welding.reporting import repair_rate, weld_rows

from .helpers import World, world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/welding"
TODAY = date.today()
D = (TODAY - timedelta(days=5)).isoformat()


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _setup(w: World) -> dict:
    """An approved GTAW WPS and welders: W1 qualified, W2 expired, W3 lapsed continuity, W4 qualified."""
    pid = w.project.id
    wps = await w.post(
        f"{API}/wps/",
        {"project_id": pid, "code": "WPS-01", "process": "GTAW", "base_material_group": "P1", "thickness_max": "20"},
        expect=201,
    )
    welders = {}
    for stamp, qualified, expires, last in [
        ("W1", TODAY - timedelta(days=100), None, None),
        ("W2", TODAY - timedelta(days=800), TODAY - timedelta(days=30), TODAY - timedelta(days=40)),
        ("W3", TODAY - timedelta(days=400), None, None),
        ("W4", TODAY - timedelta(days=50), TODAY + timedelta(days=300), None),
    ]:
        welder = await w.post(f"{API}/welders/", {"project_id": pid, "stamp": stamp, "name": f"Welder {stamp}"}, expect=201)
        await w.post(
            f"{API}/welders/{welder['id']}/qualifications",
            {
                "process": "GTAW",
                "qualified_on": qualified.isoformat(),
                "expires_on": expires.isoformat() if expires else None,
                "material_groups": ["P1"],
            },
            expect=201,
        )
        if last:
            await w.post(
                f"{API}/welders/{welder['id']}/continuity", {"process": "GTAW", "welded_on": last.isoformat()}, expect=201
            )
        welders[stamp] = welder
    return {"wps": wps, **welders}


async def _weld(w: World, number: str, wps_id: int, **extra) -> dict:
    return await w.post(
        f"{API}/welds/",
        {
            "project_id": w.project.id,
            "node_id": w.rsw["id"],
            "weld_number": number,
            "drawing_ref": "ISO-1",
            "wps_id": wps_id,
            **extra,
        },
        expect=201,
    )


async def _weld_by(w: World, weld: dict, *welder_ids: int, expect: int = 200) -> dict:
    passes = [{"welder_id": i, "pass_name": "root" if n == 0 else "cap"} for n, i in enumerate(welder_ids)]
    return await w.post(f"{API}/welds/{weld['id']}/weld", {"welded_on": D, "passes": passes}, expect=expect)


async def test_unqualified_welders_and_unapproved_wps_are_blocked(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    w = await world(client, db_session, test_user)
    s = await _setup(w)
    weld = await _weld(w, "W-001", s["wps"]["id"], thickness="8")
    assert weld["status"] == "fit_up" and weld["nde_required"] == {"rt": 5.0}

    draft = await _weld_by(w, weld, s["W1"]["id"], expect=422)
    assert "not approved" in draft["detail"]
    await w.post(f"{API}/wps/{s['wps']['id']}/status", {"status": "approved"})

    expired = await _weld_by(w, weld, s["W1"]["id"], s["W2"]["id"], expect=422)
    assert "W2" in expired["detail"] and "expired" in expired["detail"]
    lapsed = await _weld_by(w, weld, s["W3"]["id"], expect=422)
    assert "W3" in lapsed["detail"] and "continuity lapsed" in lapsed["detail"]
    thick = await _weld(w, "W-002", s["wps"]["id"], thickness="25")
    assert "outside" in (await _weld_by(w, thick, s["W1"]["id"], expect=422))["detail"]

    done = await _weld_by(w, weld, s["W1"]["id"], s["W4"]["id"])
    assert done["status"] == "welded" and done["welders"] == ["W1", "W4"]
    assert [p["welder_stamp"] for p in done["passes"]] == ["W1", "W4"]
    w1 = await w.get(f"{API}/welders/{s['W1']['id']}")
    assert w1["continuity"][0]["welded_on"] == D and w1["qualifications"][0]["continuity_last_on"] == D

    matrix = await w.get(f"{API}/qualification-matrix", project_id=w.project.id)
    states = {r["stamp"]: r["cells"]["GTAW"]["state"] for r in matrix["rows"]}
    assert states == {"W1": "valid", "W2": "expired", "W3": "lapsed", "W4": "valid"}

    # A suspended qualification blocks too.
    await w.patch(f"{API}/qualifications/{w1['qualifications'][0]['id']}", {"status": "suspended"})
    other = await _weld(w, "W-003", s["wps"]["id"])
    assert "suspended" in (await _weld_by(w, other, s["W1"]["id"], expect=422))["detail"]


async def test_sampling_and_progressive_examination(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    s = await _setup(w)
    await w.post(f"{API}/wps/{s['wps']['id']}/status", {"status": "approved"})
    put = await w.client.put(f"{API}/settings/{w.project.id}", json={"nde_rates": {"normal": {"rt": 10}}}, headers=w.headers)
    assert put.status_code == 200, put.text
    welds = []
    for n in range(10):
        weld = await _weld(w, f"A-{n:02d}", s["wps"]["id"])
        welds.append(await _weld_by(w, weld, s["W1"]["id"]))
    other = await _weld_by(w, await _weld(w, "B-01", s["wps"]["id"]), s["W4"]["id"])

    sampling = await w.get(f"{API}/sampling", project_id=w.project.id, method="rt")
    lots = {lot["stamp"]: lot for lot in sampling["lots"]}
    assert (lots["W1"]["welds"], lots["W1"]["required"], lots["W1"]["shortfall"]) == (10, 1, 1)
    assert lots["W4"]["required"] == 1
    assert sampling["proposed_weld_ids"] == [welds[0]["id"], other["id"]]

    req = await w.post(
        f"{API}/nde-requests/", {"project_id": w.project.id, "method": "rt", "weld_ids": [welds[0]["id"]]}, expect=201
    )
    assert req["code"] == "NDE-001" and req["total"] == 1
    again = await w.get(f"{API}/sampling", project_id=w.project.id, method="rt")
    assert again["proposed_weld_ids"] == [other["id"]]
    detail = await w.get(f"{API}/nde-requests/{req['id']}")
    first = detail["results"][0]
    assert (await w.get(f"{API}/welds/{welds[0]['id']}"))["status"] == "nde_pending"

    # Rejected sample: two more of W1's welds (tier 1).
    out = await w.post(f"{API}/nde-results/{first['id']}", {"result": "rejected", "examined_on": D, "report_ref": "RT-1"})
    assert out["weld_status"] == "rejected" and len(out["added"]) == 2
    assert {a["tier"] for a in out["added"]} == {1} and {a["reason"] for a in out["added"]} == {"progressive"}
    # One of those rejects: two more (tier 2).
    out2 = await w.post(f"{API}/nde-results/{out['added'][0]['id']}", {"result": "rejected", "examined_on": D})
    assert len(out2["added"]) == 2 and {a["tier"] for a in out2["added"]} == {2}
    await w.post(f"{API}/nde-results/{out['added'][1]['id']}", {"result": "accepted", "examined_on": D})
    # A tier-2 rejection: every remaining weld of W1 (10 - 1 - 2 - 2 = 5).
    out3 = await w.post(f"{API}/nde-results/{out2['added'][0]['id']}", {"result": "rejected", "examined_on": D})
    assert len(out3["added"]) == 5 and {a["tier"] for a in out3["added"]} == {3} and "100 %" in out3["message"]

    pending = await w.get(f"{API}/nde-results/", project_id=w.project.id, result="pending", unrequested=True)
    assert pending["total_count"] == 6  # one tier-2 weld and five tier-3 welds
    batch = await w.post(f"{API}/nde-requests/", {"project_id": w.project.id, "method": "rt"}, expect=201)
    assert batch["total"] == 6 and batch["pending"] == 6
    refused = await w.client.post(f"{API}/nde-requests/{batch['id']}/status", json={"status": "completed"}, headers=w.headers)
    assert refused.status_code == 422

    rates = await w.get(f"{API}/repair-rates", project_id=w.project.id)
    by = {r["label"].split()[0]: r for r in rates["by_welder"]}
    assert (by["W1"]["examined"], by["W1"]["rejected"], by["W1"]["rate"]) == (4, 3, 75.0)
    assert rates["by_method"][0]["key"] == "rt" and rates["overall"]["rejected"] == 3
    assert await repair_rate(db_session, w.project.id) == 75.0
    assert len(await weld_rows(db_session, w.project.id, {})) == 11


async def test_repairs_escalate_to_cut_out_and_acceptance_rules(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    w = await world(client, db_session, test_user)
    s = await _setup(w)
    await w.post(f"{API}/wps/{s['wps']['id']}/status", {"status": "approved"})
    weld = await _weld(w, "R-001", s["wps"]["id"], weld_category="high_pressure", pwht_required=True)
    weld = await _weld_by(w, weld, s["W1"]["id"])
    assert weld["status"] == "nde_pending"  # 100 % RT added at once
    full = weld["nde"][0]
    assert (full["reason"], full["method"]) == ("full", "rt")

    out = await w.post(f"{API}/nde-results/{full['id']}", {"result": "rejected", "examined_on": D, "defect": "LOF"})
    assert out["added"] == []  # a 100 % examination is not a sample: no progressive
    r1 = await w.post(f"{API}/welds/{weld['id']}/repairs", {"repaired_on": D, "welder_ids": [s["W1"]["id"]], "defect": "LOF"})
    assert r1["repair_label"] == "R1" and r1["status"] == "nde_pending"
    re1 = [r for r in r1["nde"] if r["repair_seq"] == 1]
    assert len(re1) == 1 and re1[0]["reason"] == "repair"
    await w.post(f"{API}/nde-results/{re1[0]['id']}", {"result": "rejected", "examined_on": D})

    expired = await w.post(f"{API}/welds/{weld['id']}/repairs", {"repaired_on": D, "welder_ids": [s["W2"]["id"]]}, expect=422)
    assert "W2" in expired["detail"]
    r2 = await w.post(f"{API}/welds/{weld['id']}/repairs", {"repaired_on": D, "welder_ids": [s["W4"]["id"]]})
    assert r2["repair_label"] == "R2" and [p["welder_stamp"] for p in r2["passes"] if p["repair_seq"] == 2] == ["W4"]
    re2 = [r for r in r2["nde"] if r["repair_seq"] == 2][0]
    last = await w.post(f"{API}/nde-results/{re2['id']}", {"result": "rejected", "examined_on": D})
    assert "cut it out" in last["message"]
    limit = await w.post(f"{API}/welds/{weld['id']}/repairs", {"repaired_on": D, "welder_ids": [s["W1"]["id"]]}, expect=422)
    assert "cut it out" in limit["detail"]
    cut = await w.post(f"{API}/welds/{weld['id']}/cut-out", {"note": "Two repairs failed"})
    assert cut["status"] == "cut_out"

    # The replacement weld: accepted only with visual, PWHT and the 100 % RT accepted.
    new = await _weld(
        w, "R-001A", s["wps"]["id"], weld_category="high_pressure", pwht_required=True, replaces_weld_id=weld["id"]
    )
    new = await _weld_by(w, new, s["W4"]["id"])
    early = await w.post(f"{API}/welds/{new['id']}/accept", {}, expect=422)
    assert "visual" in early["detail"] and "PWHT" in early["detail"] and "nde pending" in early["detail"]
    await w.post(f"{API}/welds/{new['id']}/visual", {"result": "accepted"})
    await w.post(f"{API}/welds/{new['id']}/pwht", {"done_on": TODAY.isoformat()})
    await w.post(f"{API}/nde-results/{new['nde'][0]['id']}", {"result": "accepted", "examined_on": D})
    accepted = await w.post(f"{API}/welds/{new['id']}/accept", {})
    assert accepted["status"] == "accepted"
    history = await w.get(f"{API}/welds/{weld['id']}/history")
    assert history[-1]["to_status"] == "cut_out"
    maps = await w.get(f"{API}/drawings", project_id=w.project.id)
    assert maps == [{"drawing_ref": "ISO-1", "welds": 2, "accepted": 1, "rejected": 0, "open": 0}]


async def test_bolted_joint_breakout_and_make_up_with_calibrated_tools(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    w = await world(client, db_session, test_user)
    cal = "/api/v1/calibration"
    wrench = await w.post(
        f"{cal}/equipment/", {"project_id": w.project.id, "name": "Wrench", "equipment_type": "torque_wrench"}
    )
    await w.post(f"{cal}/equipment/{wrench['id']}/certificates", {"certificate_number": "TW", "calibrated_on": D})
    old = await w.post(
        f"{cal}/equipment/", {"project_id": w.project.id, "name": "Old wrench", "equipment_type": "torque_wrench"}
    )
    await w.post(f"{cal}/equipment/{old['id']}/certificates", {"certificate_number": "OW", "calibrated_on": D})
    row = await db_session.get(Equipment, old["id"])
    assert row is not None
    row.due_on = TODAY - timedelta(days=1)
    await db_session.commit()

    joint = await w.post(
        f"{API}/joints/",
        {
            "project_id": w.project.id,
            "node_id": w.rsw["id"],
            "joint_ref": "FJ-01",
            "size": "6in",
            "rating": "300#",
            "target_value": "400",
            "unit": "Nm",
            "status": "made_up",
        },
        expect=201,
    )
    ev = f"{API}/joints/{joint['id']}/events"
    early = await w.post(
        ev, {"kind": "make_up", "performed_on": D, "equipment_ids": [wrench["id"]], "applied_value": "400"}, expect=422
    )
    assert "breakout" in early["detail"]
    broken = await w.post(ev, {"kind": "breakout", "performed_on": D, "reason": "Valve change"}, expect=201)
    assert broken["status"] == "broken_out"

    gate = await w.post(
        ev,
        {"kind": "make_up", "performed_on": TODAY.isoformat(), "equipment_ids": [old["id"]], "applied_value": "400"},
        expect=422,
    )
    assert "Calibration gate" in gate["detail"] and old["code"] in gate["detail"]
    off = await w.post(
        ev,
        {"kind": "make_up", "performed_on": TODAY.isoformat(), "equipment_ids": [wrench["id"]], "applied_value": "300"},
        expect=422,
    )
    assert "re-tighten" in off["detail"]
    made = await w.post(
        ev,
        {
            "kind": "make_up",
            "performed_on": TODAY.isoformat(),
            "equipment_ids": [wrench["id"]],
            "applied_value": "410",
            "pass_values": ["120", "280", "410"],
            "gasket_replaced": True,
        },
        expect=201,
    )
    assert made["status"] == "made_up" and made["breakouts"] == 1 and len(made["events"]) == 2
    assert made["events"][-1]["equipment_ids"] == [wrench["id"]]

    listing = await w.get(f"{API}/joints/", project_id=w.project.id)
    assert listing["data"][0]["node_path"] == "S / 101 / 101.1"

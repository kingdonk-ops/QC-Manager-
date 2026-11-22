"""Plan → daily plan → log → sign-off: hours per work anchor, earned quantities, delay codes, events, plan vs actual."""

from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient

from src.infrastructure.modules import events

from .conftest import Site
from .test_planner import make_crew, make_pack, make_plan

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

D1, D2 = date(2026, 11, 24), date(2026, 11, 25)


async def planned_day(client: AsyncClient, site: Site) -> tuple[dict, dict, dict]:
    crew = await make_crew(client, site)
    plan = await make_plan(client, site)
    n = site.nodes
    await make_pack(
        client,
        site,
        plan,
        [
            {"node_id": n["rsw1"]["id"], "planned_qty": "40", "uom": "m2", "planned_hours": "60"},
            {"node_id": n["rsw3"]["id"], "planned_qty": "10", "planned_hours": "20"},
        ],
        crew_id=crew["id"],
    )
    for anchor in ("rsw1", "rsw3"):
        r = await client.post(
            "/api/v1/planner/assignments",
            json={"plan_id": plan["id"], "crew_id": crew["id"], "anchor_id": n[anchor]["id"], "work_date": str(D1)},
            headers=site.headers,
        )
        assert r.status_code == 200, r.text
    return crew, plan, n


async def new_log(client: AsyncClient, site: Site, crew: dict, day: date = D1, **extra: Any) -> dict:
    r = await client.post(
        "/api/v1/workface-log/logs/",
        json={"project_id": site.project.id, "crew_id": crew["id"], "work_date": str(day), **extra},
        headers=site.headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_plan_to_log_to_hours_per_work_anchor(client: AsyncClient, site: Site):
    crew, plan, n = await planned_day(client, site)
    log = await new_log(client, site, crew)
    assert log["code"] == "DWL-001" and log["status"] == "draft"
    # Prefilled from the crew and the planner's daily plan.
    assert [h["person"] for h in log["hours"]] == ["J. Miller", "K. Thorne"]
    assert all(h["anchor_id"] == n["rsw1"]["id"] for h in log["hours"])
    assert sorted(q["anchor_id"] for q in log["quantities"]) == sorted([n["rsw1"]["id"], n["rsw3"]["id"]])
    assert log["quantities"][0]["uom"] == "m2"

    saved = await client.put(
        f"/api/v1/workface-log/logs/{log['id']}",
        json={
            "weather": "Fine, gusty",
            "temp_max_c": "32",
            "wind_kmh": "28",
            "rain_mm": "0",
            "hours": [
                {"person": "J. Miller", "trade": "Rigger", "hours": "8.5", "node_id": n["rsw1"]["id"]},
                {"person": "J. Miller", "trade": "Rigger", "hours": "1.5", "delay_code": "weather", "node_id": n["rsw1"]["id"]},
                {"person": "K. Thorne", "trade": "Welder", "hours": "6", "node_id": n["rsw3"]["id"]},
                {"person": "K. Thorne", "trade": "Welder", "hours": "4", "delay_code": "permit"},
                {"person": "Both", "hours": "1", "overhead_code": "toolbox"},
            ],
            "quantities": [{"node_id": n["rsw1"]["id"], "qty": "14"}, {"node_id": n["rsw3"]["id"], "qty": "4.2"}],
            "delays": [
                {"code": "weather", "hours": "1.5", "node_id": n["rsw1"]["id"], "description": "High wind, crane stood down"}
            ],
            "equipment": [{"equipment": "CR-08 100t crane", "hours": "8.5"}],
        },
        headers=site.headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    totals = body["totals"]
    assert float(totals["productive_hours"]) == 14.5
    assert float(totals["delay_hours"]) == 5.5
    assert float(totals["overhead_hours"]) == 1
    assert float(totals["total_hours"]) == 21
    assert totals["headcount"] == 3
    assert {k: float(v) for k, v in totals["by_delay_code"].items()} == {"weather": 1.5, "permit": 4}
    by_anchor = {r["anchor_id"]: (float(r["hours"]), float(r["qty"])) for r in totals["by_anchor"]}
    assert by_anchor == {n["rsw1"]["id"]: (8.5, 14), n["rsw3"]["id"]: (6, 4.2)}
    assert [h["category"] for h in body["hours"]] == ["productive", "delay", "productive", "delay", "overhead"]

    # Not signed yet: nothing rolls up and nothing is earned.
    assert (await client.get("/api/v1/workface-log/rollup", params={"project_id": site.project.id})).json() == []
    unsigned = (
        await client.get("/api/v1/workface-log/rollup", params={"project_id": site.project.id, "signed_only": False})
    ).json()
    assert len(unsigned) == 2

    received: list[dict] = []

    async def capture(event: str, payload: dict) -> None:
        received.append(payload)

    events.subscribe("workface_log.day.signed")(capture)
    try:
        submitted = await client.post(f"/api/v1/workface-log/logs/{log['id']}/submit", json={}, headers=site.headers)
        assert submitted.status_code == 200, submitted.text
        locked = await client.put(f"/api/v1/workface-log/logs/{log['id']}", json={"notes": "late"}, headers=site.headers)
        assert locked.status_code == 422
        signed = await client.post(
            f"/api/v1/workface-log/logs/{log['id']}/sign", json={"note": "Checked"}, headers=site.headers
        )
        assert signed.status_code == 200, signed.text
        assert signed.json()["status"] == "signed" and signed.json()["signed_by_id"] == site.user["id"]
    finally:
        events._handlers.remove(("workface_log.day.signed", capture))

    assert received == [
        {
            "project_id": site.project.id,
            "log_id": log["id"],
            "code": "DWL-001",
            "crew_id": crew["id"],
            "work_date": str(D1),
            "shift": "day",
            "hours_by_anchor": {str(n["rsw1"]["id"]): 8.5, str(n["rsw3"]["id"]): 6.0},
            "qty_by_node": {str(n["rsw1"]["id"]): 14.0, str(n["rsw3"]["id"]): 4.2},
            "delay_hours_by_code": {"weather": 1.5, "permit": 4.0},
            "overhead_hours_by_code": {"toolbox": 1.0},
            "total_hours": 21.0,
            "signed_by_id": site.user["id"],
        }
    ]

    # Earned quantity moved on the nodes, once.
    rsw1 = (await client.get(f"/api/v1/asset-tree/nodes/{n['rsw1']['id']}")).json()
    assert float(rsw1["earned_qty"]) == 14
    again = await client.post(f"/api/v1/workface-log/logs/{log['id']}/sign", json={}, headers=site.headers)
    assert again.status_code == 422

    rollup = (await client.get("/api/v1/workface-log/rollup", params={"project_id": site.project.id})).json()
    assert {r["anchor_code"]: (float(r["hours"]), float(r["qty"])) for r in rollup} == {
        "101 / 101.1": (8.5, 14),
        "102 / 102.1": (6, 4.2),
    }

    # Plan vs actual on the planner reads the signed log through the actuals registry.
    pva = (await client.get(f"/api/v1/planner/plans/{plan['id']}/plan-vs-actual")).json()
    rows = {r["anchor_id"]: r for r in pva["rows"]}
    assert float(rows[n["rsw1"]["id"]]["planned_hours"]) == 60
    assert float(rows[n["rsw1"]["id"]]["actual_hours"]) == 8.5
    assert float(rows[n["rsw1"]["id"]]["actual_qty"]) == 14
    assert rows[n["rsw1"]["id"]]["percent_qty"] == 35.0
    assert float(rows[n["rsw1"]["id"]]["earned_qty"]) == 14
    assert rows[n["rsw1"]["id"]]["assigned_days"] == 1
    assert float(pva["actual_hours"]) == 14.5

    history = (await client.get(f"/api/v1/workface-log/logs/{log['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "submitted", "signed"]


async def test_hours_need_a_work_anchor_unless_coded(client: AsyncClient, site: Site):
    crew = await make_crew(client, site)
    log = await new_log(client, site, crew, prefill=False)
    n = site.nodes
    url = f"/api/v1/workface-log/logs/{log['id']}"
    nowhere = await client.put(url, json={"hours": [{"person": "J. Miller", "hours": "8"}]}, headers=site.headers)
    assert nowhere.status_code == 422
    assert "work anchor" in nowhere.text and "J. Miller" in nowhere.text
    too_high = await client.put(
        url, json={"hours": [{"person": "J. Miller", "hours": "8", "node_id": n["asset"]["id"]}]}, headers=site.headers
    )
    assert too_high.status_code == 422
    assert "work anchor" in too_high.text
    both = await client.put(
        url,
        json={"hours": [{"person": "J. Miller", "hours": "8", "delay_code": "weather", "overhead_code": "toolbox"}]},
        headers=site.headers,
    )
    assert both.status_code == 422
    coded = await client.put(
        url, json={"hours": [{"person": "J. Miller", "hours": "8", "delay_code": "client_hold"}]}, headers=site.headers
    )
    assert coded.status_code == 200
    assert coded.json()["hours"][0]["anchor_id"] is None
    # A quantity on a node above the work anchor has nowhere to earn.
    qty = await client.put(url, json={"quantities": [{"node_id": n["area"]["id"], "qty": "3"}]}, headers=site.headers)
    assert qty.status_code == 422


async def test_empty_log_cant_be_submitted_and_can_be_returned(client: AsyncClient, site: Site):
    crew = await make_crew(client, site)
    log = await new_log(client, site, crew)
    empty = await client.post(f"/api/v1/workface-log/logs/{log['id']}/submit", json={}, headers=site.headers)
    assert empty.status_code == 422
    await client.put(
        f"/api/v1/workface-log/logs/{log['id']}",
        json={"hours": [{"person": "J. Miller", "hours": "10", "overhead_code": "induction"}]},
        headers=site.headers,
    )
    await client.post(f"/api/v1/workface-log/logs/{log['id']}/submit", json={}, headers=site.headers)
    back = await client.post(
        f"/api/v1/workface-log/logs/{log['id']}/return", json={"note": "Add the crane hours"}, headers=site.headers
    )
    assert back.json()["status"] == "draft"
    dup = await client.post(
        "/api/v1/workface-log/logs/",
        json={"project_id": site.project.id, "crew_id": crew["id"], "work_date": str(D1)},
        headers=site.headers,
    )
    assert dup.status_code == 409
    night = await new_log(client, site, crew, shift="night")
    assert night["shift"] == "night"


async def test_copy_yesterday_and_over_budget_warning(client: AsyncClient, site: Site):
    crew = await make_crew(client, site)
    n = site.nodes
    first = await new_log(client, site, crew, prefill=False)
    await client.put(
        f"/api/v1/workface-log/logs/{first['id']}",
        json={
            "hours": [{"person": "J. Miller", "hours": "10", "node_id": n["rsw2"]["id"]}],
            "equipment": [{"equipment": "EWP-3", "hours": "6", "status": "standby"}],
        },
        headers=site.headers,
    )
    second = await new_log(client, site, crew, day=D2, prefill=False)
    copied = await client.post(f"/api/v1/workface-log/logs/{second['id']}/copy-previous", headers=site.headers)
    assert copied.status_code == 200, copied.text
    assert [(h["person"], float(h["hours"]), h["anchor_id"]) for h in copied.json()["hours"]] == [
        ("J. Miller", 10, n["rsw2"]["id"])
    ]
    assert copied.json()["equipment"][0]["equipment"] == "EWP-3"
    nothing_before = await client.post(f"/api/v1/workface-log/logs/{first['id']}/copy-previous", headers=site.headers)
    assert nothing_before.status_code == 422

    over = await client.put(
        f"/api/v1/workface-log/logs/{second['id']}",
        json={"quantities": [{"node_id": n["rsw2"]["id"], "qty": "25"}]},
        headers=site.headers,
    )
    assert any("exceeds the budget of 20" in w for w in over.json()["warnings"])


async def test_day_summary(client: AsyncClient, site: Site):
    crew, _plan, n = await planned_day(client, site)
    idle = await make_crew(client, site, code="P-01")
    log = await new_log(client, site, crew, prefill=False)
    await client.put(
        f"/api/v1/workface-log/logs/{log['id']}",
        json={"hours": [{"person": "J. Miller", "hours": "9", "node_id": n["rsw1"]["id"]}]},
        headers=site.headers,
    )
    summary = (
        await client.get("/api/v1/workface-log/day-summary", params={"project_id": site.project.id, "work_date": str(D1)})
    ).json()
    assert [c["crew_code"] for c in summary["crews"]] == ["R-04"]  # P-01 neither planned nor logged
    assert summary["crews"][0]["planned_anchors"] == 2 and summary["crews"][0]["status"] == "draft"
    assert float(summary["totals"]["productive_hours"]) == 9
    assert idle["id"]
    listed = (
        await client.get("/api/v1/workface-log/logs/", params={"project_id": site.project.id, "work_date": str(D1)})
    ).json()
    assert listed["total_count"] == 1 and float(listed["data"][0]["total_hours"]) == 9
    codes = (await client.get("/api/v1/workface-log/codes")).json()
    assert "weather" in codes["delay_codes"] and "toolbox" in codes["overhead_codes"]

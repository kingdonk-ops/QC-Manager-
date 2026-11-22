"""Work plans as work_plan collections, packs against work anchors, readiness, the board and the daily plan."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.infrastructure.modules.models import ModuleSetting
from src.modules.notifications.models import Notification
from src.modules.planner import readiness
from src.modules.planner.readiness import Finding, ReadinessContext, readiness_providers, register_readiness
from src.modules.schedule.models import Activity

from .conftest import Site

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

D1, D2, D3 = date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25)


async def make_crew(client: AsyncClient, site: Site, code: str = "R-04", **extra) -> dict:
    r = await client.post(
        "/api/v1/planner/crews/",
        json={
            "project_id": site.project.id,
            "code": code,
            "name": "Rigging",
            "trade": "Rigger",
            "supervisor_id": site.other["id"],
            "members": [{"name": "J. Miller", "trade": "Rigger"}, {"name": "K. Thorne", "trade": "Welder"}],
            **extra,
        },
        headers=site.headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_plan(client: AsyncClient, site: Site, **extra) -> dict:
    r = await client.post(
        "/api/v1/planner/plans/",
        json={
            "project_id": site.project.id,
            "title": "Two-week look-ahead",
            "window_start": str(D1),
            "window_end": "2026-12-06",
        }
        | extra,
        headers=site.headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_pack(client: AsyncClient, site: Site, plan: dict, lines: list[dict], **extra) -> dict:
    r = await client.post(
        "/api/v1/planner/packs/",
        json={"plan_id": plan["id"], "title": "Blast and paint", "lines": lines, **extra},
        headers=site.headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_plan_is_a_work_plan_collection_of_its_packs_anchors(client: AsyncClient, site: Site):
    plan = await make_plan(client, site, kind="shutdown", client_ref="SHUT-0001")
    assert plan["code"] == "WP-001"
    n = site.nodes
    pack = await make_pack(
        client,
        site,
        plan,
        [
            {"node_id": n["rsw1"]["id"], "planned_qty": "40", "uom": "m2", "planned_hours": "80"},
            {"node_id": n["rsw3"]["id"], "planned_qty": "10", "planned_hours": "24", "activity_code": "CP"},
        ],
    )
    assert pack["code"] == "JC-001"
    assert [line["anchor_id"] for line in pack["lines"]] == [n["rsw1"]["id"], n["rsw3"]["id"]]
    assert pack["lines"][0]["anchor_path"] == "KAR / A1 / 101 / 101.1"
    assert float(pack["planned_hours"]) == 104
    # defaults to the plan's window
    assert pack["planned_start"] == str(D1)

    collection = (
        await client.get("/api/v1/asset-tree/collections/", params={"project_id": site.project.id, "kind": "work_plan"})
    ).json()["data"]
    assert collection[0]["code"] == "WP-001"
    assert sorted(collection[0]["node_ids"]) == sorted([n["rsw1"]["id"], n["rsw3"]["id"]])

    listed = (await client.get("/api/v1/planner/plans/", params={"project_id": site.project.id})).json()["data"][0]
    assert listed["pack_count"] == 1 and listed["anchor_count"] == 2 and float(listed["planned_hours"]) == 104


async def test_plan_milestones_are_stored(client: AsyncClient, site: Site):
    plan = await make_plan(client, site, milestones=[{"name": "Tier 1 handover", "day": "2026-12-01"}])
    assert plan["milestones"][0]["day"] == "2026-12-01"
    moved = await client.patch(
        f"/api/v1/planner/plans/{plan['id']}",
        json={"milestones": [{"name": "Tier 1 handover", "day": "2026-12-02"}]},
        headers=site.headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["milestones"][0]["day"] == "2026-12-02"


async def test_lines_need_a_work_anchor(client: AsyncClient, site: Site):
    plan = await make_plan(client, site)
    above = await client.post(
        "/api/v1/planner/packs/",
        json={"plan_id": plan["id"], "title": "Too high", "lines": [{"node_id": site.nodes["asset"]["id"]}]},
        headers=site.headers,
    )
    assert above.status_code == 422
    assert "work anchor" in above.text
    nothing = await client.post(
        "/api/v1/planner/packs/", json={"plan_id": plan["id"], "title": "Nothing", "lines": [{}]}, headers=site.headers
    )
    assert nothing.status_code == 422


async def test_readiness_prerequisites_constraints_and_quantities(client: AsyncClient, site: Site):
    plan = await make_plan(client, site)
    n = site.nodes
    pack = await make_pack(client, site, plan, [{"node_id": n["rsw2"]["id"], "planned_qty": "25", "uom": "m2"}])
    assert pack["readiness"] == "warning"
    assert any(f["source"] == "quantities" and "20" in f["message"] for f in pack["findings"])

    pre = await client.post(
        f"/api/v1/planner/packs/{pack['id']}/prerequisites",
        json={"kind": "scaffold", "description": "Scaffold green-tagged at 101.2"},
        headers=site.headers,
    )
    assert pre.status_code == 201, pre.text
    con = await client.post(
        "/api/v1/planner/constraints/",
        json={
            "project_id": site.project.id,
            "category": "materials",
            "description": "Coating kit not delivered",
            "node_id": n["rsw2"]["id"],
            "owner_id": site.other["id"],
            "due_date": "2026-11-20",
        },
        headers=site.headers,
    )
    assert con.status_code == 201, con.text
    assert con.json()["anchor_id"] == n["rsw2"]["id"] and con.json()["code"] == "CON-001"

    got = (await client.get(f"/api/v1/planner/packs/{pack['id']}")).json()
    assert got["readiness"] == "blocked"
    sources = {f["source"] for f in got["findings"]}
    assert {"prerequisites", "constraints", "quantities"} <= sources

    refused = await client.post(
        f"/api/v1/planner/packs/{pack['id']}/transition", json={"status": "ready"}, headers=site.headers
    )
    assert refused.status_code == 422
    assert "Scaffold" in refused.text

    await client.patch(f"/api/v1/planner/prerequisites/{pre.json()['id']}", json={"status": "cleared"}, headers=site.headers)
    await client.patch(
        f"/api/v1/planner/constraints/{con.json()['id']}",
        json={"status": "resolved", "resolution": "Delivered to laydown"},
        headers=site.headers,
    )
    ready = await client.post(f"/api/v1/planner/packs/{pack['id']}/transition", json={"status": "ready"}, headers=site.headers)
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready" and ready.json()["readiness"] == "warning"
    history = (await client.get(f"/api/v1/planner/packs/{pack['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["planned", "ready"]


async def test_forcing_past_blockers_is_recorded(client: AsyncClient, site: Site):
    plan = await make_plan(client, site)
    pack = await make_pack(client, site, plan, [{"node_id": site.nodes["rsw1"]["id"]}])
    await client.post(
        f"/api/v1/planner/packs/{pack['id']}/prerequisites",
        json={"kind": "permit", "description": "Hot work permit"},
        headers=site.headers,
    )
    forced = await client.post(
        f"/api/v1/planner/packs/{pack['id']}/transition", json={"status": "ready", "force": True}, headers=site.headers
    )
    assert forced.status_code == 200
    history = (await client.get(f"/api/v1/planner/packs/{pack['id']}/history")).json()
    assert "forced past" in history[-1]["note"]


async def test_other_modules_plug_into_readiness(client: AsyncClient, site: Site):
    async def materials(db, ctx: ReadinessContext) -> list[Finding]:
        return [Finding("materials", "materials", "warning", f"{len(ctx.anchor_ids)} anchor(s) short of paint")]

    register_readiness("test.materials", "planner", materials)
    try:
        plan = await make_plan(client, site)
        pack = await make_pack(client, site, plan, [{"node_id": site.nodes["rsw1"]["id"]}])
        assert pack["findings"] == [
            {
                "source": "materials",
                "kind": "materials",
                "severity": "warning",
                "message": "1 anchor(s) short of paint",
                "anchor_id": None,
            }
        ]
        assert ("test.materials", "planner") in readiness_providers()
    finally:
        readiness._readiness.pop("test.materials", None)


async def test_programme_link_is_checked_only_while_schedule_is_on(client: AsyncClient, site: Site, db_session: AsyncSession):
    activity = Activity(
        project_id=site.project.id,
        code="A100",
        wbs_code="1.1",
        name="CV01 / CP / 101.1",
        planned_start=D2,
        planned_finish=D3,
    )
    db_session.add(activity)
    await db_session.commit()
    plan = await make_plan(client, site, schedule_activity_ids=[activity.id])
    bad = await client.post(
        "/api/v1/planner/plans/",
        json={
            "project_id": site.project.id,
            "title": "x",
            "window_start": str(D1),
            "window_end": str(D3),
            "schedule_activity_ids": [999999],
        },
        headers=site.headers,
    )
    assert bad.status_code == 422
    pack = await make_pack(
        client, site, plan, [{"node_id": site.nodes["rsw1"]["id"]}], schedule_activity_id=activity.id, planned_end=str(D3)
    )
    assert any(f["source"] == "programme" and "before programme activity A100" in f["message"] for f in pack["findings"])

    db_session.add(ModuleSetting(name="schedule", enabled=False))
    await db_session.commit()
    state.invalidate()
    plain = await client.post(
        "/api/v1/planner/plans/",
        json={
            "project_id": site.project.id,
            "title": "x",
            "window_start": str(D1),
            "window_end": str(D3),
            "schedule_activity_ids": [999999],
        },
        headers=site.headers,
    )
    assert plain.status_code == 201
    again = (await client.get(f"/api/v1/planner/packs/{pack['id']}")).json()
    assert not any(f["source"] == "programme" for f in again["findings"])


async def test_board_assignments_and_daily_plan(client: AsyncClient, site: Site, db_session: AsyncSession):
    crew = await make_crew(client, site)
    plan = await make_plan(client, site)
    n = site.nodes
    pack = await make_pack(
        client,
        site,
        plan,
        [{"node_id": n["rsw1"]["id"], "planned_hours": "40"}, {"node_id": n["rsw3"]["id"]}],
        crew_id=crew["id"],
    )
    cell = await client.post(
        "/api/v1/planner/assignments",
        json={
            "plan_id": plan["id"],
            "crew_id": crew["id"],
            "anchor_id": n["rsw1"]["id"],
            "work_date": str(D2),
            "planned_hours": "16",
        },
        headers=site.headers,
    )
    assert cell.status_code == 200, cell.text
    assert cell.json()["pack_id"] == pack["id"] and cell.json()["warnings"] == []

    off_plan = await client.post(
        "/api/v1/planner/assignments",
        json={"plan_id": plan["id"], "crew_id": crew["id"], "anchor_id": n["rsw2"]["id"], "work_date": str(D2)},
        headers=site.headers,
    )
    assert off_plan.status_code == 422
    outside = await client.post(
        "/api/v1/planner/assignments",
        json={"plan_id": plan["id"], "crew_id": crew["id"], "anchor_id": n["rsw1"]["id"], "work_date": "2027-01-10"},
        headers=site.headers,
    )
    assert outside.status_code == 422

    board = (await client.get(f"/api/v1/planner/plans/{plan['id']}/board")).json()
    assert len(board["days"]) == 14
    assert [r["anchor_id"] for r in board["rows"]] == [n["rsw1"]["id"], n["rsw3"]["id"]]
    assert board["rows"][0]["pack_codes"] == [pack["code"]]
    assert [a["crew_code"] for a in board["assignments"]] == ["R-04"]
    assert board["crews"][0]["headcount"] == 2

    # The same crew booked on another plan that day: a warning on the cell and on the pack.
    other = await make_plan(client, site, title="Break-in", kind="break_in", window_start=str(D2), window_end=str(D2))
    await make_pack(client, site, other, [{"node_id": n["rsw2"]["id"]}])
    clash = await client.post(
        "/api/v1/planner/assignments",
        json={"plan_id": other["id"], "crew_id": crew["id"], "anchor_id": n["rsw2"]["id"], "work_date": str(D2)},
        headers=site.headers,
    )
    assert "WP-001" in clash.json()["warnings"][0]
    findings = (await client.get(f"/api/v1/planner/packs/{pack['id']}")).json()["findings"]
    assert any(f["source"] == "crew" and "WP-002" in f["message"] for f in findings)

    daily = (
        await client.get(
            "/api/v1/planner/daily-plan", params={"project_id": site.project.id, "work_date": str(D2), "crew_id": crew["id"]}
        )
    ).json()
    assert sorted(a["anchor_code"] for a in daily) == ["101 / 101.1", "101 / 101.2"]

    issued = await client.post(
        f"/api/v1/planner/plans/{plan['id']}/transition", json={"status": "issued"}, headers=site.headers
    )
    assert issued.status_code == 200 and issued.json()["issued_at"]
    told = (
        (await db_session.execute(select(Notification.title).where(Notification.user_id == site.other["id"]))).scalars().all()
    )
    assert any("WP-001 issued" in t for t in told)

    removed = await client.delete(f"/api/v1/planner/assignments/{cell.json()['id']}", headers=site.headers)
    assert removed.status_code == 200


async def test_issuing_needs_scope_and_cancelled_plans_can_be_deleted(client: AsyncClient, site: Site):
    plan = await make_plan(client, site)
    empty = await client.post(f"/api/v1/planner/plans/{plan['id']}/transition", json={"status": "issued"}, headers=site.headers)
    assert empty.status_code == 422
    skip = await client.post(f"/api/v1/planner/plans/{plan['id']}/transition", json={"status": "closed"}, headers=site.headers)
    assert skip.status_code == 422
    await client.post(f"/api/v1/planner/plans/{plan['id']}/transition", json={"status": "cancelled"}, headers=site.headers)
    gone = await client.delete(f"/api/v1/planner/plans/{plan['id']}", headers=site.headers)
    assert gone.status_code == 200
    collections = (
        await client.get("/api/v1/asset-tree/collections/", params={"project_id": site.project.id, "kind": "work_plan"})
    ).json()["data"]
    assert collections == []


async def test_work_pack_pdf(client: AsyncClient, site: Site):
    crew = await make_crew(client, site)
    plan = await make_plan(client, site)
    pack = await make_pack(
        client, site, plan, [{"node_id": site.nodes["rsw1"]["id"], "planned_qty": "10", "uom": "m2"}], crew_id=crew["id"]
    )
    r = await client.get(f"/api/v1/planner/packs/{pack['id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert (await client.get(f"/api/v1/planner/packs/{pack['id']}")).json()["issued_at"]

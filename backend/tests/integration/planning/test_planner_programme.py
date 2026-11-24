"""Planner "Add from programme": packs per RSW or per P6 activity from the mirrored programme."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.schedule.models import Activity, P6Link

from .conftest import Site
from .test_planner import make_plan

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def mirror(
    db: AsyncSession,
    site: Site,
    code: str,
    name: str,
    start: date,
    finish: date,
    hours: str,
    anchors: list[str],
    qualifier: str | None = None,
    activity_type: str | None = None,
) -> Activity:
    """A P6-mirrored activity linked (confirmed) to the given RSWs, as a committed P6 import leaves it."""
    act = Activity(
        project_id=site.project.id,
        code=code,
        wbs_code=code,
        name=name,
        planned_start=start,
        planned_finish=finish,
        budget_hours=Decimal(hours),
        p6_activity_id=code,
        p6_facts={"src": {"codes": {"Site Status": "Shut"}}, "groups": {"activity_type": activity_type}},
    )
    db.add(act)
    await db.flush()
    for key in anchors:
        db.add(
            P6Link(
                project_id=site.project.id,
                activity_id=act.id,
                node_id=site.nodes[key]["id"],
                status="confirmed",
                parsed={"qualifier": qualifier} if qualifier else {},
            )
        )
    await db.commit()
    return act


async def test_packs_per_rsw_or_per_activity_from_the_programme(client: AsyncClient, site: Site, db_session: AsyncSession):
    d = date(2026, 11, 23)
    a = await mirror(
        db_session,
        site,
        "C100",
        "101 / SCA Erect / 101.1 - 101.2 OHP",
        d,
        date(2026, 11, 24),
        "40",
        ["rsw1", "rsw2"],
        "OHP",
        "SCA Erect",
    )
    b = await mirror(
        db_session, site, "C110", "101 / B / 101.1", date(2026, 11, 25), date(2026, 11, 27), "10", ["rsw1"], activity_type="B"
    )
    c = await mirror(db_session, site, "C120", "Mobilisation", d, d, "0", [])
    later = await mirror(db_session, site, "C130", "102 / P / 102.1", date(2027, 3, 1), date(2027, 3, 5), "16", ["rsw3"])
    plan = await make_plan(client, site)
    base = f"/api/v1/planner/plans/{plan['id']}"

    r = await client.get(f"{base}/programme")
    assert r.status_code == 200, r.text
    rows = {x["p6_activity_id"]: x for x in r.json()}
    assert set(rows) == {"C100", "C110", "C120"}  # the plan's window only
    assert [x["code"] for x in rows["C100"]["anchors"]] == ["101.1", "101.2"]
    assert rows["C100"]["anchors"][0]["qualifier"] == "OHP" and rows["C100"]["activity_type"] == "SCA Erect"
    assert rows["C120"]["anchors"] == [] and not rows["C100"]["in_plan"]
    whole = (await client.get(f"{base}/programme", params={"whole_programme": True})).json()
    assert {x["p6_activity_id"] for x in whole} == {"C100", "C110", "C120", "C130"}
    found = (await client.get(f"{base}/programme", params={"search": "shut"})).json()  # matches the activity code
    assert len(found) == 3

    # One pack per RSW (default): RSW 101.1 gets both its activities, 101.2 gets the shared one.
    r = await client.post(f"{base}/from-programme", json={"activity_ids": [a.id, b.id, c.id]}, headers=site.headers)
    assert r.status_code == 201, r.text
    res = r.json()
    assert (res["packs_created"], res["lines_added"], res["already_in_plan"], res["unlinked"]) == (2, 3, 0, ["C120"])
    packs = (await client.get("/api/v1/planner/packs/", params={"project_id": site.project.id, "plan_id": plan["id"]})).json()[
        "data"
    ]
    by_title = {p["title"]: p for p in packs}
    assert set(by_title) == {"101.1", "101.2"}
    rsw1 = (await client.get(f"/api/v1/planner/packs/{by_title['101.1']['id']}")).json()
    assert [(ln["activity_code"], float(ln["planned_hours"])) for ln in rsw1["lines"]] == [("C100", 20.0), ("C110", 10.0)]
    assert rsw1["lines"][0]["description"] == "101 / SCA Erect / 101.1 - 101.2 OHP (OHP)"
    assert (rsw1["planned_start"], rsw1["planned_end"]) == ("2026-11-23", "2026-11-27")
    assert rsw1["schedule_activity_id"] == a.id

    # Adding the same activities again never duplicates them; they now show as in the plan.
    again = (await client.post(f"{base}/from-programme", json={"activity_ids": [a.id, b.id]}, headers=site.headers)).json()
    assert (again["packs_created"], again["already_in_plan"]) == (0, 3)
    rows = {x["p6_activity_id"]: x for x in (await client.get(f"{base}/programme")).json()}
    assert rows["C100"]["in_plan"] and rows["C110"]["in_plan"] and not rows["C120"]["in_plan"]

    # One pack for the whole P6 activity.
    r = await client.post(
        f"{base}/from-programme", json={"activity_ids": [later.id], "grouping": "activity"}, headers=site.headers
    )
    assert r.status_code == 201 and r.json()["packs_created"] == 1
    pack = (await client.get(f"/api/v1/planner/packs/{r.json()['pack_ids'][0]}")).json()
    assert pack["title"] == "C130 102 / P / 102.1"
    assert [ln["anchor_id"] for ln in pack["lines"]] == [site.nodes["rsw3"]["id"]]
    plan_now = (await client.get(base)).json()
    assert set(plan_now["schedule_activity_ids"]) == {a.id, b.id, later.id}

    bad = await client.post(f"{base}/from-programme", json={"activity_ids": [999999]}, headers=site.headers)
    assert bad.status_code == 422


async def test_a_long_activity_brings_only_the_hours_inside_the_plan_window(
    client: AsyncClient, site: Site, db_session: AsyncSession
):
    """A six-week activity planned in a two-week window takes the window's share of its hours, not all of them."""
    long = await mirror(db_session, site, "C200", "101 / P / 101.1", date(2026, 11, 16), date(2026, 12, 25), "300", ["rsw1"])
    plan = await make_plan(client, site)  # 2026-11-23 .. 2026-12-06
    base = f"/api/v1/planner/plans/{plan['id']}"

    rows = {x["p6_activity_id"]: x for x in (await client.get(f"{base}/programme")).json()}
    # Mon-Fri project calendar: 30 working days in the activity, 10 of them in the window.
    assert rows["C200"]["window_share"] == pytest.approx(0.3333, abs=1e-4)
    assert float(rows["C200"]["hours_in_window"]) == 100.0
    assert float(rows["C200"]["budget_hours"]) == 300.0  # the P6 figure is never changed

    r = await client.post(f"{base}/from-programme", json={"activity_ids": [long.id]}, headers=site.headers)
    assert r.status_code == 201, r.text
    pack = (await client.get(f"/api/v1/planner/packs/{r.json()['pack_ids'][0]}")).json()
    assert [float(ln["planned_hours"]) for ln in pack["lines"]] == [100.0]
    assert pack["lines"][0]["description"] == "101 / P / 101.1 — 100 of 300 h in this plan"
    assert (pack["planned_start"], pack["planned_end"]) == ("2026-11-23", "2026-12-06")  # clipped to the window

    # Outside the window entirely (picked from the whole programme): no hours, the pack spans the window.
    later = await mirror(db_session, site, "C210", "102 / B / 102.1", date(2027, 2, 1), date(2027, 2, 5), "40", ["rsw3"])
    r = await client.post(f"{base}/from-programme", json={"activity_ids": [later.id]}, headers=site.headers)
    pack = (await client.get(f"/api/v1/planner/packs/{r.json()['pack_ids'][0]}")).json()
    assert float(pack["lines"][0]["planned_hours"]) == 0.0
    assert pack["lines"][0]["description"].endswith("— 0 of 40 h in this plan")
    assert (pack["planned_start"], pack["planned_end"]) == ("2026-11-23", "2026-12-06")

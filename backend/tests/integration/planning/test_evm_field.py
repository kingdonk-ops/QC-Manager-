"""EVM pulls actual hours from signed workface logs, matched to work packages through the asset breakdown's WBS."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.rbac.test_user_permissions import _grant

from .conftest import Site
from .test_workface_log import D2, new_log, planned_day

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

EVM = ("evm.read", "evm.create", "evm.update", "schedule.read")


async def test_signed_hours_reach_the_matching_work_package(client: AsyncClient, db_session: AsyncSession, site: Site):
    await _grant(db_session, site.user["id"], "evm", *EVM)
    await site.login(client, site.user)
    crew, _, n = await planned_day(client, site)
    tagged = await client.patch(
        f"/api/v1/asset-tree/nodes/{n['asset']['id']}", json={"wbs_code": "WBS-101"}, headers=site.headers
    )
    assert tagged.status_code == 200, tagged.text

    def package(code: str, wbs: str) -> dict:
        return {"project_id": site.project.id, "code": code, "name": code, "wbs": wbs, "budget_hours": "100"}

    matched = (await client.post("/api/v1/evm/work-packages/", json=package("WP-1", "wbs-101"), headers=site.headers)).json()
    other = (await client.post("/api/v1/evm/work-packages/", json=package("WP-2", "WBS-999"), headers=site.headers)).json()

    log = await new_log(client, site, crew)
    hours = [
        {"person": "J. Miller", "hours": "8.5", "node_id": n["rsw1"]["id"]},
        {"person": "K. Thorne", "hours": "6", "node_id": n["rsw3"]["id"]},  # under asset 102: another WBS
    ]
    assert (
        await client.put(f"/api/v1/workface-log/logs/{log['id']}", json={"hours": hours}, headers=site.headers)
    ).status_code == 200
    url = f"/api/v1/evm/{site.project.id}/progress/from-field"

    before = (await client.post(url, params={"date": str(D2)}, headers=site.headers)).json()
    rows = {r["code"]: r for r in before["rows"]}
    assert float(rows["WP-1"]["actual_hours"]) == 0  # not signed yet
    assert rows["WP-2"]["nodes"] == 0 and rows["WP-2"]["actual_hours"] is None

    await client.post(f"/api/v1/workface-log/logs/{log['id']}/submit", json={}, headers=site.headers)
    await client.post(f"/api/v1/workface-log/logs/{log['id']}/sign", json={}, headers=site.headers)

    dry = (await client.post(url, params={"date": str(D2), "dry_run": True}, headers=site.headers)).json()
    assert (dry["saved"], float({r["code"]: r for r in dry["rows"]}["WP-1"]["actual_hours"])) == (0, 8.5)
    saved = (await client.post(url, params={"date": str(D2)}, headers=site.headers)).json()
    assert saved["saved"] == 1
    sheet = (await client.get(f"/api/v1/evm/{site.project.id}/progress", params={"date": str(D2)})).json()
    by_id = {r["work_package_id"]: r for r in sheet["rows"]}
    assert float(by_id[matched["id"]]["actual_hours"]) == 8.5
    assert float(by_id[other["id"]]["actual_hours"]) == 0

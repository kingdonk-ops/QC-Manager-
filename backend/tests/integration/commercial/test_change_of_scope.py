"""Change of scope: cards on the breakdown, workflow permissions, 14-day expiry with a reminder, conversion to an
approved change order (and the guard when Change Orders is off), register export."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.change_of_scope import service
from src.modules.change_of_scope.models import ChangeCard
from src.modules.notifications.models import Notification
from src.modules.projects.models import Project, ProjectModuleOverride
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

FIELD = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "asset_tree.configure",
    "change_orders.read",
    *(f"change_of_scope.{a}" for a in ("read", "create", "update", "delete", "submit", "export")),
)
CLIENT = ("change_of_scope.respond", "change_of_scope.approve")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest_asyncio.fixture
async def ctx(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="COS-P", name="Pipe rack")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "field", *FIELD)
    h = {"X-CSRF-Token": await _login(client, test_user)}
    await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=h)
    ids = {}
    parent = None
    for level, code in (("site", "S"), ("asset", "101"), ("rsw", "305")):
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=h,
        )
        assert r.status_code == 201, r.text
        ids[level] = parent = r.json()["id"]

    async def card(**kw) -> dict:
        body = {
            "project_id": project.id,
            "title": "2 off PFC corroded: scope to increase",
            "source": "field_finding",
            "change_type": "scope_increase",
            "node_id": ids["rsw"],
            "client_reference": "SI-042",
            "lines": [
                {"description": "Replace PFC", "quantity": "2", "unit": "ea", "rate": "450", "hours": "6"},
                {"description": "Blast and coat", "quantity": "4.5", "unit": "m2", "rate": "120", "hours": "3.5"},
            ],
            **kw,
        }
        r = await client.post("/api/v1/change-of-scope/cards/", json=body, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    async def move(card_id: int, status: str, expect: int = 200, **kw) -> dict:
        r = await client.patch(f"/api/v1/change-of-scope/cards/{card_id}/status", json={"status": status, **kw}, headers=h)
        assert r.status_code == expect, r.text
        return r.json()

    return {"project": project, "h": h, "ids": ids, "card": card, "move": move, "user": test_user}


async def test_card_is_anchored_and_priced(client: AsyncClient, ctx):
    c = await ctx["card"]()
    assert c["code"] == "COS-001" and c["status"] == "draft"
    assert c["work_anchor_id"] == ctx["ids"]["rsw"] and c["node_path"] == "S / 101 / 305"
    assert Decimal(c["estimated_amount"]) == Decimal("1440.00") and Decimal(c["estimated_hours"]) == Decimal("9.50")
    asset = await ctx["card"](node_id=ctx["ids"]["asset"], lines=[])
    assert asset["work_anchor_id"] is None  # an asset has no work anchor on its path above it

    r = await client.patch(f"/api/v1/change-of-scope/cards/{c['id']}", json={"lines": []}, headers=ctx["h"])
    assert Decimal(r.json()["estimated_amount"]) == 0


async def test_workflow_needs_the_client_permissions(client: AsyncClient, ctx, db_session: AsyncSession):
    c = await ctx["card"]()
    sub = await ctx["move"](c["id"], "submitted")
    assert sub["expires_in_days"] in (13, 14)
    await ctx["move"](c["id"], "acknowledged", expect=403)
    await ctx["move"](c["id"], "approved", expect=403)
    r = await client.patch(f"/api/v1/change-of-scope/cards/{c['id']}", json={"title": "x"}, headers=ctx["h"])
    assert r.status_code == 422  # only drafts are edited

    await _grant(db_session, ctx["user"]["id"], "client", *CLIENT)
    ack = await ctx["move"](c["id"], "acknowledged")
    assert ack["acknowledged_at"]
    done = await ctx["move"](c["id"], "approved", approved_amount="1300", note="Agreed on walkdown")
    assert done["status"] == "approved" and Decimal(done["approved_amount"]) == 1300 and done["expires_at"] is None
    await ctx["move"](c["id"], "converted", expect=403)  # only /convert converts
    hist = (await client.get(f"/api/v1/change-of-scope/cards/{c['id']}/history")).json()
    assert [x["to_status"] for x in hist] == ["draft", "submitted", "acknowledged", "approved"]


async def test_cards_expire_after_14_days_with_one_reminder(client: AsyncClient, ctx, db_session: AsyncSession):
    c = await ctx["card"]()
    await ctx["move"](c["id"], "submitted")
    card = await db_session.get(ChangeCard, c["id"])
    await db_session.refresh(card)
    start = card.submitted_at
    assert card.expires_at - start == timedelta(days=14)

    assert await service.expire_due(db_session, now=start + timedelta(days=10)) == {"expired": 0, "reminded": 0}
    assert await service.expire_due(db_session, now=start + timedelta(days=11, hours=1)) == {"expired": 0, "reminded": 1}
    assert await service.expire_due(db_session, now=start + timedelta(days=12)) == {"expired": 0, "reminded": 0}
    assert await service.expire_due(db_session, now=start + timedelta(days=14, minutes=1)) == {"expired": 1, "reminded": 0}
    got = (await client.get(f"/api/v1/change-of-scope/cards/{c['id']}")).json()
    assert got["status"] == "expired" and got["expires_at"] is None
    notes = (
        (
            await db_session.execute(
                select(Notification.title).where(Notification.entity_type == "change_card", Notification.entity_id == c["id"])
            )
        )
        .scalars()
        .all()
    )
    assert sorted(notes) == ["COS-001 expired without a client decision", "COS-001 expires in 3 day(s)"]
    resub = await ctx["move"](c["id"], "submitted")
    assert resub["status"] == "submitted" and resub["expires_in_days"] in (13, 14)
    summary = (await client.get("/api/v1/change-of-scope/summary", params={"project_id": ctx["project"].id})).json()
    assert summary["by_status"]["submitted"]["count"] == 1


async def test_approved_card_converts_to_an_approved_change_order(client: AsyncClient, ctx, db_session: AsyncSession):
    await _grant(db_session, ctx["user"]["id"], "client", *CLIENT)
    c = await ctx["card"]()
    r = await client.post(f"/api/v1/change-of-scope/cards/{c['id']}/convert", headers=ctx["h"])
    assert r.status_code == 422  # not approved yet
    await ctx["move"](c["id"], "submitted")
    await ctx["move"](c["id"], "approved", approved_amount="720")
    r = await client.post(f"/api/v1/change-of-scope/cards/{c['id']}/convert", headers=ctx["h"])
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["status"] == "converted" and card["change_order_code"] == "CO-001"
    co = (await client.get(f"/api/v1/change-orders/{card['change_order_id']}")).json()
    assert co["status"] == "approved" and "COS-001" in co["title"] and "COS-001" in co["description"]
    assert Decimal(co["total_delta"]) == Decimal("720.00")  # scaled to the approved amount
    back = (
        await client.get(
            "/api/v1/change-of-scope/cards/",
            params={"project_id": ctx["project"].id, "change_order_id": card["change_order_id"]},
        )
    ).json()
    assert [x["code"] for x in back["data"]] == ["COS-001"]
    again = await client.post(f"/api/v1/change-of-scope/cards/{c['id']}/convert", headers=ctx["h"])
    assert again.status_code == 422


async def test_conversion_is_guarded_when_change_orders_is_off(client: AsyncClient, ctx, db_session: AsyncSession):
    await _grant(db_session, ctx["user"]["id"], "client", *CLIENT)
    c = await ctx["card"]()
    await ctx["move"](c["id"], "submitted")
    await ctx["move"](c["id"], "approved")
    db_session.add(ProjectModuleOverride(project_id=ctx["project"].id, module="change_orders", enabled=False))
    await db_session.commit()
    state.invalidate()
    r = await client.post(f"/api/v1/change-of-scope/cards/{c['id']}/convert", headers=ctx["h"])
    assert r.status_code == 422 and "switched off" in r.json()["detail"]


async def test_register_filters_and_export(client: AsyncClient, ctx):
    a = await ctx["card"]()
    await ctx["card"](title="Job looks done already: descope?", change_type="already_done")
    await ctx["move"](a["id"], "submitted")
    pid = ctx["project"].id
    waiting = (await client.get("/api/v1/change-of-scope/cards/", params={"project_id": pid, "status": "waiting"})).json()
    assert [x["code"] for x in waiting["data"]] == ["COS-001"]
    done = (
        await client.get("/api/v1/change-of-scope/cards/", params={"project_id": pid, "change_type": "already_done"})
    ).json()
    assert [x["code"] for x in done["data"]] == ["COS-002"]
    on_node = (
        await client.get("/api/v1/change-of-scope/cards/", params={"project_id": pid, "node_id": ctx["ids"]["rsw"]})
    ).json()
    assert on_node["total_count"] == 2
    x = await client.get("/api/v1/change-of-scope/cards/export", params={"project_id": pid})
    assert x.status_code == 200
    sheet = load_workbook(io.BytesIO(x.content)).active
    assert sheet["A1"].value == "No." and sheet["A2"].value == "COS-001"

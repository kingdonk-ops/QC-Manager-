"""Shift handover: sections, carry-forward, acknowledgement by the incoming supervisor, and reminders."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.handover.models import Handover
from src.modules.handover.service import remind_unacknowledged
from src.modules.notifications.models import Notification

from .conftest import Site

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

DAY = date(2026, 11, 24)


def items(site: Site) -> list[dict]:
    n = site.nodes
    return [
        {"kind": "safety", "title": "Dropped-object zone below rack 3", "detail": "Barricade stays up overnight"},
        {"kind": "permit", "title": "Hot work", "reference": "PTW-1182", "node_id": n["rsw1"]["id"]},
        {"kind": "equipment", "title": "CR-08 crane", "status": "defective", "detail": "Slew brake noisy"},
        {"kind": "wip", "title": "Blast 101.1 north face", "node_id": n["rsw1"]["id"], "detail": "60% blasted"},
        {"kind": "open_item", "title": "Paint batch certs", "status": "closed"},
        {"kind": "issue", "title": "Coating NCR", "link_type": "ncr", "link_id": 4, "link_label": "NCR-004"},
    ]


async def start(client: AsyncClient, site: Site, **extra) -> dict:
    r = await client.post(
        "/api/v1/handover/handovers/",
        json={
            "project_id": site.project.id,
            "shift_date": str(DAY),
            "area_node_id": site.nodes["area"]["id"],
            "recipient_id": site.other["id"],
            "summary": "Blasting on 101 continues; crane under watch.",
            "items": items(site),
        }
        | extra,
        headers=site.headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_handover_submit_and_acknowledge(client: AsyncClient, site: Site, db_session: AsyncSession, test_user_2: dict):
    h = await start(client, site)
    assert h["code"] == "HO-001" and h["status"] == "draft"
    assert h["area_name"] == "KAR / A1"
    assert [i["kind"] for i in h["items"]] == ["safety", "permit", "equipment", "wip", "open_item", "issue"]
    assert h["items"][0]["status"] == "open" and h["items"][1]["status"] == "active"
    assert h["items"][3]["anchor_code"] == "101 / 101.1"
    assert h["item_count"] == 6 and h["open_count"] == 5

    submitted = await client.post(f"/api/v1/handover/handovers/{h['id']}/submit", headers=site.headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted" and submitted.json()["waiting_hours"] is not None
    told = (await db_session.execute(select(Notification.title).where(Notification.user_id == site.other["id"]))).scalars()
    assert "Handover HO-001 for your night shift" in list(told)

    # The author can't acknowledge their own handover; the incoming supervisor can.
    mine = await client.post(f"/api/v1/handover/handovers/{h['id']}/acknowledge", json={}, headers=site.headers)
    assert mine.status_code == 403
    await site.login(client, test_user_2)
    waiting = (
        await client.get(
            "/api/v1/handover/handovers/", params={"project_id": site.project.id, "mine": "to", "unacknowledged": True}
        )
    ).json()
    assert [w["code"] for w in waiting["data"]] == ["HO-001"]
    ack = await client.post(
        f"/api/v1/handover/handovers/{h['id']}/acknowledge",
        json={"note": "Read; will check the crane first"},
        headers=site.headers,
    )
    assert ack.status_code == 200, ack.text
    body = ack.json()
    assert body["status"] == "acknowledged" and body["acknowledged_at"] and body["ack_note"].startswith("Read")
    history = (await client.get(f"/api/v1/handover/handovers/{h['id']}/history")).json()
    assert [x["to_status"] for x in history] == ["draft", "submitted", "acknowledged"]
    author_told = (
        await db_session.execute(select(Notification.title).where(Notification.user_id == site.user["id"]))
    ).scalars()
    assert "Handover HO-001 acknowledged" in list(author_told)

    pdf = await client.get(f"/api/v1/handover/handovers/{h['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    gone = await client.delete(f"/api/v1/handover/handovers/{h['id']}", headers=site.headers)
    assert gone.status_code == 422


async def test_rules_for_drafts_wip_and_recipients(client: AsyncClient, site: Site, test_user_2: dict):
    no_anchor = await client.post(
        "/api/v1/handover/handovers/",
        json={"project_id": site.project.id, "shift_date": str(DAY), "items": [{"kind": "wip", "title": "Somewhere"}]},
        headers=site.headers,
    )
    assert no_anchor.status_code == 422 and "work anchor" in no_anchor.text
    above = await client.post(
        "/api/v1/handover/handovers/",
        json={
            "project_id": site.project.id,
            "shift_date": str(DAY),
            "items": [{"kind": "wip", "title": "Asset level", "node_id": site.nodes["asset"]["id"]}],
        },
        headers=site.headers,
    )
    assert above.status_code == 422
    bad_status = await client.post(
        "/api/v1/handover/handovers/",
        json={
            "project_id": site.project.id,
            "shift_date": str(DAY),
            "items": [{"kind": "permit", "title": "x", "status": "open"}],
        },
        headers=site.headers,
    )
    assert bad_status.status_code == 422

    h = await start(client, site, recipient_id=None, items=[])
    nobody = await client.post(f"/api/v1/handover/handovers/{h['id']}/submit", headers=site.headers)
    assert nobody.status_code == 422
    saved = await client.put(
        f"/api/v1/handover/handovers/{h['id']}", json={"recipient_id": site.other["id"]}, headers=site.headers
    )
    assert saved.json()["recipient_name"]
    await client.post(f"/api/v1/handover/handovers/{h['id']}/submit", headers=site.headers)
    locked = await client.put(f"/api/v1/handover/handovers/{h['id']}", json={"summary": "x"}, headers=site.headers)
    assert locked.status_code == 422
    recalled = await client.post(f"/api/v1/handover/handovers/{h['id']}/recall", headers=site.headers)
    assert recalled.json()["status"] == "draft"

    await site.login(client, test_user_2)
    not_author = await client.put(f"/api/v1/handover/handovers/{h['id']}", json={"summary": "mine now"}, headers=site.headers)
    assert not_author.status_code == 403


async def test_open_items_carry_forward_to_the_next_shift(client: AsyncClient, site: Site, test_user_2: dict):
    first = await start(client, site)
    await client.post(f"/api/v1/handover/handovers/{first['id']}/submit", headers=site.headers)
    await site.login(client, test_user_2)
    nxt = await client.post(
        "/api/v1/handover/handovers/",
        json={
            "project_id": site.project.id,
            "shift_date": str(DAY),
            "from_shift": "night",
            "to_shift": "day",
            "area_node_id": site.nodes["area"]["id"],
            "recipient_id": site.user["id"],
            "items": [{"kind": "open_item", "title": "New: check fire watch log"}],
        },
        headers=site.headers,
    )
    assert nxt.status_code == 201, nxt.text
    body = nxt.json()
    assert body["carried_from_id"] == first["id"]
    titles = [i["title"] for i in body["items"]]
    assert "Paint batch certs" not in titles  # closed, so not carried
    assert titles == [
        "Dropped-object zone below rack 3",
        "Hot work",
        "CR-08 crane",
        "Blast 101.1 north face",
        "Coating NCR",
        "New: check fire watch log",
    ]
    fresh = await client.post(
        "/api/v1/handover/handovers/",
        json={
            "project_id": site.project.id,
            "shift_date": str(DAY),
            "area_node_id": site.nodes["area"]["id"],
            "carry_forward": False,
        },
        headers=site.headers,
    )
    assert fresh.json()["items"] == []


async def test_unacknowledged_handovers_are_reminded_then_escalated(client: AsyncClient, site: Site, db_session: AsyncSession):
    h = await start(client, site)
    await client.post(f"/api/v1/handover/handovers/{h['id']}/submit", headers=site.headers)
    row = await db_session.get(Handover, h["id"])
    assert row is not None and row.submitted_at is not None
    t0 = row.submitted_at

    assert await remind_unacknowledged(db_session, t0 + timedelta(minutes=30)) == 0  # too soon
    assert await remind_unacknowledged(db_session, t0 + timedelta(hours=1, minutes=5)) == 1
    assert await remind_unacknowledged(db_session, t0 + timedelta(hours=2)) == 0  # reminded within 2 h
    assert await remind_unacknowledged(db_session, t0 + timedelta(hours=3, minutes=10)) == 1
    assert await remind_unacknowledged(db_session, t0 + timedelta(hours=5, minutes=20)) == 1

    async def titles(user_id: int) -> list[str]:
        return list((await db_session.execute(select(Notification.title).where(Notification.user_id == user_id))).scalars())

    assert (await titles(site.other["id"])).count("Handover HO-001 is waiting for your acknowledgement") == 3
    assert "Handover HO-001 still not acknowledged" in await titles(site.user["id"])
    await db_session.refresh(row)
    assert row.reminders_sent == 3

    row.status = "acknowledged"
    row.acknowledged_at = datetime.now(UTC)
    await db_session.commit()
    assert await remind_unacknowledged(db_session, t0 + timedelta(hours=9)) == 0

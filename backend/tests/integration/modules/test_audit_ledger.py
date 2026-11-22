"""The audit ledger: append-only, hash-chained, verifiable; wired into module toggles, access and the asset tree."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import GENESIS_HASH, AppendOnlyError, AuditEntry, record_audit, verify_chain
from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


async def _three(db: AsyncSession) -> list[AuditEntry]:
    entries = [
        await record_audit(db, "test.thing.created", "thing", 1, actor_id=None, summary="one", after={"n": 1}),
        await record_audit(
            db,
            "test.thing.changed",
            "thing",
            1,
            summary="two",
            before={"n": 1},
            after={"n": Decimal("2.50"), "on": date(2026, 1, 2)},
        ),
        await record_audit(db, "test.thing.retired", "thing", 1, summary="three", after={"ratio": 0.1}),
    ]
    await db.commit()
    return entries


async def test_entries_chain_and_verify(db_session: AsyncSession):
    first, second, third = await _three(db_session)
    assert (first.seq, second.seq, third.seq) == (1, 2, 3)
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash and third.prev_hash == second.hash
    assert second.after == {"n": "2.50", "on": "2026-01-02"}  # stored as it hashes

    report = await verify_chain(db_session)
    assert report.ok and report.length == 3 and report.head_hash == third.hash


async def test_editing_a_row_is_detected_at_the_first_broken_link(db_session: AsyncSession):
    await _three(db_session)
    await db_session.execute(text("UPDATE audit_ledger SET summary = 'edited' WHERE seq = 2"))
    await db_session.commit()

    report = await verify_chain(db_session)
    assert not report.ok
    assert report.first_broken_seq == 2
    assert "changed" in (report.problem or "")
    assert report.length == 1


async def test_a_removed_row_is_detected(db_session: AsyncSession):
    await _three(db_session)
    await db_session.execute(text("DELETE FROM audit_ledger WHERE seq = 2"))
    await db_session.commit()

    report = await verify_chain(db_session)
    assert (report.ok, report.first_broken_seq) == (False, 3)


async def test_the_orm_refuses_changes(db_session: AsyncSession):
    first, *_ = await _three(db_session)
    first.summary = "rewritten"
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()
    entry = await db_session.scalar(select(AuditEntry).where(AuditEntry.seq == 1))
    assert entry is not None
    await db_session.delete(entry)
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()


async def test_explorer_filters_verifies_and_exports(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _three(db_session)
    await record_audit(db_session, "other.x.done", "other", 5, actor_id=test_user["id"])
    await db_session.commit()
    await _grant(db_session, test_user["id"], "auditor", "audit.read", "audit.export", "projects.read")
    await _login(client, test_user)

    page = (await client.get("/api/v1/audit/entries/", params={"entity_type": "thing"})).json()
    assert [e["seq"] for e in page["data"]] == [3, 2, 1]
    mine = (await client.get("/api/v1/audit/entries/", params={"actor_id": test_user["id"]})).json()
    assert [e["actor_name"] for e in mine["data"]] == [test_user["name"]]
    today = date.today().isoformat()
    assert (await client.get("/api/v1/audit/entries/", params={"date_from": today, "date_to": today})).json()[
        "total_count"
    ] == 4
    assert (await client.get("/api/v1/audit/entries/", params={"action": "test.thing."})).json()["total_count"] == 3

    verified = (await client.get("/api/v1/audit/verify")).json()
    assert verified["ok"] is True and verified["length"] == 4

    exported = await client.get("/api/v1/audit/export", params={"format": "csv", "entity_type": "thing"})
    assert exported.status_code == 200
    lines = exported.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("Seq,") and len(lines) == 4


async def test_module_toggles_access_levels_and_tree_restructures_are_audited(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = Project(code="P-1", name="Plant")
    db_session.add(project)
    await db_session.commit()
    perms = ("platform.modules", "platform.access", "projects.read", "projects.update", "audit.read")
    tree = tuple(f"asset_tree.{a}" for a in ("read", "create", "update", "configure"))
    await _grant(db_session, test_user["id"], "admin", *perms, *tree)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    assert (await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": False}, headers=headers)).status_code == 200
    assert (
        await client.put(f"/api/v1/platform/access/{test_user_2['id']}", json={"levels": {"cvr": "view"}}, headers=headers)
    ).status_code == 200
    put = await client.put(f"/api/v1/projects/{project.id}/modules", json={"overrides": {"ncr": False}}, headers=headers)
    assert put.status_code == 200, put.text

    await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers)

    async def node(level: str, code: str, parent: int | None = None) -> dict:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        return r.json()

    site = await node("site", "S")
    a1, a2 = await node("area", "A1", site["id"]), await node("area", "A2", site["id"])
    asset = await node("asset", "101", a1["id"])
    await client.post(f"/api/v1/asset-tree/nodes/{asset['id']}/move", json={"parent_id": a2["id"]}, headers=headers)
    await client.post(f"/api/v1/asset-tree/nodes/{asset['id']}/retire", json={}, headers=headers)

    actions = [e["action"] for e in (await client.get("/api/v1/audit/entries/")).json()["data"]]
    assert actions == [
        "asset_tree.node.retired",
        "asset_tree.node.moved",
        "projects.modules.overridden",
        "platform.access.changed",
        "platform.module.toggled",
    ]
    moved = (await client.get("/api/v1/audit/entries/", params={"action": "asset_tree.node.moved"})).json()["data"][0]
    assert moved["before"]["display_path"] == "S / A1 / 101" and moved["after"]["display_path"] == "S / A2 / 101"
    assert (await client.get("/api/v1/audit/verify")).json()["ok"] is True
    await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": True}, headers=headers)

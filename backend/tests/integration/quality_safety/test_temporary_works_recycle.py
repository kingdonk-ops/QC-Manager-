"""The recycle bin and the hidden Deleted folder: where a deleted draft goes, the two separate views that only the restore
permission can see, restore back to draft with children left as they were, refusal without the permission, the scheduled
purge after the project's retention (with its minimal audit entry), and the retention setting. The purge is run directly
with a pinned moment; records with history are made through the API, and states the API cannot reach are seeded."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.modules.temporary_works.deletion import purge_expired
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/temporary-works"
TRASH = f"{API}/trash"
VIEWER = ("projects.read", "temporary_works.read")
EDITOR = (*VIEWER, *(f"temporary_works.{a}" for a in ("create", "update", "delete", "transition")))
MANAGER = (*EDITOR, "temporary_works.issue", "temporary_works.return_to_draft")  # may delete, may not restore
RESTORER = (*VIEWER, "temporary_works.restore")
BLIND_RESTORER = ("temporary_works.read", "temporary_works.restore")  # cannot see the project at all
DAY = timedelta(days=1)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session)


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict[str, str]:
    await _grant(db, user["id"], f"tw-{uuid4().hex[:8]}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _item(client: AsyncClient, headers: dict, site: Tree, reference: str, expect: int = 201, **extra: Any) -> dict:
    body = {"project_id": site.project.id, "reference": reference, "title": "Slab props", "family": "propping", **extra}
    made = await client.post(f"{API}/", json=body, headers=headers)
    assert made.status_code == expect, made.text
    return made.json()


async def _permit(client: AsyncClient, headers: dict, item_id: int, number: str, **extra: Any) -> dict:
    body = {"number": number, "kind": "load", **extra}
    made = await client.post(f"{API}/permits/?item_id={item_id}", json=body, headers=headers)
    assert made.status_code == 201, made.text
    return made.json()


async def _delete(client: AsyncClient, headers: dict, path: str, expect: int = 200) -> dict:
    gone = await client.delete(f"{API}/{path}", headers=headers)
    assert gone.status_code == expect, gone.text
    return gone.json()


async def _post(client: AsyncClient, headers: dict, path: str, expect: int = 200, **body: Any) -> dict:
    done = await client.post(f"{API}/{path}", json=body or None, headers=headers)
    assert done.status_code == expect, done.text
    return done.json()


async def _put(client: AsyncClient, headers: dict, project_id: int, days: Any, **more: Any) -> Response:
    body = {"project_id": project_id, "bin_retention_days": days, **more}
    return await client.put(f"{TRASH}/settings", json=body, headers=headers)


async def _listed(client: AsyncClient, site: Tree, path: str) -> list[dict]:
    got = await client.get(f"{TRASH}/{path}?project_id={site.project.id}")
    assert got.status_code == 200, got.text
    return got.json()["data"]


async def _refs(client: AsyncClient, site: Tree, view: str, kind: str = "items") -> set[str]:
    key = "reference" if kind == "items" else "number"
    return {row[key] for row in await _listed(client, site, f"{view}/{kind}")}


async def _row(db: AsyncSession, model: Any, row_id: int) -> Any:
    return await db.scalar(select(model).where(model.id == row_id).execution_options(populate_existing=True))


async def _audit(db: AsyncSession, action: str, entity_id: int) -> list[AuditEntry]:
    query = select(AuditEntry).where(AuditEntry.action == action, AuditEntry.entity_id == str(entity_id))
    return list((await db.execute(query.order_by(AuditEntry.seq))).scalars())


async def _history_item(client: AsyncClient, headers: dict, site: Tree, reference: str) -> dict:
    """A draft that has been through a status change and back: it is a draft again but has history."""
    item = await _item(client, headers, site, reference)
    await _post(client, headers, f"{item['id']}/transition", status="design_brief")
    await _post(client, headers, f"{item['id']}/return-to-draft", reason="Brief withdrawn")
    return item


# --- bin delete -----------------------------------------------------------------------------------------------


async def test_a_draft_with_no_history_goes_to_the_bin_hidden_from_lists_and_counts_and_visible_to_the_restorer(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    bare = await _item(client, manager, site, "TW-1")
    parent = await _item(client, manager, site, "TW-2")
    permit = await _permit(client, manager, parent["id"], "P-1")

    assert (await _delete(client, manager, f"permits/{permit['id']}"))["destination"] == "bin"
    assert (await _delete(client, manager, str(bare["id"])))["destination"] == "bin"

    for model, row_id in ((TemporaryWorksItem, bare["id"]), (TemporaryWorksPermit, permit["id"])):
        row = await _row(db_session, model, row_id)  # a tombstone, not yet removed
        assert (row.deleted_kind, row.deleted_by_id) == ("bin", test_user["id"])
        assert row.deleted_at is not None
    assert (await client.get(f"{API}/{bare['id']}")).status_code == 404
    listed = (await client.get(f"{API}/?project_id={site.project.id}")).json()["data"]
    assert [i["reference"] for i in listed] == ["TW-2"]
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}")).json()["total_count"] == 0
    entry = (await _audit(db_session, "temporary_works.item.deleted", bare["id"]))[0]
    assert (entry.actor_id, entry.after) == (test_user["id"], {"deleted": True, "destination": "bin"})

    await _as(client, db_session, test_user_2, *RESTORER)
    assert await _refs(client, site, "bin") == {"TW-1"}
    assert await _refs(client, site, "bin", "permits") == {"P-1"}
    assert await _refs(client, site, "deleted") == set()
    assert await _refs(client, site, "deleted", "permits") == set()
    shown = (await _listed(client, site, "bin/items"))[0]
    wait = datetime.fromisoformat(shown["purge_on"]) - datetime.fromisoformat(shown["deleted_at"])
    assert (shown["deleted_kind"], wait) == ("bin", timedelta(days=30))
    rollup = (await client.get(f"{API}/register?project_id={site.project.id}")).json()
    assert rollup["total"] == 1  # counts skip the bin


# --- Deleted-folder delete ------------------------------------------------------------------------------------


async def test_a_draft_with_history_a_permit_or_a_link_is_soft_deleted_into_the_hidden_deleted_folder(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    returned = await _history_item(client, manager, site, "TW-RET")
    had_permit = await _item(client, manager, site, "TW-HAD")
    gone = await _permit(client, manager, had_permit["id"], "P-GONE")
    linked = await _item(client, manager, site, "TW-LINK", related_refs={"drawing": "D-1"})
    holder = await _item(client, manager, site, "TW-HOLD")
    issued = await _permit(client, manager, holder["id"], "P-HIST", kind="strike")
    await _post(client, manager, f"permits/{issued['id']}/issue")
    await _post(client, manager, f"permits/{issued['id']}/return-to-draft", reason="Dates were wrong")
    inspected = await _permit(client, manager, holder["id"], "P-INSP", inspection_id=7)

    assert (await _delete(client, manager, f"permits/{gone['id']}"))["destination"] == "bin"  # no history of its own
    for item in (returned, had_permit, linked):  # a status change, a permit ever had, a link: each is history
        assert (await _delete(client, manager, str(item["id"])))["destination"] == "folder", item["reference"]
    for permit in (issued, inspected):
        assert (await _delete(client, manager, f"permits/{permit['id']}"))["destination"] == "folder", permit["number"]
    assert (await _row(db_session, TemporaryWorksItem, returned["id"])).deleted_kind == "folder"

    await _as(client, db_session, test_user_2, *RESTORER)
    assert await _refs(client, site, "deleted") == {"TW-RET", "TW-HAD", "TW-LINK"}
    assert await _refs(client, site, "deleted", "permits") == {"P-HIST", "P-INSP"}
    assert await _refs(client, site, "bin") == set()
    assert await _refs(client, site, "bin", "permits") == {"P-GONE"}
    assert {row["purge_on"] for row in await _listed(client, site, "deleted/items")} == {None}  # never purged
    assert (await client.get(f"{API}/{returned['id']}")).status_code == 404  # and hidden from the normal view


# --- restore --------------------------------------------------------------------------------------------------


async def test_a_restore_brings_a_bin_or_folder_record_back_to_draft_and_is_audited(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    binned = await _item(client, manager, site, "TW-BIN")
    kept = await _history_item(client, manager, site, "TW-KEPT")
    for item in (binned, kept):
        await _delete(client, manager, str(item["id"]))

    restorer = await _as(client, db_session, test_user_2, *RESTORER)
    for item, origin in ((binned, "bin"), (kept, "folder")):
        back = await _post(client, restorer, f"trash/items/{item['id']}/restore")
        assert (back["status"], back["held_from"]) == ("identified", None)
        entry = (await _audit(db_session, "temporary_works.item.restored", item["id"]))[0]
        assert entry.actor_id == test_user_2["id"]
        assert (entry.before["destination"], entry.after) == (origin, {"status": "identified", "deleted": False})
        row = await _row(db_session, TemporaryWorksItem, item["id"])
        assert (row.deleted_at, row.deleted_by_id, row.deleted_kind) == (None, None, None)
    listed = (await client.get(f"{API}/?project_id={site.project.id}")).json()["data"]
    assert {i["reference"] for i in listed} == {"TW-BIN", "TW-KEPT"}
    assert (await _refs(client, site, "bin"), await _refs(client, site, "deleted")) == (set(), set())
    await _post(client, restorer, f"trash/items/{binned['id']}/restore", expect=409)  # no longer deleted
    await _post(client, restorer, f"trash/items/{binned['id'] + 5000}/restore", expect=404)


async def test_a_restore_leaves_the_children_as_they_were_and_a_permit_waits_for_its_item(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    item = await _item(client, manager, site, "TW-1")
    permit = await _permit(client, manager, item["id"], "P-1")
    await _delete(client, manager, f"permits/{permit['id']}")  # children first
    assert (await _delete(client, manager, str(item["id"])))["destination"] == "folder"  # it had a permit

    restorer = await _as(client, db_session, test_user_2, *RESTORER)
    refused = await _post(client, restorer, f"trash/permits/{permit['id']}/restore", expect=409)
    assert "item-deleted" in refused["detail"]
    assert (await _post(client, restorer, f"trash/items/{item['id']}/restore"))["status"] == "identified"
    assert await _refs(client, site, "bin", "permits") == {"P-1"}  # still deleted: the item's restore did not touch it
    assert (await client.get(f"{API}/permits/{permit['id']}")).status_code == 404

    back = await _post(client, restorer, f"trash/permits/{permit['id']}/restore")
    assert (back["status"], back["item_id"]) == ("draft", item["id"])
    assert (await client.get(f"{API}/permits/{permit['id']}")).status_code == 200
    assert len(await _audit(db_session, "temporary_works.permit.restored", permit["id"])) == 1


# --- refusal without the permission ---------------------------------------------------------------------------


async def test_the_views_restore_and_the_retention_setting_are_refused_without_the_restore_permission(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)  # may delete and return to draft, may not restore
    item = await _item(client, manager, site, "TW-1")
    await _delete(client, manager, str(item["id"]))
    project = site.project.id
    for path in (f"bin/items?project_id={project}", f"deleted/permits?project_id={project}", f"settings?project_id={project}"):
        assert (await client.get(f"{TRASH}/{path}")).status_code == 403, path
    await _post(client, manager, f"trash/items/{item['id']}/restore", expect=403)
    assert (await _put(client, manager, project, 10)).status_code == 403
    assert (await _row(db_session, TemporaryWorksItem, item["id"])).deleted_at is not None  # still deleted

    blind = await _as(client, db_session, test_user_2, *BLIND_RESTORER)  # the permission without access to the project
    assert (await client.get(f"{TRASH}/bin/items?project_id={project}")).status_code == 404
    await _post(client, blind, f"trash/items/{item['id']}/restore", expect=404)
    assert (await _row(db_session, TemporaryWorksItem, item["id"])).deleted_at is not None


async def test_the_view_must_be_the_bin_or_the_deleted_folder(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _as(client, db_session, test_user, *RESTORER)
    assert (await client.get(f"{TRASH}/everything/items?project_id={site.project.id}")).status_code == 422
    assert (await client.get(f"{TRASH}/bin/items?project_id=0")).status_code == 422


# --- the purge ------------------------------------------------------------------------------------------------


async def test_the_purge_removes_only_bin_records_after_the_retention_and_leaves_a_minimal_audit_entry(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    binned = await _item(client, manager, site, "TW-BIN")
    folder = await _history_item(client, manager, site, "TW-FOLDER")
    live = await _item(client, manager, site, "TW-LIVE")
    permit = await _permit(client, manager, live["id"], "P-BIN")
    for path in (str(binned["id"]), str(folder["id"]), f"permits/{permit['id']}"):
        await _delete(client, manager, path)
    await _item(client, manager, site, "TW-BIN", expect=409)  # the tombstone holds its reference until the purge
    retention_ends = (await _row(db_session, TemporaryWorksItem, binned["id"])).deleted_at + timedelta(days=30)

    early = await purge_expired(db_session, retention_ends - timedelta(seconds=1))
    assert early.total == 0
    assert await _row(db_session, TemporaryWorksItem, binned["id"]) is not None

    moment = retention_ends + timedelta(minutes=5)
    done = await purge_expired(db_session, moment)
    assert (done.items, done.permits) == (1, 1)
    assert await _row(db_session, TemporaryWorksItem, binned["id"]) is None  # physically removed
    assert await _row(db_session, TemporaryWorksPermit, permit["id"]) is None
    assert (await _row(db_session, TemporaryWorksItem, folder["id"])).deleted_kind == "folder"  # the folder is kept
    assert (await _row(db_session, TemporaryWorksItem, live["id"])).deleted_at is None

    entry = (await _audit(db_session, "temporary_works.item.purged", binned["id"]))[0]
    assert entry.actor_id is None
    assert (entry.project_id, entry.before["reference"]) == (site.project.id, "TW-BIN")
    assert datetime.fromisoformat(entry.after["purged_at"]) == moment
    assert len(await _audit(db_session, "temporary_works.permit.purged", permit["id"])) == 1
    assert len(await _audit(db_session, "temporary_works.item.deleted", binned["id"])) == 1  # the delete entry stays

    assert (await purge_expired(db_session, moment + 5000 * DAY)).total == 0  # idempotent; the folder never goes
    await _item(client, manager, site, "TW-BIN")  # the reference is free again


async def test_the_purge_never_removes_an_unknown_kind_or_an_item_that_still_has_a_permit(
    db_session: AsyncSession, test_user: dict, site: Tree
):
    long_ago = datetime.now(UTC) - 400 * DAY
    values: dict[str, Any] = {"project_id": site.project.id, "title": "Seeded", "family": "propping"}
    unknown = TemporaryWorksItem(reference="TW-UNK", deleted_at=long_ago, deleted_by_id=test_user["id"], **values)
    parent = TemporaryWorksItem(reference="TW-PAR", deleted_at=long_ago, deleted_kind="bin", **values)
    db_session.add_all([unknown, parent])
    await db_session.commit()
    db_session.add(TemporaryWorksPermit(project_id=site.project.id, item_id=parent.id, number="P-KEEP", kind="load"))
    await db_session.commit()

    assert (await purge_expired(db_session)).total == 0
    assert await _row(db_session, TemporaryWorksItem, unknown.id) is not None  # no kind reads as the folder
    assert await _row(db_session, TemporaryWorksItem, parent.id) is not None  # a permit row still refers to it


# --- the retention setting ------------------------------------------------------------------------------------


async def test_the_retention_defaults_to_thirty_days_is_set_within_one_to_sixty_and_decides_the_purge(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    item = await _item(client, manager, site, "TW-1")
    await _delete(client, manager, str(item["id"]))
    deleted_at = (await _row(db_session, TemporaryWorksItem, item["id"])).deleted_at

    restorer = await _as(client, db_session, test_user_2, *RESTORER)
    project = site.project.id
    current = f"{TRASH}/settings?project_id={project}"
    assert (await client.get(current)).json()["bin_retention_days"] == 30
    for bad in (0, 61, -1, "ten", None, 7.5):
        assert (await _put(client, restorer, project, bad)).status_code == 422, bad
    assert (await _put(client, restorer, project, 7, x=1)).status_code == 422  # no extra fields
    assert (await client.get(current)).json()["bin_retention_days"] == 30

    for days in (60, 7):
        saved = await _put(client, restorer, project, days)
        assert (saved.status_code, saved.json()["bin_retention_days"]) == (200, days), saved.text
    entries = await _audit(db_session, "temporary_works.settings.updated", project)
    assert [(e.before, e.after) for e in entries] == [
        ({"bin_retention_days": 30}, {"bin_retention_days": 60}),
        ({"bin_retention_days": 60}, {"bin_retention_days": 7}),
    ]
    shown = (await _listed(client, site, "bin/items"))[0]
    assert datetime.fromisoformat(shown["purge_on"]) - deleted_at == timedelta(days=7)  # the setting as it stands

    assert (await purge_expired(db_session, deleted_at + timedelta(days=7) - timedelta(seconds=1))).total == 0
    assert (await purge_expired(db_session, deleted_at + timedelta(days=7))).items == 1

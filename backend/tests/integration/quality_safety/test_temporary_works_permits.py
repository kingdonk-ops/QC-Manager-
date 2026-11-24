"""Temporary works permits API: draft creation from the request context, the issue, activate, close and return-to-draft
actions with their permissions, history, audit and notices, edit-while-draft, listing and filters, project visibility, and
the draft-only soft delete."""

from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.modules.notifications.models import Notification
from src.modules.temporary_works.constants import site_today
from src.modules.temporary_works.models import TemporaryWorksPermit
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/temporary-works"
VIEWER = ("projects.read", "temporary_works.read")
EDITOR = (*VIEWER, *(f"temporary_works.{a}" for a in ("create", "update", "delete", "transition")))
COORDINATOR = (*EDITOR, "temporary_works.issue")
MANAGER = (*COORDINATOR, "temporary_works.return_to_draft")
OUTSIDER = ("temporary_works.read", "temporary_works.create", "temporary_works.update", "temporary_works.delete")
TODAY = site_today()


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


async def _item(client: AsyncClient, headers: dict, site: Tree, reference: str = "TW-1", **extra: Any) -> dict:
    body = {"project_id": site.project.id, "reference": reference, "title": "Slab props", "family": "propping", **extra}
    made = await client.post(f"{API}/", json=body, headers=headers)
    assert made.status_code == 201, made.text
    return made.json()


async def _permit(
    client: AsyncClient, headers: dict, item_id: int, number: str = "P-1", /, expect: int = 201, **extra: Any
) -> Any:
    """Positional-only item and number, so a body that names either (to be refused) can ride along in ``extra``."""
    body = {"number": number, "kind": "load", **extra}
    made = await client.post(f"{API}/permits/?item_id={item_id}", json=body, headers=headers)
    assert made.status_code == expect, made.text
    return made.json()


async def _act(client: AsyncClient, headers: dict, permit_id: int, action: str, expect: int = 200, **body: Any) -> Any:
    done = await client.post(f"{API}/permits/{permit_id}/{action}", json=body or None, headers=headers)
    assert done.status_code == expect, done.text
    return done.json()


async def _audit(db: AsyncSession, action: str, entity_id: int) -> list[AuditEntry]:
    rows = await db.execute(
        select(AuditEntry).where(AuditEntry.action == action, AuditEntry.entity_id == str(entity_id)).order_by(AuditEntry.seq)
    )
    return list(rows.scalars())


async def _notices(db: AsyncSession, user_id: int, permit_id: int) -> list[Notification]:
    rows = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.entity_type == "temporary_works_permit",
            Notification.entity_id == permit_id,
        )
    )
    return list(rows.scalars())


async def _stored(db: AsyncSession, permit_id: int) -> TemporaryWorksPermit:
    query = select(TemporaryWorksPermit).where(TemporaryWorksPermit.id == permit_id).execution_options(populate_existing=True)
    row = await db.scalar(query)
    assert row is not None
    return row


BOTH = {"design_check_accepted": True, "inspection_passed": True}


# --- create and read ------------------------------------------------------------------------------------------


async def test_a_permit_is_created_as_a_draft_for_the_item_in_the_request_context_and_echoes_every_field(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    made = await _permit(
        client,
        headers,
        item["id"],
        "P-100",
        kind="strike",
        issued_by_name="Kim Ng",
        valid_from="2026-03-01",
        valid_to="2026-03-31",
        inspection_id=7,
        conditions="Strike from the top down",
    )
    assert (made["status"], made["kind"], made["number"]) == ("draft", "strike", "P-100")
    assert (made["item_id"], made["project_id"]) == (item["id"], site.project.id)
    window = (made["issued_by_name"], made["valid_from"], made["valid_to"], made["inspection_id"])
    assert window == ("Kim Ng", "2026-03-01", "2026-03-31", 7)
    assert (made["issued_on"], made["closed_on"], made["closed_by_id"]) == (None, None, None)
    assert (made["design_check_accepted"], made["inspection_passed"]) == (False, False)
    assert made["created_by_id"] == test_user["id"]
    assert made["created_at"] is not None
    assert made["warnings"] == []
    assert (await client.get(f"{API}/permits/{made['id']}")).json()["number"] == "P-100"


async def test_the_body_never_names_the_item_the_project_or_the_status(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    named = ({"item_id": item["id"]}, {"project_id": site.project.id}, {"status": "issued"}, {"kind": "bogus"}, {"number": ""})
    for extra in named:
        await _permit(client, headers, item["id"], "P-X", expect=422, **extra)
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}")).json()["total_count"] == 0


async def test_a_permit_for_an_item_of_another_project_or_a_missing_item_is_not_found(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    other = await build_tree(db_session, "SC-2")
    foreign = await _item(client, editor, other, "TW-F")
    await _permit(client, editor, item["id"] + 1000, expect=404)
    listed = await client.get(f"{API}/permits/?project_id={site.project.id}&item_id={foreign['id']}")
    assert listed.status_code == 404  # the item is not in the project named

    outsider = await _as(client, db_session, test_user_2, *OUTSIDER)  # cannot see the project at all
    await _permit(client, outsider, item["id"], expect=404)
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}&item_id={item['id']}")).status_code == 404


# --- issue, activate, close -----------------------------------------------------------------------------------


async def test_issuing_a_permit_to_load_reports_one_error_per_missing_prerequisite_and_it_stays_a_draft(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *COORDINATOR)
    item = await _item(client, headers, site)
    bare = await _permit(client, headers, item["id"], "P-1")  # a draft carries no such errors
    refused = await _act(client, headers, bare["id"], "issue", expect=422)
    assert "load-prerequisite-design-check" in refused["detail"]
    assert "load-prerequisite-inspection" in refused["detail"]
    assert (await _stored(db_session, bare["id"])).status == "draft"

    one = await _permit(client, headers, item["id"], "P-2", design_check_accepted=True)
    only = await _act(client, headers, one["id"], "issue", expect=422)
    assert "load-prerequisite-inspection" in only["detail"]
    assert "load-prerequisite-design-check" not in only["detail"]

    full = await _permit(client, headers, item["id"], "P-3", **BOTH)
    issued = await _act(client, headers, full["id"], "issue")
    assert (issued["status"], issued["issued_on"]) == ("issued", TODAY.isoformat())

    strike = await _permit(client, headers, item["id"], "P-4", kind="strike")  # no prerequisite needed
    assert (await _act(client, headers, strike["id"], "issue"))["status"] == "issued"


async def test_the_date_order_is_refused_on_create_and_on_edit(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    refused = await _permit(client, headers, item["id"], expect=422, valid_from="2026-03-10", valid_to="2026-03-01")
    assert "valid-to-before-from" in refused["detail"]
    ok = await _permit(client, headers, item["id"], valid_from="2026-03-01", valid_to="2026-03-10")
    edited = await client.patch(f"{API}/permits/{ok['id']}", json={"valid_to": "2026-02-01"}, headers=headers)
    assert edited.status_code == 422
    assert "valid-to-before-from" in edited.json()["detail"]
    assert (await _stored(db_session, ok["id"])).valid_to.isoformat() == "2026-03-10"


async def test_a_permit_moves_through_issue_activate_and_close_with_history_audit_and_a_notice_to_the_coordinator(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *COORDINATOR)
    item = await _item(client, headers, site, coordinator_user_id=test_user_2["id"])
    permit = await _permit(client, headers, item["id"], **BOTH)
    pid = permit["id"]
    await _act(client, headers, pid, "close", expect=422)  # a draft cannot be closed
    await _act(client, headers, pid, "activate", expect=422)  # nor activated
    await _act(client, headers, pid, "issue")
    await _act(client, headers, pid, "issue", expect=422)  # the second sees the new status
    await _act(client, headers, pid, "activate")
    closed = await _act(client, headers, pid, "close")
    assert (closed["status"], closed["closed_on"], closed["closed_by_id"]) == ("closed", TODAY.isoformat(), test_user["id"])
    await _act(client, headers, pid, "activate", expect=422)  # closed is final

    history = (await client.get(f"{API}/permits/{pid}/history")).json()
    moves = [(h["from_status"], h["to_status"]) for h in history]
    assert moves == [("draft", "issued"), ("issued", "active"), ("active", "closed")]
    for verb in ("issued", "active", "closed"):
        entries = await _audit(db_session, f"temporary_works.permit.{verb}", pid)
        assert len(entries) == 1, verb
        assert entries[0].actor_id == test_user["id"]
    assert len(await _notices(db_session, test_user_2["id"], pid)) == 3  # after each commit
    assert await _notices(db_session, test_user["id"], pid) == []  # the actor is not told


async def test_issuing_activating_and_closing_need_the_issue_permission_while_an_editor_still_edits_drafts(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    permit = await _permit(client, editor, item["id"], **BOTH)
    edited = await client.patch(f"{API}/permits/{permit['id']}", json={"conditions": "Dry weather only"}, headers=editor)
    assert edited.status_code == 200, edited.text
    for action in ("issue", "activate", "close"):
        await _act(client, editor, permit["id"], action, expect=403)

    coordinator = await _as(client, db_session, test_user_2, *COORDINATOR)
    assert (await _act(client, coordinator, permit["id"], "issue"))["status"] == "issued"


async def test_a_viewer_reads_permits_but_cannot_write(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    editor = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, editor, site)
    permit = await _permit(client, editor, item["id"])
    viewer = await _as(client, db_session, test_user_2, *VIEWER)
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}")).status_code == 200
    assert (await client.get(f"{API}/permits/{permit['id']}")).status_code == 200
    await _permit(client, viewer, item["id"], "P-V", expect=403)
    assert (await client.patch(f"{API}/permits/{permit['id']}", json={"conditions": "x"}, headers=viewer)).status_code == 403
    assert (await client.delete(f"{API}/permits/{permit['id']}", headers=viewer)).status_code == 403
    await _act(client, viewer, permit["id"], "issue", expect=403)


# --- edit rules -----------------------------------------------------------------------------------------------


async def test_only_a_draft_is_edited_and_the_status_is_never_written_directly(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *COORDINATOR)
    item = await _item(client, headers, site)
    permit = await _permit(client, headers, item["id"], **BOTH)
    url = f"{API}/permits/{permit['id']}"
    for bad in ({"status": "issued"}, {"item_id": 5}, {"project_id": 5}, {"issued_on": "2026-01-01"}, {"number": None}):
        assert (await client.patch(url, json=bad, headers=headers)).status_code == 422, bad

    await _act(client, headers, permit["id"], "issue")
    refused = await client.patch(url, json={"conditions": "Changed"}, headers=headers)
    assert refused.status_code == 409  # an issued permit's fields are not edited
    await _act(client, headers, permit["id"], "close")
    assert (await client.patch(url, json={"conditions": "Changed"}, headers=headers)).status_code == 409
    assert (await _stored(db_session, permit["id"])).conditions is None


async def test_a_number_is_unique_within_a_project_and_a_permit_keeps_its_own(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *EDITOR)
    item = await _item(client, headers, site)
    first = await _permit(client, headers, item["id"], "P-1")
    await _permit(client, headers, item["id"], "P-1", expect=409)
    other = await build_tree(db_session, "SC-2")
    await _permit(client, headers, (await _item(client, headers, other))["id"], "P-1")  # another project: accepted
    keep = await client.patch(f"{API}/permits/{first['id']}", json={"number": "P-1", "conditions": "x"}, headers=headers)
    assert keep.status_code == 200, keep.text
    second = await _permit(client, headers, item["id"], "P-2")
    assert (await client.patch(f"{API}/permits/{second['id']}", json={"number": "P-1"}, headers=headers)).status_code == 409


# --- list -----------------------------------------------------------------------------------------------------


async def test_permits_list_in_creation_order_and_filter_by_item_and_status(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *COORDINATOR)
    one, two = await _item(client, headers, site, "TW-1"), await _item(client, headers, site, "TW-2")
    first = await _permit(client, headers, one["id"], "P-1", **BOTH)
    await _permit(client, headers, two["id"], "P-2")
    await _permit(client, headers, one["id"], "P-3", kind="dismantle")
    await _act(client, headers, first["id"], "issue")

    async def numbers(query: str = "") -> list[str]:
        listed = await client.get(f"{API}/permits/?project_id={site.project.id}{query}")
        assert listed.status_code == 200, listed.text
        return [p["number"] for p in listed.json()["data"]]

    assert await numbers() == ["P-1", "P-2", "P-3"]
    assert await numbers(f"&item_id={one['id']}") == ["P-1", "P-3"]
    assert await numbers("&status=draft") == ["P-2", "P-3"]
    assert await numbers("&status=issued") == ["P-1"]
    assert await numbers(f"&item_id={one['id']}&status=draft") == ["P-3"]
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}&status=bogus")).status_code == 422
    assert (await client.get(f"{API}/permits/?project_id={site.project.id}&items_per_page=2&page=2")).json()["total_count"] == 3


# --- return to draft and delete -------------------------------------------------------------------------------


async def test_returning_a_permit_to_draft_needs_its_own_permission_and_a_reason_and_is_audited(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    coordinator = await _as(client, db_session, test_user, *COORDINATOR)
    item = await _item(client, coordinator, site)
    permit = await _permit(client, coordinator, item["id"], **BOTH)
    pid = permit["id"]
    await _act(client, coordinator, pid, "issue")
    # the issue permission is not enough: sending a permit back needs its own
    await _act(client, coordinator, pid, "return-to-draft", expect=403, reason="Wrong dates")

    manager = await _as(client, db_session, test_user_2, *MANAGER)
    for bad in ({}, {"reason": ""}, {"reason": "  "}):
        await _act(client, manager, pid, "return-to-draft", expect=422, **bad)
    back = await _act(client, manager, pid, "return-to-draft", reason="Wrong dates")
    assert (back["status"], back["issued_on"], back["closed_on"]) == ("draft", None, None)
    await _act(client, manager, pid, "return-to-draft", expect=422, reason="Again")  # already a draft

    history = (await client.get(f"{API}/permits/{pid}/history")).json()
    assert (history[-1]["from_status"], history[-1]["to_status"]) == ("issued", "draft")
    assert "Wrong dates" in history[-1]["note"]
    entries = await _audit(db_session, "temporary_works.permit.returned_to_draft", pid)
    assert len(entries) == 1
    assert entries[0].after == {"status": "draft", "reason": "Wrong dates"}
    assert entries[0].actor_id == test_user_2["id"]
    assert (await _act(client, manager, pid, "issue"))["issued_on"] == TODAY.isoformat()  # recorded afresh

    await _act(client, manager, pid, "close")
    reopened = await _act(client, manager, pid, "return-to-draft", reason="Closed in error")
    assert (reopened["status"], reopened["closed_on"], reopened["closed_by_id"]) == ("draft", None, None)


async def test_only_a_draft_permit_is_deleted_and_the_delete_is_a_soft_audited_tombstone(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _as(client, db_session, test_user, *COORDINATOR)
    item = await _item(client, headers, site)
    draft = await _permit(client, headers, item["id"], "P-1", **BOTH)
    issued = await _permit(client, headers, item["id"], "P-2", **BOTH)
    await _act(client, headers, issued["id"], "issue")

    blocked = await client.delete(f"{API}/permits/{issued['id']}", headers=headers)
    assert blocked.status_code == 409
    assert "not-draft" in blocked.json()["detail"]

    gone = await client.delete(f"{API}/permits/{draft['id']}", headers=headers)
    assert gone.status_code == 200, gone.text
    assert (await client.get(f"{API}/permits/{draft['id']}")).status_code == 404
    listed = await client.get(f"{API}/permits/?project_id={site.project.id}")
    assert [p["number"] for p in listed.json()["data"]] == ["P-2"]
    row = await _stored(db_session, draft["id"])  # never physically removed
    assert (row.deleted_at is not None, row.deleted_by_id) == (True, test_user["id"])
    entries = await _audit(db_session, "temporary_works.permit.deleted", draft["id"])
    assert len(entries) == 1
    assert entries[0].actor_id == test_user["id"]
    await _permit(client, headers, item["id"], "P-1", expect=409)  # the tombstone keeps its number

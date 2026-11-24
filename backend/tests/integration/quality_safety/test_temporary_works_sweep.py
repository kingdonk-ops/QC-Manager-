"""The hourly temporary works sweep: permit expiry, the once-only expiring-soon notice and breach handling (notices, task,
audit, red tag on a linked standing scaffold), its idempotence, and the clearing of the once-per-breach marker. The sweep
is run directly with a pinned day; items and permits are seeded through the models."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.infrastructure.records.models import StatusChange
from src.modules.notifications.models import Notification
from src.modules.scaffolds.models import Scaffold
from src.modules.tasks.models import Task
from src.modules.temporary_works.models import TemporaryWorksItem, TemporaryWorksPermit
from src.modules.temporary_works.sweep import run_sweep
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

TODAY = date(2026, 6, 15)
YESTERDAY = TODAY - timedelta(days=1)
ITEM = "temporary_works_item"
PERMIT = "temporary_works_permit"
BREACH_TITLE = "bearing load with no valid permit to load"
SCAFFOLD_ACTIONS = ("read", "create", "update", "transition", "approve", "inspect", "delete")
SCAFFOLDS = ("tasks.read", "projects.read", *(f"scaffolds.{a}" for a in SCAFFOLD_ACTIONS))


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session)


async def _item(db: AsyncSession, site: Tree, reference: str, status: str, **extra: Any) -> TemporaryWorksItem:
    fields: dict[str, Any] = {"family": "propping", "title": f"Item {reference}", "design_check_category": 1, **extra}
    item = TemporaryWorksItem(project_id=site.project.id, reference=reference, **fields)
    item.status = status
    db.add(item)
    await db.commit()
    return item


async def _permit(db: AsyncSession, item: TemporaryWorksItem, number: str, **extra: Any) -> TemporaryWorksPermit:
    values: dict[str, Any] = {
        "status": "issued",
        "valid_from": TODAY - timedelta(days=30),
        "valid_to": TODAY + timedelta(days=30),
        "design_check_accepted": True,
        "inspection_passed": True,
        **extra,
    }
    kind = values.pop("kind", "load")
    permit = TemporaryWorksPermit(project_id=item.project_id, item_id=item.id, number=number, kind=kind, **values)
    db.add(permit)
    await db.commit()
    return permit


async def _fresh(db: AsyncSession, model: Any, row_id: int) -> Any:
    row = await db.scalar(select(model).where(model.id == row_id).execution_options(populate_existing=True))
    assert row is not None
    return row


async def _notices(db: AsyncSession, user_id: int, entity: str, entity_id: int) -> list[Notification]:
    rows = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.entity_type == entity, Notification.entity_id == entity_id
        )
    )
    return list(rows.scalars())


async def _tasks(db: AsyncSession, item_id: int) -> list[Task]:
    rows = await db.execute(select(Task).where(Task.entity_type == ITEM, Task.entity_id == item_id))
    return list(rows.scalars())


async def _audit(db: AsyncSession, action: str, entity_id: int) -> list[AuditEntry]:
    rows = await db.execute(select(AuditEntry).where(AuditEntry.action == action, AuditEntry.entity_id == str(entity_id)))
    return list(rows.scalars())


async def _history(db: AsyncSession, entity: str, entity_id: int) -> list[StatusChange]:
    query = select(StatusChange).where(StatusChange.entity_type == entity, StatusChange.entity_id == entity_id)
    rows = await db.execute(query.order_by(StatusChange.id))
    return list(rows.scalars())


async def _issuer(db: AsyncSession, user: dict) -> None:
    await _grant(db, user["id"], f"tw-issue-{uuid4().hex[:8]}", "temporary_works.issue")


# --- breach handling ------------------------------------------------------------------------------------------


async def test_a_breach_is_announced_once_and_never_changes_the_item_or_blocks_its_edits(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    await _issuer(db_session, test_user_2)
    item = await _item(db_session, site, "TW-1", "in_use", coordinator_user_id=test_user["id"])
    await _permit(db_session, item, "P-1", valid_to=YESTERDAY)  # the permit to load ended yesterday

    first = await run_sweep(db_session, TODAY)
    assert first.breaches == 1
    assert len(await _notices(db_session, test_user["id"], ITEM, item.id)) == 1  # the coordinator
    assert len(await _notices(db_session, test_user_2["id"], ITEM, item.id)) == 1  # a holder of the issue permission
    notice = (await _notices(db_session, test_user["id"], ITEM, item.id))[0]
    assert BREACH_TITLE in notice.title
    tasks = await _tasks(db_session, item.id)
    assert len(tasks) == 1
    assert (tasks[0].assignee_id, tasks[0].due_date, tasks[0].project_id) == (test_user["id"], TODAY, site.project.id)
    assert len(await _audit(db_session, "temporary_works.item.breach", item.id)) == 1
    stored = await _fresh(db_session, TemporaryWorksItem, item.id)
    assert stored.status == "in_use"  # the sweep never moves the item
    assert stored.breach_notified_on == TODAY

    second = await run_sweep(db_session, TODAY)  # idempotent: nothing repeats
    assert second.total == 0
    assert len(await _notices(db_session, test_user["id"], ITEM, item.id)) == 1
    assert len(await _notices(db_session, test_user_2["id"], ITEM, item.id)) == 1
    assert len(await _tasks(db_session, item.id)) == 1
    assert len(await _audit(db_session, "temporary_works.item.breach", item.id)) == 1

    await _grant(db_session, test_user["id"], f"tw-edit-{uuid4().hex[:8]}", "projects.read", "temporary_works.update")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    edited = await client.patch(f"/api/v1/temporary-works/{item.id}", json={"notes": "Pour paused"}, headers=headers)
    assert edited.status_code == 200, edited.text  # edits are not blocked


async def test_clearing_the_breach_resets_the_marker_and_a_later_breach_is_announced_again(
    db_session: AsyncSession, test_user: dict, site: Tree
):
    item = await _item(db_session, site, "TW-1", "loaded", coordinator_user_id=test_user["id"])
    assert (await run_sweep(db_session, TODAY)).breaches == 1

    valid = await _permit(db_session, item, "P-1")  # a valid permit to load is recorded
    cleared = await run_sweep(db_session, TODAY)
    assert (cleared.breaches, cleared.markers_reset) == (0, 1)
    assert (await _fresh(db_session, TemporaryWorksItem, item.id)).breach_notified_on is None

    valid.status = "closed"  # a new breach
    await db_session.commit()
    again = await run_sweep(db_session, TODAY + timedelta(days=1))
    assert again.breaches == 1
    assert len(await _notices(db_session, test_user["id"], ITEM, item.id)) == 2
    assert len(await _tasks(db_session, item.id)) == 2
    assert len(await _audit(db_session, "temporary_works.item.breach", item.id)) == 2


async def test_a_change_of_status_also_clears_the_marker(db_session: AsyncSession, test_user: dict, site: Tree):
    item = await _item(db_session, site, "TW-1", "in_use", coordinator_user_id=test_user["id"])
    assert (await run_sweep(db_session, TODAY)).breaches == 1
    item.status = "approved_to_strike"
    await db_session.commit()
    result = await run_sweep(db_session, TODAY)
    assert (result.breaches, result.markers_reset) == (0, 1)
    assert (await _fresh(db_session, TemporaryWorksItem, item.id)).breach_notified_on is None


async def test_items_that_are_not_bearing_load_or_are_deleted_are_never_announced(
    db_session: AsyncSession, test_user: dict, site: Tree
):
    await _item(db_session, site, "TW-1", "approved_to_load", coordinator_user_id=test_user["id"])
    await _item(db_session, site, "TW-2", "on_hold", coordinator_user_id=test_user["id"])
    gone = await _item(db_session, site, "TW-3", "in_use", coordinator_user_id=test_user["id"], deleted_at=datetime.now(UTC))
    result = await run_sweep(db_session, TODAY)
    assert result.total == 0
    assert await _tasks(db_session, gone.id) == []


async def test_an_item_with_no_coordinator_still_gets_an_unassigned_task_and_tells_the_issue_holders(
    db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    await _issuer(db_session, test_user_2)
    item = await _item(db_session, site, "TW-1", "loaded")
    assert (await run_sweep(db_session, TODAY)).breaches == 1
    tasks = await _tasks(db_session, item.id)
    assert [(t.assignee_id, t.due_date) for t in tasks] == [(None, TODAY)]
    assert len(await _notices(db_session, test_user_2["id"], ITEM, item.id)) == 1


# --- the red tag on a linked scaffold ---------------------------------------------------------------------------


async def _scaffold(client: AsyncClient, headers: dict, site: Tree, tag: str | None = "green", steps: bool = True) -> int:
    made = await client.post(
        "/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw, "purpose": "Access"}, headers=headers
    )
    assert made.status_code == 201, made.text
    sid = int(made.json()["id"])
    for step in ("approved", "erecting", "erected") if steps else ():
        moved = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    if tag and steps:
        body = {"kind": "handover", "tag": tag}
        tagged = await client.post(f"/api/v1/scaffolds/{sid}/inspections", json=body, headers=headers)
        assert tagged.status_code == 201, tagged.text
    return sid


async def test_a_breach_writes_the_red_tag_on_a_linked_standing_scaffold_once_and_leaves_others_alone(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    await _grant(db_session, test_user["id"], f"tw-sc-{uuid4().hex[:8]}", *SCAFFOLDS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    standing = await _scaffold(client, headers, site, "green")
    requested = await _scaffold(client, headers, site, steps=False)  # only requested: not standing
    linked = await _item(db_session, site, "TW-1", "loaded", scaffold_id=standing, coordinator_user_id=test_user["id"])
    idle = await _item(db_session, site, "TW-2", "in_use", scaffold_id=requested)

    result = await run_sweep(db_session, TODAY)
    assert (result.breaches, result.red_tagged) == (2, 1)
    assert (await _fresh(db_session, Scaffold, standing)).tag_status == "red"
    assert (await _fresh(db_session, Scaffold, requested)).tag_status == "none"
    tag_moves = await _history(db_session, "scaffold_tag", standing)
    assert [(h.from_status, h.to_status) for h in tag_moves] == [("green", "red")]
    assert await _history(db_session, "scaffold_tag", requested) == []
    assert (await _fresh(db_session, TemporaryWorksItem, linked.id)).status == "loaded"  # the item itself is not touched
    assert (await _fresh(db_session, TemporaryWorksItem, idle.id)).status == "in_use"

    assert (await run_sweep(db_session, TODAY)).total == 0  # a second run adds no history entry
    assert len(await _history(db_session, "scaffold_tag", standing)) == 1


# --- permit expiry and the expiring-soon notice ------------------------------------------------------------------


async def test_a_lapsed_permit_is_moved_to_expired_with_history_audit_and_a_notice_and_only_once(
    db_session: AsyncSession, test_user: dict, site: Tree
):
    item = await _item(db_session, site, "TW-1", "approved_to_load", coordinator_user_id=test_user["id"])
    issued = await _permit(db_session, item, "P-1", valid_to=YESTERDAY)
    active = await _permit(db_session, item, "P-2", status="active", valid_to=YESTERDAY - timedelta(days=3))
    today_end = await _permit(db_session, item, "P-3", valid_to=TODAY)  # valid through today: still valid
    draft = await _permit(db_session, item, "P-4", status="draft", valid_to=YESTERDAY)
    closed = await _permit(db_session, item, "P-5", status="closed", valid_to=YESTERDAY)
    open_ended = await _permit(db_session, item, "P-6", valid_to=None)

    result = await run_sweep(db_session, TODAY)
    assert result.expired == 2
    statuses = {}
    for permit in (issued, active, today_end, draft, closed, open_ended):
        statuses[permit.number] = (await _fresh(db_session, TemporaryWorksPermit, permit.id)).status
    assert statuses == {"P-1": "expired", "P-2": "expired", "P-3": "issued", "P-4": "draft", "P-5": "closed", "P-6": "issued"}
    for permit, before in ((issued, "issued"), (active, "active")):
        moves = await _history(db_session, PERMIT, permit.id)
        assert [(h.from_status, h.to_status, h.changed_by_id) for h in moves] == [(before, "expired", None)]
        assert len(await _audit(db_session, "temporary_works.permit.expired", permit.id)) == 1
        assert len(await _notices(db_session, test_user["id"], PERMIT, permit.id)) == 1
    assert (await _fresh(db_session, TemporaryWorksItem, item.id)).status == "approved_to_load"

    assert (await run_sweep(db_session, TODAY)).expired == 0
    assert len(await _history(db_session, PERMIT, issued.id)) == 1


async def test_a_permit_lapsing_within_three_days_gets_one_expiring_soon_notice_only(
    db_session: AsyncSession, test_user: dict, site: Tree
):
    item = await _item(db_session, site, "TW-1", "approved_to_load", coordinator_user_id=test_user["id"])
    soon = await _permit(db_session, item, "P-1", valid_to=TODAY + timedelta(days=2))
    edge = await _permit(db_session, item, "P-2", valid_to=TODAY + timedelta(days=3))
    later = await _permit(db_session, item, "P-3", valid_to=TODAY + timedelta(days=4))
    drafted = await _permit(db_session, item, "P-4", status="draft", valid_to=TODAY + timedelta(days=1))

    first = await run_sweep(db_session, TODAY)
    assert (first.expiring_soon, first.expired) == (2, 0)
    for permit, expected in ((soon, 1), (edge, 1), (later, 0), (drafted, 0)):
        assert len(await _notices(db_session, test_user["id"], PERMIT, permit.id)) == expected, permit.number
    assert (await _fresh(db_session, TemporaryWorksPermit, soon.id)).expiry_notified_on == TODAY
    assert (await _fresh(db_session, TemporaryWorksPermit, soon.id)).status == "issued"  # the status does not move yet

    again = await run_sweep(db_session, TODAY + timedelta(days=1))
    assert again.expiring_soon == 1  # the permit that has now come into the window; the first two are not repeated
    assert len(await _notices(db_session, test_user["id"], PERMIT, soon.id)) == 1
    assert len(await _notices(db_session, test_user["id"], PERMIT, later.id)) == 1

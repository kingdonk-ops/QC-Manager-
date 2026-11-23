"""Scaffold breach helper: the red-tag write-back for a linked temporary works item bearing load without a valid permit
to load, and the scaffold state read. The helper never commits; each test commits (or rolls back) itself."""

from dataclasses import fields
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.infrastructure.records.models import StatusChange
from src.modules.notifications.models import Notification
from src.modules.scaffolds import breach
from src.modules.scaffolds.breach import ScaffoldState, mark_breach_red, scaffold_state
from src.modules.scaffolds.models import Scaffold
from src.modules.scaffolds.service import mark_overdue, scaffold_ready
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

ALL = (
    "projects.read",
    "tasks.read",
    *(f"scaffolds.{a}" for a in ("read", "create", "update", "transition", "approve", "inspect", "delete", "export")),
)
REASON = "tag is red"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session)


async def _headers(client: AsyncClient, db: AsyncSession, user: dict) -> dict:
    await _grant(db, user["id"], f"breach-{user['id']}", *ALL)
    return {"X-CSRF-Token": await _login(client, user)}


def _utc_today() -> date:
    return datetime.now(UTC).date()


async def _scaffold(
    client: AsyncClient, headers: dict, site: Tree, tag: str | None = "green", restrictions: str | None = None, **extra
) -> dict:
    """Request, approve and erect a scaffold, then hang a tag on it (none: leave it erected and untagged). ``extra``
    goes into the build request."""
    body = {"project_id": site.project.id, "node_id": site.rsw, "purpose": "Access to tail pulley", **extra}
    made = await client.post("/api/v1/scaffolds/", json=body, headers=headers)
    assert made.status_code == 201, made.text
    sid = made.json()["id"]
    for step in ("approved", "erecting", "erected"):
        moved = await client.post(f"/api/v1/scaffolds/{sid}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    if tag is not None:
        inspection = {"kind": "handover", "tag": tag, **({"restrictions": restrictions} if restrictions else {})}
        tagged = await client.post(f"/api/v1/scaffolds/{sid}/inspections", json=inspection, headers=headers)
        assert tagged.status_code == 201, tagged.text
    return (await client.get(f"/api/v1/scaffolds/{sid}")).json()


async def _tag_history(db: AsyncSession, scaffold_id: int) -> list[StatusChange]:
    rows = await db.execute(
        select(StatusChange)
        .where(StatusChange.entity_type == "scaffold_tag", StatusChange.entity_id == scaffold_id)
        .order_by(StatusChange.id)
    )
    return list(rows.scalars())


async def _notices(db: AsyncSession, user_id: int, scaffold_id: int) -> int:
    rows = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.entity_type == "scaffold",
            Notification.entity_id == scaffold_id,
            Notification.title.contains(REASON),
        )
    )
    return len(list(rows.scalars()))


async def _stored(db: AsyncSession, scaffold_id: int) -> Scaffold:
    row = await db.scalar(select(Scaffold).where(Scaffold.id == scaffold_id).execution_options(populate_existing=True))
    assert row is not None
    return row


# --- the red-tag write-back ---------------------------------------------------------------------------------


async def test_a_breach_turns_a_standing_green_scaffold_red_once_and_tells_its_custodian_and_requester(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green", custodian_id=test_user_2["id"])
    assert (s["status"], s["tag_status"]) == ("in_use", "green")
    assert await scaffold_ready(db_session, site.rsw, date.today())

    wrote = await mark_breach_red(db_session, s["id"], project_id=site.project.id, item_reference="TW-14")
    await db_session.commit()
    assert wrote is True

    row = await _stored(db_session, s["id"])
    assert row.tag_status == "red"
    assert row.status == "in_use"  # the scaffold's own status is untouched
    history = await _tag_history(db_session, s["id"])
    assert [(h.from_status, h.to_status) for h in history] == [("green", "red")]
    assert "TW-14" in (history[0].note or "")
    assert await _notices(db_session, test_user_2["id"], s["id"]) == 1  # the custodian
    assert await _notices(db_session, test_user["id"], s["id"]) == 1  # the requester

    # running it again changes nothing: no second history entry, no second notice
    again = await mark_breach_red(db_session, s["id"], project_id=site.project.id, item_reference="TW-14")
    await db_session.commit()
    assert again is False
    assert len(await _tag_history(db_session, s["id"])) == 1
    assert await _notices(db_session, test_user_2["id"], s["id"]) == 1
    assert await _notices(db_session, test_user["id"], s["id"]) == 1


async def test_a_yellow_scaffold_is_written_red_too(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "yellow", restrictions="No loading above lift 3")
    assert s["tag_status"] == "yellow"
    assert await mark_breach_red(db_session, s["id"]) is True
    await db_session.commit()
    assert [(h.from_status, h.to_status) for h in await _tag_history(db_session, s["id"])] == [("yellow", "red")]


async def test_nothing_is_written_for_a_scaffold_that_is_not_standing(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    made = await client.post("/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw}, headers=headers)
    sid = made.json()["id"]  # only requested, so not standing

    assert await mark_breach_red(db_session, sid, project_id=site.project.id) is False
    await db_session.commit()
    row = await _stored(db_session, sid)
    assert (row.status, row.tag_status) == ("requested", "none")
    assert await _tag_history(db_session, sid) == []
    assert await _notices(db_session, test_user["id"], sid) == 0


async def test_a_dismantled_scaffold_is_left_alone(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, tag=None)
    for step in ("dismantle_requested", "dismantling", "dismantled"):
        moved = await client.post(f"/api/v1/scaffolds/{s['id']}/transition", json={"status": step}, headers=headers)
        assert moved.status_code == 200, moved.text
    before = len(await _tag_history(db_session, s["id"]))

    assert await mark_breach_red(db_session, s["id"]) is False
    await db_session.commit()
    assert len(await _tag_history(db_session, s["id"])) == before
    assert (await _stored(db_session, s["id"])).tag_status == "none"


async def test_nothing_is_written_for_a_scaffold_that_is_already_red(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "red", custodian_id=test_user["id"])
    assert s["tag_status"] == "red"

    assert await mark_breach_red(db_session, s["id"], project_id=site.project.id) is False
    await db_session.commit()
    assert await _tag_history(db_session, s["id"]) == []
    assert await _notices(db_session, test_user["id"], s["id"]) == 0


async def test_an_erected_scaffold_not_yet_tagged_is_written_red(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, tag=None)
    assert (s["status"], s["tag_status"]) == ("erected", "none")

    assert await mark_breach_red(db_session, s["id"]) is True
    await db_session.commit()
    assert [(h.from_status, h.to_status) for h in await _tag_history(db_session, s["id"])] == [("none", "red")]


async def test_the_module_setting_switches_the_write_back_off(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree, monkeypatch: pytest.MonkeyPatch
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")
    monkeypatch.setattr(breach, "RED_TAG_WRITE_BACK", False)

    assert await mark_breach_red(db_session, s["id"], project_id=site.project.id) is False
    await db_session.commit()
    assert (await _stored(db_session, s["id"])).tag_status == "green"
    assert await _tag_history(db_session, s["id"]) == []

    monkeypatch.setattr(breach, "RED_TAG_WRITE_BACK", True)
    assert await mark_breach_red(db_session, s["id"], project_id=site.project.id) is True


async def test_a_missing_scaffold_or_one_of_another_project_is_left_alone(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")
    other = await build_tree(db_session, "SC-2")

    assert await mark_breach_red(db_session, s["id"], project_id=other.project.id) is False
    assert await mark_breach_red(db_session, s["id"] + 1000) is False
    await db_session.commit()
    assert (await _stored(db_session, s["id"])).tag_status == "green"
    assert await _tag_history(db_session, s["id"]) == []


async def test_the_helper_flushes_but_leaves_the_commit_to_the_caller(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")

    assert await mark_breach_red(db_session, s["id"]) is True
    assert (await _stored(db_session, s["id"])).tag_status == "red"  # visible inside the unit of work
    await db_session.rollback()  # the caller decides: here it abandons the unit of work

    assert (await _stored(db_session, s["id"])).tag_status == "green"
    assert await _tag_history(db_session, s["id"]) == []


async def test_the_planner_blocks_on_the_red_tag_and_the_overdue_job_adds_no_second_history_entry(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")
    today = date.today()
    assert await scaffold_ready(db_session, site.rsw, today)

    assert await mark_breach_red(db_session, s["id"]) is True
    await db_session.commit()

    assert not await scaffold_ready(db_session, site.rsw, today)
    answer = (await client.get("/api/v1/scaffolds/readiness", params={"node_id": site.rsw})).json()
    assert answer["ready"] is False
    assert answer["blockers"][0]["reason"] == "red tag"

    # the hourly overdue job skips a scaffold that is already red, so tag history does not double up
    assert await mark_overdue(db_session) == 0
    assert len(await _tag_history(db_session, s["id"])) == 1

    # an inspection clears it, and a later breach writes it red again
    cleared = await client.post(
        f"/api/v1/scaffolds/{s['id']}/inspections", json={"kind": "periodic", "tag": "green"}, headers=headers
    )
    assert cleared.status_code == 201, cleared.text
    assert await scaffold_ready(db_session, site.rsw, today)
    assert await mark_breach_red(db_session, s["id"]) is True
    await db_session.commit()
    assert len(await _tag_history(db_session, s["id"])) == 2


# --- the state read -----------------------------------------------------------------------------------------


async def test_the_state_read_gives_status_effective_tag_and_next_due(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")

    now = await scaffold_state(db_session, s["id"], site.project.id)
    assert now is not None
    assert (now.scaffold_id, now.code, now.status, now.standing) == (s["id"], s["code"], "in_use", True)
    assert (now.effective_tag, now.inspection_overdue) == ("green", False)
    assert now.next_inspection_due is not None

    # the default interval is seven days: due again before the end of the eighth day
    later = await scaffold_state(db_session, s["id"], site.project.id, _utc_today() + timedelta(days=8))
    assert later is not None
    assert (later.effective_tag, later.inspection_overdue) == ("red", True)


async def test_the_state_read_uses_the_scaffolds_own_interval_and_adds_no_interval_field(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")
    changed = await client.patch(f"/api/v1/scaffolds/{s['id']}", json={"inspection_interval_days": 3}, headers=headers)
    assert changed.status_code == 200, changed.text

    soon = await scaffold_state(db_session, s["id"], day=_utc_today() + timedelta(days=2))
    late = await scaffold_state(db_session, s["id"], day=_utc_today() + timedelta(days=4))
    assert soon is not None
    assert late is not None
    assert (soon.effective_tag, soon.inspection_overdue) == ("green", False)
    assert (late.effective_tag, late.inspection_overdue) == ("red", True)
    assert {f.name for f in fields(ScaffoldState)} == {
        "scaffold_id",
        "code",
        "status",
        "standing",
        "effective_tag",
        "inspection_overdue",
        "next_inspection_due",
    }


async def test_a_scaffold_whose_inspection_is_overdue_reads_red_before_anything_is_written(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, tag=None)
    old = (_utc_today() - timedelta(days=8)).isoformat() + "T08:00:00+00:00"
    tagged = await client.post(
        f"/api/v1/scaffolds/{s['id']}/inspections",
        json={"kind": "handover", "tag": "yellow", "restrictions": "Light loads only", "inspected_at": old},
        headers=headers,
    )
    assert tagged.status_code == 201, tagged.text

    read = await scaffold_state(db_session, s["id"])
    assert read is not None
    assert (read.effective_tag, read.inspection_overdue) == ("red", True)
    assert (await _stored(db_session, s["id"])).tag_status == "yellow"  # read only: nothing was written


async def test_the_state_read_of_a_requested_scaffold_is_not_standing_and_has_no_tag(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    made = await client.post("/api/v1/scaffolds/", json={"project_id": site.project.id, "node_id": site.rsw}, headers=headers)
    read = await scaffold_state(db_session, made.json()["id"])
    assert read is not None
    assert (read.standing, read.effective_tag, read.inspection_overdue) == (False, "none", False)


async def test_the_state_read_of_a_missing_scaffold_or_one_of_another_project_is_none(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree
):
    headers = await _headers(client, db_session, test_user)
    s = await _scaffold(client, headers, site, "green")
    other = await build_tree(db_session, "SC-2")
    assert await scaffold_state(db_session, s["id"] + 1000) is None
    assert await scaffold_state(db_session, s["id"], other.project.id) is None
    assert await scaffold_state(db_session, s["id"], site.project.id) is not None

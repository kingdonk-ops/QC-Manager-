"""What an override changes about the counts and the can-proceed answers: plain pending, overridden-pending and open report
counts on the dossier gate; dossier scope reach; and overridden gates listed apart from plain ones, where only a dossier
attachment stops treating them as blocking."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.inspections import gates as gate_service
from src.modules.tasks import service as tasks
from tests.integration.quality_safety.test_quality_dossier_override import ONE_CHECK, World, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest_asyncio.fixture
async def world(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> World:
    return await make_world(client, db_session, test_user, test_user_2, tmp_path, monkeypatch)


async def _counts(w: World, base: str) -> tuple[int | None, int | None, int | None]:
    c = (await w.check(base))["counts"]
    return c["plain_pending_holds"], c["overridden_pending_holds"], c["open_reports"]


async def _proceed(w: World, kind: str, target: int) -> dict[str, Any]:
    r = await w.client.get(
        f"{API}/gates/can-proceed", params={"project_id": w.project_id, "attachment_kind": kind, "attachment_id": target}
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- counts on the dossier gate --------------------------------------------------------------------------


async def test_the_gate_counts_follow_a_hold_from_plain_pending_to_overridden_pending(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    assert await _counts(w, base) == (0, 0, 0)

    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    await w.gate(kind="surveillance", attachment_kind="node", attachment_id=w.tree.rsw)  # advisory: never counted
    assert await _counts(w, base) == (2, 0, 0)

    await w.override(base)
    assert await _counts(w, base) == (0, 2, 1)
    later = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    assert await _counts(w, base) == (1, 2, 1)  # the later hold is plain pending, the covered ones are not
    await w.release(later["id"])
    assert await _counts(w, base) == (0, 2, 1)


async def test_the_counts_reach_unattached_holds_and_holds_on_the_dossier_whatever_the_scope(world: World):
    w = world
    base = await w.dossier(w.tree.rsw2)
    dossier_id = int(base.rsplit("/", 1)[1])
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)  # another RSW, outside the scope
    loose = await w.gate()  # no attachment: counts whatever the scope
    on_dossier = await w.gate(attachment_kind="dossier", attachment_id=dossier_id)  # found even though the scope has nodes

    quality = await w.check(base)
    assert [f["reference"] for f in quality["findings"]] == [loose["number"], on_dossier["number"]]
    assert await _counts(w, base) == (2, 0, 0)
    await w.issue(base, 422)

    await w.override(base)
    assert await _counts(w, base) == (0, 2, 1)
    answer = await _proceed(w, "dossier", dossier_id)  # for a dossier attachment overridden gates do not block
    assert answer["can_proceed"] is True and answer["gate_numbers"] == []
    assert answer["overridden_gate_numbers"] == [on_dossier["number"]]
    await w.issue(base, 201)


# --- can-proceed: listed apart, and only a dossier attachment stops blocking ------------------------------


async def test_an_overridden_task_gate_is_listed_apart_and_still_blocks_the_task(world: World):
    w = world
    task_id = (await tasks.create_task(w.db, project_id=w.project_id, title="Hang the scaffold", created_by_id=None)).id
    base = await w.dossier()  # no scope nodes: every pending blocking gate of the project is in scope
    on_task = await w.gate(attachment_kind="task", attachment_id=task_id)
    assert (await _proceed(w, "task", task_id))["gate_numbers"] == [on_task["number"]]

    made = await w.override(base)
    assert on_task["number"] in made["gate_numbers"]
    answer = await _proceed(w, "task", task_id)
    assert answer["can_proceed"] is False  # overridden gates still block every kind but a dossier
    assert answer["gate_numbers"] == [] and answer["overridden_gate_numbers"] == [on_task["number"]]
    assert answer["overridden_gate_ids"] == [on_task["id"]]
    assert (await w.gates())[on_task["number"]]["status"] == "pending"


async def test_a_dossier_scoped_override_does_not_reach_a_task_gate_and_issue_ignores_it(world: World):
    w = world
    task_id = (await tasks.create_task(w.db, project_id=w.project_id, title="Hang the scaffold", created_by_id=None)).id
    base = await w.dossier(w.tree.asset)  # a task is not in the scope
    on_task = await w.gate(attachment_kind="task", attachment_id=task_id)

    nothing = await w.override(base, 409)
    assert "Nothing blocks" in str(nothing)
    await w.issue(base, 201)  # issue neither refuses nor needs anything for the task
    answer = await _proceed(w, "task", task_id)
    assert answer["can_proceed"] is False and answer["gate_numbers"] == [on_task["number"]]
    assert answer["overridden_gate_numbers"] == []


async def test_an_overridden_gate_and_an_earlier_unreleased_hold_point_are_listed_apart(world: World):
    w = world
    pid = w.project_id
    form_body = {"project_id": pid, "name": "ITR", "area": "qa_itp", "is_formal": True, "sections": ONE_CHECK}
    form = (await w.client.post(f"{API}/templates/", json=form_body, headers=w.headers)).json()
    activities = [
        {"title": f"Activity {n}", "form_template_id": form["id"], "points": points}
        for n, points in enumerate(({"contractor": "H"}, {"contractor": "R"}), start=1)
    ]
    plan = await w.client.post(
        f"{API}/templates/",
        json={"project_id": pid, "name": "Plan", "kind": "itp", "activities": activities},
        headers=w.headers,
    )
    assert plan.status_code == 201, plan.text
    made = await w.client.post(
        f"{API}/itp/instances", json={"template_id": plan.json()["id"], "node_id": w.tree.rsw}, headers=w.headers
    )
    assert made.status_code == 201, made.text
    hold_line, next_line = made.json()["lines"]

    held = await w.gate(attachment_kind="inspection", attachment_id=next_line["id"])
    # The dossier gate refuses an unreleased plan hold point, so the annotation is applied directly here.
    await gate_service.annotate_pending(w.db, pid, [held["number"]], 1, "DOSS-OVR-01")
    await w.db.commit()

    answer = await _proceed(w, "inspection", next_line["id"])
    assert answer["can_proceed"] is False
    assert answer["gate_numbers"] == [] and answer["overridden_gate_numbers"] == [held["number"]]
    assert [h["code"] for h in answer["hold_points"]] == [hold_line["code"]]

    on_first = await w.gate(attachment_kind="inspection", attachment_id=hold_line["id"])
    await gate_service.annotate_pending(w.db, pid, [on_first["number"]], 1, "DOSS-OVR-01")
    await w.db.commit()
    first = await _proceed(w, "inspection", hold_line["id"])  # no earlier hold point; the overridden gate still blocks
    assert first["hold_points"] == [] and first["can_proceed"] is False
    assert first["overridden_gate_numbers"] == [on_first["number"]]

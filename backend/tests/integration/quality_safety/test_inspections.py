"""Inspections: templates, snapshotting, scoring with numeric limits, photo rule, deficiency tasks and NCRs, trends."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state, subscribe
from src.infrastructure.modules.events import _handlers
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    "inspections.read",
    "inspections.create",
    "inspections.update",
    "inspections.delete",
    "inspections.transition",
    "ncr.read",
    "tasks.read",
    "files.read",
    "files.upload",
)

TEMPLATE = {
    "name": "Hot pipe insulation",
    "trade": "Insulation",
    "activity": "Mineral wool + aluminium cladding",
    "sections": [
        {
            "title": "Insulation",
            "items": [
                {"text": "Joints staggered and butted", "requires_photo_on_fail": True},
                {
                    "text": "Insulation thickness",
                    "response_type": "numeric",
                    "unit": "mm",
                    "min_value": 50,
                    "max_value": 55,
                },
            ],
        },
        {
            "title": "Cladding",
            "items": [
                {"text": "Cladding overlap", "response_type": "numeric", "unit": "mm", "min_value": 50},
                {"text": "Penetrations sealed"},
            ],
        },
    ],
}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(code="Q-1", name="LNG Train 3")
    db_session.add(p)
    await db_session.commit()
    return p


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def test_starter_templates_seed_once_and_templates_version(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    listed = (await client.get("/api/v1/inspections/templates/", params={"project_id": project.id})).json()
    names = sorted(t["name"] for t in listed["data"])
    assert names == ["Pipe insulation & cladding", "Protective coating DFT", "Refractory lining"]
    dft = next(t for t in listed["data"] if t["name"] == "Protective coating DFT")
    assert any(i["response_type"] == "numeric" and i["unit"] == "µm" for s in dft["sections"] for i in s["items"])

    await client.delete(f"/api/v1/inspections/templates/{dft['id']}", headers=headers)
    again = (await client.get("/api/v1/inspections/templates/", params={"project_id": project.id})).json()
    assert again["total_count"] == 2  # deleting a starter sticks

    reseeded = await client.post("/api/v1/inspections/templates/starter", json={"project_id": project.id}, headers=headers)
    assert [t["name"] for t in reseeded.json()] == ["Protective coating DFT"]

    created = (
        await client.post("/api/v1/inspections/templates/", json={"project_id": project.id, **TEMPLATE}, headers=headers)
    ).json()
    assert (created["version"], created["item_count"]) == (1, 4)
    copy = (await client.post(f"/api/v1/inspections/templates/{created['id']}/duplicate", headers=headers)).json()
    assert copy["name"] == "Hot pipe insulation (copy)" and copy["item_count"] == 4

    renamed = await client.patch(f"/api/v1/inspections/templates/{created['id']}", json={"name": "Renamed"}, headers=headers)
    assert renamed.json()["version"] == 1
    sections = TEMPLATE["sections"][:1]
    edited = await client.patch(f"/api/v1/inspections/templates/{created['id']}", json={"sections": sections}, headers=headers)
    assert (edited.json()["version"], edited.json()["item_count"]) == (2, 2)

    bad = {
        "project_id": project.id,
        "name": "x",
        "sections": [{"title": "s", "items": [{"text": "t", "min_value": 5, "max_value": 1}]}],
    }
    assert (await client.post("/api/v1/inspections/templates/", json=bad, headers=headers)).status_code == 422


async def test_inspection_scores_and_raises_tasks_and_ncrs(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    seen: list[dict[str, Any]] = []

    @subscribe("inspections.item.ncr_requested")
    async def capture(event: str, payload: dict[str, Any]) -> None:
        seen.append(payload)

    try:
        template = (
            await client.post("/api/v1/inspections/templates/", json={"project_id": project.id, **TEMPLATE}, headers=headers)
        ).json()
        made = await client.post(
            "/api/v1/inspections/",
            json={"project_id": project.id, "template_id": template["id"], "location": "Pipe rack 3", "area": "Level 2"},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        inspection = made.json()
        assert (inspection["code"], inspection["status"], inspection["trade"], inspection["total"]) == (
            "INS-001",
            "planned",
            "Insulation",
            4,
        )
        joints, thickness, overlap, sealed = inspection["items"]
        assert (thickness["min_value"], thickness["max_value"], thickness["unit"]) == (50, 55, "mm")

        # Editing the template afterwards doesn't touch the inspection's copy.
        await client.patch(
            f"/api/v1/inspections/templates/{template['id']}", json={"sections": TEMPLATE["sections"][:1]}, headers=headers
        )

        filled = await client.patch(
            f"/api/v1/inspections/{inspection['id']}/items",
            json={
                "items": [
                    {"id": joints["id"], "result": "fail", "notes": "Gaps at elbow"},
                    {"id": thickness["id"], "result": "pass", "reading": 48},  # below 50: a fail whatever was chosen
                    {"id": overlap["id"], "reading": 60},  # above the minimum, no maximum: pass
                    {"id": sealed["id"], "result": "na"},
                ]
            },
            headers=headers,
        )
        assert filled.status_code == 200, filled.text
        scored = filled.json()
        assert [i["outcome"] for i in scored["items"]] == ["fail", "fail", "pass", "na"]
        assert (scored["passed"], scored["failed"], scored["not_applicable"], scored["unanswered"]) == (1, 2, 1, 0)
        assert scored["pass_rate"] == 33.3  # 1 / (1 + 2), N/A excluded
        assert scored["status"] == "in_progress" and scored["inspected_date"]
        assert len(scored["items"]) == 4

        # The failed joints item needs a photo before completing.
        follow_ups = [{"item_id": thickness["id"], "action": "ncr", "severity": "major", "assignee_id": test_user_2["id"]}]
        refused = await client.post(
            f"/api/v1/inspections/{inspection['id']}/complete", json={"follow_ups": follow_ups}, headers=headers
        )
        assert refused.status_code == 422 and "photo" in refused.text
        photo = await client.post(
            "/api/v1/files/",
            data={"project_id": str(project.id), "entity_type": "inspection_item", "entity_id": str(joints["id"])},
            files={"file": ("elbow.jpg", b"\xff\xd8\xff fake jpeg", "image/jpeg")},
            headers=headers,
        )
        assert photo.status_code == 201, photo.text

        done = await client.post(
            f"/api/v1/inspections/{inspection['id']}/complete",
            json={"follow_ups": follow_ups, "default_assignee_id": test_user_2["id"], "default_due_date": "2026-12-01"},
            headers=headers,
        )
        assert done.status_code == 200, done.text
        completed = done.json()
        assert completed["status"] == "completed" and completed["completed_at"]
        items = {i["id"]: i for i in completed["items"]}
        assert items[joints["id"]]["photo_count"] == 1
        assert items[joints["id"]]["follow_up"] == "task" and items[joints["id"]]["task_id"]
        assert items[thickness["id"]]["follow_up"] == "ncr" and items[thickness["id"]]["ncr_id"]
        assert items[thickness["id"]]["task_id"] is None
        assert items[overlap["id"]]["task_id"] is None and items[overlap["id"]]["ncr_id"] is None

        tasks = (
            await client.get(
                "/api/v1/tasks/",
                params={"project_id": project.id, "entity_type": "inspection", "entity_id": inspection["id"]},
            )
        ).json()["data"]
        assert len(tasks) == 1
        assert tasks[0]["title"].startswith("INS-001 #1: Joints staggered")
        assert (tasks[0]["assignee_id"], tasks[0]["due_date"], tasks[0]["priority"]) == (
            test_user_2["id"],
            "2026-12-01",
            "high",
        )

        ncr = (await client.get(f"/api/v1/ncr/{items[thickness['id']]['ncr_id']}")).json()
        assert (ncr["code"], ncr["source"], ncr["severity"], ncr["status"]) == ("NCR-001", "inspection", "major", "open")
        assert (ncr["inspection_id"], ncr["inspection_item_id"]) == (inspection["id"], thickness["id"])
        assert ncr["source_reference"] == "INS-001 item 2"
        assert "Reading 48 mm" in ncr["description"] and "Acceptance 50-55 mm" in ncr["description"]
        assert ncr["location"] == "Pipe rack 3 / Level 2"
        assert ncr["responsible_user_id"] == test_user_2["id"]

        assert seen == [
            {
                "project_id": project.id,
                "inspection_id": inspection["id"],
                "item_id": thickness["id"],
                "ncr_id": ncr["id"],
                "title": "INS-001 #2: Insulation thickness",
            }
        ]

        locked = await client.patch(
            f"/api/v1/inspections/{inspection['id']}/items",
            json={"items": [{"id": sealed["id"], "result": "pass"}]},
            headers=headers,
        )
        assert locked.status_code == 422

        # Reopen, fix, recomplete: existing follow-ups aren't raised twice.
        reopened = await client.patch(
            f"/api/v1/inspections/{inspection['id']}/status", json={"status": "in_progress"}, headers=headers
        )
        assert reopened.json()["status"] == "in_progress"
        await client.patch(
            f"/api/v1/inspections/{inspection['id']}/items",
            json={"items": [{"id": sealed["id"], "result": "pass"}]},
            headers=headers,
        )
        again = await client.post(f"/api/v1/inspections/{inspection['id']}/complete", json={}, headers=headers)
        assert again.json()["pass_rate"] == 50.0
        tasks_after = (
            await client.get(
                "/api/v1/tasks/",
                params={"project_id": project.id, "entity_type": "inspection", "entity_id": inspection["id"]},
            )
        ).json()
        assert tasks_after["total_count"] == 1
        assert (await client.get("/api/v1/ncr/", params={"project_id": project.id})).json()["total_count"] == 1
        assert len(seen) == 1

        closed = await client.patch(
            f"/api/v1/inspections/{inspection['id']}/status", json={"status": "closed"}, headers=headers
        )
        assert closed.json()["status"] == "closed"
        history = (await client.get(f"/api/v1/inspections/{inspection['id']}/history")).json()
        assert [h["to_status"] for h in history] == [
            "planned",
            "in_progress",
            "completed",
            "in_progress",
            "completed",
            "closed",
        ]

        pdf = await client.get(f"/api/v1/inspections/{inspection['id']}/report.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    finally:
        _handlers.remove(("inspections.item.ncr_requested", capture))


async def test_unanswered_items_block_completion_and_trends_group(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    template = (
        await client.post(
            "/api/v1/inspections/templates/",
            json={
                "project_id": project.id,
                "name": "Coating",
                "trade": "Coatings",
                "sections": [
                    {
                        "title": "DFT",
                        "items": [
                            {"text": "DFT", "response_type": "numeric", "unit": "µm", "min_value": 250, "max_value": 350},
                            {"text": "No runs or sags"},
                        ],
                    }
                ],
            },
            headers=headers,
        )
    ).json()

    async def inspect(location: str, dft: float, finish: str, *, complete: bool = True) -> dict:
        made = (
            await client.post(
                "/api/v1/inspections/",
                json={"project_id": project.id, "template_id": template["id"], "location": location},
                headers=headers,
            )
        ).json()
        dft_item, finish_item = made["items"]
        await client.patch(
            f"/api/v1/inspections/{made['id']}/items",
            json={"items": [{"id": dft_item["id"], "reading": dft}, {"id": finish_item["id"], "result": finish}]},
            headers=headers,
        )
        if complete:
            done = await client.post(
                f"/api/v1/inspections/{made['id']}/complete",
                json={
                    "follow_ups": [
                        {"item_id": dft_item["id"], "action": "none"},
                        {"item_id": finish_item["id"], "action": "none"},
                    ]
                },
                headers=headers,
            )
            assert done.status_code == 200, done.text
            return done.json()
        return made

    partial = (
        await client.post(
            "/api/v1/inspections/", json={"project_id": project.id, "template_id": template["id"]}, headers=headers
        )
    ).json()
    planned = await client.post(f"/api/v1/inspections/{partial['id']}/complete", json={}, headers=headers)
    assert planned.status_code == 422
    await client.patch(
        f"/api/v1/inspections/{partial['id']}/items",
        json={"items": [{"id": partial["items"][0]["id"], "reading": 300}]},
        headers=headers,
    )
    unanswered = await client.post(f"/api/v1/inspections/{partial['id']}/complete", json={}, headers=headers)
    assert unanswered.status_code == 422 and "unanswered" in unanswered.text
    forced = await client.post(
        f"/api/v1/inspections/{partial['id']}/complete", json={"allow_unanswered": True}, headers=headers
    )
    assert forced.json()["pass_rate"] == 100.0 and forced.json()["unanswered"] == 1

    await inspect("Tank 1", 300, "pass")  # 100 %
    await inspect("Tank 1", 400, "pass")  # 50 %: DFT over the maximum
    await inspect("Tank 2", 200, "fail")  # 0 %
    await inspect("Tank 2", 300, "pass", complete=False)  # not completed: left out of trends

    by_location = (
        await client.get("/api/v1/inspections/trends", params={"project_id": project.id, "group_by": "location"})
    ).json()
    groups = {g["key"]: g for g in by_location["groups"]}
    assert set(groups) == {"Tank 1", "Tank 2", "Unspecified"}
    assert (groups["Tank 1"]["inspections"], groups["Tank 1"]["passed"], groups["Tank 1"]["failed"]) == (2, 3, 1)
    assert groups["Tank 1"]["pass_rate"] == 75.0
    assert [p["pass_rate"] for p in groups["Tank 1"]["points"]] == [100.0, 50.0]
    assert groups["Tank 2"]["pass_rate"] == 0.0
    assert groups["Tank 1"]["monthly"][0]["inspections"] == 2

    by_trade = (await client.get("/api/v1/inspections/trends", params={"project_id": project.id})).json()
    assert [(g["key"], g["inspections"]) for g in by_trade["groups"]] == [("Coatings", 4)]

    register = (
        await client.get("/api/v1/inspections/", params={"project_id": project.id, "status": "completed", "location": "tank 1"})
    ).json()
    assert register["total_count"] == 2 and register["data"][0]["items"] == []


async def test_inspections_follow_project_visibility(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    template = (
        await client.post("/api/v1/inspections/templates/", json={"project_id": project.id, **TEMPLATE}, headers=headers)
    ).json()
    made = (
        await client.post(
            "/api/v1/inspections/", json={"project_id": project.id, "template_id": template["id"]}, headers=headers
        )
    ).json()
    await _as(client, db_session, test_user_2, *(p for p in PERMS if p != "projects.read"))
    assert (await client.get(f"/api/v1/inspections/{made['id']}")).status_code == 404
    assert (await client.get("/api/v1/inspections/", params={"project_id": project.id})).status_code == 404

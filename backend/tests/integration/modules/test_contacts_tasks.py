"""Contacts (directory, companies, project roles, import) and Tasks (board, WIP, notifications)."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

CONTACTS = ("contacts.read", "contacts.create", "contacts.update", "contacts.delete", "contacts.import", "projects.read")
TASKS = ("tasks.read", "tasks.create", "tasks.update", "tasks.delete", "projects.read")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant")
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def test_contacts_with_companies_and_project_roles(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *CONTACTS)

    company = (
        await client.post(
            "/api/v1/contacts/companies/", json={"name": "Acme Scaffolding", "type": "subcontractor"}, headers=headers
        )
    ).json()
    created = await client.post(
        "/api/v1/contacts/",
        json={
            "first_name": "Jo",
            "last_name": "Bloggs",
            "company_id": company["id"],
            "type": "subcontractor",
            "email": "jo@acme.example",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    contact = created.json()
    assert contact["full_name"] == "Jo Bloggs"
    assert contact["company_name"] == "Acme Scaffolding"

    linked = await client.put(
        f"/api/v1/contacts/projects/{project.id}/{contact['id']}", json={"role": "Scaffold supervisor"}, headers=headers
    )
    assert linked.json()["projects"] == [
        {"project_id": project.id, "project_code": "P-1", "project_name": "Plant", "role": "Scaffold supervisor"}
    ]

    by_project = (await client.get("/api/v1/contacts/", params={"project_id": project.id})).json()["data"]
    by_search = (await client.get("/api/v1/contacts/", params={"search": "acme"})).json()["data"]
    assert [c["id"] for c in by_project] == [contact["id"]]
    assert [c["id"] for c in by_search] == [contact["id"]]
    assert (await client.get("/api/v1/contacts/companies/")).json()["data"][0]["contact_count"] == 1


async def test_import_maps_columns_detects_duplicates_and_dry_runs(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    headers = await _as(client, db_session, test_user, *CONTACTS)
    await client.post("/api/v1/contacts/", json={"first_name": "Existing", "email": "dup@example.com"}, headers=headers)
    csv = (
        b"Name,E-mail,Company,Type\n"
        b"Alex Smith,alex@example.com,Northwind,client\n"
        b"Same Person,DUP@example.com,,supplier\n"
        b",nobody@example.com,,\n"
    )
    upload = {"file": ("contacts.csv", csv, "text/csv")}

    preview = (await client.post("/api/v1/contacts/import/preview", files=upload, headers=headers)).json()
    assert preview["mapping"] == {"full_name": "Name", "email": "E-mail", "company": "Company", "type": "Type"}

    dry = (await client.post("/api/v1/contacts/import", files=upload, data={"dry_run": "true"}, headers=headers)).json()
    assert (dry["created"], dry["skipped"], len(dry["duplicates"]), len(dry["errors"])) == (1, 2, 1, 1)
    assert (await client.get("/api/v1/contacts/")).json()["total_count"] == 1

    real = (await client.post("/api/v1/contacts/import", files=upload, data={"on_duplicate": "update"}, headers=headers)).json()
    assert (real["created"], real["updated"]) == (1, 1)
    contacts = {c["email"]: c for c in (await client.get("/api/v1/contacts/")).json()["data"]}
    assert contacts["alex@example.com"]["company_name"] == "Northwind"
    assert contacts["dup@example.com"]["type"] == "supplier"


async def test_a_task_board_moves_cards_and_enforces_wip(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *TASKS)

    def make(title: str, **kw):
        return client.post("/api/v1/tasks/", json={"project_id": project.id, "title": title, **kw}, headers=headers)

    first = (
        await make(
            "Install insulation level 2", type="construction", type_fields={"location": "L2"}, assignee_id=test_user_2["id"]
        )
    ).json()
    second = (await make("Order cladding", type="procurement", priority="high")).json()
    assert (first["code"], second["code"]) == ("TASK-001", "TASK-002")

    await client.put(f"/api/v1/tasks/board/{project.id}/limits", json={"wip_limits": {"in_progress": 1}}, headers=headers)
    moved = await client.post(f"/api/v1/tasks/{first['id']}/move", json={"status": "in_progress"}, headers=headers)
    assert moved.json()["status"] == "in_progress"
    blocked = await client.post(f"/api/v1/tasks/{second['id']}/move", json={"status": "in_progress"}, headers=headers)
    assert blocked.status_code == 422
    forced = await client.post(
        f"/api/v1/tasks/{second['id']}/move",
        json={"status": "in_progress", "before_id": first["id"], "override_wip": True},
        headers=headers,
    )
    assert forced.status_code == 200

    board = (await client.get(f"/api/v1/tasks/board/{project.id}")).json()
    column = next(c for c in board["columns"] if c["status"] == "in_progress")
    assert [t["code"] for t in column["tasks"]] == ["TASK-002", "TASK-001"]
    assert column["wip_limit"] == 1

    await _login(client, test_user_2)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert {n["category"] for n in inbox} == {"assignment", "status"}


async def test_tasks_filter_and_link_to_records(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *TASKS)
    await client.post(
        "/api/v1/tasks/",
        json={
            "project_id": project.id,
            "title": "Answer RFI",
            "entity_type": "rfi",
            "entity_id": 4,
            "due_date": "2020-01-01",
            "assignee_id": test_user["id"],
        },
        headers=headers,
    )
    await client.post("/api/v1/tasks/", json={"project_id": project.id, "title": "Other"}, headers=headers)

    def codes(**params):
        return client.get("/api/v1/tasks/", params={"project_id": project.id, **params})

    assert [t["title"] for t in (await codes(entity_type="rfi", entity_id=4)).json()["data"]] == ["Answer RFI"]
    overdue = (await codes(overdue=True)).json()["data"]
    assert [t["overdue"] for t in overdue] == [True]
    assert (await codes(assignee="me")).json()["total_count"] == 1


async def test_tasks_need_a_visible_project(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "tasks.read", "tasks.create")

    assert (
        await client.post("/api/v1/tasks/", json={"project_id": project.id, "title": "x"}, headers=headers)
    ).status_code == 404

"""The contacts export and the task assignee lookup the Tasks, Contacts and Meetings screens use."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def test_contacts_export_as_excel_and_csv(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "exporter", "contacts.read", "contacts.create")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    await client.post("/api/v1/contacts/", json={"first_name": "Jo", "last_name": "Bloggs", "tags": ["hse"]}, headers=headers)
    await client.post("/api/v1/contacts/", json={"first_name": "Al", "type": "client"}, headers=headers)

    xlsx = await client.get("/api/v1/contacts/export", params={"format": "xlsx"})
    assert xlsx.status_code == 200
    sheet = load_workbook(io.BytesIO(xlsx.content)).active
    assert sheet is not None
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][:2] == ("First name", "Last name")
    assert {r[0] for r in rows[1:]} == {"Jo", "Al"}

    csv = await client.get("/api/v1/contacts/export", params={"format": "csv", "type": "client"})
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.content.decode("utf-8-sig").strip().splitlines()
    assert len(lines) == 2 and lines[1].startswith("Al,")


async def test_assignees_lists_active_accounts(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "reader", "tasks.read")
    await _login(client, test_user)

    everyone = (await client.get("/api/v1/tasks/assignees")).json()
    assert {test_user["id"], test_user_2["id"]} <= {p["id"] for p in everyone}
    found = (await client.get("/api/v1/tasks/assignees", params={"search": test_user_2["name"]})).json()
    assert [p["id"] for p in found] == [test_user_2["id"]]

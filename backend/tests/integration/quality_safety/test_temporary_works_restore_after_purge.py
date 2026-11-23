"""A restore that arrives after the scheduled purge has removed the record answers not-found, not a server error. The
purge is run directly with a pinned moment."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
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
MANAGER = (
    "projects.read",
    *(f"temporary_works.{a}" for a in ("read", "create", "update", "delete", "transition", "issue", "return_to_draft")),
)
RESTORER = ("projects.read", "temporary_works.read", "temporary_works.restore")


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


async def test_restoring_a_purged_item_or_permit_answers_not_found(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, site: Tree
):
    manager = await _as(client, db_session, test_user, *MANAGER)
    made = await client.post(
        f"{API}/",
        json={"project_id": site.project.id, "reference": "TW-P", "title": "Props", "family": "propping"},
        headers=manager,
    )
    assert made.status_code == 201, made.text
    lone = made.json()
    parent = (
        await client.post(
            f"{API}/",
            json={"project_id": site.project.id, "reference": "TW-Q", "title": "Props", "family": "propping"},
            headers=manager,
        )
    ).json()
    permit = (
        await client.post(f"{API}/permits/?item_id={parent['id']}", json={"number": "P-1", "kind": "load"}, headers=manager)
    ).json()
    assert (await client.delete(f"{API}/permits/{permit['id']}", headers=manager)).status_code == 200
    assert (await client.delete(f"{API}/{lone['id']}", headers=manager)).status_code == 200

    purged = await purge_expired(db_session, datetime.now(UTC) + timedelta(days=31))
    assert (purged.items, purged.permits) == (1, 1)
    assert await db_session.get(TemporaryWorksItem, lone["id"]) is None
    assert await db_session.get(TemporaryWorksPermit, permit["id"]) is None
    entries = await db_session.scalars(select(AuditEntry.action).where(AuditEntry.action.like("temporary_works.%.purged")))
    assert sorted(entries) == ["temporary_works.item.purged", "temporary_works.permit.purged"]

    restorer = await _as(client, db_session, test_user_2, *RESTORER)
    for path in (f"trash/items/{lone['id']}/restore", f"trash/permits/{permit['id']}/restore"):
        gone = await client.post(f"{API}/{path}", headers=restorer)
        assert gone.status_code == 404, (path, gone.text)

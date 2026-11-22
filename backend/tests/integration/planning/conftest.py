"""A project with a Site / Area / Asset / RSW breakdown, two supervisors and every planning permission."""

from dataclasses import dataclass
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

PERMS = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "asset_tree.update",
    "asset_tree.configure",
    *(f"planner.{a}" for a in ("read", "create", "update", "delete", "assign", "transition", "export")),
    *(f"workface_log.{a}" for a in ("read", "create", "update", "delete", "submit", "review", "export")),
    *(f"handover.{a}" for a in ("read", "create", "update", "delete", "submit", "respond", "export")),
)


@dataclass
class Site:
    project: Project
    headers: dict[str, str]
    nodes: dict[str, dict[str, Any]]
    user: dict
    other: dict

    async def login(self, client: AsyncClient, who: dict) -> None:
        self.headers = {"X-CSRF-Token": await _login(client, who)}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest_asyncio.fixture
async def site(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> Site:
    project = Project(code="P-PLAN", name="Gas Plant")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "planner-a", *PERMS)
    await _grant(db_session, test_user_2["id"], "planner-b", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    applied = await client.post(
        "/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers
    )
    assert applied.status_code == 200, applied.text

    async def node(key: str, level: str, code: str, parent: str | None = None, **extra: Any) -> None:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={
                "project_id": project.id,
                "level_key": level,
                "code": code,
                "parent_id": nodes[parent]["id"] if parent else None,
                **extra,
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        nodes[key] = r.json()

    nodes: dict[str, dict[str, Any]] = {}
    await node("site", "site", "KAR")
    await node("area", "area", "A1", "site")
    await node("asset", "asset", "101", "area")
    await node("rsw1", "rsw", "101.1", "asset", budget_qty="100", uom="m2")
    await node("rsw2", "rsw", "101.2", "asset", budget_qty="20", uom="m2")
    await node("asset2", "asset", "102", "area")
    await node("rsw3", "rsw", "102.1", "asset2", budget_qty="50", uom="Lm")
    return Site(project=project, headers=headers, nodes=nodes, user=test_user, other=test_user_2)

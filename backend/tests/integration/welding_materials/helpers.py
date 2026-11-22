"""Shared setup: a project with the RSW breakdown, a work anchor, and a signed-in user holding every permission."""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.files.models import StoredFile
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

PERMS = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "asset_tree.configure",
    *(f"welding.{a}" for a in ("read", "create", "update", "delete", "review", "approve", "export")),
    *(f"materials.{a}" for a in ("read", "create", "update", "delete", "upload", "review", "approve", "export")),
    *(f"calibration.{a}" for a in ("read", "create", "update", "delete", "upload", "transition", "export")),
)


@dataclass
class World:
    client: AsyncClient
    db: AsyncSession
    project: Project
    headers: dict[str, str]
    site: dict
    asset: dict
    rsw: dict

    async def post(self, path: str, body: dict | None = None, expect: int | None = None, **params: Any) -> dict:
        r = await self.client.post(path, json=body or {}, headers=self.headers, params=params or None)
        if expect is not None:
            assert r.status_code == expect, r.text
        else:
            assert r.status_code in (200, 201), r.text
        return r.json()

    async def get(self, path: str, expect: int = 200, **params: Any) -> Any:
        r = await self.client.get(path, params=params or None)
        assert r.status_code == expect, r.text
        return r.json()

    async def patch(self, path: str, body: dict, expect: int = 200) -> dict:
        r = await self.client.patch(path, json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def node(self, level: str, code: str, parent: int | None = None, **extra: Any) -> dict:
        return await self.post(
            "/api/v1/asset-tree/nodes/",
            {"project_id": self.project.id, "level_key": level, "code": code, "parent_id": parent, **extra},
        )

    async def file(self, name: str = "cert.pdf") -> int:
        f = StoredFile(
            name=name,
            content_type="application/pdf",
            size=10,
            sha256="0" * 64,
            storage_key=f"xx/{name}",
            uploaded_by_id=None,
            project_id=self.project.id,
        )
        self.db.add(f)
        await self.db.commit()
        return f.id


async def world(client: AsyncClient, db: AsyncSession, user: dict, code: str = "P-1") -> World:
    project = Project(code=code, name="Plant")
    db.add(project)
    await db.commit()
    await _grant(db, user["id"], f"k4-{code}", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, user)}
    applied = await client.post(
        "/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers
    )
    assert applied.status_code == 200, applied.text
    w = World(client, db, project, headers, {}, {}, {})
    w.site = await w.node("site", "S")
    w.asset = await w.node("asset", "101", w.site["id"])
    w.rsw = await w.node("rsw", "101.1", w.asset["id"], planned_start="2030-01-10")
    return w

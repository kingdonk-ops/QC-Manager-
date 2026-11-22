#!/usr/bin/env python3
"""Scaffold a full-stack module: backend package, frontend folder, registry entry, smoke test.

    python scripts/new_module.py punch_list --display "Punch List" --depends projects

Then generate its migration and the typed client (the script prints the commands).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

BACKEND_FILES: dict[str, str] = {
    "__init__.py": '''"""{display}."""


async def on_startup() -> None:
    """Runs once when the app starts, after the modules it depends on. Delete it if unused."""
''',
    "manifest.py": '''from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="{name}",
    version="0.1.0",
    display_name="{display}",
    description="TODO: one sentence on what {display} does.",
    depends=({depends}),
)
''',
    "permissions.py": '''from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("{name}")
class {Class}PermissionName(StrEnum):
    READ = "{name}.read"
    EDIT = "{name}.edit"
''',
    "models.py": '''from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class {Class}Item(Base, TimestampMixin):
    __tablename__ = "{name}_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
''',
    "schemas.py": '''from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText


class {Class}ItemCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None


class {Class}ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime | None = None
''',
    "service.py": '''from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from .models import {Class}Item
from .schemas import {Class}ItemRead


class {Class}Service:
    async def page(self, db: AsyncSession, skip: int, limit: int) -> dict[str, Any]:
        total = await db.scalar(select(func.count()).select_from({Class}Item))
        rows = (await db.execute(select({Class}Item).order_by({Class}Item.id).offset(skip).limit(limit))).scalars()

        return {{"data": [{Class}ItemRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total or 0}}

    async def create(self, db: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
        item = {Class}Item(**values)
        db.add(item)
        await db.commit()
        await publish("{name}.item.created", {{"item_id": item.id}})

        return {Class}ItemRead.model_validate(item).model_dump(mode="json")
''',
    "router.py": '''"""Mounted at /api/v1/{prefix}."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import ItemsPerPageDep, PageDep
from .permissions import {Class}PermissionName
from .schemas import {Class}ItemCreate, {Class}ItemRead
from .service import {Class}Service

router = APIRouter(tags=["{display}"])

Service = Annotated[{Class}Service, Depends({Class}Service)]


@router.get(
    "/items/",
    response_model=PaginatedListResponse[{Class}ItemRead],
    summary="List {display} Items",
    dependencies=[require_permissions({Class}PermissionName.READ.value)],
)
async def list_items(
    db: AsyncSessionDep, _: CurrentUserDep, service: Service, page: PageDep = 1, items_per_page: ItemsPerPageDep = 50
) -> Any:
    data = await service.page(db, compute_offset(page, items_per_page), items_per_page)

    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/items/",
    response_model={Class}ItemRead,
    status_code=201,
    summary="Add a {display} Item",
    dependencies=[require_permissions({Class}PermissionName.EDIT.value)],
)
async def create_item(values: {Class}ItemCreate, db: AsyncSessionDep, _: CurrentUserDep, service: Service) -> Any:
    return await service.create(db, values.model_dump())
''',
    "events.py": '''"""Reactions to other modules' events. Imported at startup; delete it if unused.

from ...infrastructure.modules import subscribe


@subscribe("projects.project.created")
async def on_project_created(event: str, payload: dict) -> None:
    ...
"""
''',
}

BACKEND_TEST = '''import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def test_items_round_trip(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "{name}-editor", "{name}.read", "{name}.edit")
    headers = {{"X-CSRF-Token": await _login(client, test_user)}}

    created = await client.post("/api/v1/{prefix}/items/", json={{"name": "First"}}, headers=headers)
    listed = await client.get("/api/v1/{prefix}/items/")

    assert created.status_code == 201, created.text
    assert [i["name"] for i in listed.json()["data"]] == ["First"]
'''

FRONTEND_FILES: dict[str, str] = {
    "manifest.ts": """import {{ lazy }} from 'react'
import {{ Boxes }} from 'lucide-react'
import type {{ ModuleManifest }} from '../_types'

export const manifest: ModuleManifest = {{
  id: '{name}',
  name: '{display}',
  version: '0.1.0',
  depends: [{depends_ts}],
  routes: [
    {{
      path: '/{prefix}',
      component: lazy(() => import('./{kebab}-page')),
      permission: '{name}.read',
    }},
  ],
  navItems: [
    {{
      labelKey: 'nav.{name}',
      to: '/{prefix}',
      icon: Boxes,
      group: 'general',
      order: 50,
      permission: '{name}.read',
    }},
  ],
  messages: {{
    en: {{
      'nav.{name}': '{display}',
      '{name}.title': '{display}',
      '{name}.description': 'TODO: describe {display}.',
      '{name}.name': 'Name',
      '{name}.add': 'Add',
    }},
  }},
}}
""",
    "{kebab}-page.tsx": """import {{ useMemo, useState }} from 'react'
import {{ useMutation, useQuery, useQueryClient }} from '@tanstack/react-query'
import type {{ ColDef }} from 'ag-grid-community'
import {{ Plus }} from 'lucide-react'
import {{ useTranslation }} from 'react-i18next'
import {{ api, unwrap }} from '@/api/client'
import {{ handleServerError }} from '@/lib/handle-server-error'
import {{ can, useSession }} from '@/lib/session'
import {{ Button }} from '@/components/ui/button'
import {{ Input }} from '@/components/ui/input'
import {{ DataGrid }} from '@/components/data-grid'
import {{ Page }} from '@/components/layout/page'

// After `pnpm gen:api`, replace this with components['schemas']['{Class}ItemRead'] and drop the casts below.
type Item = {{ id: number; name: string; description?: string | null }}
const path = '/api/v1/{prefix}/items/' as never

export default function {Class}Page() {{
  const {{ t }} = useTranslation()
  const session = useSession()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const {{ data }} = useQuery({{
    queryKey: ['{name}', 'items'],
    queryFn: () => unwrap(api.GET(path)) as Promise<{{ data: Item[] }}>,
  }})
  const add = useMutation({{
    mutationFn: () => unwrap(api.POST(path, {{ body: {{ name }} }} as never)),
    onSuccess: () => {{
      setName('')
      void queryClient.invalidateQueries({{ queryKey: ['{name}'] }})
    }},
    onError: handleServerError,
  }})
  const columns = useMemo<ColDef<Item>[]>(
    () => [{{ field: 'name', headerName: t('{name}.name'), flex: 1 }}],
    [t]
  )

  return (
    <Page title={{t('{name}.title')}} description={{t('{name}.description')}}>
      {{can(session, '{name}.edit') ? (
        <form
          className='flex gap-2'
          onSubmit={{(e) => {{
            e.preventDefault()
            add.mutate()
          }}}}
        >
          <Input className='h-8 w-64' value={{name}} onChange={{(e) => setName(e.target.value)}} required />
          <Button size='sm' type='submit'>
            <Plus /> {{t('{name}.add')}}
          </Button>
        </form>
      ) : null}}
      <div className='h-[480px]'>
        <DataGrid rowData={{data?.data ?? []}} columnDefs={{columns}} getRowId={{(p) => String(p.data.id)}} />
      </div>
    </Page>
  )
}}
""",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="snake_case module name, e.g. punch_list")
    parser.add_argument("--display", help="Display name, e.g. 'Punch List'")
    parser.add_argument("--depends", nargs="*", default=[], help="Modules this one needs, e.g. projects")
    args = parser.parse_args()

    name: str = args.name
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        parser.error("the name must be snake_case")
    kebab = name.replace("_", "-")
    values = {
        "name": name,
        "kebab": kebab,
        "prefix": kebab,
        "display": args.display or name.replace("_", " ").title(),
        "Class": "".join(part.title() for part in name.split("_")),
        "depends": "".join(f'"{d}", ' for d in args.depends).rstrip(" ") if args.depends else "",
        "depends_ts": ", ".join(f"'{d}'" for d in args.depends),
    }

    backend_dir = BACKEND / "src" / "modules" / name
    frontend_dir = FRONTEND / "src" / "modules" / kebab
    for existing in (backend_dir, frontend_dir):
        if existing.exists():
            print(f"{existing} already exists; nothing written.", file=sys.stderr)
            return 1

    backend_dir.mkdir(parents=True)
    for file, template in BACKEND_FILES.items():
        (backend_dir / file).write_text(template.format(**values))
    test_dir = BACKEND / "tests" / "integration" / name
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "__init__.py").write_text("")
    (test_dir / f"test_{name}.py").write_text(BACKEND_TEST.format(**values))

    frontend_dir.mkdir(parents=True)
    for file, template in FRONTEND_FILES.items():
        (frontend_dir / file.format(**values)).write_text(template.format(**values))

    registry = FRONTEND / "src" / "modules" / "_registry.ts"
    text = registry.read_text()
    variable = re.sub(r"_(\w)", lambda m: m.group(1).upper(), name)
    text = text.replace(
        "import type { ModuleManifest }",
        f"import {{ manifest as {variable} }} from './{kebab}/manifest'\nimport type {{ ModuleManifest }}",
    )
    text = text.replace("\n]\n", f"\n  {variable},\n]\n")
    registry.write_text(text)

    print(f"""Created:
  backend/src/modules/{name}/        mounted at /api/v1/{kebab}
  backend/tests/integration/{name}/
  frontend/src/modules/{kebab}/       page at /{kebab}, registered in _registry.ts

Next:
  cd backend && uv run alembic revision --autogenerate -m "{name} module" && uv run alembic upgrade head
  cd frontend && pnpm gen:api && pnpm prettier --write src/modules
  Grant {name}.read / {name}.edit to a role (or map an Entra app role to it).""")
    return 0


if __name__ == "__main__":
    sys.exit(main())

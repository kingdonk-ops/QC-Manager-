"""Runtime module switches, and the gate that answers 404 for a switched-off module.

The switches live in ``platform_module_settings`` and are cached per process for a few seconds;
a toggle clears this process's cache, and other workers catch up within the TTL. A project can
override the switch for its own routes: the ``projects`` module registers that resolver, and the
gate asks it when a route carries a ``project_id`` path parameter.
"""

import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.session import async_session
from ..http_exceptions import NotFoundException
from .loader import installed_modules
from .models import ModuleSetting

TTL_SECONDS = 10.0

_cache: tuple[float, dict[str, bool]] | None = None

ProjectOverride = Callable[[AsyncSession, int, str], Awaitable[bool | None]]
_project_override: ProjectOverride | None = None


def register_project_override(resolver: ProjectOverride) -> None:
    """``resolver(db, project_id, module) -> True/False/None`` (None: no override)."""
    global _project_override
    _project_override = resolver


def invalidate() -> None:
    global _cache
    _cache = None


async def switches(db: AsyncSession) -> dict[str, bool]:
    """Every installed module's global on/off state, defaults filled in from the manifests."""
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < TTL_SECONDS:
        return _cache[1]

    stored: dict[str, bool] = {n: e for n, e in (await db.execute(select(ModuleSetting.name, ModuleSetting.enabled))).all()}
    state = {}
    for module in installed_modules():
        if not module.enabled:
            state[module.manifest.name] = False
        elif module.manifest.core:
            state[module.manifest.name] = True
        else:
            state[module.manifest.name] = stored.get(module.manifest.name, True)
    _cache = (time.monotonic(), state)

    return state


async def is_enabled(db: AsyncSession, module: str, project_id: int | None = None) -> bool:
    state = await switches(db)
    if not state.get(module, False):
        return False
    if project_id is not None and _project_override is not None:
        override = await _project_override(db, project_id, module)
        if override is not None:
            return override

    return True


def module_gate(name: str) -> Any:
    """A router dependency: 404 while the module is off, globally or for the route's project."""

    async def gate(request: Request, db: Annotated[AsyncSession, Depends(async_session)]) -> None:
        raw = request.path_params.get("project_id")
        project_id = int(raw) if isinstance(raw, (int, str)) and str(raw).isdigit() else None
        if not await is_enabled(db, name, project_id):
            raise NotFoundException("This module is switched off.")

    return Depends(gate)

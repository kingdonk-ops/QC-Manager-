"""Per-user module access: None, View, Edit or Full, on top of roles.

A level set for a module replaces whatever the user's roles grant for that module's permission
resources: ``none`` removes them all, ``view`` leaves the reading actions, ``edit`` adds the
creating and changing ones, ``full`` grants every permission the module declares. A module with no
level set follows the roles. Superusers are not affected.
"""

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.loader import installed_modules
from ...infrastructure.permissions import permission_groups
from .models import ModuleAccess


class AccessLevel(StrEnum):
    NONE = "none"
    VIEW = "view"
    EDIT = "edit"
    FULL = "full"


VIEW_ACTIONS = frozenset({"read", "view", "list", "export"})
EDIT_ACTIONS = VIEW_ACTIONS | frozenset(
    {"create", "update", "edit", "respond", "submit", "assign", "import", "comment", "upload", "review", "transition", "invite"}
)


def module_permissions(module: str) -> frozenset[str]:
    """Every permission the module's resources declare."""
    manifest = next((m.manifest for m in installed_modules() if m.manifest.name == module), None)
    if manifest is None:
        return frozenset()
    groups = permission_groups()

    return frozenset(p for resource in manifest.resources for p in groups.get(resource, ()))


def permissions_for(module: str, level: AccessLevel) -> frozenset[str]:
    every = module_permissions(module)
    if level == AccessLevel.FULL:
        return every
    allowed = VIEW_ACTIONS if level == AccessLevel.VIEW else EDIT_ACTIONS if level == AccessLevel.EDIT else frozenset()

    return frozenset(p for p in every if p.split(".", 1)[1] in allowed)


async def levels_of(db: AsyncSession, user_id: int) -> dict[str, AccessLevel]:
    rows = await db.execute(select(ModuleAccess.module, ModuleAccess.level).where(ModuleAccess.user_id == user_id))

    return {module: AccessLevel(level) for module, level in rows.all()}


async def module_access_filter(db: AsyncSession, user_id: int, held: frozenset[str]) -> frozenset[str]:
    levels = await levels_of(db, user_id)
    if not levels:
        return held
    result = set(held)
    for module, level in levels.items():
        result -= module_permissions(module)
        result |= permissions_for(module, level)

    return frozenset(result)

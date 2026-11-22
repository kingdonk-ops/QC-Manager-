"""The four built-in roles, kept in step with every installed module's permissions at startup.

* Admin: every permission.
* Manager: everything except platform administration (module switches, access levels, roles,
  deactivating accounts, Entra settings).
* Editor: the reading and changing actions of every module (no deletes, no administration).
* Viewer: the reading actions of every module.

Each startup recomputes what they carry, so a newly installed module's permissions reach them.
Map Entra app roles QC.Admin, QC.Manager, QC.Editor and QC.Viewer to them (seed_demo does).
"""

from sqlalchemy import delete, select

from ...infrastructure.database.session import local_session
from ...infrastructure.logging import get_logger
from ...infrastructure.permissions import all_permissions
from ..role.models import Role, RolePermission
from .access import EDIT_ACTIONS, VIEW_ACTIONS

logger = get_logger()

BUILTIN_MARK = "Built-in role."
ADMIN_ONLY = frozenset({"platform", "role", "entra"})
ADMIN_ONLY_PERMISSIONS = frozenset({"people.manage"})


def builtin_role_permissions() -> dict[str, frozenset[str]]:
    every = all_permissions()

    def action(p: str) -> str:
        return p.split(".", 1)[1]

    def resource(p: str) -> str:
        return p.split(".", 1)[0]

    return {
        "Admin": every,
        "Manager": frozenset(p for p in every if resource(p) not in ADMIN_ONLY and p not in ADMIN_ONLY_PERMISSIONS),
        "Editor": frozenset(p for p in every if resource(p) not in ADMIN_ONLY and action(p) in EDIT_ACTIONS),
        "Viewer": frozenset(p for p in every if resource(p) not in ADMIN_ONLY and action(p) in VIEW_ACTIONS),
    }


async def sync_builtin_roles() -> None:
    async with local_session() as db:
        for name, permissions in builtin_role_permissions().items():
            role = await db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=f"{BUILTIN_MARK} {name} access to every module.")
                db.add(role)
                await db.flush()
            elif not (role.description or "").startswith(BUILTIN_MARK):
                logger.warning("A role named like a built-in exists; leaving it alone", extra={"role": name})
                continue
            await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in sorted(permissions)])
        await db.commit()

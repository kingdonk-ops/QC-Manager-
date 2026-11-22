"""Reading the directory, and switching accounts off and on.

Deactivating soft-deletes the account (``is_deleted``), which every authentication path already
refuses, without anonymising it the way ``DELETE /users/{username}`` does, so it can be reactivated.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from crudauth.utils.hashing import is_unusable_password
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..role.models import Role, UserRole
from ..team.models import EntraRoleMapping, Team, TeamMembership
from ..user.exceptions import UserNotFoundError
from ..user.models import User
from .exceptions import SelfDeactivationError, SuperuserProtectedError
from .schemas import Person, PersonRole, PersonTeam, RoleOption


async def _people(db: AsyncSession, users: list[User]) -> list[Person]:
    ids = [u.id for u in users]
    roles: dict[int, list[PersonRole]] = defaultdict(list)
    teams: dict[int, list[PersonTeam]] = defaultdict(list)
    if ids:
        role_rows = await db.execute(
            select(UserRole.user_id, Role.id, Role.name, EntraRoleMapping.app_role_value)
            .join(Role, Role.id == UserRole.role_id)
            .outerjoin(EntraRoleMapping, EntraRoleMapping.role_id == Role.id)
            .where(UserRole.user_id.in_(ids))
            .order_by(Role.name)
        )
        for user_id, role_id, name, app_role in role_rows.all():
            if not any(r.id == role_id for r in roles[user_id]):
                roles[user_id].append(PersonRole(id=role_id, name=name, entra_app_role=app_role))
        team_rows = await db.execute(
            select(TeamMembership.user_id, Team.id, Team.name, TeamMembership.role, Team.entra_group_id)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(TeamMembership.user_id.in_(ids))
            .order_by(Team.name)
        )
        for user_id, team_id, name, role, group in team_rows.all():
            teams[user_id].append(PersonTeam(id=team_id, name=name, role=role, entra_managed=group is not None))

    return [
        Person(
            id=u.id,
            name=u.name,
            username=u.username,
            email=u.email,
            account_type="staff" if u.entra_id or u.is_superuser else "external",
            sign_in_method="entra" if u.entra_id else "password",
            is_superuser=u.is_superuser,
            active=not u.is_deleted,
            activated=bool(u.entra_id) or not is_unusable_password(u.hashed_password),
            roles=roles[u.id],
            teams=teams[u.id],
            created_at=u.created_at,
        )
        for u in users
    ]


class PeopleService:
    async def page(self, db: AsyncSession, skip: int, limit: int, search: str | None, include_inactive: bool) -> dict[str, Any]:
        filters: list[Any] = []
        if not include_inactive:
            filters.append(User.is_deleted.is_(False))
        if search:
            like = f"%{search.lower()}%"
            filters.append(
                or_(func.lower(User.name).like(like), func.lower(User.email).like(like), func.lower(User.username).like(like))
            )
        total = await db.scalar(select(func.count()).select_from(User).where(*filters))
        users = (await db.execute(select(User).where(*filters).order_by(User.name).offset(skip).limit(limit))).scalars()
        people = await _people(db, list(users))

        return {"data": [p.model_dump(mode="json") for p in people], "total_count": total or 0}

    async def get(self, db: AsyncSession, user_id: int) -> Person:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")

        return (await _people(db, [user]))[0]

    async def roles(self, db: AsyncSession) -> list[RoleOption]:
        rows = await db.execute(
            select(Role.id, Role.name, Role.description, EntraRoleMapping.app_role_value)
            .outerjoin(EntraRoleMapping, EntraRoleMapping.role_id == Role.id)
            .order_by(Role.name)
        )
        options: dict[int, RoleOption] = {}
        for role_id, name, description, app_role in rows.all():
            options.setdefault(role_id, RoleOption(id=role_id, name=name, description=description, entra_app_role=app_role))

        return list(options.values())

    async def set_active(self, db: AsyncSession, user_id: int, active: bool, caller: dict[str, Any]) -> Person:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        if not active and user.id == caller["id"]:
            raise SelfDeactivationError("Self")
        if user.is_superuser and not caller.get("is_superuser"):
            raise SuperuserProtectedError("Superuser")
        user.is_deleted = not active
        user.deleted_at = None if active else datetime.now(UTC)
        if not active:
            user.token_version += 1
        await db.commit()

        return (await _people(db, [user]))[0]

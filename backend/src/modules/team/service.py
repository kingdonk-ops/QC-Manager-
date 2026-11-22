"""Reading and changing teams and their members, and the Entra role mappings."""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..role.exceptions import RoleNotFoundError
from ..role.models import Role
from ..user.exceptions import UserNotFoundError
from ..user.models import User
from .constants import TeamRole
from .exceptions import (
    EntraManagedTeamError,
    MembershipNotFoundError,
    RoleMappingNotFoundError,
    TeamExistsError,
    TeamNotFoundError,
)
from .models import EntraRoleMapping, Team, TeamMembership
from .schemas import MyTeamRead, RoleMappingRead, TeamDetail, TeamMemberRead, TeamRead

ROLE_RANK = {TeamRole.MEMBER: 0, TeamRole.LEAD: 1, TeamRole.MANAGER: 2}


def _member_counts():
    return select(TeamMembership.team_id, func.count().label("member_count")).group_by(TeamMembership.team_id).subquery()


def _read(team: Team, count: int | None) -> dict[str, Any]:
    return TeamRead(
        id=team.id,
        name=team.name,
        description=team.description,
        entra_group_id=team.entra_group_id,
        member_count=count or 0,
        created_at=team.created_at,
        updated_at=team.updated_at,
    ).model_dump()


class TeamService:
    async def page(self, db: AsyncSession, skip: int, limit: int) -> dict[str, Any]:
        counts = _member_counts()
        total = await db.scalar(select(func.count()).select_from(Team))
        rows = (
            await db.execute(
                select(Team, counts.c.member_count)
                .outerjoin(counts, counts.c.team_id == Team.id)
                .order_by(Team.name)
                .offset(skip)
                .limit(limit)
            )
        ).all()

        return {"data": [_read(team, count) for team, count in rows], "total_count": total or 0}

    async def mine(self, db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
        counts = _member_counts()
        rows = (
            await db.execute(
                select(Team, counts.c.member_count, TeamMembership.role)
                .join(TeamMembership, TeamMembership.team_id == Team.id)
                .outerjoin(counts, counts.c.team_id == Team.id)
                .where(TeamMembership.user_id == user_id)
                .order_by(Team.name)
            )
        ).all()

        return [MyTeamRead(**_read(team, count), my_role=TeamRole(role)).model_dump() for team, count, role in rows]

    async def role_in(self, db: AsyncSession, team_id: int, user_id: int) -> TeamRole | None:
        role = await db.scalar(
            select(TeamMembership.role).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        )

        return TeamRole(role) if role else None

    async def _team(self, db: AsyncSession, team_id: int) -> Team:
        team = await db.get(Team, team_id)
        if team is None:
            raise TeamNotFoundError(f"Team {team_id} not found")

        return team

    async def get(self, db: AsyncSession, team_id: int) -> dict[str, Any]:
        team = await self._team(db, team_id)
        rows = (
            await db.execute(
                select(User.id, User.name, User.username, User.email, TeamMembership.role, TeamMembership.created_at)
                .join(TeamMembership, TeamMembership.user_id == User.id)
                .where(TeamMembership.team_id == team_id, User.is_deleted.is_(False))
                .order_by(User.name)
            )
        ).all()
        members = [
            TeamMemberRead(user_id=uid, name=name, username=username, email=email, role=TeamRole(role), joined_at=joined)
            for uid, name, username, email, role, joined in rows
        ]

        return TeamDetail(**_read(team, len(members)), members=members).model_dump()

    async def _commit(self, db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise TeamExistsError("Team name or group already used") from exc

    async def create(self, db: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
        team = Team(**values)
        db.add(team)
        await self._commit(db)

        return _read(team, 0)

    async def update(self, db: AsyncSession, team_id: int, values: dict[str, Any]) -> dict[str, Any]:
        """Change a team. Linking a group doesn't change its members until the next sync or sign-in."""
        team = await self._team(db, team_id)
        for key, value in values.items():
            if key == "name" and value is None:
                continue
            setattr(team, key, value)
        await self._commit(db)

        return await self.get(db, team_id)

    async def delete(self, db: AsyncSession, team_id: int) -> None:
        team = await self._team(db, team_id)
        await db.delete(team)
        await db.commit()

    async def set_member(self, db: AsyncSession, team_id: int, user_id: int, role: TeamRole) -> None:
        """Add a member or change their role. On an Entra-linked team, only the role of an existing member."""
        team = await self._team(db, team_id)
        membership = await db.get(TeamMembership, (team_id, user_id))
        if membership is None:
            if team.entra_group_id:
                raise EntraManagedTeamError("Members of a linked team come from Entra")
            user = await db.scalar(select(User.id).where(User.id == user_id, User.is_deleted.is_(False)))
            if user is None:
                raise UserNotFoundError(f"User {user_id} not found")
            db.add(TeamMembership(team_id=team_id, user_id=user_id, role=role.value))
        else:
            membership.role = role.value
        await db.commit()

    async def remove_member(self, db: AsyncSession, team_id: int, user_id: int) -> None:
        team = await self._team(db, team_id)
        if team.entra_group_id:
            raise EntraManagedTeamError("Members of a linked team come from Entra")
        result = await db.execute(
            delete(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        )
        if not getattr(result, "rowcount", 0):
            raise MembershipNotFoundError("Not a member")
        await db.commit()

    # --- Entra app role -> role ---------------------------------------------------------------
    async def role_mappings(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(EntraRoleMapping.app_role_value, Role.id, Role.name)
                .join(Role, Role.id == EntraRoleMapping.role_id)
                .order_by(EntraRoleMapping.app_role_value)
            )
        ).all()

        return [RoleMappingRead(app_role_value=v, role_id=rid, role_name=n).model_dump() for v, rid, n in rows]

    async def set_role_mapping(self, db: AsyncSession, app_role_value: str, role_id: int) -> dict[str, Any]:
        role = await db.get(Role, role_id)
        if role is None:
            raise RoleNotFoundError(f"Role {role_id} not found")
        mapping = await db.get(EntraRoleMapping, app_role_value)
        if mapping is None:
            db.add(EntraRoleMapping(app_role_value=app_role_value, role_id=role_id))
        else:
            mapping.role_id = role_id
        await db.commit()

        return RoleMappingRead(app_role_value=app_role_value, role_id=role.id, role_name=role.name).model_dump()

    async def delete_role_mapping(self, db: AsyncSession, app_role_value: str) -> None:
        """Unmap an app role. Users keep the role they hold, which becomes hand-assigned."""
        result = await db.execute(delete(EntraRoleMapping).where(EntraRoleMapping.app_role_value == app_role_value))
        if not getattr(result, "rowcount", 0):
            raise RoleMappingNotFoundError("No such mapping")
        await db.commit()

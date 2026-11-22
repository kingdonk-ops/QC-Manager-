"""Keeping roles and team memberships in step with Entra ID.

Two paths feed it:

* every Entra sign-in, from the ``roles`` and ``groups`` claims in the verified ID token, and
* the scheduled Graph sync (``tasks.py``), which reads each linked group's members so a change in
  Entra lands without waiting for that user's next sign-in.

Only what Entra owns is touched: roles that have an ``EntraRoleMapping``, and memberships of teams
that have an ``entra_group_id``. A membership the sync adds starts as ``member``; an existing
membership keeps whatever role it was given here.
"""

from collections.abc import Collection, Iterable
from typing import Any

from crudauth.oauth import OAuthUserInfo
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.entra import app_roles_of, groups_of
from ...infrastructure.config.settings import settings
from ...infrastructure.logging import get_logger
from ..role.models import UserRole
from ..user.models import User
from .constants import TeamRole
from .models import EntraRoleMapping, Team, TeamMembership

logger = get_logger()


async def sync_user_roles(db: AsyncSession, user_id: int, app_roles: Iterable[str]) -> tuple[int, int]:
    """Make the user's Entra-mapped roles exactly those ``app_roles`` grant. Answers (added, removed)."""
    mappings = (await db.execute(select(EntraRoleMapping.app_role_value, EntraRoleMapping.role_id))).all()
    if not mappings:
        return 0, 0

    held_values = set(app_roles)
    managed = {role_id for _, role_id in mappings}
    wanted = {role_id for value, role_id in mappings if value in held_values}
    current = set(
        (await db.execute(select(UserRole.role_id).where(UserRole.user_id == user_id, UserRole.role_id.in_(managed)))).scalars()
    )

    to_add, to_remove = wanted - current, current - wanted
    for role_id in to_add:
        db.add(UserRole(user_id=user_id, role_id=role_id))
    if to_remove:
        await db.execute(delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(to_remove)))

    return len(to_add), len(to_remove)


async def sync_user_teams(db: AsyncSession, user_id: int, group_ids: Collection[str]) -> tuple[int, int]:
    """Make the user's memberships of Entra-linked teams match ``group_ids``. Answers (added, removed)."""
    linked = (await db.execute(select(Team.id, Team.entra_group_id).where(Team.entra_group_id.is_not(None)))).all()
    if not linked:
        return 0, 0

    groups = {group.lower() for group in group_ids}
    managed = {team_id for team_id, _ in linked}
    wanted = {team_id for team_id, group in linked if group in groups}
    current = set(
        (
            await db.execute(
                select(TeamMembership.team_id).where(TeamMembership.user_id == user_id, TeamMembership.team_id.in_(managed))
            )
        ).scalars()
    )

    to_add, to_remove = wanted - current, current - wanted
    for team_id in to_add:
        db.add(TeamMembership(team_id=team_id, user_id=user_id, role=TeamRole.MEMBER.value))
    if to_remove:
        await db.execute(delete(TeamMembership).where(TeamMembership.user_id == user_id, TeamMembership.team_id.in_(to_remove)))

    return len(to_add), len(to_remove)


async def sync_access_from_sign_in(user: dict[str, Any], info: OAuthUserInfo, db: AsyncSession) -> None:
    """The ``on_oauth_login`` contribution: apply the sign-in's roles and groups claims."""
    app_roles = app_roles_of(info)
    if app_roles is None:
        return

    roles_added, roles_removed = await sync_user_roles(db, user["id"], app_roles)

    teams_added = teams_removed = 0
    groups = groups_of(info)
    if groups is None:
        logger.info("Entra left the groups claim out (overage); the Graph sync will place this user in teams")
    elif groups or settings.OAUTH_ENTRA_GROUPS_CLAIM:
        teams_added, teams_removed = await sync_user_teams(db, user["id"], groups)

    await db.commit()
    if roles_added or roles_removed or teams_added or teams_removed:
        logger.info(
            "Entra sign-in changed access",
            extra={
                "user_id": user["id"],
                "roles_added": roles_added,
                "roles_removed": roles_removed,
                "teams_added": teams_added,
                "teams_removed": teams_removed,
            },
        )


async def set_team_members_from_group(db: AsyncSession, team_id: int, member_object_ids: Collection[str]) -> dict[str, int]:
    """Make an Entra-linked team's members exactly the known users among ``member_object_ids``.

    A group member who has never signed in has no account yet, so is skipped and counted: they are
    added at their first sign-in, from the groups claim.
    """
    oids = {oid.lower() for oid in member_object_ids}
    known: dict[str, int] = {}
    if oids:
        rows = await db.execute(select(User.entra_id, User.id).where(User.entra_id.in_(oids), User.is_deleted.is_(False)))
        known = {str(oid): user_id for oid, user_id in rows.all()}
    wanted = set(known.values())
    current = set((await db.execute(select(TeamMembership.user_id).where(TeamMembership.team_id == team_id))).scalars())

    to_add, to_remove = wanted - current, current - wanted
    for user_id in to_add:
        db.add(TeamMembership(team_id=team_id, user_id=user_id, role=TeamRole.MEMBER.value))
    if to_remove:
        await db.execute(delete(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id.in_(to_remove)))

    return {"added": len(to_add), "removed": len(to_remove), "unknown": len(oids) - len(known)}

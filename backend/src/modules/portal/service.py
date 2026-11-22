"""Inviting external users.

An invitation creates the account with an unusable password and sends crudauth's password-reset
email: following the link sets the first password, which also proves the address. Until then the
account can't sign in. Lockout, the password policy and session handling are the platform's own.
"""

import re
import secrets
from typing import Any

from crudauth.utils.hashing import is_unusable_password, make_unusable_password
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.setup import auth
from ..team.exceptions import EntraManagedTeamError, TeamNotFoundError
from ..team.models import Team, TeamMembership
from ..user.constants import USERNAME_MAX_LENGTH
from ..user.exceptions import UserNotFoundError
from ..user.models import User
from .exceptions import EmailTakenError
from .schemas import ExternalUserRead


def _external():
    return (User.entra_id.is_(None), User.is_superuser.is_(False), User.is_deleted.is_(False))


async def _unique_username(db: AsyncSession, email: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", email.split("@", 1)[0].lower())[: USERNAME_MAX_LENGTH - 5] or "user"
    candidate = base
    while await db.scalar(select(User.id).where(User.username == candidate)):
        candidate = f"{base}_{secrets.randbelow(10_000):04d}"

    return candidate


async def _send_set_password_link(db: AsyncSession, email: str) -> None:
    if auth.emails is not None:
        await auth.emails.request_password_reset(db, email, redirect_to="/")


class PortalService:
    async def invite(self, db: AsyncSession, name: str, email: str, team_ids: list[int]) -> dict[str, Any]:
        email = email.lower()
        if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
            raise EmailTakenError("Email in use")

        teams = []
        for team_id in team_ids:
            team = await db.get(Team, team_id)
            if team is None:
                raise TeamNotFoundError(f"Team {team_id} not found")
            if team.entra_group_id:
                raise EntraManagedTeamError("Linked teams take members from Entra")
            teams.append(team)

        user = User(
            name=name,
            username=await _unique_username(db, email),
            email=email,
            hashed_password=make_unusable_password(),
        )
        db.add(user)
        await db.flush()
        db.add_all([TeamMembership(team_id=team.id, user_id=user.id) for team in teams])
        await db.commit()
        await _send_set_password_link(db, email)

        return (await self.get(db, user.id)).model_dump()

    async def get(self, db: AsyncSession, user_id: int) -> ExternalUserRead:
        user = await db.scalar(select(User).where(User.id == user_id, *_external()))
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        teams = (
            await db.execute(
                select(Team.name)
                .join(TeamMembership, TeamMembership.team_id == Team.id)
                .where(TeamMembership.user_id == user_id)
            )
        ).scalars()

        return ExternalUserRead(
            id=user.id,
            name=user.name,
            username=user.username,
            email=user.email,
            email_verified=user.email_verified,
            activated=not is_unusable_password(user.hashed_password),
            created_at=user.created_at,
            teams=sorted(teams),
        )

    async def list(self, db: AsyncSession) -> list[dict[str, Any]]:
        ids = (await db.execute(select(User.id).where(*_external()).order_by(User.name))).scalars().all()

        return [(await self.get(db, user_id)).model_dump() for user_id in ids]

    async def resend(self, db: AsyncSession, user_id: int) -> None:
        user = await self.get(db, user_id)
        await _send_set_password_link(db, user.email)

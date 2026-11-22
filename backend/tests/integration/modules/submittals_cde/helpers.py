"""Users, roles and sign-in for the submittals and CDE tests."""

import secrets

from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.projects.models import Project
from src.modules.team.models import Team, TeamMembership
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.rbac.test_user_permissions import _grant, _login

PASSWORD = "Password123!"


async def make_user(db: AsyncSession, name: str, *permissions: str) -> dict:
    tag = secrets.token_hex(4)
    user = User(
        name=name,
        username=f"u{tag}",
        email=f"{tag}@example.com",
        hashed_password=get_password_hash(PASSWORD),
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await reset_password_budget(user.id)
    account = {"id": user.id, "name": name, "username": user.username, "password": PASSWORD}
    if permissions:
        await _grant(db, user.id, f"role-{tag}", *permissions)
    return account


async def sign_in(client: AsyncClient, user: dict) -> dict[str, str]:
    return {"X-CSRF-Token": await _login(client, user)}


async def make_project(db: AsyncSession, code: str = "P-1", client_team_id: int | None = None) -> Project:
    project = Project(code=code, name="Plant", client_team_id=client_team_id)
    db.add(project)
    await db.commit()
    return project


async def client_team(db: AsyncSession, *user_ids: int) -> Team:
    team = Team(name=f"Client {secrets.token_hex(3)}")
    db.add(team)
    await db.flush()
    db.add_all([TeamMembership(team_id=team.id, user_id=uid) for uid in user_ids])
    await db.commit()
    return team

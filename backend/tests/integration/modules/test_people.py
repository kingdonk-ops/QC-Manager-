"""The user directory, profiles, and deactivating accounts."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role
from src.modules.team.models import EntraRoleMapping, Team, TeamMembership
from src.modules.user.models import User
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def test_my_profile_lists_my_roles_and_teams(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    role = await _grant(db_session, test_user["id"], "qs", "projects.read")
    db_session.add(EntraRoleMapping(app_role_value="QC.QS", role_id=role.id))
    team = Team(name="Perth")
    db_session.add(team)
    await db_session.flush()
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"], role="lead"))
    await db_session.commit()
    await _login(client, test_user)

    me = (await client.get("/api/v1/people/me")).json()

    assert me["account_type"] == "external"
    assert me["activated"] is True
    assert me["roles"] == [{"id": role.id, "name": "qs", "entra_app_role": "QC.QS"}]
    assert me["teams"] == [{"id": team.id, "name": "Perth", "role": "lead", "entra_managed": False}]


async def test_the_directory_needs_people_read_and_searches(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _login(client, test_user)
    assert (await client.get("/api/v1/people/")).status_code == 403

    await _grant(db_session, test_user["id"], "hr", "people.read")
    listed = (await client.get("/api/v1/people/", params={"search": test_user_2["username"]})).json()

    assert [p["id"] for p in listed["data"]] == [test_user_2["id"]]


async def test_roles_show_which_ones_entra_grants(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "role-reader", "role.read")
    mapped = Role(name="admin")
    db_session.add(mapped)
    await db_session.flush()
    db_session.add(EntraRoleMapping(app_role_value="QC.Admin", role_id=mapped.id))
    await db_session.commit()
    await _login(client, test_user)

    roles = {r["name"]: r["entra_app_role"] for r in (await client.get("/api/v1/people/roles")).json()}

    assert roles == {"admin": "QC.Admin", "role-reader": None}


async def test_a_deactivated_account_cannot_sign_in_until_reactivated(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "hr", "people.read", "people.manage")
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    off = await client.post(f"/api/v1/people/{test_user_2['id']}/deactivate", headers=headers)
    assert off.status_code == 200
    assert off.json()["active"] is False
    login = await client.post(
        "/api/v1/auth/login", data={"username": test_user_2["username"], "password": test_user_2["password"]}
    )
    assert login.status_code != 200

    on = await client.post(f"/api/v1/people/{test_user_2['id']}/reactivate", headers=headers)
    assert on.json()["active"] is True
    await _login(client, test_user_2)


async def test_nobody_deactivates_themselves_or_a_superuser_without_being_one(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "hr", "people.manage")
    other = await db_session.get(User, test_user_2["id"])
    other.is_superuser = True
    await db_session.commit()
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    assert (await client.post(f"/api/v1/people/{test_user['id']}/deactivate", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/people/{test_user_2['id']}/deactivate", headers=headers)).status_code == 403

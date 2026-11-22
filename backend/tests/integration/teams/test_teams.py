"""Teams through the API, and the Entra role and group sync."""

import httpx
import pytest
from crudauth.oauth import OAuthUserInfo
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.config.settings import settings
from src.modules.role.models import Role, UserRole
from src.modules.team.entra_sync import set_team_members_from_group, sync_access_from_sign_in
from src.modules.team.models import EntraRoleMapping, Team, TeamMembership
from src.modules.team.sync_job import sync_all_linked_teams
from src.modules.user.models import User
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

GROUP = "aabbccdd-0000-0000-0000-000000000001"
OTHER_GROUP = "aabbccdd-0000-0000-0000-000000000002"
OID = "99999999-8888-7777-6666-555555555555"

MANAGING = ("team.read", "team.create", "team.update", "team.delete", "team.manage_members")


def _sign_in(**raw) -> OAuthUserInfo:
    return OAuthUserInfo(provider="entra", provider_user_id=OID, raw_data=raw)


async def _members(db: AsyncSession, team_id: int) -> dict[int, str]:
    rows = await db.execute(select(TeamMembership.user_id, TeamMembership.role).where(TeamMembership.team_id == team_id))
    return dict(rows.all())


async def _team(db: AsyncSession, name: str, group: str | None = None) -> Team:
    team = Team(name=name, entra_group_id=group)
    db.add(team)
    await db.commit()
    return team


# --- the API ---------------------------------------------------------------------------------


async def test_a_manager_creates_a_team_and_adds_a_member(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "team-admin", *MANAGING)
    csrf = await _login(client, test_user)
    headers = {"X-CSRF-Token": csrf}

    created = await client.post("/api/v1/teams/", json={"name": "QC Perth"}, headers=headers)
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]

    added = await client.put(f"/api/v1/teams/{team_id}/members/{test_user_2['id']}", json={"role": "lead"}, headers=headers)
    assert added.status_code == 200, added.text

    detail = await client.get(f"/api/v1/teams/{team_id}")
    assert [(m["user_id"], m["role"]) for m in detail.json()["members"]] == [(test_user_2["id"], "lead")]

    listed = await client.get("/api/v1/teams/")
    assert listed.json()["data"][0]["member_count"] == 1


async def test_without_permissions_a_user_sees_only_their_own_teams(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    mine = await _team(db_session, "Mine")
    theirs = await _team(db_session, "Theirs")
    db_session.add(TeamMembership(team_id=mine.id, user_id=test_user["id"]))
    await db_session.commit()
    await _login(client, test_user)

    assert (await client.get("/api/v1/teams/")).status_code == 403
    assert [t["name"] for t in (await client.get("/api/v1/teams/mine")).json()] == ["Mine"]
    assert (await client.get(f"/api/v1/teams/{mine.id}")).status_code == 200
    assert (await client.get(f"/api/v1/teams/{theirs.id}")).status_code == 404


async def test_a_lead_manages_members_but_cannot_make_a_manager(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    team = await _team(db_session, "Led")
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"], role="lead"))
    await db_session.commit()
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    as_member = await client.put(f"/api/v1/teams/{team.id}/members/{test_user_2['id']}", json={}, headers=headers)
    as_manager = await client.put(
        f"/api/v1/teams/{team.id}/members/{test_user_2['id']}", json={"role": "manager"}, headers=headers
    )

    assert as_member.status_code == 200
    assert as_manager.status_code == 403
    assert (await _members(db_session, team.id))[test_user_2["id"]] == "member"


async def test_a_plain_member_cannot_change_members(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    team = await _team(db_session, "Flat")
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"]))
    await db_session.commit()
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    response = await client.put(f"/api/v1/teams/{team.id}/members/{test_user_2['id']}", json={}, headers=headers)

    assert response.status_code == 403


async def test_a_linked_team_refuses_hand_added_members_but_takes_role_changes(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "team-admin", *MANAGING)
    team = await _team(db_session, "Linked", GROUP)
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"]))
    await db_session.commit()
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    add = await client.put(f"/api/v1/teams/{team.id}/members/{test_user_2['id']}", json={}, headers=headers)
    promote = await client.put(f"/api/v1/teams/{team.id}/members/{test_user['id']}", json={"role": "lead"}, headers=headers)
    remove = await client.delete(f"/api/v1/teams/{team.id}/members/{test_user['id']}", headers=headers)

    assert add.status_code == 422
    assert promote.status_code == 200
    assert remove.status_code == 422


async def test_a_duplicate_name_or_group_is_a_conflict(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "team-admin", *MANAGING)
    await _team(db_session, "Taken", GROUP)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    same_name = await client.post("/api/v1/teams/", json={"name": "Taken"}, headers=headers)
    same_group = await client.post("/api/v1/teams/", json={"name": "New", "entra_group_id": GROUP.upper()}, headers=headers)

    assert same_name.status_code == 409
    assert same_group.status_code == 409


async def test_role_mappings_need_entra_manage(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    role = Role(name="qc-admin")
    db_session.add(role)
    await db_session.commit()
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    refused = await client.put("/api/v1/entra/role-mappings/QC.Admin", json={"role_id": role.id}, headers=headers)
    assert refused.status_code == 403

    await _grant(db_session, test_user["id"], "entra-admin", "entra.manage")
    saved = await client.put("/api/v1/entra/role-mappings/QC.Admin", json={"role_id": role.id}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert (await client.get("/api/v1/entra/role-mappings")).json() == [
        {"app_role_value": "QC.Admin", "role_id": role.id, "role_name": "qc-admin"}
    ]


async def test_signup_is_off_unless_enabled(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_SIGNUP_ENABLED", False)

    response = await client.post(
        "/api/v1/users/",
        json={"name": "New User", "username": "newuser42", "email": "new.user@example.com", "password": "Password123!"},
    )

    assert response.status_code == 403, response.text


# --- sign-in sync ----------------------------------------------------------------------------


async def test_a_sign_in_applies_mapped_roles_and_leaves_hand_assigned_ones(db_session: AsyncSession, test_user: dict):
    admin, inspector, manual = Role(name="qc-admin"), Role(name="inspector"), Role(name="manual")
    db_session.add_all([admin, inspector, manual])
    await db_session.flush()
    db_session.add_all(
        [
            EntraRoleMapping(app_role_value="QC.Admin", role_id=admin.id),
            EntraRoleMapping(app_role_value="QC.Inspector", role_id=inspector.id),
            UserRole(user_id=test_user["id"], role_id=inspector.id),
            UserRole(user_id=test_user["id"], role_id=manual.id),
        ]
    )
    await db_session.commit()

    await sync_access_from_sign_in(test_user, _sign_in(roles=["QC.Admin", "Unmapped"]), db_session)

    held = set((await db_session.execute(select(UserRole.role_id).where(UserRole.user_id == test_user["id"]))).scalars())
    assert held == {admin.id, manual.id}


async def test_a_sign_in_places_the_user_in_linked_teams_only(db_session: AsyncSession, test_user: dict):
    in_group = await _team(db_session, "In", GROUP)
    left_group = await _team(db_session, "Left", OTHER_GROUP)
    manual = await _team(db_session, "Manual")
    db_session.add_all(
        [
            TeamMembership(team_id=left_group.id, user_id=test_user["id"]),
            TeamMembership(team_id=manual.id, user_id=test_user["id"]),
        ]
    )
    await db_session.commit()

    await sync_access_from_sign_in(test_user, _sign_in(groups=[GROUP.upper()]), db_session)

    teams = set(
        (await db_session.execute(select(TeamMembership.team_id).where(TeamMembership.user_id == test_user["id"]))).scalars()
    )
    assert teams == {in_group.id, manual.id}


async def test_a_sign_in_with_groups_overage_leaves_teams_alone(db_session: AsyncSession, test_user: dict):
    team = await _team(db_session, "Kept", GROUP)
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"]))
    await db_session.commit()

    await sync_access_from_sign_in(test_user, _sign_in(_claim_names={"groups": "src1"}), db_session)

    assert test_user["id"] in await _members(db_session, team.id)


async def test_a_resync_keeps_a_members_role(db_session: AsyncSession, test_user: dict):
    team = await _team(db_session, "Roles", GROUP)
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user["id"], role="lead"))
    await db_session.commit()

    await sync_access_from_sign_in(test_user, _sign_in(groups=[GROUP]), db_session)

    assert (await _members(db_session, team.id)) == {test_user["id"]: "lead"}


# --- Graph sync ------------------------------------------------------------------------------


async def test_a_group_sync_adds_known_users_and_drops_leavers(db_session: AsyncSession, test_user: dict, test_user_2: dict):
    team = await _team(db_session, "Graph", GROUP)
    user = await db_session.get(User, test_user["id"])
    user.entra_id = OID
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user_2["id"]))
    await db_session.commit()

    outcome = await set_team_members_from_group(db_session, team.id, {OID.upper(), "never-signed-in"})
    await db_session.commit()

    assert outcome == {"added": 1, "removed": 1, "unknown": 1}
    assert await _members(db_session, team.id) == {test_user["id"]: "member"}


async def test_the_sync_job_reads_every_linked_group_and_reports_failures(
    db_session: AsyncSession, test_user: dict, monkeypatch
):
    monkeypatch.setattr(settings, "OAUTH_ENTRA_TENANT_ID", "t")
    monkeypatch.setattr(settings, "OAUTH_ENTRA_CLIENT_ID", "c")
    monkeypatch.setattr(settings, "OAUTH_ENTRA_CLIENT_SECRET", "s")
    good = await _team(db_session, "Good", GROUP)
    await _team(db_session, "Broken", OTHER_GROUP)
    user = await db_session.get(User, test_user["id"])
    user.entra_id = OID
    await db_session.commit()

    def graph(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "app-token"})
        assert request.headers["Authorization"] == "Bearer app-token"
        if GROUP in request.url.path:
            return httpx.Response(200, json={"value": [{"id": OID}]})
        return httpx.Response(403, json={"error": "Authorization_RequestDenied"})

    report = await sync_all_linked_teams(db_session, transport=httpx.MockTransport(graph))

    assert report.teams_synced == 1
    assert report.memberships_added == 1
    assert report.teams_failed == ["Broken"]
    assert await _members(db_session, good.id) == {test_user["id"]: "member"}

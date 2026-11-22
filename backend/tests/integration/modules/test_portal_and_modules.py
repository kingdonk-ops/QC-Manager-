"""Staff and external sign-in, the client portal, and the projects and CVR example modules."""

from typing import Any

import pytest
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import email_config
from src.modules.team.models import Team, TeamMembership
from src.modules.user.models import User
from tests.fixtures.accounts import reset_recovery_budgets
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


class _Capture(EmailSender):
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        self.sent.append({"to": to, "link": context.link})


@pytest.fixture
def delivered(monkeypatch) -> list[dict[str, Any]]:
    capture = _Capture()
    monkeypatch.setattr(email_config, "sender", capture)
    return capture.sent


# --- sign-in -----------------------------------------------------------------------------------


async def test_an_entra_linked_account_cannot_use_a_password(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    user = await db_session.get(User, test_user["id"])
    user.entra_id = "99999999-8888-7777-6666-555555555555"
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]}
    )

    assert response.status_code == 403
    assert "Microsoft" in response.text


async def test_whoami_tells_staff_from_external(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "viewer", "projects.read")
    await _login(client, test_user)

    me = (await client.get("/api/v1/auth/whoami")).json()

    assert me["account_type"] == "external"
    assert me["sign_in_method"] == "password"
    assert me["permissions"] == ["projects.read"]


async def test_modules_are_listed_in_dependency_order(auth_client: AsyncClient):
    modules = [m["name"] for m in (await auth_client.get("/api/v1/modules")).json()]

    assert modules.index("team") < modules.index("projects") < modules.index("cvr")
    assert {"team", "portal", "projects", "cvr"} <= set(modules)


# --- portal invitations ------------------------------------------------------------------------


async def test_an_invitation_creates_an_account_that_sets_its_own_password(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, delivered: list
):
    team = Team(name="Client - Acme")
    db_session.add(team)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "inviter", "portal.invite")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    await reset_recovery_budgets("client@acme.example")

    response = await client.post(
        "/api/v1/portal/invitations",
        json={"name": "Casey Client", "email": "Client@Acme.example", "team_ids": [team.id]},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    invited = response.json()
    assert invited["email"] == "client@acme.example"
    assert invited["activated"] is False
    assert invited["teams"] == ["Client - Acme"]
    assert [m["to"] for m in delivered] == ["client@acme.example"]
    assert "/reset-password?token=" in delivered[0]["link"]

    token = delivered[0]["link"].split("token=")[1]
    reset = await client.post("/api/v1/auth/password/reset-confirm", json={"token": token, "new_password": "Cl1ent!Passw0rd"})
    assert reset.status_code == 200, reset.text
    login = await client.post("/api/v1/auth/login", data={"username": invited["username"], "password": "Cl1ent!Passw0rd"})
    assert login.status_code == 200, login.text


async def test_inviting_needs_the_permission_and_a_free_address(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, delivered: list
):
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    body = {"name": "Someone Else", "email": test_user_2["email"]}

    assert (await client.post("/api/v1/portal/invitations", json=body, headers=headers)).status_code == 403

    await _grant(db_session, test_user["id"], "inviter", "portal.invite")
    assert (await client.post("/api/v1/portal/invitations", json=body, headers=headers)).status_code == 409


async def test_an_invitation_cannot_join_an_entra_linked_team(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, delivered: list
):
    team = Team(name="Staff", entra_group_id="aabbccdd-0000-0000-0000-000000000001")
    db_session.add(team)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "inviter", "portal.invite")
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    response = await client.post(
        "/api/v1/portal/invitations",
        json={"name": "Ex Ternal", "email": "x@ext.example", "team_ids": [team.id]},
        headers=headers,
    )

    assert response.status_code == 422
    assert await db_session.scalar(select(User.id).where(User.email == "x@ext.example")) is None


# --- projects and CVR ----------------------------------------------------------------------------


async def _project(client: AsyncClient, headers: dict, **values: Any) -> dict:
    response = await client.post("/api/v1/projects/", json={"code": "P-1", "name": "Plant upgrade", **values}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_client_sees_only_the_projects_of_their_team(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    team = Team(name="Client - Acme")
    db_session.add(team)
    await db_session.flush()
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user_2["id"]))
    await db_session.commit()
    await _grant(db_session, test_user["id"], "pm", "projects.create", "projects.read")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    theirs = await _project(client, headers, client_team_id=team.id)
    other = await _project(client, headers, code="P-2")

    await _login(client, test_user_2)

    assert [p["code"] for p in (await client.get("/api/v1/projects/")).json()["data"]] == ["P-1"]
    assert (await client.get(f"/api/v1/projects/{theirs['id']}")).status_code == 200
    assert (await client.get(f"/api/v1/projects/{other['id']}")).status_code == 404


async def test_cvr_reconciles_cost_against_value(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "qs", "projects.create", "projects.read", "cvr.read", "cvr.edit")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    project = await _project(client, headers)
    base = f"/api/v1/cvr/projects/{project['id']}"

    for code, cost, value in [("01", "1000.00", "1200.00"), ("02", "500.50", "400.00")]:
        added = await client.post(
            f"{base}/cost-heads",
            json={"code": code, "description": f"Head {code}", "cost_to_date": cost, "value_to_date": value},
            headers=headers,
        )
        assert added.status_code == 201, added.text
    heads = (await client.get(f"{base}/cost-heads")).json()
    edited = await client.patch(f"{base}/cost-heads/{heads[1]['id']}", json={"value_to_date": "600.50"}, headers=headers)
    summary = (await client.get(f"{base}/summary")).json()

    assert heads[0]["margin_to_date"] == "200.00"
    assert edited.json()["margin_to_date"] == "100.00"
    assert summary["cost_to_date"] == "1500.50"
    assert summary["margin_to_date"] == "300.00"
    assert summary["currency"] == "AUD"

    duplicate = await client.post(f"{base}/cost-heads", json={"code": "01", "description": "Again"}, headers=headers)
    assert duplicate.status_code == 409

    cashflow = await client.put(
        f"{base}/cashflow",
        json={"periods": [{"period": "2026-03-17", "planned_cost": "100"}, {"period": "2026-02-01", "planned_cost": "50"}]},
        headers=headers,
    )
    assert [p["period"] for p in cashflow.json()] == ["2026-02-01", "2026-03-01"]


async def test_cvr_needs_its_own_permission_even_on_a_visible_project(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    await _grant(db_session, test_user["id"], "pm", "projects.create", "projects.read")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    project = await _project(client, headers)

    assert (await client.get(f"/api/v1/cvr/projects/{project['id']}/cost-heads")).status_code == 403

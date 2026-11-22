"""The lobby: listing, the access-request lifecycle with its cooldown, and single-use email-bound invites."""

import re
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mail import service as mail_service
from src.infrastructure.modules import state
from src.modules.lobby.models import AccessRequest, ProjectInvite
from src.modules.notifications.models import Notification
from src.modules.projects.models import Project, ProjectMember
from src.modules.team.models import Team, TeamMembership
from src.modules.user.models import User
from tests.integration.modules.people import PASSWORD, grant, login, make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

MANAGER = ("projects.read", "projects.manage_access")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture
def mails(monkeypatch) -> list:
    sent: list = []

    async def capture(mail) -> None:
        sent.append(mail)

    monkeypatch.setattr(mail_service, "deliver", capture)
    monkeypatch.setattr("src.modules.lobby.service.deliver", capture)
    return sent


@pytest_asyncio.fixture
async def world(db_session: AsyncSession):
    team = Team(name="Client - Rail Co")
    db_session.add(team)
    await db_session.flush()
    listed = Project(code="LB-1", name="Rail loop", client_team_id=team.id)
    hidden = Project(code="LB-2", name="Stacker reclaimer")
    db_session.add_all([listed, hidden])
    await db_session.commit()
    manager = await make_user(db_session, "Maya Manager")
    await grant(db_session, manager, *MANAGER)
    return listed, hidden, team, manager


async def _staff_session(client: AsyncClient, db: AsyncSession, user: dict) -> dict:
    """Sign in, then mark the account Entra-linked (internal staff) for the rest of the session."""
    await db.execute(update(User).where(User.id == user["id"]).values(entra_id=None))
    await db.commit()
    headers = await login(client, user)
    await db.execute(update(User).where(User.id == user["id"]).values(entra_id=f"00000000-0000-0000-0000-{user['id']:012d}"))
    await db.commit()
    return headers


async def test_access_request_lifecycle_with_cooldown(client: AsyncClient, db_session: AsyncSession, world):
    listed, hidden, _, manager = world
    requester = await make_user(db_session, "Ian Internal")

    headers_m = await login(client, manager)
    assert (
        await client.put(f"/api/v1/lobby/projects/{listed.id}/listing", json={"visible": True}, headers=headers_m)
    ).status_code == 200

    headers = await _staff_session(client, db_session, requester)
    lobby = (await client.get("/api/v1/lobby/projects/")).json()["data"]
    assert [p["code"] for p in lobby] == ["LB-1"]  # the unlisted project isn't shown
    assert (await client.get(f"/api/v1/projects/{listed.id}")).status_code == 404

    # an unlisted project by id alone is not found; by its exact code it is
    assert (await client.post("/api/v1/lobby/requests", json={"project_id": hidden.id}, headers=headers)).status_code == 404
    assert (await client.get("/api/v1/lobby/lookup", params={"code": "lb-2"})).json()["name"] == "Stacker reclaimer"

    filed = await client.post(
        "/api/v1/lobby/requests", json={"project_id": listed.id, "message": "Joining the shutdown crew"}, headers=headers
    )
    assert filed.status_code == 201, filed.text
    rid = filed.json()["id"]
    assert (await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)).status_code == 409
    titles = (await db_session.execute(select(Notification.title).where(Notification.user_id == manager["id"]))).scalars()
    assert "Ian Internal asks to join LB-1" in list(titles)

    # withdrawn: no cooldown
    assert (await client.post(f"/api/v1/lobby/requests/{rid}/withdraw", headers=headers)).json()["status"] == "withdrawn"
    rid = (await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)).json()["id"]

    headers_m = await login(client, manager)
    queue = (await client.get("/api/v1/lobby/requests/")).json()["data"]
    assert [(r["id"], r["user_name"]) for r in queue] == [(rid, "Ian Internal")]
    rejected = await client.post(
        f"/api/v1/lobby/requests/{rid}/reject", json={"reason": "Ask your supervisor first"}, headers=headers_m
    )
    assert rejected.json()["status"] == "rejected"

    headers = await _staff_session(client, db_session, requester)
    mine = (await client.get("/api/v1/lobby/requests/mine")).json()
    assert [(r["status"], r["rejection_reason"]) for r in mine] == [("rejected", "Ask your supervisor first")]
    again_at = datetime.fromisoformat(mine[0]["request_again_at"])
    assert timedelta(hours=23, minutes=59) < again_at - datetime.now(UTC) <= timedelta(hours=24)
    too_soon = await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)
    assert too_soon.status_code == 409
    assert "request access again from" in too_soon.text

    # a day later "Request again" works
    await db_session.execute(
        update(AccessRequest).where(AccessRequest.id == rid).values(decided_at=datetime.now(UTC) - timedelta(hours=25))
    )
    unlist = await client.put(f"/api/v1/lobby/projects/{listed.id}/listing", json={"visible": False}, headers=headers)
    assert unlist.status_code == 403  # not theirs to change
    await db_session.commit()
    rid = (await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)).json()["id"]

    headers_m = await login(client, manager)
    approved = await client.post(f"/api/v1/lobby/requests/{rid}/approve", json={}, headers=headers_m)
    assert (approved.json()["status"], approved.json()["grant"]) == ("approved", "member")
    assert (await client.post(f"/api/v1/lobby/requests/{rid}/reject", json={}, headers=headers_m)).status_code == 409
    members = (await client.get(f"/api/v1/lobby/projects/{listed.id}/members")).json()
    assert [(m["name"], m["via"], m["source"]) for m in members] == [("Ian Internal", "direct", "access_request")]

    headers = await _staff_session(client, db_session, requester)
    assert (await client.get(f"/api/v1/projects/{listed.id}")).status_code == 200
    assert [p["code"] for p in (await client.get("/api/v1/projects/")).json()["data"]] == ["LB-1"]
    assert (await client.get("/api/v1/lobby/projects/")).json()["data"] == []
    assert (await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)).status_code == 409


async def test_externals_cannot_browse_or_request(client: AsyncClient, db_session: AsyncSession, world):
    listed, _, _, manager = world
    headers_m = await login(client, manager)
    await client.put(f"/api/v1/lobby/projects/{listed.id}/listing", json={"visible": True}, headers=headers_m)
    outsider = await make_user(db_session, "Erin External")
    headers = await login(client, outsider)
    assert (await client.get("/api/v1/lobby/projects/")).json()["data"] == []
    assert (await client.get("/api/v1/lobby/lookup", params={"code": "LB-1"})).status_code == 404
    assert (await client.post("/api/v1/lobby/requests", json={"project_id": listed.id}, headers=headers)).status_code == 404
    assert (await client.get("/api/v1/lobby/requests/")).status_code == 403


def _token(link: str) -> str:
    match = re.search(r"/invite#([A-Za-z0-9_-]+)$", link)
    assert match, link
    return match.group(1)


async def test_invites_are_single_use_expiring_and_bound_to_the_email(
    client: AsyncClient, db_session: AsyncSession, world, mails: list
):
    listed, _, team, manager = world
    invitee = await make_user(db_session, "Carla Client")
    other = await make_user(db_session, "Otto Other")

    headers_m = await login(client, manager)
    made = await client.post(
        f"/api/v1/lobby/projects/{listed.id}/invites", json={"email": invitee["email"].upper()}, headers=headers_m
    )
    assert made.status_code == 201, made.text
    invite = made.json()
    assert (invite["email"], invite["grant"], invite["created_account"]) == (invitee["email"], "client_team", False)
    token = _token(invite["link"])
    assert [m.to for m in mails] == [[invitee["email"]]]
    assert invite["link"] in mails[0].text
    stored = await db_session.scalar(select(ProjectInvite.token_hash).where(ProjectInvite.id == invite["id"]))
    assert stored != token and len(stored or "") == 64  # only the hash is kept

    # another account can't use it
    headers_o = await login(client, other)
    preview = await client.post("/api/v1/lobby/invites/preview", json={"token": token}, headers=headers_o)
    assert (preview.json()["project_code"], preview.json()["for_you"]) == ("LB-1", False)
    assert preview.headers["cache-control"] == "no-store"
    assert (await client.post("/api/v1/lobby/invites/accept", json={"token": token}, headers=headers_o)).status_code == 403

    headers_i = await login(client, invitee)
    joined = await client.post("/api/v1/lobby/invites/accept", json={"token": token}, headers=headers_i)
    assert joined.status_code == 200, joined.text
    assert joined.json()["project_code"] == "LB-1"
    assert await db_session.get(TeamMembership, (team.id, invitee["id"])) is not None
    assert (await client.get(f"/api/v1/projects/{listed.id}")).status_code == 200
    # single use
    assert (await client.post("/api/v1/lobby/invites/accept", json={"token": token}, headers=headers_i)).status_code == 410

    # expiry, and a re-send replacing the link
    headers_m = await login(client, manager)
    second = (
        await client.post(
            f"/api/v1/lobby/projects/{listed.id}/invites", json={"email": other["email"], "grant": "member"}, headers=headers_m
        )
    ).json()
    await db_session.execute(
        update(ProjectInvite)
        .where(ProjectInvite.id == second["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    headers_o = await login(client, other)
    assert (
        await client.post("/api/v1/lobby/invites/accept", json={"token": _token(second["link"])}, headers=headers_o)
    ).status_code == 410

    headers_m = await login(client, manager)
    resent = (await client.post(f"/api/v1/lobby/invites/{second['id']}/resend", headers=headers_m)).json()
    assert resent["expired"] is False
    headers_o = await login(client, other)
    assert (
        await client.post("/api/v1/lobby/invites/accept", json={"token": _token(second["link"])}, headers=headers_o)
    ).status_code == 410
    accepted = await client.post("/api/v1/lobby/invites/accept", json={"token": _token(resent["link"])}, headers=headers_o)
    assert accepted.status_code == 200
    assert await db_session.get(ProjectMember, (listed.id, other["id"])) is not None

    # a revoked invite is dead
    headers_m = await login(client, manager)
    third_user = await make_user(db_session, "Rae Revoked")
    third = (
        await client.post(f"/api/v1/lobby/projects/{listed.id}/invites", json={"email": third_user["email"]}, headers=headers_m)
    ).json()
    assert (await client.post(f"/api/v1/lobby/invites/{third['id']}/revoke", headers=headers_m)).json()["status"] == "revoked"
    headers_r = await login(client, third_user)
    assert (
        await client.post("/api/v1/lobby/invites/accept", json={"token": _token(third["link"])}, headers=headers_r)
    ).status_code == 410


async def test_a_new_person_joins_at_first_sign_in(client: AsyncClient, db_session: AsyncSession, world, mails: list):
    listed, _, team, manager = world
    headers_m = await login(client, manager)
    made = await client.post(
        f"/api/v1/lobby/projects/{listed.id}/invites",
        json={"email": "new.person@rail.example", "name": "Nina New"},
        headers=headers_m,
    )
    assert made.status_code == 201, made.text
    assert made.json()["created_account"] is True
    account = await db_session.scalar(select(User).where(User.email == "new.person@rail.example"))
    assert account is not None and account.entra_id is None

    # they set their password from the emailed link (simulated) and sign in for the first time
    account.hashed_password = get_password_hash(PASSWORD)
    await db_session.commit()
    headers = await login(client, {"username": account.username, "password": PASSWORD})
    joined = (await client.post("/api/v1/lobby/claim", headers=headers)).json()
    assert [j["project_code"] for j in joined] == ["LB-1"]
    assert await db_session.get(TeamMembership, (team.id, account.id)) is not None


async def test_an_invited_external_joins_from_the_lobby(client: AsyncClient, db_session: AsyncSession, world, mails: list):
    listed, hidden, _, manager = world
    invitee = await make_user(db_session, "Lou Lobby")
    headers_m = await login(client, manager)
    invite = (
        await client.post(f"/api/v1/lobby/projects/{hidden.id}/invites", json={"email": invitee["email"]}, headers=headers_m)
    ).json()
    assert invite["grant"] == "member"  # no client team on that project

    headers = await login(client, invitee)
    lobby = (await client.get("/api/v1/lobby/projects/")).json()["data"]
    assert [(p["code"], p["invite_id"]) for p in lobby] == [("LB-2", invite["id"])]
    joined = await client.post(f"/api/v1/lobby/invites/{invite['id']}/join", headers=headers)
    assert joined.status_code == 200, joined.text
    assert (await client.get(f"/api/v1/projects/{hidden.id}")).status_code == 200

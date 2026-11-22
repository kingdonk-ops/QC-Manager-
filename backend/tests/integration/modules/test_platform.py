"""The shared platform: module switches, access levels, notifications, comments, files, numbering."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.config.settings import settings
from src.infrastructure.modules import routes, state
from src.infrastructure.records import assert_transition, history_of, next_reference, record_transition
from src.infrastructure.records.history import TransitionNotAllowed
from src.modules.notifications.models import Notification
from src.modules.notifications.service import notify
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_DIR", str(tmp_path))
    return tmp_path


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant")
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r-{user['id']}-{len(permissions)}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


# --- module switches ------------------------------------------------------------------------------


async def test_switching_a_module_off_answers_404_and_back_on_restores_it(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "platform.modules", "projects.read", "cvr.read")
    url = f"/api/v1/cvr/projects/{project.id}/cost-heads"
    assert (await client.get(url)).status_code == 200

    off = await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": False}, headers=headers)
    assert off.status_code == 200, off.text
    assert off.json()["changed"] == ["cvr"]
    assert (await client.get(url)).status_code == 404
    listed = {m["name"]: m["enabled"] for m in (await client.get("/api/v1/modules")).json()}
    assert listed["cvr"] is False

    await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": True}, headers=headers)
    assert (await client.get(url)).status_code == 200


async def test_core_modules_cannot_be_switched_off(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    headers = await _as(client, db_session, test_user, "platform.modules")

    response = await client.patch("/api/v1/modules/projects/toggle", json={"enabled": False}, headers=headers)

    assert response.status_code == 422


async def test_switching_needs_the_permission(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    assert (await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": False}, headers=headers)).status_code == 403


async def test_dependents_need_cascade(client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch):
    monkeypatch.setattr(routes, "dependents_of", lambda name: ("cvr",) if name == "portal" else ())
    headers = await _as(client, db_session, test_user, "platform.modules")

    refused = await client.patch("/api/v1/modules/portal/toggle", json={"enabled": False}, headers=headers)
    assert refused.status_code == 422
    assert "cascade" in refused.text

    cascaded = await client.patch("/api/v1/modules/portal/toggle", json={"enabled": False, "cascade": True}, headers=headers)
    assert cascaded.json()["changed"] == ["portal", "cvr"]
    await client.patch("/api/v1/modules/portal/toggle", json={"enabled": True}, headers=headers)
    await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": True}, headers=headers)


async def test_a_project_can_switch_a_module_off_for_itself(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    one, two = await _project(db_session, "P-1"), await _project(db_session, "P-2")
    headers = await _as(client, db_session, test_user, "projects.read", "projects.update", "cvr.read")

    saved = await client.put(f"/api/v1/projects/{one.id}/modules", json={"overrides": {"cvr": False}}, headers=headers)

    assert saved.json() == {"cvr": False}
    assert (await client.get(f"/api/v1/cvr/projects/{one.id}/cost-heads")).status_code == 404
    assert (await client.get(f"/api/v1/cvr/projects/{two.id}/cost-heads")).status_code == 200
    scoped = {m["name"]: m["enabled"] for m in (await client.get("/api/v1/modules", params={"project_id": one.id})).json()}
    assert scoped["cvr"] is False


# --- access levels ---------------------------------------------------------------------------------


async def test_an_access_level_replaces_what_roles_give_for_that_module(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user_2["id"], "qs", "cvr.read", "cvr.edit", "projects.read")
    headers = await _as(client, db_session, test_user, "platform.access")

    view = await client.put(f"/api/v1/platform/access/{test_user_2['id']}", json={"levels": {"cvr": "view"}}, headers=headers)
    assert view.status_code == 200, view.text
    rows = {r["module"]: r for r in view.json()}
    assert rows["cvr"]["level"] == "view"
    assert rows["cvr"]["effective"] == ["cvr.read"]

    none = await client.post(f"/api/v1/platform/access/{test_user_2['id']}/preset", json={"preset": "minimal"}, headers=headers)
    rows = {r["module"]: r for r in none.json()}
    assert rows["cvr"]["effective"] == []
    assert rows["projects"]["effective"] == ["projects.read"]

    cleared = await client.post(
        f"/api/v1/platform/access/{test_user_2['id']}/preset", json={"preset": "clear"}, headers=headers
    )
    assert {r["module"]: r for r in cleared.json()}["cvr"]["effective"] == ["cvr.edit", "cvr.read"]


async def test_nobody_sets_their_own_access(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    headers = await _as(client, db_session, test_user, "platform.access")

    response = await client.put(f"/api/v1/platform/access/{test_user['id']}", json={"levels": {"cvr": "full"}}, headers=headers)

    assert response.status_code == 422


async def test_preferences_round_trip(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    await client.put("/api/v1/platform/me/preferences/onboarding", json={"value": {"done": True}}, headers=headers)

    assert (await client.get("/api/v1/platform/me/preferences")).json() == {"onboarding": {"done": True}}


# --- comments and notifications --------------------------------------------------------------------


async def test_a_mention_notifies_and_a_reply_notifies_the_thread(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    perms = ("projects.read", "comments.read", "comments.create")
    await _grant(db_session, test_user_2["id"], "commenter2", *perms)
    headers = await _as(client, db_session, test_user, *perms)

    posted = await client.post(
        "/api/v1/comments/",
        json={
            "project_id": project.id,
            "entity_type": "rfi",
            "entity_id": 7,
            "body": f"Can you check? @{test_user_2['username']}",
        },
        headers=headers,
        params={"link": "/rfi?id=7"},
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["mentions"] == [test_user_2["id"]]

    headers_2 = {"X-CSRF-Token": await _login(client, test_user_2)}
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert [n["category"] for n in inbox] == ["mention"]
    assert inbox[0]["link"] == "/rfi?id=7"
    assert (await client.get("/api/v1/notifications/unread-count")).json() == {"unread": 1}

    replied = await client.post(f"/api/v1/comments/{posted.json()['id']}/reply", json={"body": "Done."}, headers=headers_2)
    assert replied.status_code == 201
    await client.post("/api/v1/notifications/read-all", headers=headers_2)
    assert (await client.get("/api/v1/notifications/unread-count")).json() == {"unread": 0}

    await _login(client, test_user)
    threads = (
        await client.get("/api/v1/comments/", params={"project_id": project.id, "entity_type": "rfi", "entity_id": 7})
    ).json()
    assert [r["body"] for r in threads[0]["replies"]] == ["Done."]
    unread = (await client.get("/api/v1/notifications/", params={"unread_only": True})).json()["data"]
    assert [n["category"] for n in unread] == ["status"]


async def test_comments_follow_project_visibility(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    await _as(client, db_session, test_user, "comments.read")

    response = await client.get("/api/v1/comments/", params={"project_id": project.id, "entity_type": "rfi", "entity_id": 1})

    assert response.status_code == 404


async def test_preferences_can_switch_in_app_notifications_off(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    await client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "status", "in_app": False, "email": False}]},
        headers=headers,
    )

    await notify(db_session, [test_user["id"]], "status", "Ignored")
    await notify(db_session, [test_user["id"]], "assignment", "Kept")
    await db_session.commit()

    titles = [n["title"] for n in (await client.get("/api/v1/notifications/")).json()["data"]]
    assert titles == ["Kept"]
    assert await db_session.get(Notification, 10_000) is None


# --- files ------------------------------------------------------------------------------------------


async def test_upload_revise_download_and_delete(client: AsyncClient, db_session: AsyncSession, test_user: dict, storage_dir):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "projects.read", "files.read", "files.upload")

    first = await client.post(
        "/api/v1/files/",
        data={"project_id": str(project.id), "tags": "level 2, east"},
        files={"file": ("PRJ-ZZZ-XX-DR-A-0001.pdf", b"%PDF-1.4 one", "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert first.json()["category"] == "drawing"
    assert first.json()["tags"] == ["level 2", "east"]

    second = await client.post(
        "/api/v1/files/",
        data={"supersedes_id": str(first.json()["id"])},
        files={"file": ("PRJ-ZZZ-XX-DR-A-0001.pdf", b"%PDF-1.4 two", "application/pdf")},
        headers=headers,
    )
    assert second.json()["revision"] == 2

    listed = (await client.get("/api/v1/files/", params={"project_id": project.id})).json()["data"]
    assert [f["revision"] for f in listed] == [2]
    assert (await client.get("/api/v1/files/", params={"project_id": project.id, "search": "east"})).json()["total_count"] == 1

    body = await client.get(f"/api/v1/files/{second.json()['id']}/download", params={"inline": True})
    assert body.content == b"%PDF-1.4 two"
    assert body.headers["content-disposition"].startswith("inline")

    assert (await client.delete(f"/api/v1/files/{second.json()['id']}", headers=headers)).status_code == 200
    assert [f["revision"] for f in (await client.get("/api/v1/files/", params={"project_id": project.id})).json()["data"]] == [
        1
    ]


async def test_files_of_an_unseen_project_are_hidden(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, storage_dir
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, "projects.read", "files.read", "files.upload")
    uploaded = await client.post(
        "/api/v1/files/",
        data={"project_id": str(project.id)},
        files={"file": ("a.txt", b"x", "text/plain")},
        headers=headers,
    )
    await _as(client, db_session, test_user_2, "files.read")

    assert (await client.get(f"/api/v1/files/{uploaded.json()['id']}/download")).status_code == 404


async def test_uploads_over_the_limit_are_refused(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, storage_dir, monkeypatch
):
    monkeypatch.setattr(settings, "FILE_MAX_UPLOAD_MB", 0)
    headers = await _as(client, db_session, test_user, "files.upload")

    response = await client.post(
        "/api/v1/files/", files={"file": ("big.bin", b"xx", "application/octet-stream")}, headers=headers
    )

    assert response.status_code == 422
    assert list(storage_dir.rglob("*.*")) == []


# --- records -----------------------------------------------------------------------------------------


async def test_reference_numbers_count_per_project(db_session: AsyncSession):
    one, two = await _project(db_session, "A"), await _project(db_session, "B")

    refs = [await next_reference(db_session, "RFI", one.id), await next_reference(db_session, "RFI", one.id)]
    other = await next_reference(db_session, "RFI", two.id)
    await db_session.commit()

    assert refs == ["RFI-001", "RFI-002"]
    assert other == "RFI-001"


async def test_transitions_are_checked_and_recorded(db_session: AsyncSession):
    flow = {"draft": {"open"}, "open": {"answered"}}
    assert_transition(flow, "draft", "open")
    with pytest.raises(TransitionNotAllowed):
        assert_transition(flow, "draft", "answered")

    await record_transition(db_session, "rfi", 1, "draft", "open", None, note="Issued")
    await db_session.commit()

    assert [(h["from_status"], h["to_status"], h["note"]) for h in await history_of(db_session, "rfi", 1)] == [
        ("draft", "open", "Issued")
    ]

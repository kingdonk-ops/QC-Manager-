"""CDE: naming validation, P/C revisions, approval gates and access by state."""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state

from .helpers import client_team, make_project, make_user, sign_in

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

STAFF = ("projects.read", "cde.read")
AUTHOR = (*STAFF, "cde.upload", "cde.transition")

FIELDS = {
    "project": "PRJ",
    "originator": "ORG",
    "volume": "ZZ",
    "level": "XX",
    "type": "DR",
    "role": "A",
    "number": "0001",
}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _register(client: AsyncClient, headers: dict, project_id: int, fields: dict | None = None, **form):
    data = {"project_id": str(project_id), "title": "General arrangement", **form}
    if fields is not None:
        data["fields"] = json.dumps(fields)
    return await client.post(
        "/api/v1/cde/documents/",
        data=data,
        files={"file": ("ga.pdf", b"%PDF-1.4 ga", "application/pdf")},
        headers=headers,
    )


async def _status(client: AsyncClient, headers: dict, doc_id: int, **body) -> dict:
    response = await client.patch(f"/api/v1/cde/documents/{doc_id}/status", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_names_are_checked_against_the_convention(client: AsyncClient, db_session: AsyncSession):
    project = await make_project(db_session)
    author = await make_user(db_session, "Author", *AUTHOR, "cde.manage")
    headers = await sign_in(client, author)

    default = (await client.get(f"/api/v1/cde/naming/{project.id}")).json()
    assert default["is_default"] is True
    assert [f["key"] for f in default["fields"]] == ["project", "originator", "volume", "level", "type", "role", "number"]

    bad = await _register(client, headers, project.id, {**FIELDS, "type": "XY", "number": "12"})
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert "Type (type): 'XY' is not an allowed code" in detail
    assert "Number (number): '12' must be 4 to 6 characters long" in detail
    assert "Role" not in detail

    short = await _register(client, headers, project.id, name="PRJ-ORG-ZZ-DR")
    assert short.status_code == 422
    assert "has 4 parts separated by '-' but the convention has 7" in short.json()["detail"]

    good = await _register(client, headers, project.id, name="prj-org-zz-xx-dr-a-0001")
    assert good.status_code == 201, good.text
    doc = good.json()
    assert (doc["name"], doc["state"], doc["suitability"], doc["revision"]) == ("PRJ-ORG-ZZ-XX-DR-A-0001", "wip", "S0", "P01")
    assert doc["fields"]["type"] == "DR"
    assert (await _register(client, headers, project.id, FIELDS)).status_code == 409

    custom = await client.put(
        f"/api/v1/cde/naming/{project.id}",
        json={
            "separator": "_",
            "require_share_approval": False,
            "fields": [
                {"key": "originator", "label": "Originator", "min_length": 3, "max_length": 3},
                {"key": "discipline", "label": "Discipline", "codes": [{"code": "mec"}, {"code": "ele"}]},
                {"key": "number", "label": "Number", "min_length": 3, "max_length": 3, "charset": "numeric"},
            ],
        },
        headers=headers,
    )
    assert custom.status_code == 200, custom.text
    assert custom.json()["example"] == "XXX_MEC_001"
    wrong = await _register(client, headers, project.id, {"originator": "KAE", "discipline": "CIV", "number": "0A1"})
    detail = wrong.json()["detail"]
    assert "Discipline (discipline): 'CIV' is not an allowed code (allowed: MEC, ELE)" in detail
    assert "Number (number): '0A1' may contain only digits" in detail
    ok = await _register(client, headers, project.id, {"originator": "KAE", "discipline": "ele", "number": "001"})
    assert ok.json()["name"] == "KAE_ELE_001"

    # Without the gate, the author shares straight away.
    shared = await _status(client, headers, ok.json()["id"], state="shared", suitability="S1")
    assert (shared["state"], shared["suitability"], shared["pending_state"]) == ("shared", "S1", None)


async def test_revisions_gates_and_access_by_state(client: AsyncClient, db_session: AsyncSession):
    external = await make_user(db_session, "Client viewer", "cde.read")
    team = await client_team(db_session, external["id"])
    project = await make_project(db_session, client_team_id=team.id)
    author = await make_user(db_session, "Author", *AUTHOR)
    colleague = await make_user(db_session, "Colleague", *AUTHOR)
    checker = await make_user(db_session, "Checker", *STAFF, "cde.review")
    approver = await make_user(db_session, "Approver", *AUTHOR, "cde.approve")

    headers = await sign_in(client, author)
    doc = (await _register(client, headers, project.id, FIELDS)).json()
    did = doc["id"]

    revised = await client.post(
        f"/api/v1/cde/documents/{did}/revisions",
        data={"comment": "Grid lines moved"},
        files={"file": ("ga-p02.pdf", b"%PDF-1.4 p02", "application/pdf")},
        headers=headers,
    )
    assert revised.status_code == 201, revised.text
    body = revised.json()
    assert body["revision"] == "P02"
    assert [(r["code"], r["superseded"]) for r in body["revisions"]] == [("P02", False), ("P01", True)]

    # WIP is the author's: a colleague can't see it.
    await sign_in(client, colleague)
    assert (await client.get(f"/api/v1/cde/documents/{did}")).status_code == 404
    assert (await client.get("/api/v1/cde/documents/", params={"project_id": project.id})).json()["total_count"] == 0

    # Sharing needs the task team's check (the default convention requires it).
    headers = await sign_in(client, author)
    bad = await client.patch(
        f"/api/v1/cde/documents/{did}/status", json={"state": "shared", "suitability": "A1"}, headers=headers
    )
    assert bad.status_code == 422
    requested = await _status(client, headers, did, state="shared", suitability="S2", comment="For coordination")
    assert (requested["state"], requested["pending_state"]) == ("wip", "shared")
    own = await client.patch(f"/api/v1/cde/documents/{did}/status", json={"decision": "approve"}, headers=headers)
    assert own.status_code == 403

    headers = await sign_in(client, checker)
    queue = (await client.get("/api/v1/cde/documents/", params={"project_id": project.id, "awaiting_me": True})).json()
    assert [d["id"] for d in queue["data"]] == [did]
    assert queue["data"][0]["can_decide"] is True
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(n["category"] == "approval" and "share" in n["title"] for n in inbox)
    shared = await _status(client, headers, did, decision="approve", comment="Checked")
    assert (shared["state"], shared["suitability"], shared["revision"]) == ("shared", "S2", "P02")

    # Shared is visible to the whole project team, not to the client.
    await sign_in(client, colleague)
    assert (await client.get(f"/api/v1/cde/documents/{did}")).status_code == 200
    await sign_in(client, external)
    assert (await client.get(f"/api/v1/cde/documents/{did}")).status_code == 404

    # Publishing always needs a cde.approve holder; a rejection keeps it shared.
    headers = await sign_in(client, author)
    await _status(client, headers, did, state="published", suitability="A1")
    headers = await sign_in(client, checker)
    refused = await client.patch(f"/api/v1/cde/documents/{did}/status", json={"decision": "approve"}, headers=headers)
    assert refused.status_code == 403
    headers = await sign_in(client, approver)
    rejected = await _status(client, headers, did, decision="reject", comment="Title block incomplete")
    assert (rejected["state"], rejected["pending_state"]) == ("shared", None)

    headers = await sign_in(client, author)
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any("rejected" in n["title"] for n in inbox)
    await _status(client, headers, did, state="published", suitability="A1", comment="Title block fixed")
    headers = await sign_in(client, approver)
    published = await _status(client, headers, did, decision="approve")
    assert (published["state"], published["suitability"], published["revision"]) == ("published", "A1", "C01")
    assert [(r["code"], r["superseded"]) for r in published["revisions"]] == [
        ("C01", False),
        ("P02", True),
        ("P01", True),
    ]

    history = (await client.get(f"/api/v1/cde/documents/{did}/history")).json()
    assert [h["to_status"] for h in history] == [
        "wip",
        "wip",
        "shared_requested",
        "shared",
        "published_requested",
        "published_rejected",
        "published_requested",
        "published",
    ]
    assert history[3]["changed_by_name"] == "Checker"

    # The client sees it now, with the published revision only.
    await sign_in(client, external)
    seen = (await client.get("/api/v1/cde/documents/", params={"project_id": project.id})).json()
    assert [d["revision"] for d in seen["data"]] == ["C01"]
    detail = (await client.get(f"/api/v1/cde/documents/{did}")).json()
    assert [r["code"] for r in detail["revisions"]] == ["C01"]
    assert (await client.get(f"/api/v1/cde/documents/{did}/download")).content == b"%PDF-1.4 p02"
    p01 = published["revisions"][2]["id"]
    blocked = await client.get(f"/api/v1/cde/documents/{did}/download", params={"revision_id": p01})
    assert blocked.status_code == 404
    counts = (await client.get("/api/v1/cde/documents/counts", params={"project_id": project.id})).json()
    assert counts == {"wip": 0, "shared": 0, "published": 1, "archived": 0, "awaiting_me": 0}
    assert {h["to_status"] for h in (await client.get(f"/api/v1/cde/documents/{did}/history")).json()} == {"published"}

    # A new revision of a published container restarts the P series in WIP.
    headers = await sign_in(client, author)
    next_one = await client.post(
        f"/api/v1/cde/documents/{did}/revisions",
        files={"file": ("ga-p03.pdf", b"%PDF-1.4 p03", "application/pdf")},
        headers=headers,
    )
    assert (next_one.json()["revision"], next_one.json()["state"]) == ("P03", "wip")
    filtered = await client.get(
        "/api/v1/cde/documents/", params={"project_id": project.id, "code": ["type:dr", "role:A"], "state": "wip"}
    )
    assert filtered.json()["total_count"] == 1
    none = await client.get("/api/v1/cde/documents/", params={"project_id": project.id, "code": ["type:M3"]})
    assert none.json()["total_count"] == 0

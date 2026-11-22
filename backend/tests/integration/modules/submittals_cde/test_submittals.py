"""Submittals: multi-stage review with a parallel step, early termination, revisions, the register."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state

from .helpers import make_project, make_user, sign_in

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

AUTHOR = (
    "projects.read",
    "submittals.read",
    "submittals.create",
    "submittals.update",
    "submittals.submit",
    "submittals.export",
    "files.read",
    "files.upload",
)
REVIEWER = ("projects.read", "submittals.read", "submittals.review")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def team(db_session: AsyncSession) -> dict:
    return {
        "author": await make_user(db_session, "Author", *AUTHOR),
        "contractor": await make_user(db_session, "Contractor", *REVIEWER),
        "engineer": await make_user(db_session, "Engineer", *REVIEWER),
        "architect": await make_user(db_session, "Architect", *REVIEWER),
        "client": await make_user(db_session, "Client", *REVIEWER),
    }


def _workflow(team: dict) -> list[dict]:
    return [
        {"name": "Contractor", "reviewer_ids": [team["contractor"]["id"]]},
        {"name": "Design team", "reviewer_ids": [team["engineer"]["id"], team["architect"]["id"]], "parallel": True},
        {"name": "Client", "reviewer_ids": [team["client"]["id"]]},
    ]


async def _create(client: AsyncClient, headers: dict, project_id: int, team: dict, **extra) -> dict:
    response = await client.post(
        "/api/v1/submittals/",
        json={
            "project_id": project_id,
            "title": "Pipe support shop drawings",
            "type": "shop_drawing",
            "spec_section": "15 10 00",
            "workflow": _workflow(team),
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _decide(client: AsyncClient, user: dict, sid: int, decision: str, comment: str = "") -> dict:
    headers = await sign_in(client, user)
    response = await client.post(
        f"/api/v1/submittals/{sid}/review", json={"decision": decision, "comment": comment or None}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_multi_stage_review_with_a_parallel_step(client: AsyncClient, db_session: AsyncSession, team: dict):
    project = await make_project(db_session)
    headers = await sign_in(client, team["author"])
    sub = await _create(client, headers, project.id, team, required_by="2020-01-01")
    assert (sub["code"], sub["status"], sub["revision_letter"]) == ("SUB-001", "draft", "A")
    assert [len(s["reviewer_ids"]) for s in sub["workflow"]] == [1, 2, 1]

    submitted = (await client.post(f"/api/v1/submittals/{sub['id']}/submit", json={}, headers=headers)).json()
    assert submitted["status"] == "submitted"
    assert submitted["current_reviewers"] == ["Contractor"]
    assert submitted["days_outstanding"] == 0
    assert submitted["overdue"] is True

    # Only the open step's reviewer may decide.
    early = await client.post(
        f"/api/v1/submittals/{sub['id']}/review",
        json={"decision": "approved"},
        headers=await sign_in(client, team["engineer"]),
    )
    assert early.status_code == 403

    after_contractor = await _decide(client, team["contractor"], sub["id"], "approved")
    assert after_contractor["status"] == "under_review"
    assert sorted(after_contractor["current_reviewers"]) == ["Architect", "Engineer"]

    # Engineer is notified when the parallel step opens (category approval).
    await sign_in(client, team["engineer"])
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(n["category"] == "approval" for n in inbox)
    mine = (await client.get("/api/v1/submittals/", params={"project_id": project.id, "reviewer": "me"})).json()["data"]
    assert [s["id"] for s in mine] == [sub["id"]]

    halfway = await _decide(client, team["engineer"], sub["id"], "approved_as_noted", "Add bracket spacing")
    assert halfway["current_reviewers"] == ["Architect"]
    after_design = await _decide(client, team["architect"], sub["id"], "approved")
    assert after_design["current_reviewers"] == ["Client"]

    done = await _decide(client, team["client"], sub["id"], "approved")
    assert done["status"] == "approved"
    assert done["days_outstanding"] is None
    stamps = {(r["reviewer_name"], r["decision"], r["comment"]) for r in done["reviews"]}
    assert ("Engineer", "approved_as_noted", "Add bracket spacing") in stamps
    assert all(r["state"] == "decided" for r in done["reviews"])

    headers = await sign_in(client, team["author"])
    history = (await client.get(f"/api/v1/submittals/{sub['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "submitted", "under_review", "approved"]
    export = await client.get("/api/v1/submittals/export", params={"project_id": project.id, "format": "csv"})
    assert export.status_code == 200
    assert "SUB-001" in export.text and "Rev A" in export.text


async def test_the_final_stage_outcome_is_its_most_severe_decision(client: AsyncClient, db_session: AsyncSession, team: dict):
    project = await make_project(db_session)
    headers = await sign_in(client, team["author"])
    sub = await _create(
        client,
        headers,
        project.id,
        team,
        workflow=[{"name": "Design", "reviewer_ids": [team["engineer"]["id"], team["architect"]["id"]], "parallel": True}],
    )
    await client.post(f"/api/v1/submittals/{sub['id']}/submit", json={}, headers=headers)
    await _decide(client, team["engineer"], sub["id"], "approved")
    done = await _decide(client, team["architect"], sub["id"], "approved_as_noted")
    assert done["status"] == "approved_as_noted"


async def test_revise_and_resubmit_ends_early_and_rev_b_starts_a_new_cycle(
    client: AsyncClient, db_session: AsyncSession, team: dict
):
    project = await make_project(db_session)
    headers = await sign_in(client, team["author"])
    sub = await _create(client, headers, project.id, team)

    # A file on Rev A.
    rev_a = sub["current_revision_id"]
    uploaded = await client.post(
        "/api/v1/files/",
        files={"file": ("drawing-a.pdf", b"%PDF-1.4 a", "application/pdf")},
        data={"project_id": str(project.id), "entity_type": "submittal_revision", "entity_id": str(rev_a)},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    await client.post(f"/api/v1/submittals/{sub['id']}/submit", json={}, headers=headers)

    await _decide(client, team["contractor"], sub["id"], "approved")
    ended = await _decide(client, team["engineer"], sub["id"], "revise_and_resubmit", "Wrong pipe class")
    assert ended["status"] == "revise_and_resubmit"
    states = {r["reviewer_name"]: r["state"] for r in ended["reviews"]}
    assert states == {"Contractor": "decided", "Engineer": "decided", "Architect": "skipped", "Client": "skipped"}
    assert ended["current_reviewers"] == []

    # The architect can no longer decide.
    late = await client.post(
        f"/api/v1/submittals/{sub['id']}/review",
        json={"decision": "approved"},
        headers=await sign_in(client, team["architect"]),
    )
    assert late.status_code == 403

    headers = await sign_in(client, team["author"])
    new_file = await client.post(
        "/api/v1/files/", files={"file": ("drawing-b.pdf", b"%PDF-1.4 b", "application/pdf")}, headers=headers
    )
    revised = await client.post(
        f"/api/v1/submittals/{sub['id']}/revise",
        json={"note": "Pipe class corrected", "file_ids": [new_file.json()["id"]]},
        headers=headers,
    )
    assert revised.status_code == 200, revised.text
    body = revised.json()
    assert (body["revision_letter"], body["status"], body["current_reviewers"]) == ("B", "submitted", ["Contractor"])
    assert all(r["state"] in ("open", "pending") for r in body["reviews"])

    cycles = (await client.get(f"/api/v1/submittals/{sub['id']}/revisions")).json()
    assert [(c["letter"], c["outcome"]) for c in cycles] == [("B", None), ("A", "revise_and_resubmit")]
    assert [f["name"] for f in cycles[0]["files"]] == ["drawing-b.pdf"]
    assert [f["name"] for f in cycles[1]["files"]] == ["drawing-a.pdf"]
    assert {r["decision"] for r in cycles[1]["reviews"]} == {"approved", "revise_and_resubmit", None}

    # A second revision while one is still in review is refused.
    again = await client.post(f"/api/v1/submittals/{sub['id']}/revise", json={}, headers=headers)
    assert again.status_code == 422


async def test_submitting_needs_a_workflow_and_the_register_filters(client: AsyncClient, db_session: AsyncSession, team: dict):
    project = await make_project(db_session)
    headers = await sign_in(client, team["author"])
    empty = await _create(client, headers, project.id, team, workflow=[], spec_section="09 90 00")
    refused = await client.post(f"/api/v1/submittals/{empty['id']}/submit", json={}, headers=headers)
    assert refused.status_code == 422

    # Sequential reviewers given on one step become one step each.
    patched = await client.patch(
        f"/api/v1/submittals/{empty['id']}",
        json={"workflow": [{"name": "Review", "reviewer_ids": [team["engineer"]["id"], team["client"]["id"]]}]},
        headers=headers,
    )
    assert [s["reviewer_ids"] for s in patched.json()["workflow"]] == [[team["engineer"]["id"]], [team["client"]["id"]]]

    bad = await client.patch(
        f"/api/v1/submittals/{empty['id']}", json={"workflow": [{"reviewer_ids": [999999]}]}, headers=headers
    )
    assert bad.status_code == 422

    other = await _create(client, headers, project.id, team, spec_section="15 10 00")
    await client.post(f"/api/v1/submittals/{other['id']}/submit", json={}, headers=headers)

    def codes(**params):
        return client.get("/api/v1/submittals/", params={"project_id": project.id, **params})

    assert [s["code"] for s in (await codes(spec_section="09")).json()["data"]] == [empty["code"]]
    assert [s["code"] for s in (await codes(status="submitted")).json()["data"]] == [other["code"]]
    assert (await codes()).json()["total_count"] == 2

    outsider = await make_user(db_session, "Outsider", "submittals.read")
    await sign_in(client, outsider)
    assert (await client.get(f"/api/v1/submittals/{other['id']}")).status_code == 404

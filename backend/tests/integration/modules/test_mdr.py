"""MDR dossiers: providers per section, the gate and how it degrades, draft compile with deduplicated certificate
appendices, and the issue -> sign -> client acceptance -> Rev 0 flow with the hash of the final bytes."""

import hashlib
import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import dossier as dossier_registry
from src.infrastructure.config.settings import settings
from src.infrastructure.dossier import MdrCheck, register_mdr_check
from src.infrastructure.modules import state
from src.modules.inspections.models import Inspection
from src.modules.projects.models import Project
from src.modules.team.models import Team, TeamMembership
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

STAFF = (
    "projects.read",
    "projects.update",
    "files.read",
    "files.upload",
    "ncr.read",
    "ncr.create",
    "ncr.update",
    "audit.read",
    *(f"asset_tree.{a}" for a in ("read", "create", "update", "configure")),
    *(f"mdr.{a}" for a in ("read", "create", "update", "delete", "submit", "sign")),
)


def pdf(marker: str, pages: int) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    for n in range(pages):
        c.drawString(100, 700, f"{marker} {n + 1}")
        c.showPage()
    c.save()
    return buffer.getvalue()


def pages_with(data: bytes, marker: str) -> int:
    return sum(1 for p in PdfReader(io.BytesIO(data)).pages if marker in (p.extract_text() or ""))


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest_asyncio.fixture
async def setup(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_DIR", str(tmp_path))
    team = Team(name="Client - Acme")
    db_session.add(team)
    await db_session.flush()
    db_session.add(TeamMembership(team_id=team.id, user_id=test_user_2["id"]))
    project = Project(code="P-1", name="Plant", client_team_id=team.id)
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "qa", *STAFF)
    await _grant(db_session, test_user_2["id"], "client", "mdr.read", "mdr.accept")
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers)

    async def node(level: str, code: str, parent: int | None = None) -> int:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        return int(r.json()["id"])

    async def upload(name: str, data: bytes, tags: str, **form: int | str) -> dict:
        r = await client.post(
            "/api/v1/files/",
            files={"file": (name, data, "application/pdf")},
            data={"project_id": str(project.id), "tags": tags, **{k: str(v) for k, v in form.items()}},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        return r.json()

    async def dossier(**body: object) -> dict:
        r = await client.post(
            "/api/v1/mdr/dossiers/", json={"project_id": project.id, "title": "Piping turnover", **body}, headers=headers
        )
        assert r.status_code == 201, r.text
        return r.json()

    return project, headers, node, upload, dossier


async def test_sections_list_their_providers_and_the_gate_degrades(client: AsyncClient, setup):
    project, headers, _, _, dossier = setup
    made = await dossier()
    assert made["code"] == "MDR-001"
    assert [s["key"] for s in made["sections"]][:3] == ["index", "itp", "inspections"]

    sections = {
        s["key"]: s["providers"] for s in (await client.get("/api/v1/mdr/sections", params={"project_id": project.id})).json()
    }
    assert sections["material_certs"] == ["files"]
    assert sections["ncr_register"] == ["ncr"]
    assert sections["as_built"] == ["cde", "files"]
    assert sections["itp"] == []

    gate = (await client.get(f"/api/v1/mdr/dossiers/{made['id']}/gate")).json()
    status = {c["key"]: c["status"] for c in gate["checks"]}
    assert status["issues_blocking"] == status["itp_hold_points"] == status["equipment_calibrated"] == "not_available"
    assert status["inspections_complete"] == status["ncr_open_major"] == "pass"
    assert gate["ready"] is True

    # A module switched off for the project, and a check that crashes, both degrade to "not available".
    await client.put(f"/api/v1/projects/{project.id}/modules", json={"overrides": {"ncr": False}}, headers=headers)

    async def broken(db, ctx):  # noqa: ANN001, ANN202
        raise RuntimeError("boom")

    register_mdr_check(MdrCheck("zz_broken", "Broken check", "mdr", broken))
    try:
        gate = (await client.get(f"/api/v1/mdr/dossiers/{made['id']}/gate")).json()
    finally:
        dossier_registry._checks.pop("zz_broken", None)
    status = {c["key"]: c["status"] for c in gate["checks"]}
    assert status["ncr_open_major"] == "not_available"
    assert status["zz_broken"] == "not_available"
    assert gate["ready"] is True


async def test_a_draft_merges_records_and_attaches_each_certificate_once(client: AsyncClient, setup):
    project, headers, node, upload, dossier = setup
    site = await node("site", "S")
    a1, a2 = await node("area", "A1", site), await node("area", "A2", site)
    asset = await node("asset", "101", a1)

    cert = pdf("CERTPAGE", 3)
    await upload("MTR-heat-42.pdf", cert, "mtr", entity_type="asset_node", entity_id=asset)
    await upload("MTR-heat-42-copy.pdf", cert, "mtr")  # the same certificate uploaded again
    await upload("CAL-0007.pdf", pdf("CALPAGE", 1), "calibration")
    await upload("MTR-elsewhere.pdf", pdf("OUTOFSCOPE", 2), "mtr", entity_type="asset_node", entity_id=a2)
    await upload("ISO-101-01.pdf", pdf("DRAWINGPAGE", 2), "as-built")

    made = await dossier(scope_node_ids=[a1])
    assert made["scope_labels"] == ["S / A1"]
    draft = await client.post(f"/api/v1/mdr/dossiers/{made['id']}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    revision = draft.json()
    assert revision["kind"] == "draft" and revision["revision"] is None

    appendix = revision["manifest"]["appendix"]
    assert [(a["name"], sorted(a["refs"])) for a in appendix] == [
        ("MTR-heat-42-copy.pdf", ["MTR-heat-42-copy.pdf", "MTR-heat-42.pdf"]),  # first by name
        ("CAL-0007.pdf", ["CAL-0007.pdf"]),
    ]
    assert appendix[0]["sha256"] == hashlib.sha256(cert).hexdigest()

    body = (await client.get(f"/api/v1/mdr/revisions/{revision['id']}/download")).content
    assert len(PdfReader(io.BytesIO(body)).pages) == revision["page_count"]
    assert pages_with(body, "CERTPAGE") == 3  # once, not twice
    assert pages_with(body, "CALPAGE") == 1
    assert pages_with(body, "DRAWINGPAGE") == 2
    assert pages_with(body, "OUTOFSCOPE") == 0
    assert pages_with(body, "DRAFT") == revision["page_count"]  # every page stamped
    sections = {s["key"]: s for s in revision["manifest"]["sections"]}
    assert "Not available" in (sections["itp"]["note"] or "")
    assert sections["material_certs"]["records"] == 2

    # A second draft replaces the first; the output file keeps its revision history.
    again = (await client.post(f"/api/v1/mdr/dossiers/{made['id']}/draft", headers=headers)).json()
    assert again["id"] == revision["id"] and again["file_id"] != revision["file_id"]
    history = (
        await client.get(
            "/api/v1/files/",
            params={"project_id": project.id, "entity_type": "mdr_output", "entity_id": made["id"], "include_superseded": True},
        )
    ).json()
    assert sorted(f["revision"] for f in history["data"]) == [1, 2]


async def test_issue_sign_accept_and_final(client: AsyncClient, setup, test_user: dict, test_user_2: dict):
    project, headers, _, upload, dossier = setup
    await upload("CAL-0007.pdf", pdf("CALPAGE", 1), "calibration")
    made = await dossier()
    base = f"/api/v1/mdr/dossiers/{made['id']}"

    ncr = (
        await client.post(
            "/api/v1/ncr/", json={"project_id": project.id, "title": "Weld undercut", "severity": "major"}, headers=headers
        )
    ).json()
    blocked = await client.post(f"{base}/issue", json={"purpose": "review"}, headers=headers)
    assert blocked.status_code == 422
    assert ncr["code"] in blocked.text
    assert (await client.post(f"{base}/draft", headers=headers)).status_code == 200  # a draft compiles anyway
    await client.patch(f"/api/v1/ncr/{ncr['id']}", json={"severity": "minor"}, headers=headers)

    assert (await client.post(f"{base}/issue", json={"purpose": "final"}, headers=headers)).status_code == 422
    issued = await client.post(f"{base}/issue", json={"purpose": "review", "note": "First issue"}, headers=headers)
    assert issued.status_code == 201, issued.text
    rev_a = issued.json()
    assert (rev_a["revision"], rev_a["status"]) == ("A", "pending_signature")
    assert (await client.post(f"{base}/issue", json={"purpose": "review"}, headers=headers)).status_code == 422

    signed = await client.post(f"/api/v1/mdr/revisions/{rev_a['id']}/sign", json={"confirm": True}, headers=headers)
    assert signed.status_code == 200, signed.text
    rev_a = signed.json()
    assert rev_a["status"] == "issued" and rev_a["signature"]["signer_id"] == test_user["id"]
    final_bytes = (await client.get(f"/api/v1/mdr/revisions/{rev_a['id']}/download")).content
    assert hashlib.sha256(final_bytes).hexdigest() == rev_a["sha256"]  # the hash is of the final, signed bytes
    assert rev_a["sha256"] != rev_a["signature"]["content_sha256"]
    assert pages_with(final_bytes, "Signature attestation") == 1
    stamped = rev_a["page_count"] - 1  # "Page n of N" was stamped before the attestation page was added
    assert pages_with(final_bytes, f"of {stamped}") == stamped
    assert (await client.get(base)).json()["status"] == "in_review"

    # The client, a portal user in the project's client team, accepts; it can't sign.
    client_headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    no_sign = await client.post(f"/api/v1/mdr/revisions/{rev_a['id']}/sign", json={"confirm": True}, headers=client_headers)
    assert no_sign.status_code == 403
    accepted = await client.post(
        f"/api/v1/mdr/revisions/{rev_a['id']}/decision", json={"decision": "accepted", "note": "OK"}, headers=client_headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decided_by_id"] == test_user_2["id"]

    headers = {"X-CSRF-Token": await _login(client, test_user)}
    gate = (await client.get(f"{base}/gate", params={"purpose": "final"})).json()
    assert {c["key"]: c["status"] for c in gate["checks"]}["client_acceptance"] == "pass"
    rev_0 = (await client.post(f"{base}/issue", json={"purpose": "final"}, headers=headers)).json()
    assert rev_0["revision"] == "0"
    rev_0 = (await client.post(f"/api/v1/mdr/revisions/{rev_0['id']}/sign", json={"confirm": True}, headers=headers)).json()
    dossier_now = (await client.get(base)).json()
    assert (dossier_now["status"], dossier_now["current_revision"]) == ("final", "0")

    copy = (await client.get(f"/api/v1/mdr/revisions/{rev_0['id']}/download")).content
    check = await client.post(f"{base}/verify-hash", json={"sha256": hashlib.sha256(copy).hexdigest()}, headers=headers)
    assert check.json() == {
        "match": True,
        "revision_id": rev_0["id"],
        "revision": "0",
        "kind": "final",
        "signed": True,
        "file_id": rev_0["file_id"],
    }
    assert (await client.post(f"{base}/verify-hash", json={"sha256": "0" * 64}, headers=headers)).json()["match"] is False

    revisions = (await client.get(f"{base}/revisions")).json()
    assert [(r["kind"], r["revision"], r["status"]) for r in revisions] == [
        ("final", "0", "issued"),
        ("review", "A", "accepted"),
        ("draft", None, "draft"),
    ]
    actions = [e["action"] for e in (await client.get("/api/v1/audit/entries/", params={"action": "mdr."})).json()["data"]]
    assert actions == [
        "mdr.revision.signed",
        "mdr.revision.issued",
        "mdr.revision.accepted",
        "mdr.revision.signed",
        "mdr.revision.issued",
        "mdr.dossier.created",
    ]
    assert (await client.get("/api/v1/audit/verify")).json()["ok"] is True
    assert (await client.delete(base, headers=headers)).status_code == 422


async def test_inspections_feed_the_records_section_and_block_while_open(client: AsyncClient, db_session: AsyncSession, setup):
    project, headers, _, _, dossier = setup
    db_session.add_all(
        [
            Inspection(project_id=project.id, code="INS-001", title="Hydrotest loop 1", status="completed"),
            Inspection(project_id=project.id, code="INS-002", title="Coating DFT", status="in_progress"),
        ]
    )
    await db_session.commit()
    made = await dossier(sections=[{"key": "inspections"}, {"key": "ncr_register", "enabled": False}])
    gate = (await client.get(f"/api/v1/mdr/dossiers/{made['id']}/gate")).json()
    check = next(c for c in gate["checks"] if c["key"] == "inspections_complete")
    assert check["status"] == "fail" and check["findings"][0]["reference"] == "INS-002"
    assert gate["ready"] is False

    draft = (await client.post(f"/api/v1/mdr/dossiers/{made['id']}/draft", headers=headers)).json()
    assert [(s["key"], s["records"]) for s in draft["manifest"]["sections"]] == [("inspections", 1)]
    body = (await client.get(f"/api/v1/mdr/revisions/{draft['id']}/download")).content
    assert pages_with(body, "Inspection INS-001") == 1
    assert pages_with(body, "INS-002") >= 1  # listed as an open finding on the draft's cover

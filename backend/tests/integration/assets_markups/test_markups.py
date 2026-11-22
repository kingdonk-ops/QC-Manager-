"""Markups on PDF drawings: sets, annotations, calibration, stamps, authorship and the flattened PDF."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

MARKUP = ("markups.read", "markups.create", "markups.export", "projects.read", "files.read", "files.upload")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


def _pdf() -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(842, 595))
    for i in range(2):
        canvas.drawString(72, 72, f"GA plan sheet {i + 1}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


async def _drawing(client: AsyncClient, db: AsyncSession, user: dict) -> tuple[Project, dict, dict]:
    project = Project(code="P-1", name="Plant")
    db.add(project)
    await db.commit()
    await _grant(db, user["id"], f"r{user['id']}", *MARKUP)
    headers = {"X-CSRF-Token": await _login(client, user)}
    uploaded = await client.post(
        "/api/v1/files/",
        data={"project_id": str(project.id)},
        files={"file": ("A-101 GA Plan.pdf", _pdf(), "application/pdf")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    return project, uploaded.json(), headers


async def test_markups_calibration_and_flattening(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project, drawing, owner_headers = await _drawing(client, db_session, test_user)
    fid = drawing["id"]

    # Someone else marks it up: their set is made for them, and the uploader hears about it.
    await _grant(db_session, test_user_2["id"], "reviewer", *MARKUP)
    headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    cloud = await client.post(
        "/api/v1/markups/",
        json={
            "file_id": fid,
            "page": 1,
            "type": "cloud",
            "geometry": {"x": 300, "y": 200, "w": -100, "h": 80},
            "style": {"color": "#2563eb", "width": 2},
            "text": "Revise door swing",
        },
        headers=headers,
    )
    assert cloud.status_code == 201, cloud.text
    body = cloud.json()
    assert body["geometry"] == {"x": 200.0, "y": 200.0, "w": 100.0, "h": 80.0}
    assert body["author_name"] == test_user_2["name"]
    sets = (await client.get("/api/v1/markups/sets/", params={"file_id": fid})).json()
    assert sets["total_count"] == 1
    assert sets["data"][0]["markup_count"] == 1 and sets["data"][0]["revision"] == 1

    length = await client.post(
        "/api/v1/markups/",
        json={"file_id": fid, "page": 1, "type": "measure_length", "geometry": {"points": [[100, 100], [300, 100]]}},
        headers=headers,
    )
    assert length.json()["measurement"] is None  # page not calibrated yet

    bad = await client.post(
        "/api/v1/markups/",
        json={"file_id": fid, "page": 1, "type": "measure_area", "geometry": {"points": [[0, 0], [1, 1]]}},
        headers=headers,
    )
    assert bad.status_code == 422

    calibrated = await client.put(
        f"/api/v1/markups/calibrations/{fid}/1",
        json={"points": [[0, 0], [400, 0]], "real_distance": 10, "unit": "m"},
        headers=headers,
    )
    assert calibrated.status_code == 200, calibrated.text
    assert calibrated.json()["meters_per_unit"] == pytest.approx(0.025)
    # The existing measurement is recalculated: 200 units x 0.025 m.
    listed = (await client.get("/api/v1/markups/", params={"file_id": fid, "pdf_page": 1})).json()["data"]
    measured = next(m for m in listed if m["type"] == "measure_length")
    assert measured["measurement"]["value"] == pytest.approx(5.0)

    area = await client.post(
        "/api/v1/markups/",
        json={
            "file_id": fid,
            "page": 1,
            "type": "measure_area",
            "geometry": {"points": [[0, 0], [200, 0], [200, 200], [0, 200]]},
        },
        headers=headers,
    )
    assert area.json()["measurement"] == {"value": pytest.approx(25.0), "unit": "m2", "meters_per_unit": pytest.approx(0.025)}
    page_two = await client.post(
        "/api/v1/markups/",
        json={"file_id": fid, "page": 2, "type": "measure_length", "geometry": {"points": [[0, 0], [100, 0]]}},
        headers=headers,
    )
    assert page_two.json()["measurement"] is None  # calibrations are per page
    assert (await client.get("/api/v1/markups/calibrations/", params={"file_id": fid})).json()["total_count"] == 1

    moved = await client.patch(
        f"/api/v1/markups/{measured['id']}", json={"geometry": {"points": [[0, 0], [0, 400]]}}, headers=headers
    )
    assert moved.json()["measurement"]["value"] == pytest.approx(10.0)

    # Stamps: the project starts with the standard ones.
    stamps = (await client.get("/api/v1/markups/stamps/", params={"project_id": project.id})).json()["data"]
    assert [s["label"] for s in stamps][:5] == ["Approved", "Approved as noted", "Rejected", "Reviewed", "For Construction"]
    assert (
        await client.post("/api/v1/markups/stamps/", json={"project_id": project.id, "label": "Hold"}, headers=headers)
    ).status_code == 403  # needs markups.update
    stamp = await client.post(
        "/api/v1/markups/",
        json={
            "file_id": fid,
            "page": 2,
            "type": "stamp",
            "geometry": {"x": 600, "y": 450, "w": 160, "h": 60},
            "style": {"color": "#16a34a"},
            "text": "Approved\n22 Nov 2026",
        },
        headers=headers,
    )
    assert stamp.status_code == 201

    # Only the author changes a markup.
    owner_headers = {"X-CSRF-Token": await _login(client, test_user)}
    assert (await client.delete(f"/api/v1/markups/{body['id']}", headers=owner_headers)).status_code == 403
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any("marking up A-101 GA Plan.pdf" in n["title"] for n in inbox)
    mine = await client.post("/api/v1/markups/sets/", json={"file_id": fid, "name": "Owner's comments"}, headers=owner_headers)
    assert mine.status_code == 201
    note = await client.post(
        "/api/v1/markups/",
        json={
            "file_id": fid,
            "set_id": mine.json()["id"],
            "page": 1,
            "type": "callout",
            "geometry": {"x": 500, "y": 300, "w": 120, "h": 30, "anchor": [450, 250]},
            "text": "See detail 4",
        },
        headers=owner_headers,
    )
    assert note.status_code == 201
    foreign_set = await client.post(
        "/api/v1/markups/",
        json={
            "file_id": fid,
            "set_id": sets["data"][0]["id"],
            "page": 1,
            "type": "line",
            "geometry": {"points": [[0, 0], [5, 5]]},
        },
        headers=owner_headers,
    )
    assert foreign_set.status_code == 403

    flat = await client.get(f"/api/v1/markups/{fid}/flattened.pdf")
    assert flat.status_code == 200, flat.text
    assert flat.headers["content-type"] == "application/pdf"
    pdf = PdfReader(io.BytesIO(flat.content))
    assert len(pdf.pages) == 2
    page_one, page_two_text = pdf.pages[0].extract_text(), pdf.pages[1].extract_text()
    assert "Revise door swing" not in page_one  # clouds carry no printed text
    assert "10.00 m" in page_one and "25.00 m²" in page_one and "See detail 4" in page_one
    assert "APPROVED" in page_two_text and "not calibrated" in page_two_text

    only_mine = await client.get(f"/api/v1/markups/{fid}/flattened.pdf", params={"set_ids": [mine.json()["id"]]})
    text = PdfReader(io.BytesIO(only_mine.content)).pages[0].extract_text()
    assert "See detail 4" in text and "25.00 m²" not in text

    # Removing the reviewer's set takes their markups with it.
    headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    assert (await client.delete(f"/api/v1/markups/sets/{sets['data'][0]['id']}", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/markups/", params={"file_id": fid})).json()["total_count"] == 1


async def test_only_project_pdfs_can_be_marked_up(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project, drawing, headers = await _drawing(client, db_session, test_user)
    text = await client.post(
        "/api/v1/files/",
        data={"project_id": str(project.id)},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )
    refused = await client.post(
        "/api/v1/markups/",
        json={"file_id": text.json()["id"], "page": 1, "type": "rect", "geometry": {"x": 0, "y": 0, "w": 1, "h": 1}},
        headers=headers,
    )
    assert refused.status_code == 422

    # Someone who can't see the project can't see its markups either.
    await _grant(db_session, test_user_2["id"], "outsider", "markups.read", "files.read")
    await _login(client, test_user_2)
    assert (await client.get("/api/v1/markups/", params={"file_id": drawing["id"]})).status_code == 404
    assert (await client.get("/api/v1/markups/stamps/", params={"project_id": project.id})).status_code == 404

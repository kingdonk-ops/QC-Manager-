"""Coatings: systems, hold points in order, the dew-point rule, DFT sets, batch numbers, calibration hook."""

import sys
import types
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.coatings import service as coatings_service
from src.modules.common.exceptions import ValidationError
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    *(f"coatings.{a}" for a in ("read", "create", "update", "review", "delete")),
    "calibration.read",
    "calibration.create",
)

SYSTEM = {
    "code": "SYS-5",
    "name": "Epoxy / polyurethane, C4",
    "surface_prep_standard": "ISO 8501-1 Sa 2½",
    "profile_min_um": 50,
    "profile_max_um": 85,
    "coats": [
        {"name": "Primer", "product": "Zinc-rich epoxy", "dft_min_um": 60, "dft_max_um": 120},
        {"name": "Topcoat", "product": "Aliphatic PU", "dft_min_um": 80, "dft_max_um": 160},
    ],
    "dft_rule": "80/20",
}
GOOD_PRIMER = [60, 70, 80, 90, 100, 55, 58, 62, 75, 85]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def site(db_session: AsyncSession) -> Tree:
    return await build_tree(db_session, "CT-1")


@pytest_asyncio.fixture
async def job(client: AsyncClient, db_session: AsyncSession, test_user: dict, site: Tree) -> tuple[dict, dict]:
    await _grant(db_session, test_user["id"], "coater", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    system = await client.post("/api/v1/coatings/systems/", json={"project_id": site.project.id, **SYSTEM}, headers=headers)
    assert system.status_code == 201, system.text
    made = await client.post(
        "/api/v1/coatings/jobs/",
        json={
            "project_id": site.project.id,
            "system_id": system.json()["id"],
            "node_id": site.rsw,
            "title": "Tail pulley frame",
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return made.json(), headers


async def test_a_job_gets_a_hold_point_per_stage(job):
    j, _ = job
    assert j["code"] == "CJ-001"
    assert [(s["kind"], s["name"], s["dft_min_um"]) for s in j["stages"]] == [
        ("surface_prep", "ISO 8501-1 Sa 2½", None),
        ("coat", "Primer", 60),
        ("coat", "Topcoat", 80),
    ]
    assert j["current_stage"] == "ISO 8501-1 Sa 2½"
    assert j["node_path"] == "KAR / A1 / 101 / 101.1"


async def test_hold_points_release_in_order_with_passing_readings(client: AsyncClient, job):
    j, headers = job
    base = f"/api/v1/coatings/jobs/{j['id']}"
    prep, primer, top = (s["id"] for s in j["stages"])

    # too damp: the surface is within 3 °C of the dew point (9.3 °C at 20 °C / 50 %)
    damp = await client.post(
        f"{base}/environment",
        json={"stage_id": prep, "air_temp_c": 20, "surface_temp_c": 12.2, "rh_pct": 50},
        headers=headers,
    )
    assert damp.status_code == 201, damp.text
    assert (damp.json()["dew_point_c"], damp.json()["passed"]) == (9.3, False)
    blocked = await client.post(f"{base}/stages/{prep}/release", json={"result": "passed"}, headers=headers)
    assert blocked.status_code == 422
    assert "environmental reading failed" in blocked.text
    assert "no surface profile measured" in blocked.text

    # out of order: the primer can't pass before surface prep
    early = await client.post(f"{base}/stages/{primer}/release", json={"result": "passed"}, headers=headers)
    assert "previous hold point" in early.text


async def _env(client: AsyncClient, base: str, stage: int, headers: dict, surface: float = 14.0) -> dict:
    r = await client.post(
        f"{base}/environment",
        json={"stage_id": stage, "air_temp_c": 20, "surface_temp_c": surface, "rh_pct": 50},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_job_passes_when_every_hold_point_passes(client: AsyncClient, job):
    j, headers = job
    base = f"/api/v1/coatings/jobs/{j['id']}"
    prep, primer, top = (s["id"] for s in j["stages"])

    assert (await _env(client, base, prep, headers))["passed"] is True
    await client.patch(f"{base}/stages/{prep}", json={"measured_profile_um": 65, "cleanliness": "Sa 2½"}, headers=headers)
    released = await client.post(f"{base}/stages/{prep}/release", json={"result": "passed"}, headers=headers)
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "in_progress"

    await _env(client, base, primer, headers)
    nodft = await client.post(f"{base}/stages/{primer}/release", json={"result": "passed"}, headers=headers)
    assert "no DFT readings" in nodft.text and "batch numbers" in nodft.text

    thin = await client.post(f"{base}/dft", json={"stage_id": primer, "readings": [50, 52, 61, 70]}, headers=headers)
    assert thin.status_code == 201, thin.text
    assert thin.json()["passed"] is False
    good = await client.post(f"{base}/dft", json={"stage_id": primer, "readings": GOOD_PRIMER}, headers=headers)
    stats = good.json()
    assert (stats["mean"], stats["minimum"], stats["maximum"], stats["pct_within"], stats["passed"]) == (
        73.5,
        55,
        100,
        80.0,
        True,
    )
    await client.patch(
        f"{base}/stages/{primer}", json={"batch_numbers": [{"product": "Zinc-rich epoxy", "batch": "ZE-2231"}]}, headers=headers
    )
    assert (await client.post(f"{base}/stages/{primer}/release", json={"result": "passed"}, headers=headers)).status_code == 200

    # the same readings fail under 90/10
    strict = await client.post(
        f"{base}/dft", json={"stage_id": top, "readings": [80, 90, 70, 100], "rule": "90/10"}, headers=headers
    )
    assert strict.json()["passed"] is False
    await client.post(f"{base}/dft", json={"stage_id": top, "readings": [90, 100, 110, 95]}, headers=headers)
    await _env(client, base, top, headers)
    await client.patch(f"{base}/stages/{top}", json={"batch_numbers": [{"batch": "PU-77"}]}, headers=headers)
    done = await client.post(f"{base}/stages/{top}/release", json={"result": "passed"}, headers=headers)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "passed"
    assert body["current_stage"] is None
    assert len(body["dft_sets"]) == 4 and len(body["environment"]) == 3

    history = (await client.get(f"{base}/history")).json()
    assert [h["to_status"] for h in history] == ["open", "in_progress", "passed"]


async def test_failing_a_hold_point_fails_the_job(client: AsyncClient, job):
    j, headers = job
    base = f"/api/v1/coatings/jobs/{j['id']}"
    prep = j["stages"][0]["id"]
    failed = await client.post(
        f"{base}/stages/{prep}/release", json={"result": "failed", "note": "Rust bloom"}, headers=headers
    )
    assert failed.json()["status"] == "failed"
    again = await client.post(f"{base}/stages/{prep}/release", json={"result": "passed"}, headers=headers)
    assert again.status_code == 422


async def test_preview_calculators(client: AsyncClient, job):
    _, headers = job
    dft = await client.post(
        "/api/v1/coatings/check/dft",
        json={"readings": GOOD_PRIMER, "dft_min_um": 60, "dft_max_um": 120, "rule": "90/10"},
        headers=headers,
    )
    assert dft.json()["passed"] is False
    env = await client.post(
        "/api/v1/coatings/check/environment", json={"surface_temp_c": 12.3, "air_temp_c": 20, "rh_pct": 50}, headers=headers
    )
    assert env.json() == {"dew_point_c": 9.3, "margin_c": 3.0, "required_margin_c": 3.0, "passed": True}


class OutOfCalibration(ValidationError):
    public_detail = "Instrument out of calibration."


async def test_readings_ask_the_calibration_module_when_it_is_there(client: AsyncClient, job, monkeypatch):
    j, headers = job
    checked: list[tuple[int, date]] = []

    async def assert_calibrated(db, equipment_ids: list[int], on_date: date | None = None, *, project_id: int | None = None):
        checked.extend((i, on_date) for i in equipment_ids)
        if 99 in equipment_ids:
            raise OutOfCalibration("99")
        return []

    fake = types.ModuleType("src.modules.calibration.service")
    fake.assert_calibrated = assert_calibrated  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.modules.calibration", types.ModuleType("src.modules.calibration"))
    monkeypatch.setitem(sys.modules, "src.modules.calibration.service", fake)

    async def on(*_: object) -> bool:
        return True

    monkeypatch.setattr(coatings_service, "is_enabled", on)
    primer = j["stages"][1]["id"]
    refused = await client.post(
        f"/api/v1/coatings/jobs/{j['id']}/dft",
        json={"stage_id": primer, "readings": [70], "equipment_ids": [99]},
        headers=headers,
    )
    assert refused.status_code == 422
    fine = await client.post(
        f"/api/v1/coatings/jobs/{j['id']}/dft",
        json={"stage_id": primer, "readings": [70], "equipment_ids": [5]},
        headers=headers,
    )
    assert fine.status_code == 201
    assert [c[0] for c in checked] == [99, 5]


async def test_readings_check_the_real_calibration_register(client: AsyncClient, job):
    j, headers = job
    made = await client.post(
        "/api/v1/calibration/equipment/",
        json={"project_id": j["project_id"], "code": "DFT-01", "name": "DFT gauge", "requires_calibration": True},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    refused = await client.post(
        f"/api/v1/coatings/jobs/{j['id']}/dft",
        json={"stage_id": j["stages"][1]["id"], "readings": [70], "equipment_ids": [made.json()["id"]]},
        headers=headers,
    )
    assert refused.status_code == 422, refused.text
    assert "DFT-01" in refused.text

"""Acceptance-criteria library: create and range validation, list filters, freeze rule, delete guard, permissions."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    "inspections.read",
    "inspections.create",
    "inspections.update",
    "inspections.delete",
    "inspections.transition",
)
URL = "/api/v1/inspections/criteria/"
TEMPLATE = {"name": "Criterion holder", "sections": [{"title": "Checks", "items": [{"text": "Thickness checked"}]}]}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(code="QC-1", name="Criteria project")
    db_session.add(p)
    await db_session.commit()
    return p


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


def _body(project: Project, code: str, **extra) -> dict:
    return {"project_id": project.id, "code": code, "title": f"Criterion {code}", **extra}


async def _make(client: AsyncClient, headers: dict, project: Project, code: str, **extra):
    return await client.post(URL, json=_body(project, code, **extra), headers=headers)


async def _record_with(client: AsyncClient, project: Project, headers: dict, criterion_id: int) -> dict:
    body = {"project_id": project.id, **TEMPLATE}
    template = (await client.post("/api/v1/inspections/templates/", json=body, headers=headers)).json()
    made = await client.post(
        "/api/v1/inspections/",
        json={"project_id": project.id, "template_id": template["id"], "criterion_id": criterion_id},
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return made.json()


async def test_create_returns_every_attribute_and_validates_range_order(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    made = await client.post(
        URL,
        json=_body(
            project,
            "INS-T",
            rule_type="range",
            lower_limit="10",
            upper_limit="20",
            nominal="15",
            unit="mm",
            standards_ref="AS 4254",
            category="insulation",
        ),
        headers=headers,
    )
    assert made.status_code == 201, made.text
    c = made.json()
    assert (c["code"], c["rule_type"], c["lower_limit"], c["upper_limit"], c["nominal"], c["unit"], c["active"]) == (
        "INS-T",
        "range",
        "10",
        "20",
        "15",
        "mm",
        True,
    )
    assert c["created_by_id"] == test_user["id"] and c["created_at"] and c["supplementary"] == {}
    assert (await client.get(f"{URL}{c['id']}")).json()["standards_ref"] == "AS 4254"

    swapped = await _make(client, headers, project, "SW", rule_type="range", lower_limit="20", upper_limit="10")
    assert swapped.status_code == 422 and "swap" in swapped.text
    equal = await _make(client, headers, project, "EQ", rule_type="range", lower_limit="15", upper_limit="15")
    assert equal.status_code == 201
    partial = await _make(client, headers, project, "NN", rule_type="range", lower_limit="ten", upper_limit="5")
    assert partial.status_code == 201
    ignored = await _make(client, headers, project, "MX", rule_type="maximum", lower_limit="20", upper_limit="10")
    assert ignored.status_code == 201
    duplicate = await client.post(URL, json=_body(project, "EQ"), headers=headers)
    assert duplicate.status_code == 409
    assert (await client.post(URL, json=_body(project, "BAD", rule_type="nonsense"), headers=headers)).status_code == 422


async def test_list_filters_by_category_and_active_and_orders_by_code(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    for code, category, active in (("C-3", "coating", True), ("C-1", "insulation", True), ("C-2", "coating", False)):
        made = await client.post(URL, json=_body(project, code, category=category, active=active), headers=headers)
        assert made.status_code == 201, made.text

    everything = (await client.get(URL, params={"project_id": project.id})).json()
    assert [c["code"] for c in everything["data"]] == ["C-1", "C-2", "C-3"]
    coating = (await client.get(URL, params={"project_id": project.id, "category": "coating"})).json()
    assert coating["total_count"] == 2
    inactive = (await client.get(URL, params={"project_id": project.id, "active": "false"})).json()
    assert [c["code"] for c in inactive["data"]] == ["C-2"]
    both = (await client.get(URL, params={"project_id": project.id, "category": "coating", "active": "true"})).json()
    assert [c["code"] for c in both["data"]] == ["C-3"] and both["total_count"] == 1


async def test_a_judged_criterion_is_frozen_but_descriptive_fields_stay_editable(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    made = await client.post(URL, json=_body(project, "FRZ", rule_type="maximum", upper_limit="50", unit="mm"), headers=headers)
    cid = made.json()["id"]
    # nothing judged yet: a limit change is fine
    assert (await client.patch(f"{URL}{cid}", json={"upper_limit": "55"}, headers=headers)).status_code == 200
    await _record_with(client, project, headers, cid)

    refused = await client.patch(f"{URL}{cid}", json={"upper_limit": "60"}, headers=headers)
    assert refused.status_code == 409
    assert "1 record(s)" in refused.text and "new criterion" in refused.text
    assert (await client.patch(f"{URL}{cid}", json={"unit": "cm"}, headers=headers)).status_code == 409
    assert (await client.patch(f"{URL}{cid}", json={"title": "Renamed"}, headers=headers)).status_code == 200
    same = await client.patch(f"{URL}{cid}", json={"upper_limit": "55", "title": "Renamed again"}, headers=headers)
    assert same.status_code == 200 and same.json()["title"] == "Renamed again"
    assert (await client.patch(f"{URL}{cid}", json={"active": False}, headers=headers)).json()["active"] is False
    assert (await client.get(f"{URL}{cid}")).json()["upper_limit"] == "55"


async def test_range_order_is_checked_on_update_only_when_the_patch_states_the_range(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    made = await _make(client, headers, project, "RNG", rule_type="range", lower_limit="1", upper_limit="9")
    cid = made.json()["id"]
    swapped = {"rule_type": "range", "lower_limit": "9", "upper_limit": "1"}
    assert (await client.patch(f"{URL}{cid}", json=swapped, headers=headers)).status_code == 422
    assert (await client.patch(f"{URL}{cid}", json={"lower_limit": "12"}, headers=headers)).status_code == 200


async def test_delete_is_refused_while_a_record_references_the_criterion(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    held = (await _make(client, headers, project, "HELD", rule_type="minimum", lower_limit="5")).json()["id"]
    free = (await client.post(URL, json=_body(project, "FREE"), headers=headers)).json()["id"]
    await _record_with(client, project, headers, held)

    refused = await client.delete(f"{URL}{held}", headers=headers)
    assert refused.status_code == 409
    assert "1 inspection records" in refused.text and "active flag" in refused.text
    assert (await client.get(f"{URL}{held}")).status_code == 200
    assert (await client.delete(f"{URL}{free}", headers=headers)).status_code == 200
    assert (await client.get(f"{URL}{free}")).status_code == 404


async def test_missing_criterion_is_not_found_and_a_read_only_user_cannot_write(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, project: Project
):
    headers = await _as(client, db_session, test_user, *PERMS)
    assert (await client.get(f"{URL}999999")).status_code == 404
    assert (await client.patch(f"{URL}999999", json={"title": "x"}, headers=headers)).status_code == 404
    assert (await client.delete(f"{URL}999999", headers=headers)).status_code == 404
    made = await client.post(URL, json=_body(project, "RO"), headers=headers)
    cid = made.json()["id"]

    ro_headers = await _as(client, db_session, test_user_2, "projects.read", "inspections.read")
    assert (await client.get(URL, params={"project_id": project.id})).status_code == 200
    assert (await client.post(URL, json=_body(project, "RO-2"), headers=ro_headers)).status_code == 403
    assert (await client.patch(f"{URL}{cid}", json={"title": "x"}, headers=ro_headers)).status_code == 403
    assert (await client.delete(f"{URL}{cid}", headers=ro_headers)).status_code == 403

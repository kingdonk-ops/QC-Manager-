"""Numbering schemes: patterns, code lists, scoped counters, row locks, numbers never reused."""

import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.modules import state
from src.infrastructure.records import NumberingError, next_number
from src.infrastructure.records.models import AllocatedNumber, NumberingScheme
from src.infrastructure.records.schemes import check_scheme, parse_pattern
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = ("projects.read", "numbering.read", "numbering.assign", "numbering.manage", "audit.read")
CODES = {
    "discipline": [{"code": "ME", "label": "Mechanical"}, {"code": "EL", "label": "Electrical"}],
    "type": [{"code": "DR"}, {"code": "SP"}],
}


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


@pytest_asyncio.fixture
async def setup(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="P24", name="Plant")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "doc-controller", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    return project, headers


def test_patterns_are_parsed_against_a_whitelist():
    assert check_scheme("{project}-{discipline}-{type}-{seq:4}", ["discipline"], CODES) == []
    assert any("Unknown token" in e for e in check_scheme("{project}-{owner}-{seq:3}", [], {}))
    assert any("exactly one" in e for e in check_scheme("{project}-X", [], {}))
    assert any("Only one" in e for e in check_scheme("{seq:2}-{seq:3}", [], {}))
    assert any("must appear in the pattern" in e for e in check_scheme("{project}-{seq:3}", ["discipline"], {}))
    assert any("Malformed" in e for e in check_scheme("{project}-{seq:3}-{oops", [], {}))
    assert any("Only {seq:N}" in e for e in check_scheme("{project:3}-{seq:3}", [], {}))
    assert [p.token for p in parse_pattern("{project}/{year}/{seq:5}").parts if p.token] == ["project", "year", "seq"]


async def test_a_scheme_is_refused_when_invalid(client: AsyncClient, setup):
    project, headers = setup
    bad = await client.post(
        "/api/v1/numbering/schemes/",
        json={"project_id": project.id, "record_kind": "document", "pattern": "{project}-{format}-{seq:4}"},
        headers=headers,
    )
    assert bad.status_code == 422
    assert "Unknown token {format}" in bad.text


async def test_preview_allocate_and_scoped_counters(client: AsyncClient, setup):
    project, headers = setup
    made = await client.post(
        "/api/v1/numbering/schemes/",
        json={
            "project_id": project.id,
            "record_kind": "document",
            "pattern": "{project}-{discipline}-{type}-{seq:4}",
            "counter_scope": ["discipline"],
            "code_lists": CODES,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    scheme = made.json()

    preview = await client.post(
        "/api/v1/numbering/preview",
        json={
            "project_id": project.id,
            "pattern": scheme["pattern"],
            "counter_scope": ["discipline"],
            "code_lists": CODES,
            "values": {"discipline": "me"},
            "scheme_id": scheme["id"],
        },
        headers=headers,
    )
    assert preview.json()["number"] == "P24-ME-TYPE-0001"
    assert preview.json()["errors"] == []

    async def take(discipline: str, kind: str = "DR", expect: int = 201) -> dict:
        r = await client.post(
            f"/api/v1/numbering/schemes/{scheme['id']}/allocate",
            json={"values": {"discipline": discipline, "type": kind}},
            headers=headers,
        )
        assert r.status_code == expect, r.text
        return r.json()

    assert (await take("ME"))["number"] == "P24-ME-DR-0001"
    assert (await take("me", "SP"))["number"] == "P24-ME-SP-0002"
    assert (await take("EL"))["number"] == "P24-EL-DR-0001"
    refused = await take("CV", expect=422)
    assert "not an allowed {discipline} code" in refused["detail"]

    # The preview peeks at the counter without moving it.
    again = await client.post(
        "/api/v1/numbering/preview",
        json={
            "project_id": project.id,
            "pattern": scheme["pattern"],
            "counter_scope": ["discipline"],
            "code_lists": CODES,
            "values": {"discipline": "ME", "type": "DR"},
            "scheme_id": scheme["id"],
        },
        headers=headers,
    )
    assert again.json()["number"] == "P24-ME-DR-0003"

    register = (await client.get("/api/v1/numbering/allocations/", params={"project_id": project.id})).json()
    assert register["total_count"] == 3
    audit = (await client.get("/api/v1/audit/entries/", params={"entity_type": "numbering_scheme"})).json()
    assert [e["action"] for e in audit["data"]] == ["numbering.scheme.created"]


async def test_numbers_are_never_reused(client: AsyncClient, db_session: AsyncSession, setup):
    project, headers = setup
    scheme = (
        await client.post(
            "/api/v1/numbering/schemes/",
            json={"project_id": project.id, "record_kind": "itp", "pattern": "ITP-{seq:3}", "start_value": 5},
            headers=headers,
        )
    ).json()
    url = f"/api/v1/numbering/schemes/{scheme['id']}/allocate"
    first = (await client.post(url, json={}, headers=headers)).json()
    assert first["number"] == "ITP-005"  # a start value continues a client's sequence

    voided = await client.post(
        f"/api/v1/numbering/allocations/{first['id']}/void", json={"reason": "Cancelled"}, headers=headers
    )
    assert voided.json()["voided"] is True
    assert (await client.post(url, json={}, headers=headers)).json()["number"] == "ITP-006"

    # Moving the start value back can't hand out a number twice: taken strings are skipped.
    await client.patch(f"/api/v1/numbering/schemes/{scheme['id']}", json={"pattern": "ITP-{seq:2}"}, headers=headers)
    await db_session.execute(
        AllocatedNumber.__table__.update().where(AllocatedNumber.number == "ITP-006").values(number="ITP-07")
    )
    await db_session.commit()
    assert (await client.post(url, json={}, headers=headers)).json()["number"] == "ITP-08"

    numbers = list((await db_session.execute(select(AllocatedNumber.number))).scalars())
    assert len(numbers) == len(set(numbers)) == 3

    blocked = await client.delete(f"/api/v1/numbering/schemes/{scheme['id']}", headers=headers)
    assert blocked.status_code == 422


async def test_without_a_scheme_next_number_falls_back(db_session: AsyncSession):
    project = Project(code="P9", name="Plant")
    db_session.add(project)
    await db_session.commit()
    assert await next_number(db_session, "mdr", project.id, fallback_prefix="MDR") == "MDR-001"
    db_session.add(NumberingScheme(project_id=project.id, record_kind="mdr", pattern="{project}-MDR-{discipline}-{seq:3}"))
    await db_session.commit()
    assert (
        await next_number(db_session, "mdr", project.id, fallback_prefix="MDR", values={"discipline": "ME"}) == "P9-MDR-ME-001"
    )
    with pytest.raises(NumberingError):
        await next_number(db_session, "mdr", project.id, fallback_prefix="MDR", values={})


async def test_two_sessions_never_get_the_same_number(test_db_engine, db_session: AsyncSession):
    project = Project(code="P7", name="Plant")
    db_session.add(project)
    await db_session.commit()
    db_session.add(NumberingScheme(project_id=project.id, record_kind="document", pattern="{project}-{seq:4}"))
    await db_session.commit()

    sessions = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as first, sessions() as second:
        a = await next_number(first, "document", project.id, fallback_prefix="DOC")
        task = asyncio.create_task(next_number(second, "document", project.id, fallback_prefix="DOC"))
        await asyncio.sleep(0.5)
        assert not task.done()  # waits on the counter's row lock
        await first.commit()
        b = await asyncio.wait_for(task, timeout=10)
        await second.commit()
    assert (a, b) == ("P7-0001", "P7-0002")

"""Two overrides of one dossier arriving together: the dossier row lock runs them one after the other, so one override is
recorded and the other finds nothing left to cover."""

import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from tests.integration.quality_safety.test_quality_dossier_override import REASON, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


async def test_two_simultaneous_overrides_of_one_dossier_record_one_report_and_one_audit_entry(
    a_session_per_request: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    test_user_2: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    w = await make_world(a_session_per_request, db_session, test_user, test_user_2, tmp_path, monkeypatch)
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    before = await w.stored()

    body = {"purpose": "review", "reason": REASON}
    answers = await asyncio.gather(
        *(a_session_per_request.post(f"{base}/override", json=body, headers=w.headers) for _ in range(2))
    )

    assert sorted(a.status_code for a in answers) == [201, 409]
    after = await w.stored()
    assert tuple(b + 1 for b in before) == after  # one record, one report, one audit entry, one annotated gate

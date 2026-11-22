"""Change orders: line deltas, the approval workflow and its notifications, CVR application, change log, PDF."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state, subscribe
from src.infrastructure.modules.events import _handlers
from src.modules.cvr.models import CostHead
from src.modules.projects.models import Project, ProjectModuleOverride
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

WRITER = (
    "change_orders.read",
    "change_orders.create",
    "change_orders.update",
    "change_orders.submit",
    "change_orders.delete",
    "change_orders.export",
    "projects.read",
)
APPROVER = ("change_orders.read", "change_orders.approve", "projects.read")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture
def events():
    seen: list[tuple[str, dict]] = []

    async def record(event: str, payload: dict) -> None:
        seen.append((event, payload))

    subscribe("change_orders.*")(record)
    yield seen
    _handlers[:] = [h for h in _handlers if h[1] is not record]


async def _setup(db: AsyncSession) -> tuple[Project, CostHead, CostHead]:
    project = Project(code="CO-P1", name="Hospital", currency="GBP")
    db.add(project)
    await db.flush()
    civils = CostHead(project_id=project.id, code="C1", description="Civils", forecast_cost=100000, forecast_value=120000)
    mech = CostHead(project_id=project.id, code="M1", description="Mechanical", forecast_cost=50000, forecast_value=60000)
    db.add_all([civils, mech])
    await db.commit()
    return project, civils, mech


async def test_deltas_approval_workflow_and_cvr(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, events: list
):
    project, civils, mech = await _setup(db_session)
    await _grant(db_session, test_user_2["id"], "co-approver", *APPROVER)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    await _grant(db_session, test_user["id"], "co-writer", *WRITER)

    created = await client.post(
        "/api/v1/change-orders/",
        json={
            "project_id": project.id,
            "title": "Extra basement drainage",
            "reason": "unforeseen_condition",
            "time_impact_days": 5,
            "cvr_apply": "value",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    co = created.json()
    assert (co["code"], co["status"], co["requested_by_id"], co["currency"]) == ("CO-001", "draft", test_user["id"], "GBP")

    def add(**line):
        return client.post(f"/api/v1/change-orders/{co['id']}/lines", json=line, headers=headers)

    first = await add(
        description="Drainage pipe",
        cost_head_id=civils.id,
        unit="m",
        original_quantity="100",
        original_rate="45.50",
        new_quantity="140",
        new_rate="45.50",
    )
    assert first.status_code == 201, first.text
    assert (first.json()["original_amount"], first.json()["new_amount"], first.json()["delta"]) == (
        "4550.00",
        "6370.00",
        "1820.00",
    )
    second = (await add(description="Pump omitted", cost_head_id=mech.id, original_quantity="1", original_rate="3000")).json()
    assert second["delta"] == "-3000.00"
    await add(description="Dewatering", cost_code="X-9", unit="day", new_quantity="2.5", new_rate="250.10")

    # A live edit recomputes the line.
    edited = await client.patch(
        f"/api/v1/change-orders/{co['id']}/lines/{second['id']}",
        json={"new_quantity": "1", "new_rate": "2000"},
        headers=headers,
    )
    assert edited.json()["delta"] == "-1000.00"

    detail = (await client.get(f"/api/v1/change-orders/{co['id']}")).json()
    assert (detail["original_total"], detail["new_total"], detail["total_delta"], detail["line_count"]) == (
        "7550.00",
        "8995.25",
        "1445.25",
        3,
    )

    # A cost head from another project is refused.
    other = Project(code="CO-P2", name="Other")
    db_session.add(other)
    await db_session.flush()
    foreign = CostHead(project_id=other.id, code="Z", description="Z")
    db_session.add(foreign)
    await db_session.commit()
    assert (await add(description="x", cost_head_id=foreign.id)).status_code == 422

    # The writer can't approve.
    assert (
        await client.patch(f"/api/v1/change-orders/{co['id']}/status", json={"status": "approved"}, headers=headers)
    ).status_code == 403
    submitted = await client.patch(f"/api/v1/change-orders/{co['id']}/status", json={"status": "submitted"}, headers=headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["submitted_at"] is not None
    # Locked once submitted.
    assert (await add(description="late")).status_code == 422
    assert (await client.patch(f"/api/v1/change-orders/{co['id']}", json={"title": "x"}, headers=headers)).status_code == 422

    # The approver was told, reviews and approves.
    approver_headers = {"X-CSRF-Token": await _login(client, test_user_2)}
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(n["category"] == "approval" and n["title"].startswith("CO-001") for n in inbox)
    assert (
        await client.patch(
            f"/api/v1/change-orders/{co['id']}/status", json={"status": "under_review"}, headers=approver_headers
        )
    ).status_code == 200
    approved = await client.patch(
        f"/api/v1/change-orders/{co['id']}/status",
        json={"status": "approved", "comment": "Agreed on site"},
        headers=approver_headers,
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert (body["approver_id"], body["decision_comment"]) == (test_user_2["id"], "Agreed on site")
    assert body["decided_on"] is not None and body["applied_to_cvr_at"] is not None

    # Deltas reached the CVR forecast value only.
    await db_session.refresh(civils)
    await db_session.refresh(mech)
    assert (civils.forecast_value, civils.forecast_cost) == (121820, 100000)
    assert (mech.forecast_value, mech.forecast_cost) == (59000, 50000)
    approved_event = next(p for e, p in events if e == "change_orders.change_order.approved")
    assert sorted(approved_event["cost_heads_updated"]) == sorted([civils.id, mech.id])
    assert approved_event["total_delta"] == "1445.25"

    # Approval is final.
    assert (
        await client.patch(f"/api/v1/change-orders/{co['id']}/status", json={"status": "rejected"}, headers=approver_headers)
    ).status_code == 422

    history = (await client.get(f"/api/v1/change-orders/{co['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "submitted", "under_review", "approved"]

    # The requester heard the decision.
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    inbox = (await client.get("/api/v1/notifications/")).json()["data"]
    assert any(n["title"] == "CO-001 was approved" for n in inbox)

    pdf = await client.get(f"/api/v1/change-orders/{co['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await client.delete(f"/api/v1/change-orders/{co['id']}", headers=headers)).status_code == 422


async def test_change_log_summary_rejection_and_cvr_switched_off(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    project, civils, _ = await _setup(db_session)
    await _grant(db_session, test_user["id"], "co-all", *WRITER, "change_orders.approve")
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    async def make(title: str, qty: str, cvr_apply: str = "none", reason: str = "client_request") -> dict:
        co = (
            await client.post(
                "/api/v1/change-orders/",
                json={"project_id": project.id, "title": title, "cvr_apply": cvr_apply, "reason": reason},
                headers=headers,
            )
        ).json()
        await client.post(
            f"/api/v1/change-orders/{co['id']}/lines",
            json={"description": title, "cost_head_id": civils.id, "new_quantity": qty, "new_rate": "100"},
            headers=headers,
        )
        return co

    async def move(co: dict, *statuses: str) -> None:
        for s in statuses:
            r = await client.patch(f"/api/v1/change-orders/{co['id']}/status", json={"status": s}, headers=headers)
            assert r.status_code == 200, r.text

    a = await make("A", "10", cvr_apply="both", reason="design_change")
    b = await make("B", "5")
    c = await make("C", "2")
    await make("D", "1")
    empty = (
        await client.post("/api/v1/change-orders/", json={"project_id": project.id, "title": "Empty"}, headers=headers)
    ).json()
    assert (
        await client.patch(f"/api/v1/change-orders/{empty['id']}/status", json={"status": "submitted"}, headers=headers)
    ).status_code == 422

    # With CVR off for the project, approval still goes through and leaves the cost heads alone.
    db_session.add(ProjectModuleOverride(project_id=project.id, module="cvr", enabled=False))
    await db_session.commit()
    await move(a, "submitted", "approved")
    await db_session.refresh(civils)
    assert civils.forecast_value == 120000

    await move(b, "submitted")
    await move(c, "submitted", "rejected", "draft")

    summary = (await client.get("/api/v1/change-orders/summary", params={"project_id": project.id})).json()
    assert summary["approved"] == {"count": 1, "delta": "1000.00", "time_impact_days": 0}
    assert summary["pending"]["count"] == 1 and summary["pending"]["delta"] == "500.00"
    assert summary["draft"]["count"] == 3  # C (revised), D and the empty one
    assert summary["by_reason"]["design_change"]["delta"] == "1000.00"

    pending = (await client.get("/api/v1/change-orders/", params={"project_id": project.id, "status": "pending"})).json()
    assert [co["code"] for co in pending["data"]] == ["CO-002"]

    export = await client.get("/api/v1/change-orders/export", params={"project_id": project.id})
    assert export.status_code == 200 and export.content[:2] == b"PK"

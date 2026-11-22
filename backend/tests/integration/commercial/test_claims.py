"""Progress claims: schedule of rates from the breakdown, verified-only quantities, variations from change of
scope, retention with a cap, previous payments, certification, frozen figures and the claim PDF."""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.claims.models import ClaimLine
from src.modules.claims.service import totals
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    "asset_tree.read",
    "asset_tree.create",
    "asset_tree.update",
    "asset_tree.configure",
    "schedule.read",
    "schedule.review",
    *(f"change_of_scope.{a}" for a in ("read", "create", "submit", "approve")),
    *(f"claims.{a}" for a in ("read", "create", "update", "delete", "submit", "export")),
)


def D(v) -> Decimal:
    return Decimal(str(v))


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def ctx(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="PC-P", name="Tank farm", currency="AUD", client_name="Client Co")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "commercial", *PERMS)
    h = {"X-CSRF-Token": await _login(client, test_user)}
    await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=h)

    async def node(level: str, code: str, parent: int | None, **fields) -> int:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=h,
        )
        assert r.status_code == 201, r.text
        if fields:
            await client.patch(f"/api/v1/asset-tree/nodes/{r.json()['id']}", json=fields, headers=h)
        return r.json()["id"]

    site = await node("site", "S", None)
    asset = await node("asset", "101", site)
    rsw_a = await node("rsw", "305", asset, budget_qty="10", uom="m2", earned_qty="10")
    rsw_b = await node("rsw", "306", asset, budget_qty="20", uom="m2", earned_qty="20")

    async def verify(node_id: int, qty: str) -> None:
        r = await client.post(
            f"/api/v1/schedule/{project.id}/progress/verifications", json={"node_id": node_id, "verified_qty": qty}, headers=h
        )
        assert r.status_code == 201, r.text

    return {"project": project, "h": h, "rsw_a": rsw_a, "rsw_b": rsw_b, "verify": verify, "user": test_user}


def by_code(claim: dict) -> dict[str, dict]:
    return {x["code"]: x for x in claim["lines"]}


async def test_claims_value_verified_completion_with_retention_and_previous_payments(
    client: AsyncClient, ctx, db_session: AsyncSession
):
    pid, h = ctx["project"].id, ctx["h"]
    seeded = await client.post("/api/v1/claims/rate-items/from-tree", params={"project_id": pid}, headers=h)
    assert seeded.json() == {"created": 2}
    assert (await client.post("/api/v1/claims/rate-items/from-tree", params={"project_id": pid}, headers=h)).json() == {
        "created": 0
    }
    items = (await client.get("/api/v1/claims/rate-items/", params={"project_id": pid})).json()["data"]
    rates = {"101 / 305": "100", "101 / 306": "50"}
    for item in items:
        r = await client.patch(f"/api/v1/claims/rate-items/{item['id']}", json={"rate": rates[item["code"]]}, headers=h)
        assert r.status_code == 200, r.text

    # An approved change card is a variation.
    card = (
        await client.post(
            "/api/v1/change-of-scope/cards/",
            json={
                "project_id": pid,
                "title": "Extra brace",
                "lines": [{"description": "Brace", "quantity": "1", "rate": "1440"}],
            },
            headers=h,
        )
    ).json()
    for status in ("submitted", "approved"):
        await client.patch(f"/api/v1/change-of-scope/cards/{card['id']}/status", json={"status": status}, headers=h)

    await ctx["verify"](ctx["rsw_a"], "4")  # 306 is reported complete but never verified
    first = await client.post(
        "/api/v1/claims/",
        json={
            "project_id": pid,
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "retention_pct": "5",
            "retention_cap": "100",
        },
        headers=h,
    )
    assert first.status_code == 201, first.text
    c1 = first.json()
    lines = by_code(c1)
    assert (D(lines["101 / 305"]["verified_qty"]), D(lines["101 / 305"]["to_date_value"])) == (4, D("400.00"))
    assert (D(lines["101 / 306"]["verified_qty"]), D(lines["101 / 306"]["to_date_value"])) == (0, 0)
    assert D(lines["COS-001"]["to_date_value"]) == D("1440.00") and lines["COS-001"]["kind"] == "variation"
    t = c1["totals"]
    assert (D(t["gross_to_date"]), D(t["retention_to_date"]), D(t["net_to_date"]), D(t["this_claim"])) == (
        D("1840.00"),
        D("92.00"),
        D("1748.00"),
        D("1748.00"),
    )

    # Only verified completion can be claimed.
    r = await client.patch(f"/api/v1/claims/{c1['id']}/lines/{lines['101 / 306']['id']}", json={"to_date_qty": "1"}, headers=h)
    assert r.status_code == 422 and "verified" in r.json()["detail"]
    r = await client.patch(f"/api/v1/claims/{c1['id']}/lines/{lines['COS-001']['id']}", json={"to_date_qty": "0.5"}, headers=h)
    assert D(r.json()["to_date_value"]) == D("720.00")
    dup = await client.post(
        "/api/v1/claims/", json={"project_id": pid, "period_start": "2026-02-01", "period_end": "2026-02-28"}, headers=h
    )
    assert dup.status_code == 422  # one draft at a time

    sub = await client.patch(f"/api/v1/claims/{c1['id']}/status", json={"status": "submitted"}, headers=h)
    assert sub.status_code == 200, sub.text
    assert D(sub.json()["totals"]["this_claim"]) == D("1064.00")  # 400 + 720 = 1120, less 56 retention
    denied = await client.patch(
        f"/api/v1/claims/{c1['id']}/status", json={"status": "certified", "certified_amount": "1000"}, headers=h
    )
    assert denied.status_code == 403
    await _grant(db_session, ctx["user"]["id"], "certifier", "claims.approve")
    nocert = await client.patch(f"/api/v1/claims/{c1['id']}/status", json={"status": "certified"}, headers=h)
    assert nocert.status_code == 422
    cert = await client.patch(
        f"/api/v1/claims/{c1['id']}/status",
        json={"status": "certified", "certified_amount": "1000", "on": "2026-02-10", "client_reference": "PC1-CERT"},
        headers=h,
    )
    assert cert.json()["status"] == "certified" and D(cert.json()["certified_amount"]) == 1000

    # Second period: more verified, the rest of the variation, retention capped, previous payment deducted.
    await ctx["verify"](ctx["rsw_a"], "10")
    await ctx["verify"](ctx["rsw_b"], "5")
    c2 = (
        await client.post(
            "/api/v1/claims/",
            json={
                "project_id": pid,
                "period_start": "2026-02-01",
                "period_end": "2026-02-28",
                "retention_pct": "5",
                "retention_cap": "100",
            },
            headers=h,
        )
    ).json()
    lines = by_code(c2)
    a, b, v = lines["101 / 305"], lines["101 / 306"], lines["COS-001"]
    assert (D(a["previous_qty"]), D(a["to_date_qty"]), D(a["this_value"])) == (4, 10, D("600.00"))
    assert (D(b["previous_qty"]), D(b["to_date_qty"]), D(b["this_value"])) == (0, 5, D("250.00"))
    assert (D(v["previous_qty"]), D(v["to_date_qty"]), D(v["this_value"])) == (D("0.5"), 1, D("720.00"))
    t = c2["totals"]
    assert D(t["gross_to_date"]) == D("2690.00")  # 1000 + 250 + 1440
    assert D(t["previous_gross"]) == D("1120.00") and D(t["gross_this_period"]) == D("1570.00")
    assert D(t["retention_to_date"]) == D("100.00")  # 134.50 capped
    assert D(t["previous_payments"]) == D("1000.00")  # what the client certified
    assert D(t["this_claim"]) == D("1590.00")

    # The first claim's figures stay frozen after later changes.
    again = (await client.get(f"/api/v1/claims/{c1['id']}")).json()
    assert D(again["totals"]["this_claim"]) == D("1064.00")
    pdf = await client.get(f"/api/v1/claims/{c2['id']}/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    paid = await client.patch(f"/api/v1/claims/{c1['id']}/status", json={"status": "paid"}, headers=h)
    assert D(paid.json()["paid_amount"]) == 1000
    reg = await client.get("/api/v1/claims/export", params={"project_id": pid, "format": "csv"})
    assert "PC-001" in reg.text and "PC-002" in reg.text
    hist = (await client.get(f"/api/v1/claims/{c1['id']}/history")).json()
    assert [x["to_status"] for x in hist] == ["draft", "submitted", "certified", "paid"]


def _line(kind: str, contract: str, rate: str, previous: str, to_date: str) -> ClaimLine:
    return ClaimLine(
        claim_id=1,
        kind=kind,
        code="x",
        description="x",
        contract_qty=D(contract),
        rate=D(rate),
        previous_qty=D(previous),
        to_date_qty=D(to_date),
    )


async def test_claim_arithmetic():
    lines = [_line("work", "100", "12.5", "40", "60"), _line("variation", "1", "500", "0", "1")]
    t = totals(lines, D("10"), None, D("900"))
    assert t["contract_sum"] == D("1250.00") and t["variations_sum"] == D("500.00")
    assert t["works_to_date"] == D("750.00") and t["variations_to_date"] == D("500.00")
    assert t["gross_to_date"] == D("1250.00") and t["previous_gross"] == D("500.00") and t["gross_this_period"] == D("750.00")
    assert t["retention_to_date"] == D("125.00") and t["net_to_date"] == D("1125.00")
    assert t["this_claim"] == D("225.00")
    capped = totals(lines, D("10"), D("50"), D("0"))
    assert capped["retention_to_date"] == D("50") and capped["this_claim"] == D("1200.00")

"""Procurement: PO totals, sending to the supplier (captured mail with the PDF), goods receipts and the summary."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mail import Mail
from src.infrastructure.modules import state
from src.modules.contacts.models import Company, Contact
from src.modules.procurement import service as procurement_service
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

BUYER = (
    "procurement.read",
    "procurement.create",
    "procurement.update",
    "procurement.submit",
    "procurement.transition",
    "procurement.delete",
    "procurement.export",
    "projects.read",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest.fixture
def mailbox(monkeypatch) -> list[Mail]:
    sent: list[Mail] = []

    async def capture(mail: Mail) -> None:
        sent.append(mail)

    monkeypatch.setattr(procurement_service, "deliver", capture)
    return sent


async def _setup(db: AsyncSession) -> tuple[Project, Company, Contact]:
    project = Project(code="PO-P1", name="Warehouse", currency="AUD", location="12 Dock Rd")
    company = Company(
        name="Steelco",
        type="supplier",
        email="orders@steelco.example",
        address="1 Forge St",
        banking={"bank": "Example Bank", "account_number": "12345678"},
    )
    db.add_all([project, company])
    await db.flush()
    contact = Contact(first_name="Sam", last_name="Smith", company_id=company.id, email="sam@steelco.example")
    db.add(contact)
    await db.commit()
    return project, company, contact


async def _po(client: AsyncClient, headers: dict, project: Project, **extra) -> dict:
    response = await client.post(
        "/api/v1/procurement/purchase-orders/", json={"project_id": project.id, **extra}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _line(client: AsyncClient, headers: dict, po: dict, **line) -> dict:
    response = await client.post(f"/api/v1/procurement/purchase-orders/{po['id']}/lines", json=line, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_totals_send_and_receipts(client: AsyncClient, db_session: AsyncSession, test_user: dict, mailbox: list[Mail]):
    project, company, contact = await _setup(db_session)
    await _grant(db_session, test_user["id"], "buyer", *BUYER)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    po = await _po(
        client,
        headers,
        project,
        title="Structural steel",
        supplier_contact_id=contact.id,
        required_by=(date.today() - timedelta(days=3)).isoformat(),
        terms="30 days EOM",
    )
    assert (po["code"], po["currency"], po["supplier_company_id"], po["status"]) == ("PO-001", "AUD", company.id, "draft")
    assert po["supplier"]["banking"] == {"bank": "Example Bank", "account_number": "12345678"}
    assert po["supplier"]["contact_email"] == "sam@steelco.example" and po["supplier_name"] == "Steelco"

    beams = await _line(client, headers, po, description="UB 310", unit="t", quantity="12.5", unit_price="1800", tax_rate="10")
    bolts = await _line(
        client, headers, po, description="M20 bolts", unit="ea", quantity="400", unit_price="1.15", tax_rate="10"
    )
    assert (beams["amount"], beams["tax"]) == ("22500.00", "2250.00")
    assert (bolts["amount"], bolts["tax"]) == ("460.00", "46.00")

    detail = (await client.get(f"/api/v1/procurement/purchase-orders/{po['id']}")).json()
    assert (detail["net_total"], detail["tax_total"], detail["gross_total"]) == ("22960.00", "2296.00", "25256.00")

    # Receiving before it's sent is refused.
    early = await client.post(
        f"/api/v1/procurement/purchase-orders/{po['id']}/receipts",
        json={"lines": [{"line_id": beams["id"], "quantity": "1"}]},
        headers=headers,
    )
    assert early.status_code == 422

    sent = await client.post(
        f"/api/v1/procurement/purchase-orders/{po['id']}/send", json={"message": "Please confirm"}, headers=headers
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent" and sent.json()["sent_to"] == "sam@steelco.example"
    assert len(mailbox) == 1
    mail = mailbox[0]
    assert mail.to == ["sam@steelco.example"] and "PO-001" in mail.subject
    assert mail.text.startswith("Please confirm") and "AUD 25,256.00" in mail.text
    assert mail.attachments[0].filename == "PO-001.pdf" and mail.attachments[0].content.startswith(b"%PDF")

    # Lines are locked once sent.
    locked = await client.patch(
        f"/api/v1/procurement/purchase-orders/{po['id']}/lines/{beams['id']}", json={"quantity": "1"}, headers=headers
    )
    assert locked.status_code == 422

    first = await client.post(
        f"/api/v1/procurement/purchase-orders/{po['id']}/receipts",
        json={
            "lines": [{"line_id": beams["id"], "quantity": "10"}, {"line_id": bolts["id"], "quantity": "400"}],
            "quality_notes": "Two beams still to come",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    result = first.json()
    assert (result["status"], result["warnings"], result["receipt"]["code"]) == ("partially_received", [], "GRN-001")
    assert result["receipt"]["received_by_id"] == test_user["id"]

    detail = (await client.get(f"/api/v1/procurement/purchase-orders/{po['id']}")).json()
    assert (detail["received_net"], detail["outstanding_net"], detail["overdue"]) == ("18460.00", "4500.00", True)
    assert [line["outstanding_quantity"] for line in detail["lines"]] == ["2.500", "0.000"]

    over = (
        await client.post(
            f"/api/v1/procurement/purchase-orders/{po['id']}/receipts",
            json={"lines": [{"line_id": beams["id"], "quantity": "3"}]},
            headers=headers,
        )
    ).json()
    assert over["status"] == "fully_received"
    assert len(over["warnings"]) == 1 and "0.5 over" in over["warnings"][0]

    detail = (await client.get(f"/api/v1/procurement/purchase-orders/{po['id']}")).json()
    assert [r["code"] for r in detail["receipts"]] == ["GRN-001", "GRN-002"]
    assert detail["overdue"] is False

    history = (await client.get(f"/api/v1/procurement/purchase-orders/{po['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "sent", "partially_received", "fully_received"]

    closed = await client.patch(
        f"/api/v1/procurement/purchase-orders/{po['id']}/status", json={"status": "closed"}, headers=headers
    )
    assert closed.status_code == 200 and closed.json()["status"] == "closed"


async def test_summary_threshold_and_recipients(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, mailbox: list[Mail]
):
    project, company, contact = await _setup(db_session)
    await _grant(db_session, test_user["id"], "buyer2", *BUYER)
    headers = {"X-CSRF-Token": await _login(client, test_user)}

    late = await _po(
        client, headers, project, supplier_company_id=company.id, required_by=(date.today() - timedelta(days=2)).isoformat()
    )
    await _line(client, headers, late, description="Cement", quantity="10", unit_price="20")
    upcoming = await _po(
        client, headers, project, supplier_company_id=company.id, required_by=(date.today() + timedelta(days=5)).isoformat()
    )
    await _line(client, headers, upcoming, description="Sand", quantity="5", unit_price="40", tax_rate="10")
    draft = await _po(client, headers, project, supplier_company_id=company.id)
    await _line(client, headers, draft, description="Gravel", quantity="1", unit_price="999")

    # Over its threshold, only an approver may send it.
    big = await _po(client, headers, project, supplier_company_id=company.id, approval_threshold="100")
    await _line(client, headers, big, description="Crane hire", quantity="1", unit_price="5000")
    assert big["needs_approval"] is False
    refused = await client.post(f"/api/v1/procurement/purchase-orders/{big['id']}/send", json={}, headers=headers)
    assert refused.status_code == 403

    # A company-only supplier gets the company address; an explicit address wins.
    await client.post(f"/api/v1/procurement/purchase-orders/{late['id']}/send", json={}, headers=headers)
    await client.post(
        f"/api/v1/procurement/purchase-orders/{upcoming['id']}/send", json={"to": ["buyer@steelco.example"]}, headers=headers
    )
    assert [m.to for m in mailbox] == [["orders@steelco.example"], ["buyer@steelco.example"]]

    summary = (await client.get("/api/v1/procurement/summary", params={"project_id": project.id})).json()
    assert (summary["committed_net"], summary["committed_gross"], summary["received_net"]) == ("400.00", "420.00", "0.00")
    assert (summary["outstanding_net"], summary["draft_net"], summary["overdue_count"]) == ("400.00", "5999.00", 1)
    assert [d["code"] for d in summary["outstanding"]] == ["PO-001", "PO-002"]
    assert summary["outstanding"][0]["overdue"] is True and summary["outstanding"][0]["days_overdue"] == 2
    assert summary["by_status"]["sent"] == 2 and summary["by_status"]["draft"] == 2

    overdue = (
        await client.get("/api/v1/procurement/purchase-orders/", params={"project_id": project.id, "overdue": True})
    ).json()
    assert [p["code"] for p in overdue["data"]] == ["PO-001"]

    # No email anywhere: refused.
    bare = Company(name="Nomail Ltd")
    db_session.add(bare)
    await db_session.commit()
    silent = await _po(client, headers, project, supplier_company_id=bare.id)
    await _line(client, headers, silent, description="x", quantity="1", unit_price="1")
    assert (
        await client.post(f"/api/v1/procurement/purchase-orders/{silent['id']}/send", json={}, headers=headers)
    ).status_code == 422

    pdf = await client.get(f"/api/v1/procurement/purchase-orders/{late['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    export = await client.get("/api/v1/procurement/purchase-orders/export", params={"project_id": project.id, "format": "csv"})
    assert export.content.decode("utf-8-sig").splitlines()[1].startswith("PO-001")

    # Sent POs can't be deleted; drafts can.
    assert (await client.delete(f"/api/v1/procurement/purchase-orders/{late['id']}", headers=headers)).status_code == 422
    assert (await client.delete(f"/api/v1/procurement/purchase-orders/{draft['id']}", headers=headers)).status_code == 200

"""Bill of quantities: catalog, assemblies, hierarchy, resource-driven rates, undo/redo, exchange."""

import io
import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

BOQ = ("boq.read", "boq.create", "boq.update", "boq.delete", "boq.import", "boq.export", "projects.read")
NS = "{http://www.gaeb.de/GAEB_DA_XML/DA83/3.3}"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession, standard: str | None = "din276") -> Project:
    project = Project(code="P-BOQ", name="Refinery insulation", currency="EUR", classification_standard=standard)
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


def _rows(bill: dict) -> dict[str, dict]:
    return {p["short_text"]: p for p in bill["positions"]}


async def _bill(client: AsyncClient, headers: dict, project_id: int) -> dict:
    created = await client.post("/api/v1/boq/", json={"project_id": project_id, "name": "Tender"}, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _add(client: AsyncClient, headers: dict, boq_id: int, **body) -> dict:
    res = await client.post(f"/api/v1/boq/{boq_id}/positions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def test_hierarchy_formulas_resources_and_markups(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *BOQ)

    wool = (
        await client.post(
            "/api/v1/boq/resources/",
            json={"code": "MW50", "name": "Mineral wool 50mm", "unit": "m2", "rate": "12.50", "currency": "EUR"},
            headers=headers,
        )
    ).json()
    fitter = (
        await client.post(
            "/api/v1/boq/resources/",
            json={"code": "L-INS", "name": "Insulator", "type": "labour", "trade": "insulator", "unit": "h", "rate": "60"},
            headers=headers,
        )
    ).json()
    assert fitter["trade"] == "insulator"

    bill = await _bill(client, headers, project.id)
    assert bill["currency"] == "EUR" and bill["classification_standard"] == "din276"
    bill = await _add(client, headers, bill["id"], kind="section", short_text="Insulation", classification="400")
    section = _rows(bill)["Insulation"]
    bill = await _add(
        client,
        headers,
        bill["id"],
        parent_id=section["id"],
        short_text="Pipe insulation",
        unit="m",
        quantity_formula="2*3.5+1.2",
        classification="420",
    )
    pipe = _rows(bill)["Pipe insulation"]
    assert Decimal(pipe["quantity"]) == Decimal("8.2") and pipe["ordinal"] == "1.1"

    bill = (
        await client.post(
            f"/api/v1/boq/positions/{pipe['id']}/resources", json={"resource_id": wool["id"], "factor": "1.05"}, headers=headers
        )
    ).json()
    bill = (
        await client.post(
            f"/api/v1/boq/positions/{pipe['id']}/resources",
            json={"resource_id": fitter["id"], "factor": "0.35"},
            headers=headers,
        )
    ).json()
    pipe = _rows(bill)["Pipe insulation"]
    # 1.05 × 12.50 + 0.35 × 60 = 13.125 + 21 = 34.125 per m; × 8.2 m = 279.825 → 279.83
    assert Decimal(pipe["unit_rate"]) == Decimal("34.125")
    assert Decimal(pipe["total"]) == Decimal("279.83")
    assert Decimal(_rows(bill)["Insulation"]["total"]) == Decimal("279.83")

    refused = await client.patch(f"/api/v1/boq/positions/{pipe['id']}", json={"unit_rate": "5"}, headers=headers)
    assert refused.status_code == 422 and "resources" in refused.json()["detail"]
    bad = await client.patch(f"/api/v1/boq/positions/{pipe['id']}", json={"quantity_formula": "2**"}, headers=headers)
    assert bad.status_code == 422

    bill = (
        await client.patch(
            f"/api/v1/boq/{bill['id']}",
            json={"overhead_pct": "10", "profit_pct": "5", "tax_pct": "19"},
            headers=headers,
        )
    ).json()
    # overhead 27.98; profit (279.83+27.98)×5% = 15.39; subtotal 323.20; tax 61.41
    assert bill["totals"]["overhead"] == "27.98"
    assert bill["totals"]["grand_total"] == "384.61"

    # a project override of the catalog rate is used for new lines
    await client.post(
        "/api/v1/boq/resources/",
        json={
            "code": "MW50",
            "name": "Mineral wool 50mm (site price)",
            "rate": "10",
            "project_id": project.id,
            "base_id": wool["id"],
        },
        headers=headers,
    )
    listed = (await client.get("/api/v1/boq/resources/", params={"project_id": project.id, "search": "mw50"})).json()
    assert [r["rate"] for r in listed["data"]] == ["10.0000"]

    report = (await client.get(f"/api/v1/boq/{bill['id']}/validate", params={"ruleset": "boq_quality"})).json()
    assert report["errors"] == 0 and report["score"] == 100
    din = (await client.get(f"/api/v1/boq/{bill['id']}/validate")).json()
    assert din["ruleset"] == "din276"
    assert any(f["rule_id"] == "DIN03" for f in din["findings"])  # no group 300


async def test_assemblies_apply_and_move_and_undo_redo(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *BOQ)
    wool = (
        await client.post("/api/v1/boq/resources/", json={"code": "W", "name": "Wool", "rate": "10"}, headers=headers)
    ).json()
    clad = (
        await client.post("/api/v1/boq/resources/", json={"code": "A", "name": "Alu", "rate": "20"}, headers=headers)
    ).json()
    assembly = await client.post(
        "/api/v1/boq/assemblies/",
        json={
            "code": "PI50",
            "name": "Pipe insulation 50mm + aluminium cladding",
            "unit": "m",
            "lines": [
                {"resource_id": wool["id"], "factor": "1.05"},
                {"resource_id": clad["id"], "factor": "1", "waste_pct": "10"},
            ],
        },
        headers=headers,
    )
    assert assembly.status_code == 201, assembly.text
    assert assembly.json()["unit_rate"] == "32.5000"  # 10.5 + 22

    bill = await _bill(client, headers, project.id)
    boq_id = bill["id"]
    bill = await _add(client, headers, boq_id, kind="section", short_text="A")
    bill = await _add(client, headers, boq_id, kind="section", short_text="B")
    a, b = _rows(bill)["A"], _rows(bill)["B"]
    bill = await _add(client, headers, boq_id, parent_id=a["id"], short_text="one", quantity="10")
    bill = await _add(client, headers, boq_id, parent_id=a["id"], short_text="two", quantity="1", unit="m", unit_rate="5")
    one = _rows(bill)["one"]

    applied = await client.post(
        f"/api/v1/boq/positions/{one['id']}/apply-assembly", json={"assembly_id": assembly.json()["id"]}, headers=headers
    )
    one = _rows(applied.json())["one"]
    assert one["unit"] == "m" and one["assembly_id"] == assembly.json()["id"]
    assert len(one["resources"]) == 2 and one["total"] == "325.00"

    moved = (await client.post(f"/api/v1/boq/positions/{one['id']}/move", json={"parent_id": b["id"]}, headers=headers)).json()
    rows = _rows(moved)
    assert (rows["two"]["ordinal"], rows["one"]["ordinal"]) == ("1.1", "2.1")
    assert rows["B"]["total"] == "325.00" and rows["A"]["total"] == "5.00"
    inside = await client.post(f"/api/v1/boq/positions/{a['id']}/move", json={"parent_id": a["id"]}, headers=headers)
    assert inside.status_code == 422

    moved = (await client.post(f"/api/v1/boq/positions/{b['id']}/move", json={"before_id": a["id"]}, headers=headers)).json()
    assert [p["ordinal"] + " " + p["short_text"] for p in moved["positions"]] == ["1 B", "1.1 one", "2 A", "2.1 two"]

    edited = (
        await client.patch(f"/api/v1/boq/positions/{rows['two']['id']}", json={"short_text": "TWO"}, headers=headers)
    ).json()
    deleted = (await client.delete(f"/api/v1/boq/positions/{a['id']}", headers=headers)).json()
    assert [p["short_text"] for p in deleted["positions"]] == ["B", "one"]
    assert deleted["can_undo"] and deleted["undo_label"].startswith("Delete")

    undone = (await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)).json()
    assert (
        [p["short_text"] for p in undone["positions"]]
        == ["B", "one", "A", "TWO"]
        == [p["short_text"] for p in edited["positions"]]
    )
    undone = (await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)).json()  # the edit
    undone = (await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)).json()  # the move of B
    assert [p["ordinal"] + " " + p["short_text"] for p in undone["positions"]] == ["1 A", "1.1 two", "2 B", "2.1 one"]
    undone = (await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)).json()  # the move of one
    undone = (await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)).json()  # the assembly
    assert _rows(undone)["one"]["resources"] == [] and _rows(undone)["one"]["total"] == "0.00"
    redone = (await client.post(f"/api/v1/boq/{boq_id}/redo", headers=headers)).json()
    assert _rows(redone)["one"]["total"] == "325.00" and redone["can_redo"]
    for _ in range(4):
        redone = (await client.post(f"/api/v1/boq/{boq_id}/redo", headers=headers)).json()
    assert [p["short_text"] for p in redone["positions"]] == ["B", "one"] and not redone["can_redo"]
    assert (await client.post(f"/api/v1/boq/{boq_id}/redo", headers=headers)).status_code == 422

    # a new change after an undo clears the redo stack
    await client.post(f"/api/v1/boq/{boq_id}/undo", headers=headers)
    fresh = await _add(client, headers, boq_id, short_text="new")
    assert not fresh["can_redo"]


async def test_locking_needs_approve(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *BOQ)
    bill = await _bill(client, headers, project.id)
    refused = await client.post(f"/api/v1/boq/{bill['id']}/transition", json={"status": "locked"}, headers=headers)
    assert refused.status_code == 403
    assert (await client.post(f"/api/v1/boq/{bill['id']}/transition", json={"status": "priced"}, headers=headers)).json()[
        "status"
    ] == "priced"

    manager = await _as(client, db_session, test_user_2, *BOQ, "boq.approve")
    locked = await client.post(f"/api/v1/boq/{bill['id']}/transition", json={"status": "locked"}, headers=manager)
    assert locked.json()["status"] == "locked"
    blocked = await client.post(f"/api/v1/boq/{bill['id']}/positions", json={"short_text": "x"}, headers=manager)
    assert blocked.status_code == 422
    history = (await client.get(f"/api/v1/boq/{bill['id']}/history")).json()
    assert [h["to_status"] for h in history] == ["draft", "priced", "locked"]


async def test_excel_import_builds_the_hierarchy_and_exports(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *BOQ)
    bill = await _bill(client, headers, project.id)

    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Pos", "Description", "Unit", "Qty", "Unit price", "KG"])
    sheet.append(["1", "Thermal insulation", None, None, None, "400"])
    sheet.append(["1.1", "Pipes DN50", "m", 120, 35.5, "420"])
    sheet.append(["1.2", "Valves", None, None, None, "420"])
    sheet.append(["1.2.1", "Valve boxes", "pcs", 4, 80, "420"])
    sheet.append(["2", "Scaffolding", "m2", 50, 12, "300"])
    buffer = io.BytesIO()
    book.save(buffer)
    upload = {"file": ("boq.xlsx", buffer.getvalue(), "application/octet-stream")}

    preview = (await client.post(f"/api/v1/boq/{bill['id']}/import/preview", files=upload, headers=headers)).json()
    assert preview["mapping"] == {
        "ordinal": "Pos",
        "short_text": "Description",
        "unit": "Unit",
        "quantity": "Qty",
        "rate": "Unit price",
        "classification": "KG",
    }
    report = (await client.post(f"/api/v1/boq/{bill['id']}/import", files=upload, headers=headers)).json()
    assert report["created"] == 5, report
    bill = (await client.get(f"/api/v1/boq/{bill['id']}")).json()
    rows = _rows(bill)
    assert [p["ordinal"] for p in bill["positions"]] == ["1", "1.1", "1.2", "1.2.1", "2"]
    assert rows["Valves"]["kind"] == "section" and rows["Thermal insulation"]["total"] == "4580.00"
    assert bill["grand_total"] == "5180.00"

    exported = await client.get(f"/api/v1/boq/{bill['id']}/export", params={"format": "xlsx"})
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).active
    assert sheet is not None
    cells = {row[0].value: row for row in sheet.iter_rows(min_row=5) if row[0].value}
    assert cells["1"][7].value.startswith("=SUBTOTAL(9,H6:H")
    assert cells["1.1"][7].value == "=ROUND(F6*G6,2)"
    assert sheet.row_dimensions[cells["1.2.1"][0].row].outline_level == 2

    csv = await client.get(f"/api/v1/boq/{bill['id']}/export", params={"format": "csv"})
    assert "Pipes DN50" in csv.content.decode("utf-8-sig")

    gaeb = await client.get(f"/api/v1/boq/{bill['id']}/export", params={"format": "x83"})
    root = ET.fromstring(gaeb.content)
    body = root.find(f"{NS}Award/{NS}BoQ/{NS}BoQBody")
    assert body is not None
    ctgys = body.findall(f"{NS}BoQCtgy")
    assert [c.findtext(f"{NS}LblTx/{NS}p/{NS}span") for c in ctgys] == ["Thermal insulation"]
    item = ctgys[0].find(f"{NS}BoQBody/{NS}Itemlist/{NS}Item")
    assert item is not None
    assert (item.findtext(f"{NS}Qty"), item.findtext(f"{NS}QU")) == ("120.000", "m")
    assert item.find(f"{NS}UP") is None
    outline = item.find(f"{NS}Description/{NS}CompleteText/{NS}OutlineText/{NS}OutlTxt/{NS}TextOutlTxt/{NS}p/{NS}span")
    assert outline is not None and outline.text == "Pipes DN50"
    assert body.find(f"{NS}Itemlist/{NS}Item/{NS}Qty").text == "50.000"  # type: ignore[union-attr]

    # GAEB round trip into a second bill
    second = await _bill(client, headers, project.id)
    imported = await client.post(
        f"/api/v1/boq/{second['id']}/import", files={"file": ("tender.x83", gaeb.content, "application/xml")}, headers=headers
    )
    assert imported.json()["created"] == 5, imported.text
    again = (await client.get(f"/api/v1/boq/{second['id']}")).json()
    assert [(p["ordinal"], p["short_text"]) for p in again["positions"]] == [
        (p["ordinal"], p["short_text"]) for p in bill["positions"]
    ]

    # one undo removes the whole import
    undone = (await client.post(f"/api/v1/boq/{second['id']}/undo", headers=headers)).json()
    assert undone["positions"] == []


async def test_paste_and_resource_import(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *BOQ)
    bill = await _bill(client, headers, project.id)
    pasted = await client.post(
        f"/api/v1/boq/{bill['id']}/positions/bulk",
        json={"rows": [{"short_text": "a", "quantity": "2", "unit_rate": "3"}, {"short_text": "b", "quantity_formula": "2x2"}]},
        headers=headers,
    )
    assert pasted.status_code == 201, pasted.text
    assert [p["total"] for p in pasted.json()["positions"]] == ["6.00", "0.00"]

    csv = b"Code;Name;Type;Unit;Rate;Trade\nL-SC;Scaffolder;labour;h;55,50;scaffolder\nM-AL;Aluminium sheet;material;m2;18;\n"
    report = (
        await client.post("/api/v1/boq/resources/import", files={"file": ("rates.csv", csv, "text/csv")}, headers=headers)
    ).json()
    assert report["created"] == 2, report
    duplicate = await client.post("/api/v1/boq/resources/", json={"code": "l-sc", "name": "Again"}, headers=headers)
    assert duplicate.status_code == 409
    labour = (await client.get("/api/v1/boq/resources/", params={"type": "labour"})).json()["data"]
    assert [(r["code"], r["rate"], r["trade"]) for r in labour] == [("L-SC", "55.5000", "scaffolder")]

"""Asset register: spatial tree, types, components, systems, bulk add, import, COBie export and validation."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.assets.cobie import SHEETS
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

ASSETS = (
    "assets.read",
    "assets.create",
    "assets.update",
    "assets.delete",
    "assets.import",
    "assets.export",
    "projects.read",
    "contacts.read",
    "contacts.create",
    "contacts.update",
    "files.read",
    "files.upload",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


async def _project(db: AsyncSession, code: str = "P-1") -> Project:
    project = Project(code=code, name="Plant", location="Port Hedland", currency="AUD")
    db.add(project)
    await db.commit()
    return project


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str) -> dict:
    await _grant(db, user["id"], f"r{user['id']}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _building(client: AsyncClient, base: str, headers: dict) -> dict:
    facility = await client.post(f"{base}/facilities/", json={"name": "Admin Building", "category": "Office"}, headers=headers)
    assert facility.status_code == 201, facility.text
    fac = facility.json()
    l1 = (
        await client.post(
            f"{base}/floors/", json={"facility_id": fac["id"], "name": "Level 1", "elevation": 0}, headers=headers
        )
    ).json()
    l2 = (
        await client.post(
            f"{base}/floors/", json={"facility_id": fac["id"], "name": "Level 2", "elevation": 3.6}, headers=headers
        )
    ).json()
    plant = (
        await client.post(
            f"{base}/spaces/",
            json={"floor_id": l1["id"], "name": "L1-01 Plant Room", "category": "Plant", "gross_area": 42.5},
            headers=headers,
        )
    ).json()
    office = (
        await client.post(
            f"{base}/spaces/", json={"floor_id": l2["id"], "name": "L2-04 Office", "category": "Office"}, headers=headers
        )
    ).json()
    return {"facility": fac, "l1": l1, "l2": l2, "plant": plant, "office": office}


async def test_register_crud_tree_systems_and_status_flow(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *ASSETS)
    base = f"/api/v1/assets/{project.id}"
    b = await _building(client, base, headers)

    company = (await client.post("/api/v1/contacts/companies/", json={"name": "Grundfos"}, headers=headers)).json()
    maker = (
        await client.post(
            "/api/v1/contacts/",
            json={"first_name": "Pat", "email": "pat@grundfos.example", "company_id": company["id"]},
            headers=headers,
        )
    ).json()
    pump_type = await client.post(
        f"{base}/types/",
        json={
            "name": "Pump CR-10",
            "category": "Pr_65_53_67 : Centrifugal pumps",
            "manufacturer_id": maker["id"],
            "model_number": "CR 10-4",
            "warranty_duration_parts": 2,
            "replacement_cost": "4500.00",
            "expected_life": 20,
            "attributes": {"Flow": "10 m3/h"},
        },
        headers=headers,
    )
    assert pump_type.status_code == 201, pump_type.text
    ptype = pump_type.json()
    assert ptype["manufacturer_name"] == "Pat (Grundfos)"

    created = await client.post(
        f"{base}/components/",
        json={
            "name": "P-101",
            "type_id": ptype["id"],
            "space_id": b["plant"]["id"],
            "serial_number": "SN1",
            "attributes": {"Duty": "Lead"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    pump = created.json()
    assert (pump["type_name"], pump["space_name"], pump["floor_name"], pump["status"]) == (
        "Pump CR-10",
        "L1-01 Plant Room",
        "Level 1",
        "planned",
    )

    bulk = await client.post(
        f"{base}/components/bulk",
        json={"names": ["P-102", "P-103", "P-101", " "], "type_id": ptype["id"], "space_id": b["plant"]["id"]},
        headers=headers,
    )
    assert bulk.status_code == 201, bulk.text
    assert [c["name"] for c in bulk.json()["created"]] == ["P-102", "P-103"]
    assert bulk.json()["skipped"] == ["P-101"]

    system = await client.post(
        f"{base}/systems/",
        json={
            "name": "Chilled water",
            "category": "Mechanical",
            "component_ids": [pump["id"], bulk.json()["created"][0]["id"]],
        },
        headers=headers,
    )
    assert system.status_code == 201
    assert len(system.json()["component_ids"]) == 2
    in_system = (await client.get(f"{base}/components/", params={"system_id": system.json()["id"]})).json()
    assert in_system["total_count"] == 2

    # Status follows the flow and is recorded.
    skip = await client.patch(f"/api/v1/assets/components/{pump['id']}", json={"status": "in_service"}, headers=headers)
    assert skip.status_code == 422
    ok = await client.patch(
        f"/api/v1/assets/components/{pump['id']}",
        json={"status": "installed", "installation_date": "2026-03-01"},
        headers=headers,
    )
    assert ok.json()["status"] == "installed"
    history = (await client.get(f"/api/v1/assets/components/{pump['id']}/history")).json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [("planned", "installed")]

    # Links must stay in the project.
    other = await _project(db_session, "P-2")
    foreign = (await client.post(f"/api/v1/assets/{other.id}/facilities/", json={"name": "Elsewhere"}, headers=headers)).json()
    bad = await client.post(f"{base}/floors/", json={"facility_id": foreign["id"], "name": "X"}, headers=headers)
    assert bad.status_code == 422

    tree = (await client.get(f"{base}/tree")).json()
    facility = tree["facilities"][0]
    assert facility["component_count"] == 3
    assert [f["name"] for f in facility["floors"]] == ["Level 1", "Level 2"]
    assert facility["floors"][0]["spaces"][0]["component_count"] == 3

    by_floor = (await client.get(f"{base}/components/", params={"floor_id": b["l1"]["id"]})).json()
    assert by_floor["total_count"] == 3
    assert (await client.get(f"{base}/components/", params={"search": "sn1"})).json()["total_count"] == 1

    # Deleting a space leaves its components unplaced.
    assert (await client.delete(f"/api/v1/assets/spaces/{b['plant']['id']}", headers=headers)).status_code == 200
    assert (await client.get(f"{base}/tree")).json()["unplaced_components"] == 3
    assert (await client.get(f"{base}/components/", params={"unplaced": True})).json()["total_count"] == 3


async def test_the_register_is_hidden_with_its_project(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *ASSETS)
    row = (await client.post(f"/api/v1/assets/{project.id}/facilities/", json={"name": "Hidden"}, headers=headers)).json()
    headers = await _as(client, db_session, test_user_2, "assets.read", "assets.update")
    assert (await client.get(f"/api/v1/assets/{project.id}/facilities/")).status_code == 404
    assert (
        await client.patch(f"/api/v1/assets/facilities/{row['id']}", json={"name": "Mine"}, headers=headers)
    ).status_code == 404


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def test_import_types_and_components_with_mapping(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *ASSETS)
    base = f"/api/v1/assets/{project.id}"
    await _building(client, base, headers)
    await client.post("/api/v1/contacts/companies/", json={"name": "Daikin"}, headers=headers)
    await client.post("/api/v1/contacts/", json={"first_name": "Dee", "email": "dee@daikin.example"}, headers=headers)

    types = _xlsx(
        [
            ["Product", "Manufacturer", "Model", "Uniclass", "Warranty (yrs)", "Replacement cost"],
            ["FCU-A", "dee@daikin.example", "FXFQ50", "Pr_60_65_03", 2, 1800],
            ["FCU-B", "Nobody Ltd", "FXFQ63", "Pr_60_65_03", "two", 2000],
        ]
    )
    upload = {"file": ("types.xlsx", types, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    preview = (await client.post(f"{base}/import/preview", files=upload, data={"target": "types"}, headers=headers)).json()
    assert preview["mapping"]["name"] == "Product"
    assert preview["mapping"]["manufacturer"] == "Manufacturer"
    mapping = (
        '{"name": "Product", "manufacturer": "Manufacturer", "model_number": "Model", "category": "Uniclass",'
        ' "warranty_duration_parts": "Warranty (yrs)", "replacement_cost": "Replacement cost"}'
    )
    report = (
        await client.post(f"{base}/import", files=upload, data={"target": "types", "mapping": mapping}, headers=headers)
    ).json()
    assert (report["created"], report["skipped"]) == (1, 1), report
    assert any("isn't a number" in e for e in report["errors"])
    fcu = (await client.get(f"{base}/types/")).json()["data"][0]
    assert (fcu["name"], fcu["model_number"], fcu["warranty_duration_parts"], fcu["replacement_cost"]) == (
        "FCU-A",
        "FXFQ50",
        2.0,
        "1800.00",
    )
    assert fcu["manufacturer_name"] == "Dee"

    components = (
        b"Asset Tag,Type,Room,Serial,Installed,Condition\n"
        b"FCU-01,FCU-A,L2-04 Office,S-1,2026-02-01,Good\n"
        b"FCU-02,FCU-NEW,Nowhere,S-2,01/02/2026,Fair\n"
        b",FCU-A,,,,\n"
    )
    upload = {"file": ("components.csv", components, "text/csv")}
    preview = (await client.post(f"{base}/import/preview", files=upload, headers=headers)).json()
    assert preview["target"] == "components"
    mapping = (
        '{"name": "Asset Tag", "type": "Type", "space": "Room", "serial_number": "Serial", "installation_date": "Installed"}'
    )
    dry = (
        await client.post(f"{base}/import", files=upload, data={"mapping": mapping, "dry_run": "true"}, headers=headers)
    ).json()
    assert (dry["created"], dry["skipped"]) == (2, 1)
    assert (await client.get(f"{base}/components/")).json()["total_count"] == 0

    real = (
        await client.post(
            f"{base}/import", files=upload, data={"mapping": mapping, "extra_as_attributes": "true"}, headers=headers
        )
    ).json()
    assert real["created"] == 2
    assert any("no space named 'Nowhere'" in e for e in real["errors"])
    rows = {c["name"]: c for c in (await client.get(f"{base}/components/")).json()["data"]}
    assert rows["FCU-01"]["space_name"] == "L2-04 Office"
    assert rows["FCU-01"]["installation_date"] == "2026-02-01"
    assert rows["FCU-01"]["attributes"] == {"Condition": "Good"}
    assert rows["FCU-02"]["type_name"] == "FCU-NEW"  # unknown types are created
    assert rows["FCU-02"]["space_id"] is None

    again = (
        await client.post(
            f"{base}/import",
            files={"file": ("c.csv", b"Asset Tag,Serial\nFCU-01,S-99\n", "text/csv")},
            data={"on_duplicate": "update"},
            headers=headers,
        )
    ).json()
    assert (again["updated"], len(again["duplicates"])) == (1, 1)
    updated = (await client.get(f"{base}/components/", params={"search": "S-99"})).json()["data"]
    assert [c["name"] for c in updated] == ["FCU-01"]

    bad = await client.post(f"{base}/import", files=upload, data={"mapping": '{"colour": "Type"}'}, headers=headers)
    assert bad.status_code == 422


async def test_cobie_workbook_and_validation(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session)
    headers = await _as(client, db_session, test_user, *ASSETS)
    base = f"/api/v1/assets/{project.id}"
    b = await _building(client, base, headers)
    company = (await client.post("/api/v1/contacts/companies/", json={"name": "Otis"}, headers=headers)).json()
    maker = (
        await client.post(
            "/api/v1/contacts/",
            json={"first_name": "Olive", "last_name": "Lift", "email": "olive@otis.example", "company_id": company["id"]},
            headers=headers,
        )
    ).json()
    await client.put(f"/api/v1/contacts/projects/{project.id}/{maker['id']}", json={"role": "Lift supplier"}, headers=headers)
    lift = (
        await client.post(
            f"{base}/types/",
            json={
                "name": "Lift Gen2",
                "category": "Pr_70_70_48 : Lifts",
                "manufacturer_id": maker["id"],
                "model_number": "Gen2",
                "attributes": {"Capacity": "1000 kg"},
            },
            headers=headers,
        )
    ).json()
    bare = (await client.post(f"{base}/types/", json={"name": "Door"}, headers=headers)).json()
    car = (
        await client.post(
            f"{base}/components/",
            json={"name": "LIFT-01", "type_id": lift["id"], "space_id": b["plant"]["id"], "serial_number": "OT-1"},
            headers=headers,
        )
    ).json()
    await client.post(f"{base}/components/", json={"name": "D-01", "type_id": bare["id"]}, headers=headers)
    await client.post(f"{base}/components/", json={"name": "d-01"}, headers=headers)
    await client.post(
        f"{base}/systems/",
        json={"name": "Vertical transport", "category": "Lifts", "component_ids": [car["id"]]},
        headers=headers,
    )
    await client.post(
        f"{base}/zones/",
        json={"name": "Fire zone A", "category": "Fire", "space_ids": [b["plant"]["id"], b["office"]["id"]]},
        headers=headers,
    )
    await client.post(
        "/api/v1/files/",
        data={"project_id": str(project.id), "entity_type": "asset", "entity_id": str(car["id"])},
        files={"file": ("lift-om-manual.pdf", b"%PDF-1.4 manual", "application/pdf")},
        headers=headers,
    )

    report = (await client.get(f"{base}/cobie/validate")).json()
    assert report["valid"] is False
    sheets = {s["sheet"]: s for s in report["sheets"]}
    assert list(sheets) == list(SHEETS)
    component_issues = {(i["row"], i["field"]) for i in sheets["Component"]["issues"] if i["severity"] == "error"}
    assert ("D-01", "Space") in component_issues  # components without space
    assert ("d-01", "TypeName") in component_issues
    assert ("D-01", "Name") in component_issues  # duplicate names, any case
    type_issues = {(i["row"], i["field"]) for i in sheets["Type"]["issues"] if i["severity"] == "error"}
    assert ("Door", "Manufacturer") in type_issues  # types without manufacturer
    assert ("Lift Gen2", "Manufacturer") not in type_issues
    assert sheets["Component"]["rows"] == 3 and sheets["Zone"]["rows"] == 2

    xlsx = await client.get(f"{base}/cobie.xlsx")
    assert xlsx.status_code == 200, xlsx.text
    assert "P-1-COBie.xlsx" in xlsx.headers["content-disposition"]
    book = load_workbook(io.BytesIO(xlsx.content))
    assert book.sheetnames == [
        "Contact",
        "Facility",
        "Floor",
        "Space",
        "Zone",
        "Type",
        "Component",
        "System",
        "Document",
        "Attribute",
    ]

    def table(name: str) -> list[dict]:
        rows = list(book[name].iter_rows(values_only=True))
        assert list(rows[0]) == SHEETS[name]
        return [dict(zip(rows[0], r, strict=True)) for r in rows[1:]]

    assert SHEETS["Component"][:6] == ["Name", "CreatedBy", "CreatedOn", "TypeName", "Space", "Description"]
    assert SHEETS["Type"][:8] == [
        "Name",
        "CreatedBy",
        "CreatedOn",
        "Category",
        "Description",
        "AssetType",
        "Manufacturer",
        "ModelNumber",
    ]
    contacts = {r["Email"]: r for r in table("Contact")}
    assert contacts["olive@otis.example"]["Company"] == "Otis"
    assert contacts["olive@otis.example"]["GivenName"] == "Olive"
    assert test_user["email"] in contacts  # CreatedBy is the exporting user, listed as a contact
    facility = table("Facility")[0]
    assert (facility["Name"], facility["ProjectName"], facility["SiteName"], facility["CurrencyUnit"]) == (
        "Admin Building",
        "Plant",
        "Port Hedland",
        "AUD",
    )
    assert facility["CreatedBy"] == test_user["email"]
    assert [r["Name"] for r in table("Floor")] == ["Level 1", "Level 2"]
    spaces = {r["Name"]: r for r in table("Space")}
    assert spaces["L1-01 Plant Room"]["FloorName"] == "Level 1"
    assert spaces["L1-01 Plant Room"]["GrossArea"] == 42.5
    assert [(z["Name"], z["SpaceNames"]) for z in table("Zone")] == [
        ("Fire zone A", "L1-01 Plant Room"),
        ("Fire zone A", "L2-04 Office"),
    ]
    types = {r["Name"]: r for r in table("Type")}
    assert types["Lift Gen2"]["Manufacturer"] == "olive@otis.example"
    assert types["Lift Gen2"]["AssetType"] == "Fixed"
    components = {r["Name"]: r for r in table("Component")}
    assert (components["LIFT-01"]["TypeName"], components["LIFT-01"]["Space"], components["LIFT-01"]["SerialNumber"]) == (
        "Lift Gen2",
        "L1-01 Plant Room",
        "OT-1",
    )
    assert components["LIFT-01"]["CreatedBy"] == test_user["email"]
    assert [(s["Name"], s["ComponentNames"]) for s in table("System")] == [("Vertical transport", "LIFT-01")]
    documents = table("Document")
    assert [(d["Name"], d["SheetName"], d["RowName"]) for d in documents] == [("lift-om-manual.pdf", "Component", "LIFT-01")]
    attributes = {(a["SheetName"], a["RowName"], a["Name"]): a["Value"] for a in table("Attribute")}
    assert attributes == {("Type", "Lift Gen2", "Capacity"): "1000 kg"}

"""The breakdown ingestion wizard (tree modes, text-safe codes, multi-value split, dry run, profiles) and terminology."""

import io
import json
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.projects.models import Project
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = ("projects.read", *(f"asset_tree.{a}" for a in ("read", "create", "update", "delete", "import", "configure")))
BASE = "/api/v1/asset-tree"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def setup(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="P-1", name="Plant")
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "assets", *PERMS)
    headers = {"X-CSRF-Token": await _login(client, test_user)}
    r = await client.post(f"{BASE}/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=headers)
    assert r.status_code == 200, r.text
    return project.id, headers


def csv_file(text: str) -> dict:
    return {"file": ("rows.csv", text.encode(), "text/csv")}


def xlsx_file(rows: list[list]) -> dict:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return {"file": ("rows.xlsx", buf.getvalue(), "application/octet-stream")}


async def run(client: AsyncClient, project_id: int, headers: dict, files: dict, mapping: dict | None = None, **form) -> dict:
    data = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()}
    if mapping is not None:
        data["mapping"] = json.dumps(mapping)
    r = await client.post(f"{BASE}/import", params={"project_id": project_id}, files=files, data=data, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def nodes(client: AsyncClient, project_id: int, level: str) -> dict[str, dict]:
    r = await client.get(f"{BASE}/nodes/", params={"project_id": project_id, "level_key": level})
    return {n["code"]: n for n in r.json()["data"]}


PER_LEVEL = {
    "tree_mode": "columns",
    "level_columns": {"site": "Site", "asset": "Asset", "rsw": "RSW"},
    "node_fields": {"name": "Description", "budget_hours": "Budget Hrs", "planned_start": "Start"},
    "custom_fields": {"priority": "Priority", "scope.shutdown": "Shutdown"},
}


async def test_per_level_columns_dry_run_then_apply(client: AsyncClient, setup):
    project_id, headers = setup
    sheet = xlsx_file(
        [
            ["Site", "Asset", "RSW", "Description", "Budget Hrs", "Start", "Priority", "Shutdown"],
            ["KAR", 101, 101.1, "Replace grating", 12.5, datetime(2026, 3, 1), "P1", "Yes"],
            ["KAR", 101, "101.3", "Recoat", "#N/A", None, "P2", "No"],
            ["KAR", 102, "102.1 and 102.2 ; 102.4", "Supports", 4, None, None, None],
        ]
    )

    preview = await client.post(f"{BASE}/import/preview", params={"project_id": project_id}, files=sheet, headers=headers)
    assert preview.status_code == 200, preview.text
    guessed = preview.json()["mapping"]
    assert guessed["level_columns"] == {"site": "Site", "asset": "Asset", "rsw": "RSW"}
    assert guessed["node_fields"]["budget_hours"] == "Budget Hrs"

    dry = await run(client, project_id, headers, sheet, PER_LEVEL, dry_run=True)
    assert dry["errors"] == []
    # 1 site + 2 assets + 2 RSWs + 3 split RSWs
    assert dry["nodes_created"] == 8
    assert any("#N/A" in w for w in dry["warnings"])
    assert any("split into 3" in w for w in dry["warnings"])
    assert await nodes(client, project_id, "rsw") == {}  # nothing written

    applied = await run(client, project_id, headers, sheet, PER_LEVEL, dry_run=False)
    assert applied["nodes_created"] == 8
    rsws = await nodes(client, project_id, "rsw")
    assert set(rsws) == {"101.1", "101.3", "102.1", "102.2", "102.4"}  # numeric 101.1 read as text
    first = rsws["101.1"]
    assert first["display_path"] == "KAR / 101 / 101.1"
    assert first["budget_hours"] == "12.5000"
    assert first["planned_start"] == "2026-03-01"
    assert first["custom_fields"] == {"priority": "P1", "scope": {"shutdown": "Yes"}}
    assert rsws["101.3"]["budget_hours"] is None
    assert rsws["102.4"]["name"] == "Supports"

    # Re-importing updates by code instead of duplicating.
    again = await run(client, project_id, headers, sheet, PER_LEVEL, dry_run=False)
    assert again["nodes_created"] == 0
    assert again["nodes_updated"] == 0
    assert again["nodes_unchanged"] == 5


async def test_update_modes_and_row_errors(client: AsyncClient, setup):
    project_id, headers = setup
    mapping = {"tree_mode": "columns", "level_columns": PER_LEVEL["level_columns"], "node_fields": {"name": "Description"}}
    first = "Site,Asset,RSW,Description\nS,A1,R1,One\n"
    assert (await run(client, project_id, headers, csv_file(first), mapping, dry_run=False))["nodes_created"] == 3

    changed = "Site,Asset,RSW,Description\nS,A1,R1,Changed\nS,A1,R2,New\n"
    create_only = await run(client, project_id, headers, csv_file(changed), mapping | {"update_mode": "create"})
    assert (create_only["nodes_created"], create_only["nodes_updated"], create_only["nodes_unchanged"]) == (1, 0, 1)

    update_only = await run(client, project_id, headers, csv_file(changed), mapping | {"update_mode": "update"}, dry_run=False)
    assert update_only["nodes_updated"] == 1
    assert update_only["skipped"] == 1
    assert update_only["errors"] == ["Row 3: there's no RSW 'R2' to update"]
    assert (await nodes(client, project_id, "rsw"))["R1"]["name"] == "Changed"

    # A code that breaks the level's rule is a row error; the good rows still go in.
    bad = "Site,Asset,RSW,Description\nS,A1,R3,\nS,,R4,\n"
    report = await run(client, project_id, headers, csv_file(bad), mapping, dry_run=False)
    assert report["nodes_created"] == 1
    assert len(report["errors"]) == 1 and report["errors"][0].startswith("Row 3:")


async def test_path_column_and_items_with_identifiers(client: AsyncClient, setup):
    project_id, headers = setup
    mapping = {
        "tree_mode": "path",
        "path_column": "Location",
        "path_separator": ">",
        "path_levels": ["site", "area", "asset", "rsw"],
        "item": {
            "tag_column": "Tag",
            "item_type_column": "Type",
            "fields": {"spec_ref": "Spec"},
            "custom_fields": {"nps": "NPS"},
            "identifiers": {"barcode": "Barcode"},
        },
    }
    text = (
        "Location,Tag,Type,Spec,NPS,Barcode\n"
        "KAR > A1 > 101 > 101.1,SP-1,Pipe spool,A106,6,0001234\n"
        "KAR > A1 > 101 > 101.1,V-1,valve,,,\n"
        "KAR > A1 > 101 > 101.1 > X,V-2,valve,,,\n"
    )
    report = await run(client, project_id, headers, csv_file(text), mapping, dry_run=False)
    assert report["nodes_created"] == 4
    assert report["items_created"] == 2
    assert report["errors"] == ["Row 4: 'KAR > A1 > 101 > 101.1 > X' has 5 parts but the mapping names 4 levels"]

    found = await client.get(f"{BASE}/items/lookup", params={"project_id": project_id, "value": "0001234"})
    assert found.status_code == 200, found.text
    item = found.json()
    assert item["tag"] == "SP-1" and item["item_type_key"] == "pipe_spool"
    assert item["custom_fields"] == {"nps": "6"}
    assert item["node_display_path"] == "KAR / A1 / 101 / 101.1"
    assert item["work_anchor_id"] is not None


async def test_parent_row_mode(client: AsyncClient, setup):
    project_id, headers = setup
    mapping = {"tree_mode": "parent_row", "code_column": "Code", "parent_column": "Parent", "level_column": "Level"}
    text = "Code,Parent,Level\nKAR,,Site\nA1,KAR,area\n101,A1,Asset\n101.1,101,RSW\n9,NOPE,Asset\n"
    report = await run(client, project_id, headers, csv_file(text), mapping, dry_run=False)
    assert report["nodes_created"] == 4
    assert report["errors"] == ["Row 6: parent 'NOPE' isn't in the file or the tree"]
    assert (await nodes(client, project_id, "rsw"))["101.1"]["display_path"] == "KAR / A1 / 101 / 101.1"


async def test_mapping_profiles_are_versioned_and_reused(client: AsyncClient, setup):
    project_id, headers = setup
    mapping = {"tree_mode": "columns", "level_columns": {"site": "Site", "asset": "Asset"}, "synonyms": {"Asset": ["Asset No"]}}
    report = await run(
        client, project_id, headers, csv_file("Site,Asset\nS,A1\n"), mapping, dry_run=False, save_profile_as="Client A"
    )
    assert report["profile"]["version"] == 1

    v2 = await client.post(
        f"{BASE}/mapping-profiles/",
        json={"project_id": project_id, "name": "Client A", "mapping": mapping | {"update_mode": "create"}},
        headers=headers,
    )
    assert v2.status_code == 201, v2.text
    assert v2.json()["version"] == 2

    latest = (await client.get(f"{BASE}/mapping-profiles/", params={"project_id": project_id})).json()["data"]
    assert [(p["name"], p["version"]) for p in latest] == [("Client A", 2)]
    history = (await client.get(f"{BASE}/mapping-profiles/", params={"project_id": project_id, "name": "Client A"})).json()
    assert [p["version"] for p in history["data"]] == [2, 1]

    # The profile maps a differently-headed file through its synonyms.
    other = csv_file("site,Asset No\nS,A2\n")
    preview = await client.post(
        f"{BASE}/import/preview",
        params={"project_id": project_id},
        files=other,
        data={"profile_id": str(v2.json()["id"])},
        headers=headers,
    )
    assert preview.json()["missing"] == []
    reused = await run(client, project_id, headers, other, profile_id=v2.json()["id"], dry_run=False)
    assert reused["errors"] == []
    assert reused["nodes_created"] == 1
    assert set(await nodes(client, project_id, "asset")) == {"A1", "A2"}


async def test_missing_columns_are_reported(client: AsyncClient, setup):
    project_id, headers = setup
    mapping = {"tree_mode": "columns", "level_columns": {"site": "Site", "rsw": "RSW No"}}
    report = await run(client, project_id, headers, csv_file("Site\nS\n"), mapping)
    assert report["errors"] == ["Columns not in the file: RSW No"]


async def test_terminology_resolves_levels_roles_and_overrides(client: AsyncClient, setup):
    project_id, headers = setup

    async def terms() -> dict[str, dict]:
        r = await client.get(f"{BASE}/terminology", params={"project_id": project_id})
        assert r.status_code == 200, r.text
        return {t["key"]: t for t in r.json()}

    t = await terms()
    assert t["level.rsw"] == {"key": "level.rsw", "one": "RSW", "other": "RSWs", "source": "level"}
    assert t["role.work_anchor"]["one"] == "RSW"
    assert t["noun.item"]["source"] == "default"

    r = await client.put(
        f"{BASE}/terminology",
        params={"project_id": project_id},
        json={
            "terms": {"level.rsw": {"one": "Work order", "other": "Work orders"}, "noun.item": {"one": "Tag", "other": "Tags"}}
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    t = await terms()
    assert t["level.rsw"]["other"] == "Work orders" and t["level.rsw"]["source"] == "project"
    assert t["role.work_anchor"]["one"] == "Work order"  # the role reads as its renamed level
    assert t["noun.item"]["one"] == "Tag"

    await client.put(
        f"{BASE}/terminology", params={"project_id": project_id}, json={"terms": {"level.rsw": None}}, headers=headers
    )
    assert (await terms())["level.rsw"]["one"] == "RSW"

    bad = await client.put(
        f"{BASE}/terminology",
        params={"project_id": project_id},
        json={"terms": {"RSW": {"one": "x", "other": "y"}}},
        headers=headers,
    )
    assert bad.status_code == 422


async def test_a_pack_brings_its_terminology(client: AsyncClient, db_session: AsyncSession, setup):
    _, headers = setup
    cui = Project(code="P-2", name="CUI")
    db_session.add(cui)
    await db_session.commit()
    await client.post(f"{BASE}/packs/cui-line/apply", params={"project_id": cui.id}, headers=headers)
    t = {x["key"]: x for x in (await client.get(f"{BASE}/terminology", params={"project_id": cui.id})).json()}
    assert t["noun.job_pack"]["one"] == "Job Package"
    assert t["role.work_anchor"]["one"] == "Line"
    assert "level.rsw" not in t

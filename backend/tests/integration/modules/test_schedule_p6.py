"""P6 mirror: preview and commit, idempotent re-import, never delete, renumbering, grammar linking with
proposals, remembered manual links, node creation, schedule facts and the verified-only actuals export."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.modules import state
from src.modules.inspections.models import Inspection
from src.modules.projects.models import Project
from src.modules.schedule.interchange import read_xer_tables
from tests.fixtures.accounts import reset_api_budget
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

PERMS = (
    "projects.read",
    *(f"schedule.{a}" for a in ("read", "create", "update", "delete", "import", "export", "review")),
    *(f"asset_tree.{a}" for a in ("read", "create", "update", "configure")),
)
D0 = date(2026, 3, 2)


def xer(tasks: list[dict], data_date: str = "2026-03-02") -> bytes:
    """A small XER in the client schedules' shape: PROJECT, PROJWBS, TASK, TASKPRED."""
    lines = [
        "ERMHDR\t24.12\t2026-03-01\tProject\tadmin\tdb\tProject Management\tAUD",
        "%T\tPROJECT",
        "%F\tproj_id\tproj_short_name\tclndr_id\tlast_recalc_date",
        f"%R\t1\tKAR-SD\t1\t{data_date} 00:00",
        "%T\tPROJWBS",
        "%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name\tproj_node_flag",
        "%R\t1\t1\t\tKAR-SD\tShutdown\tY",
        "%R\t2\t1\t1\tSITE\tSite works\tN",
        "%R\t3\t1\t2\tSHUT\tShutdown window\tN",
        "%T\tTASK",
        "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\tguid\ttask_name\ttask_type\tstatus_code\t"
        "target_drtn_hr_cnt\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\tdriving_path_flag",
    ]
    for n, t in enumerate(tasks, start=10):
        start = D0 + timedelta(days=t.get("shift", 0))
        finish = start + timedelta(days=t.get("days", 4))
        lines.append(
            "\t".join(
                [
                    "%R",
                    str(t.get("task_id", n)),
                    "1",
                    t.get("wbs", "3"),
                    "1",
                    t["code"],
                    t.get("guid", f"G-{t['code']}"),
                    t["name"],
                    t.get("type", "TT_Task"),
                    t.get("status", "TK_NotStart"),
                    "0" if t.get("type") == "TT_Mile" else str(8 * t.get("days", 4)),
                    f"{start} 08:00",
                    f"{finish} 16:00",
                    str(t.get("float", 40)),
                    t.get("driving", "N"),
                ]
            )
        )
    lines.append("%E")
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


V1 = [
    {"code": "A100", "name": "101 / B / 305", "float": 0, "driving": "Y"},
    {"code": "A110", "name": "101 / P / 410.2"},
    {"code": "A120", "name": "Mobilisation"},
    {"code": "M100", "name": "101 / B / 305", "type": "TT_Mile", "days": 0},
    {"code": "A130", "name": "101 / Prov.Sums / 305"},
]


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


@pytest_asyncio.fixture
async def ctx(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = Project(code="KAR", name="Karratha shutdown", start_date=D0)
    db_session.add(project)
    await db_session.commit()
    await _grant(db_session, test_user["id"], "planner", *PERMS)
    await reset_api_budget(test_user["id"], "/api/v1/asset-tree/nodes/")
    h = {"X-CSRF-Token": await _login(client, test_user)}
    r = await client.post("/api/v1/asset-tree/packs/remediation-rsw/apply", params={"project_id": project.id}, headers=h)
    assert r.status_code == 200, r.text

    async def node(level: str, code: str, parent: int | None = None) -> dict:
        r = await client.post(
            "/api/v1/asset-tree/nodes/",
            json={"project_id": project.id, "level_key": level, "code": code, "parent_id": parent},
            headers=h,
        )
        assert r.status_code == 201, r.text
        return r.json()

    site = await node("site", "KAR")
    area = await node("area", "A1", site["id"])
    asset = await node("asset", "101", area["id"])
    rsw = await node("rsw", "305", asset["id"])
    base = f"/api/v1/schedule/{project.id}/p6"

    async def upload(tasks: list[dict], expect: int = 201, **form) -> dict:
        r = await client.post(
            f"{base}/imports",
            files={"file": ("kar.xer", xer(tasks, form.pop("data_date", "2026-03-02")), "application/octet-stream")},
            data={k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()},
            headers=h,
        )
        assert r.status_code == expect, r.text
        return r.json()

    async def changes(import_id: int) -> list[dict]:
        r = await client.get(f"{base}/imports/{import_id}/changes/", params={"items_per_page": 100})
        assert r.status_code == 200, r.text
        return r.json()["data"]

    async def commit(import_id: int) -> dict:
        r = await client.post(f"{base}/imports/{import_id}/commit", headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    async def activities() -> dict[str, dict]:
        r = await client.get(f"/api/v1/schedule/gantt/{project.id}")
        assert r.status_code == 200, r.text
        return {a["p6_activity_id"]: a for a in r.json()["activities"] if a["p6_activity_id"]}

    async def links(**params) -> list[dict]:
        r = await client.get(f"{base}/links/", params=params)
        assert r.status_code == 200, r.text
        return r.json()["data"]

    return {
        "project": project,
        "h": h,
        "base": base,
        "node": node,
        "area": area,
        "asset": asset,
        "rsw": rsw,
        "upload": upload,
        "changes": changes,
        "commit": commit,
        "activities": activities,
        "links": links,
    }


async def test_preview_then_commit_is_idempotent(client: AsyncClient, ctx):
    imp = await ctx["upload"](V1)
    assert imp["status"] == "previewed" and imp["reused"] is False and imp["file_id"]
    assert imp["summary"]["changes"] == {"new": 5}
    assert imp["summary"]["matching"] == {"matched": 1, "unmatched": 2, "ineligible": 2}
    assert await ctx["activities"]() == {}  # nothing written before commit

    done = await ctx["commit"](imp["id"])
    assert done["status"] == "committed"
    assert done["summary"]["linking"] == {"linked": 1, "unmatched": 2, "ineligible": 2}
    acts = await ctx["activities"]()
    assert set(acts) == {"A100", "A110", "A120", "M100", "A130", "WBS:SITE", "WBS:SITE.SHUT"}
    assert acts["A100"]["parent_id"] == acts["WBS:SITE.SHUT"]["id"]
    linked = await ctx["links"](activity_id=acts["A100"]["id"])
    assert [(x["node_id"], x["method"], x["status"]) for x in linked] == [(ctx["rsw"]["id"], "name_grammar", "confirmed")]

    again = await ctx["upload"](V1)
    assert again["id"] == imp["id"] and again["reused"] is True
    assert len(await ctx["activities"]()) == 7

    unmatched = (await client.get(f"{ctx['base']}/unmatched/")).json()
    assert sorted(u["p6_activity_id"] for u in unmatched["data"]) == ["A110", "A120"]
    reasons = {u["p6_activity_id"]: u["reason"] for u in unmatched["data"]}
    assert reasons["A110"] == "RSW '410.2' not found." and reasons["A120"] == "No grammar matched the name."

    # A second, different file with nothing changed (only the data date) is all "unchanged".
    same = await ctx["upload"](V1, data_date="2026-03-09")
    assert same["summary"]["changes"] == {"unchanged": 5}
    await ctx["commit"](same["id"])


async def test_reimport_reports_changes_and_never_deletes(client: AsyncClient, ctx):
    await ctx["commit"]((await ctx["upload"](V1))["id"])
    before = await ctx["activities"]()
    v2 = [
        {"code": "A100", "name": "101 / B / 305", "shift": 3, "float": 0, "driving": "Y"},
        {"code": "A110", "name": "101 / P / 410.3"},
        {"code": "M100", "name": "101 / B / 305", "type": "TT_Mile", "days": 0},
        {"code": "A131", "name": "101 / Prov.Sums / 305", "guid": "G-A130"},
        {"code": "A140", "name": "101 / W / 305"},
    ]
    imp = await ctx["upload"](v2)
    changes = await ctx["changes"](imp["id"])
    kinds = {(c["p6_activity_id"], c["change_type"]) for c in changes}
    assert kinds == {
        ("A100", "dates_changed"),
        ("A110", "name_changed"),
        ("A131", "renumbered"),
        ("A140", "new"),
        ("A120", "removed"),
    }
    dates = next(c for c in changes if c["change_type"] == "dates_changed")
    assert dates["impact"]["start_shift_days"] == 3 and dates["impact"]["finish_shift_days"] == 3
    assert dates["impact"]["linked_nodes"] == ["KAR / A1 / 101 / 305"]
    assert imp["summary"]["date_shifts"]["max_slip_days"] == 3

    # Leave the date change out of this commit.
    r = await client.patch(
        f"{ctx['base']}/imports/{imp['id']}/changes/{dates['id']}", json={"excluded": True}, headers=ctx["h"]
    )
    assert r.json()["excluded"] is True
    await ctx["commit"](imp["id"])

    after = await ctx["activities"]()
    assert after["A120"]["schedule_state"] == "removed_from_schedule"  # kept, flagged
    assert after["A120"]["id"] == before["A120"]["id"]
    assert after["A131"]["id"] == before["A130"]["id"] and "A130" not in after  # renumbered, same identity
    assert after["A110"]["name"] == "101 / P / 410.3"
    assert after["A140"]["schedule_state"] == "active"

    # The excluded change comes back on the next file.
    nxt = await ctx["upload"](v2, data_date="2026-03-01")
    assert {(c["p6_activity_id"], c["change_type"]) for c in await ctx["changes"](nxt["id"])} == {("A100", "dates_changed")}
    await ctx["commit"](nxt["id"])
    assert (await ctx["activities"]())["A100"]["planned_start"] == str(D0 + timedelta(days=3))

    # A removed activity that returns is restored.
    back = await ctx["upload"]([*v2, {"code": "A120", "name": "Mobilisation"}])
    assert ("A120", "restored") in {(c["p6_activity_id"], c["change_type"]) for c in await ctx["changes"](back["id"])}


async def test_confirmed_links_are_never_moved_only_proposed(client: AsyncClient, ctx):
    await ctx["node"]("rsw", "306", ctx["asset"]["id"])
    await ctx["commit"]((await ctx["upload"](V1))["id"])
    imp = await ctx["upload"]([{**V1[0], "name": "101 / B / 306"}, *V1[1:]])
    renamed = next(c for c in await ctx["changes"](imp["id"]) if c["change_type"] == "name_changed")
    assert renamed["impact"]["relink_proposed"] == "KAR / A1 / 101 / 306"
    await ctx["commit"](imp["id"])
    a100 = (await ctx["activities"]())["A100"]
    got = {(x["node_path"], x["status"]) for x in await ctx["links"](activity_id=a100["id"])}
    assert got == {("KAR / A1 / 101 / 305", "confirmed"), ("KAR / A1 / 101 / 306", "proposed")}
    proposed = next(x for x in await ctx["links"](activity_id=a100["id"], status="proposed"))
    r = await client.post(f"{ctx['base']}/links/{proposed['id']}/confirm", headers=ctx["h"])
    assert r.json()["status"] == "confirmed"


async def test_manual_links_are_remembered_for_later_imports(client: AsyncClient, ctx):
    await ctx["commit"]((await ctx["upload"](V1))["id"])
    acts = await ctx["activities"]()
    r = await client.post(
        f"{ctx['base']}/activities/{acts['A120']['id']}/links",
        json={"node_id": ctx["rsw"]["id"], "remember": True},
        headers=ctx["h"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["method"] == "manual"
    left = (await client.get(f"{ctx['base']}/unmatched/")).json()["data"]
    assert [u["p6_activity_id"] for u in left] == ["A110"]

    imp = await ctx["upload"]([*V1, {"code": "A160", "name": "mobilisation "}])
    done = await ctx["commit"](imp["id"])
    assert done["summary"]["linking"]["remembered"] == 1
    a160 = (await ctx["activities"]())["A160"]
    assert [(x["node_id"], x["method"]) for x in await ctx["links"](activity_id=a160["id"])] == [
        (ctx["rsw"]["id"], "remembered")
    ]


async def test_missing_nodes_are_created_when_asked(client: AsyncClient, ctx):
    imp = await ctx["upload"](
        [{"code": "B100", "name": "202 / B / 512-21 Online"}, {"code": "B110", "name": "202 / SCA-Dism / 512-21 Shut"}],
        create_missing=True,
        create_under_node_id=ctx["area"]["id"],
    )
    assert imp["summary"]["matching"] == {"create": 2}
    await ctx["commit"](imp["id"])
    rows = await ctx["links"]()
    assert {(x["node_path"], x["work_window"]) for x in rows} == {
        ("KAR / A1 / 202 / 512-21", "Online"),
        ("KAR / A1 / 202 / 512-21", "Shut"),
    }
    assert len({x["node_id"] for x in rows}) == 1  # suffix: its own RSW; window: same RSW twice


async def test_rules_editor_and_sample_test(client: AsyncClient, ctx):
    base, h = ctx["base"], ctx["h"]
    rules = (await client.get(f"{base}/rules")).json()
    assert {r["kind"] for r in rules} == {"grammar", "eligibility", "alias"}
    tried = await client.post(
        f"{base}/rules/test",
        json={"samples": [{"name": "101 / SCA-Dism / 305 Shut"}, {"name": "Mobilise"}, {"name": "101 / Prov.Sums / 305"}]},
        headers=h,
    )
    assert tried.status_code == 200, tried.text
    first, second, third = tried.json()
    assert first["groups"] == {"asset": "101", "activity_type": "SCA Dism", "anchor_code": "305"}
    assert first["window"] == "Shut" and first["resolution"] == "matched" and first["node_id"] == ctx["rsw"]["id"]
    assert second["resolution"] == "unmatched" and second["matched_rule"] is None
    assert third["resolution"] == "ineligible"

    bad = await client.post(f"{base}/rules", json={"kind": "grammar", "name": "x", "pattern": "(unclosed"}, headers=h)
    assert bad.status_code == 422
    code_rule = await client.post(
        f"{base}/rules",
        json={
            "kind": "grammar",
            "name": "Code",
            "pattern": r"^(?P<asset>\d+)-(?P<rsw>\d+)$",
            "source": "code",
            "sort_order": 1,
        },
        headers=h,
    )
    assert code_rule.status_code == 201, code_rule.text
    tried = await client.post(f"{base}/rules/test", json={"samples": [{"name": "whatever", "code": "101-305"}]}, headers=h)
    assert tried.json()[0]["node_id"] == ctx["rsw"]["id"] and tried.json()[0]["matched_rule"] == "Code"
    trial = await client.post(
        f"{base}/rules/test",
        json={"samples": [{"name": "Area 101 RSW 305"}], "pattern": r"Area (?P<asset>\d+) RSW (?P<anchor_code>\d+)"},
        headers=h,
    )
    assert trial.json()[0]["node_id"] == ctx["rsw"]["id"]


async def test_schedule_facts_and_verified_only_export(client: AsyncClient, ctx, db_session: AsyncSession):
    base, h, rsw = ctx["base"], ctx["h"], ctx["rsw"]
    await ctx["commit"]((await ctx["upload"](V1))["id"])
    facts = (await client.get(f"{base}/facts", params={"node_id": ctx["asset"]["id"]})).json()
    assert facts["on_critical_path"] is True and facts["total_float_hours"] == 0.0
    await client.put(f"{base}/settings", json={"critical_definition": "total_float_le", "critical_float_hours": -1}, headers=h)
    assert (await client.get(f"{base}/facts", params={"node_id": rsw["id"]})).json()["on_critical_path"] is False

    r = await client.patch(
        f"/api/v1/asset-tree/nodes/{rsw['id']}", json={"budget_qty": "10", "earned_qty": "8", "uom": "m2"}, headers=h
    )
    assert r.status_code == 200, r.text
    rows = (await client.get(f"{base}/progress")).json()
    assert [(x["p6_activity_id"], x["reported_percent"], x["verified_percent"]) for x in rows] == [("A100", 80.0, 0.0)]

    insp = Inspection(project_id=ctx["project"].id, code="INS-001", title="RSW 305 hold point", status="planned")
    db_session.add(insp)
    await db_session.commit()
    v = await client.post(
        f"/api/v1/schedule/{ctx['project'].id}/progress/verifications",
        json={"node_id": rsw["id"], "verified_qty": "5", "inspection_id": insp.id, "verified_on": "2026-03-04"},
        headers=h,
    )
    assert v.status_code == 201, v.text
    assert v.json()["counts"] is False  # the inspection hasn't passed: not earned
    assert (await client.get(f"{base}/progress")).json()[0]["verified_percent"] == 0.0

    insp.status = "completed"
    await db_session.commit()
    row = (await client.get(f"{base}/progress")).json()[0]
    assert (row["verified_percent"], row["actual_start"], row["status_code"]) == (50.0, "2026-03-04", "TK_Active")

    await client.post(
        f"/api/v1/schedule/{ctx['project'].id}/progress/verifications",
        json={"node_id": rsw["id"], "verified_qty": "10", "verified_on": "2026-03-06"},
        headers=h,
    )
    row = (await client.get(f"{base}/progress")).json()[0]
    assert (row["verified_percent"], row["actual_finish"], row["status_code"]) == (100.0, "2026-03-06", "TK_Complete")

    exp = await client.post(f"{base}/exports", json={"format": "xer"}, headers=h)
    assert exp.status_code == 201, exp.text
    assert exp.json()["row_count"] == 1
    body = await client.get(f"{base}/exports/{exp.json()['id']}/download")
    tables = read_xer_tables(body.content.decode("cp1252"))
    assert [(t["task_code"], t["status_code"], t["phys_complete_pct"], t["act_end_date"]) for t in tables["TASK"]] == [
        ("A100", "TK_Complete", "100", "2026-03-06 08:00")
    ]
    for fmt, marker in (("p6_xml", b"<PhysicalPercentComplete>100</PhysicalPercentComplete>"), ("csv", b"Physical % Complete")):
        e = await client.post(f"{base}/exports", json={"format": fmt, "only_changed": False}, headers=h)
        assert marker in (await client.get(f"{base}/exports/{e.json()['id']}/download")).content
    history = (await client.get(f"{base}/exports/")).json()
    assert history["total_count"] == 3


async def test_p6_routes_need_the_project(client: AsyncClient, ctx, db_session: AsyncSession):
    other = Project(code="OTH", name="Other")
    db_session.add(other)
    await db_session.commit()
    imp = await ctx["upload"](V1)
    r = await client.get(f"/api/v1/schedule/{other.id}/p6/imports/{imp['id']}")
    assert r.status_code == 404


def xer_wbs(tasks: list[dict]) -> bytes:
    """A synthetic XER with a deeper WBS (root / Construction / region / site), two calendars and float."""
    lines = [
        "ERMHDR\t24.12\t2026-03-01\tProject\tadmin\tdb\tProject Management\tAUD",
        "%T\tPROJECT",
        "%F\tproj_id\tproj_short_name\tclndr_id\tlast_recalc_date",
        "%R\t1\tSYN-RG\t1\t2026-03-02 00:00",
        "%T\tCALENDAR",
        "%F\tclndr_id\tdefault_flag\tclndr_name\tday_hr_cnt\tclndr_data",
        "%R\t1\tY\t7x12\t12\t",
        "%R\t2\tN\t5x8\t8\t",
        "%T\tPROJWBS",
        "%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name\tproj_node_flag",
        "%R\t1\t1\t\tSYN-RG\tSynthetic programme\tY",
        "%R\t2\t1\t1\t8\tConstruction\tN",
        "%R\t3\t1\t2\t2\tNorth Region\tN",
        "%R\t4\t1\t3\tEI\tEast Island\tN",
        "%T\tTASK",
        "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\tguid\ttask_name\ttask_type\tstatus_code\t"
        "target_drtn_hr_cnt\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\ttarget_work_qty",
    ]
    for n, t in enumerate(tasks, start=10):
        start = D0 + timedelta(days=t.get("shift", 0))
        finish = start + timedelta(days=t.get("days", 4))
        lines.append(
            "\t".join(
                [
                    "%R",
                    str(n),
                    "1",
                    "4",
                    t.get("cal", "1"),
                    t["code"],
                    f"G-{t['code']}",
                    t["name"],
                    "TT_Task",
                    "TK_NotStart",
                    str(12 * t.get("days", 4)),
                    f"{start} 06:00",
                    f"{finish} 18:00",
                    str(t.get("float", 24)),
                    str(t.get("hours", 30)),
                ]
            )
        )
    lines.append("%E")
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


async def test_wbs_levels_lists_qualifiers_and_rsw_rollup(client: AsyncClient, ctx):
    """Site and Area come from the WBS, a range links every RSW in it, and P6-created RSWs are named and dated."""
    base, h = ctx["base"], ctx["h"]
    for name, depth, level in (("Region is the site", 2, "site"), ("Site is the area", 3, "area")):
        r = await client.post(
            f"{base}/rules",
            json={"kind": "wbs_level", "name": name, "params": {"depth": depth, "level": level}},
            headers=h,
        )
        assert r.status_code == 201, r.text
    bad = await client.post(f"{base}/rules", json={"kind": "wbs_level", "name": "x", "params": {"depth": 0}}, headers=h)
    assert bad.status_code == 422

    tasks = [
        {"code": "C100", "name": "CV-09 / SCA Erect / 728 - 730 OHP", "hours": 30, "float": 0},
        {"code": "C110", "name": "CV-09 / B / 729", "shift": 7, "hours": 12, "cal": "2", "float": 16},
        {"code": "C120", "name": "CV-09 / P / 905", "shift": 3, "hours": 8},
    ]

    async def upload(data: bytes) -> dict:
        r = await client.post(
            f"{base}/imports",
            files={"file": ("syn.xer", data, "application/octet-stream")},
            data={"create_missing": "true"},
            headers=h,
        )
        assert r.status_code == 201, r.text
        return r.json()

    imp = await upload(xer_wbs(tasks))
    assert imp["summary"]["matching"] == {"create": 3}
    await ctx["commit"](imp["id"])

    async def all_nodes() -> list[dict]:
        out = []
        for level in ("site", "area", "asset", "rsw"):
            r = await client.get(
                "/api/v1/asset-tree/nodes/",
                params={"project_id": ctx["project"].id, "level_key": level, "items_per_page": 100},
            )
            assert r.status_code == 200, r.text
            out += r.json()["data"]
        return out

    nodes = {n["display_path"]: n for n in await all_nodes()}
    assert "North Region / East Island / CV-09 / 729" in nodes
    rsw = {code: nodes[f"North Region / East Island / CV-09 / {code}"] for code in ("728", "729", "730", "905")}
    # Named after their activity types (earliest first); dated and given hours from the linked activities.
    assert rsw["729"]["name"] == "SCA Erect, B" and rsw["905"]["name"] == "P"
    assert rsw["729"]["planned_start"] == str(D0) and rsw["729"]["planned_finish"] == str(D0 + timedelta(days=11))
    assert float(rsw["729"]["budget_hours"]) == 22.0  # 30 h shared by three RSWs + 12 h
    assert float(rsw["728"]["budget_hours"]) == 10.0

    acts = await ctx["activities"]()
    linked = await ctx["links"](activity_id=acts["C100"]["id"])
    assert sorted(x["node_path"].split(" / ")[-1] for x in linked) == ["728", "729", "730"]
    assert all(x["status"] == "confirmed" and x["parsed"]["qualifier"] == "OHP" for x in linked)
    # P6's own float, in days on each activity's calendar, and P6's critical flag beside the CPM's.
    assert (acts["C100"]["p6_float_days"], acts["C100"]["p6_critical"]) == (0.0, True)
    assert (acts["C110"]["p6_float_days"], acts["C110"]["p6_critical"]) == (2.0, False)
    gantt = (await client.get(f"/api/v1/schedule/gantt/{ctx['project'].id}")).json()
    assert gantt["summary"]["critical_count"] == 1  # P6's view: only C100 has no float

    # Someone renames RSW 905 and sets its hours; a revised programme moves the dates.
    r = await client.patch(
        f"/api/v1/asset-tree/nodes/{rsw['905']['id']}", json={"name": "Paint, splash zone", "budget_hours": "99"}, headers=h
    )
    assert r.status_code == 200, r.text
    moved = [{**t, "shift": t.get("shift", 0) + 14} for t in tasks]
    again = await upload(xer_wbs(moved))
    await ctx["commit"](again["id"])
    after = {n["id"]: n for n in await all_nodes()}
    assert after[rsw["905"]["id"]]["name"] == "Paint, splash zone"  # a person's edit is never overwritten
    assert float(after[rsw["905"]["id"]]["budget_hours"]) == 99.0
    assert after[rsw["905"]["id"]]["planned_start"] == str(D0 + timedelta(days=17))  # untouched field follows P6
    assert after[rsw["728"]["id"]]["planned_start"] == str(D0 + timedelta(days=14))

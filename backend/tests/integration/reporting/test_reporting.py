"""Reporting and the import/export hub: registry, exports, importers, KPIs, portfolio, templates, schedules, pivots."""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mail import Mail
from src.infrastructure.modules import state
from src.modules.cvr.models import CostHead
from src.modules.projects.models import Project
from src.modules.reporting import schedules
from src.modules.reporting.models import ReportSchedule
from src.modules.tasks.models import Task
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

EVERYTHING = (
    "projects.read",
    "cvr.read",
    "cvr.edit",
    "tasks.read",
    "tasks.create",
    "contacts.read",
    "contacts.import",
    "files.read",
    "data_exchange.export",
    "data_exchange.import",
    "reporting.read",
    "reporting.export",
    "reporting.create",
    "reporting.update",
    "reporting.delete",
    "platform.modules",
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


async def _as(client: AsyncClient, db: AsyncSession, user: dict, *permissions: str, role: str = "") -> dict:
    await _grant(db, user["id"], role or f"r{user['id']}-{len(permissions)}", *permissions)
    return {"X-CSRF-Token": await _login(client, user)}


async def _project(db: AsyncSession, code: str, region: str = "AU", **heads: tuple[int, int, int, int, int]) -> Project:
    project = Project(code=code, name=f"Plant {code}", region=region)
    db.add(project)
    await db.flush()
    for i, (head, figures) in enumerate(heads.items()):
        budget, cost, value, f_cost, f_value = (Decimal(x) for x in figures)
        db.add(
            CostHead(
                project_id=project.id,
                code=head,
                description=f"Head {head}",
                sort_order=i,
                budget=budget,
                cost_to_date=cost,
                value_to_date=value,
                forecast_cost=f_cost,
                forecast_value=f_value,
            )
        )
    await db.commit()
    return project


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# --- registry ------------------------------------------------------------------------------------------


async def test_datasets_follow_permissions_and_module_switches(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1")
    headers = await _as(
        client, db_session, test_user, "data_exchange.export", "projects.read", "tasks.read", "platform.modules"
    )

    names = {d["name"] for d in (await client.get("/api/v1/data/datasets/")).json()["data"]}
    assert {"projects", "tasks"} <= names
    assert "cvr_cost_heads" not in names  # no cvr.read
    assert (await client.get(f"/api/v1/data/export/cvr_cost_heads?project_id={project.id}")).status_code == 404

    await _grant(db_session, test_user["id"], "cvr-reader", "cvr.read", "reporting.read")
    names = {d["name"] for d in (await client.get("/api/v1/data/datasets/")).json()["data"]}
    assert {"cvr_cost_heads", "cvr_cashflow"} <= names
    kpis = {k["key"] for k in (await client.get("/api/v1/reporting/kpis/")).json()["data"]}
    assert {"cvr.margin_pct", "tasks.overdue"} <= kpis

    off = await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": False}, headers=headers)
    assert off.status_code == 200, off.text
    names = {d["name"] for d in (await client.get("/api/v1/data/datasets/")).json()["data"]}
    assert not {"cvr_cost_heads", "cvr_cashflow"} & names
    kpis = {k["key"] for k in (await client.get("/api/v1/reporting/kpis/")).json()["data"]}
    assert not any(k.startswith("cvr.") for k in kpis)
    kpi_values = (await client.get(f"/api/v1/reporting/kpi/{project.id}")).json()
    assert not any(k["key"].startswith("cvr.") for k in kpi_values)

    await client.patch("/api/v1/modules/cvr/toggle", json={"enabled": True}, headers=headers)
    names = {d["name"] for d in (await client.get("/api/v1/data/datasets/")).json()["data"]}
    assert "cvr_cost_heads" in names


async def test_exports_hide_projects_the_caller_cannot_see(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _project(db_session, "P-1")
    hidden = await _project(db_session, "P-2")
    await _as(client, db_session, test_user_2, "data_exchange.export", "tasks.read")  # external: no projects.read

    assert (await client.get(f"/api/v1/data/export/tasks?project_id={hidden.id}")).status_code == 404
    body = (await client.get("/api/v1/data/export/projects?format=csv&metadata=false")).text
    assert "P-1" not in body and "P-2" not in body


# --- export --------------------------------------------------------------------------------------------


async def test_export_as_excel_csv_and_pdf(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1", A1=(1000, 400, 500, 1100, 1300), B2=(2000, 100, 150, 1900, 2400))
    await _as(client, db_session, test_user, *EVERYTHING)

    url = f"/api/v1/data/export/cvr_cost_heads?project_id={project.id}"
    xlsx = await client.get(url + "&format=xlsx")
    assert xlsx.status_code == 200, xlsx.text
    assert 'filename="cvr_cost_heads-P-1-' in xlsx.headers["content-disposition"]
    book = load_workbook(io.BytesIO(xlsx.content))
    data = book.worksheets[0]
    header = [c.value for c in data[1]]
    assert header[:3] == ["Code", "Cost head", "Budget"]
    assert [c.value for c in data[2]][:3] == ["A1", "Head A1", 1000]
    assert data["C2"].number_format == "#,##0.00"
    about = {r[0]: r[1] for r in book["About"].iter_rows(values_only=True)}
    assert about["Project"] == "P-1 — Plant P-1"
    assert about["Generated by"] == test_user["name"]
    assert about["Rows"] == 2

    filtered = await client.get(url + '&format=csv&columns=code,budget,variance&filters={"code":"B2"}')
    lines = filtered.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("# Dataset: CVR cost heads")
    assert any(line.startswith('# Filters: {"code": "B2"}') for line in lines)
    table = list(csv.reader([line for line in lines if not line.startswith("#")]))
    assert table == [["Code", "Budget", "Budget variance"], ["B2", "2000.0", "100.0"]]

    pdf = await client.get(url + "&format=pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    assert (await client.get("/api/v1/data/export/cvr_cost_heads")).status_code == 422  # needs a project
    assert (await client.get(url + "&columns=nope")).status_code == 422
    assert (await client.get(url + '&filters={"code":{"near":1}}')).status_code == 422


# --- import --------------------------------------------------------------------------------------------


async def test_budget_import_dry_runs_then_upserts_by_code(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1", A1=(1000, 0, 0, 0, 0))
    headers = await _as(client, db_session, test_user, *EVERYTHING)
    file = _xlsx(
        [
            ["Cost code", "Description", "Budget", "Forecast", "Actual cost"],
            ["A1", "Head A1", "$1,500.00", 1600, 200],
            ["B2", "Scaffolding", 3000, None, None],
            ["C3", None, 10, None, None],
            ["A1", "Again", 1, None, None],
            ["D4", "Bad", "lots", None, None],
            [None, None, None, None, None],
        ]
    )
    upload = {"file": ("budget.xlsx", file, "application/octet-stream")}

    importers = {i["name"] for i in (await client.get("/api/v1/data/importers/")).json()["data"]}
    assert {"budget", "tasks", "contacts"} <= importers
    preview = (await client.post("/api/v1/data/import/budget/preview", files=upload, headers=headers)).json()
    assert preview["mapping"] == {
        "code": "Cost code",
        "description": "Description",
        "budget": "Budget",
        "cost_to_date": "Actual cost",
        "forecast_cost": "Forecast",
    }
    assert preview["rows"] == 5

    form = {"project_id": str(project.id), "dry_run": "true"}
    dry = (await client.post("/api/v1/data/import/budget", files=upload, data=form, headers=headers)).json()
    assert (dry["created"], dry["updated"], dry["skipped"], dry["dry_run"]) == (1, 1, 3, True), dry
    assert any("C3" in e and "description" in e for e in dry["errors"])
    assert any("twice" in e for e in dry["errors"])
    assert any("lots" in e for e in dry["errors"])
    heads = (await db_session.execute(select(CostHead).where(CostHead.project_id == project.id))).scalars().all()
    assert [(h.code, h.budget) for h in heads] == [("A1", Decimal("1000.00"))]

    real = (
        await client.post("/api/v1/data/import/budget", files=upload, data={**form, "dry_run": "false"}, headers=headers)
    ).json()
    assert (real["created"], real["updated"]) == (1, 1)
    fresh = select(CostHead).where(CostHead.project_id == project.id).execution_options(populate_existing=True)
    heads = {h.code: h for h in (await db_session.execute(fresh)).scalars()}
    assert set(heads) == {"A1", "B2"}
    assert (heads["A1"].budget, heads["A1"].forecast_cost, heads["A1"].cost_to_date) == (
        Decimal("1500.00"),
        Decimal("1600.00"),
        Decimal("200.00"),
    )
    assert heads["B2"].description == "Scaffolding"

    again = (
        await client.post("/api/v1/data/import/budget", files=upload, data={**form, "dry_run": "false"}, headers=headers)
    ).json()
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 2)

    no_project = await client.post("/api/v1/data/import/budget", files=upload, headers=headers)
    assert no_project.status_code == 422


async def test_task_import_maps_statuses_and_assignees(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    project = await _project(db_session, "P-1")
    headers = await _as(client, db_session, test_user, *EVERYTHING)
    file = (
        "Task,Status,Priority,Due,Assignee\n"
        f"Pour slab,In Progress,high,31/12/2026,{test_user_2['email'].upper()}\n"
        "Order steel,done,low,2026-11-01,nobody@example.com\n"
        "Bad one,sideways,low,someday,\n"
    ).encode()
    upload = {"file": ("tasks.csv", file, "text/csv")}
    form = {"project_id": str(project.id), "dry_run": "false"}
    report = (await client.post("/api/v1/data/import/tasks", files=upload, data=form, headers=headers)).json()
    assert (report["created"], report["skipped"]) == (2, 1), report
    assert any("nobody@example.com" in w for w in report["warnings"])
    tasks = {t.title: t for t in (await db_session.execute(select(Task).where(Task.project_id == project.id))).scalars()}
    assert tasks["Pour slab"].status == "in_progress"
    assert tasks["Pour slab"].due_date == date(2026, 12, 31)
    assert tasks["Pour slab"].assignee_id == test_user_2["id"]
    assert tasks["Order steel"].status == "done"

    again = (await client.post("/api/v1/data/import/tasks", files=upload, data=form, headers=headers)).json()
    assert (again["created"], again["skipped"]) == (1, 2)  # "Order steel" is done, so not a duplicate


async def test_contacts_import_goes_through_the_contacts_importer(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    headers = await _as(client, db_session, test_user, *EVERYTHING)
    upload = {"file": ("c.csv", b"Name,Email,Company\nAlex Smith,alex@example.com,Northwind\n", "text/csv")}
    report = (
        await client.post("/api/v1/data/import/contacts", files=upload, data={"dry_run": "false"}, headers=headers)
    ).json()
    assert report["created"] == 1, report
    contacts = (await client.get("/api/v1/contacts/")).json()["data"]
    assert contacts[0]["company_name"] == "Northwind"


# --- KPIs and portfolio --------------------------------------------------------------------------------


async def test_project_kpis_with_status_colours(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1", A1=(1000, 450, 500, 1100, 1200))
    today = date.today()
    for i, (status, due) in enumerate(
        [("done", None), ("todo", today - timedelta(days=3)), ("todo", today + timedelta(days=3)), ("review", None)]
    ):
        db_session.add(Task(project_id=project.id, code=f"T{i}", title=f"T{i}", status=status, due_date=due))
    await db_session.commit()
    await _as(client, db_session, test_user, *EVERYTHING)

    kpis = {k["key"]: k for k in (await client.get(f"/api/v1/reporting/kpi/{project.id}")).json()}
    assert kpis["cvr.margin_pct"]["value"] == 10.0 and kpis["cvr.margin_pct"]["status"] == "good"
    assert kpis["cvr.cost_value_ratio"]["value"] == 90.0 and kpis["cvr.cost_value_ratio"]["status"] == "good"
    assert kpis["cvr.budget_variance_pct"]["value"] == -10.0 and kpis["cvr.budget_variance_pct"]["status"] == "bad"
    assert kpis["cvr.forecast_margin_pct"]["value"] == 8.33 and kpis["cvr.forecast_margin_pct"]["status"] == "warning"
    assert (kpis["tasks.open"]["value"], kpis["tasks.overdue"]["value"]) == (3, 1)
    assert kpis["tasks.overdue"]["status"] == "warning"
    assert kpis["tasks.completion_rate"]["value"] == 25.0 and kpis["tasks.completion_rate"]["status"] == "bad"


async def test_portfolio_numbers_filters_and_cards(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    over = await _project(db_session, "P-1", "UK", A1=(1000, 600, 700, 1200, 1500))
    await _project(db_session, "P-2", "AU", A1=(2000, 500, 600, 1800, 2400), B1=(1000, 0, 0, 0, 0))
    db_session.add(Project(code="P-3", name="Empty", region="AU", currency="EUR"))
    await db_session.commit()
    await _as(client, db_session, test_user, *EVERYTHING)

    rows = {r["code"]: r for r in (await client.get("/api/v1/reporting/portfolio/")).json()["data"]}
    assert set(rows) == {"P-1", "P-2", "P-3"}
    p1 = rows["P-1"]
    assert (p1["budget"], p1["cost_to_date"], p1["value_to_date"]) == (1000, 600, 700)
    assert (p1["variance"], p1["variance_pct"], p1["budget_status"]) == (-200, -20.0, "over")
    assert (p1["forecast_margin"], p1["forecast_margin_pct"]) == (300, 20.0)
    p2 = rows["P-2"]
    assert (p2["budget"], p2["variance"], p2["budget_status"]) == (3000, 1200, "on")
    assert rows["P-3"]["budget_status"] == "none"
    assert "tasks.overdue" in p1["kpis"]

    only_over = (await client.get("/api/v1/reporting/portfolio/?budget=over")).json()
    assert [r["project_id"] for r in only_over["data"]] == [over.id]
    au = (await client.get("/api/v1/reporting/portfolio/?region=au&items_per_page=1")).json()
    assert au["total_count"] == 2 and len(au["data"]) == 1

    summary = (await client.get("/api/v1/reporting/portfolio/summary")).json()
    assert (summary["projects"], summary["over_budget"], summary["on_budget"], summary["no_budget"]) == (3, 1, 1, 1)
    assert summary["average_variance_pct"] == 10.0  # (-20 + 40) / 2
    assert summary["regions"] == ["AU", "UK"]
    totals = {t["currency"]: t for t in summary["totals"]}
    assert totals["AUD"]["budget"] == 4000 and totals["EUR"]["budget"] == 0


async def test_portfolio_without_cvr_access_leaves_figures_out(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _project(db_session, "P-1", A1=(1000, 600, 700, 1200, 1500))
    await _as(client, db_session, test_user, "reporting.read", "projects.read")
    row = (await client.get("/api/v1/reporting/portfolio/")).json()["data"][0]
    assert row["budget"] is None and row["budget_status"] == "none"


# --- templates and generation --------------------------------------------------------------------------


async def test_templates_generate_pdf_and_excel(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1", A1=(1000, 450, 500, 1100, 1200), B2=(500, 10, 20, 400, 600))
    db_session.add(Task(project_id=project.id, code="T1", title="Pour", status="todo", priority="high"))
    await db_session.commit()
    headers = await _as(client, db_session, test_user, *EVERYTHING)

    templates = {t["builtin_key"]: t for t in (await client.get("/api/v1/reporting/templates/")).json()["data"]}
    assert {"monthly_progress", "cost_report", "task_summary"} <= set(templates)
    for key in ("monthly_progress", "cost_report", "task_summary"):
        for fmt in ("pdf", "xlsx"):
            response = await client.post(
                "/api/v1/reporting/generate",
                json={"template_id": templates[key]["id"], "project_id": project.id, "format": fmt},
                headers=headers,
            )
            assert response.status_code == 200, (key, fmt, response.text)
    cost = await client.post(
        "/api/v1/reporting/generate",
        json={"template_id": templates["cost_report"]["id"], "project_id": project.id, "format": "xlsx"},
        headers=headers,
    )
    book = load_workbook(io.BytesIO(cost.content))
    assert book.sheetnames[0] == "Summary"
    assert "Cost heads" in book.sheetnames
    summary = [r for r in book["Summary"].iter_rows(values_only=True)]
    assert ("Budget", "1,500", None) in summary
    chart_sheet = book[next(n for n in book.sheetnames if n.startswith("Budget against"))]
    assert [c.value for c in chart_sheet[1]] == ["Code", "Budget", "Forecast cost"]

    custom = await client.post(
        "/api/v1/reporting/templates/",
        json={
            "name": "Mine",
            "branding": {"company_name": "Acme Insulation"},
            "sections": [
                {"type": "text", "title": "Note", "body": "Hello"},
                {"type": "pivot", "dataset": "tasks", "rows": ["status"], "values": [{"field": "*", "agg": "count"}]},
                {"type": "chart", "dataset": "tasks", "chart": "pie", "x": "priority", "y": ["tasks"]},
                {"type": "table", "dataset": "cvr_cost_heads", "columns": ["code", "budget"], "group_by": "code"},
                {"type": "table", "dataset": "nonexistent"},
            ],
        },
        headers=headers,
    )
    assert custom.status_code == 201, custom.text
    template_id = custom.json()["id"]
    pdf = await client.post(
        "/api/v1/reporting/generate", json={"template_id": template_id, "project_id": project.id}, headers=headers
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = await client.post(
        "/api/v1/reporting/generate",
        json={"template_id": template_id, "project_id": project.id, "format": "xlsx"},
        headers=headers,
    )
    summary = [r[0] for r in load_workbook(io.BytesIO(xlsx.content))["Summary"].iter_rows(values_only=True)]
    assert "Hello" in summary
    assert any(str(line).startswith("Not available") for line in summary)

    bad = await client.post("/api/v1/reporting/templates/", json={"name": "x", "sections": [{"type": "map"}]}, headers=headers)
    assert bad.status_code == 422
    renamed = await client.put(
        f"/api/v1/reporting/templates/{template_id}", json={"name": "Renamed", "sections": []}, headers=headers
    )
    assert renamed.json()["name"] == "Renamed"
    builtin = templates["cost_report"]["id"]
    assert (await client.delete(f"/api/v1/reporting/templates/{builtin}", headers=headers)).status_code == 422
    copy = await client.post(f"/api/v1/reporting/templates/{builtin}/copy", headers=headers)
    assert copy.status_code == 201 and copy.json()["builtin_key"] is None
    assert (await client.delete(f"/api/v1/reporting/templates/{template_id}", headers=headers)).status_code == 200


# --- schedules -----------------------------------------------------------------------------------------


async def test_scheduled_reports_send_now_and_when_due(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, monkeypatch
):
    sent: list[Mail] = []

    async def capture(mail: Mail) -> None:
        sent.append(mail)

    monkeypatch.setattr(schedules, "deliver", capture)
    project = await _project(db_session, "P-1", A1=(1000, 450, 500, 1100, 1200))
    headers = await _as(client, db_session, test_user, *EVERYTHING)
    template = (await client.get("/api/v1/reporting/templates/")).json()["data"][0]

    created = await client.post(
        "/api/v1/reporting/schedules/",
        json={
            "name": "Weekly cost",
            "template_id": template["id"],
            "project_ids": [project.id],
            "cadence": "weekly",
            "weekday": 0,
            "time_of_day": "07:00",
            "recipient_user_ids": [test_user_2["id"]],
            "recipient_emails": ["PM@Example.com"],
            "format": "xlsx",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["timezone"] == "Australia/Perth"
    next_run = datetime.fromisoformat(schedule["next_run_at"])
    assert next_run.astimezone(UTC).hour == 23 and next_run.astimezone(UTC).weekday() == 6  # Mon 07:00 AWST

    runs = (await client.post(f"/api/v1/reporting/schedules/{schedule['id']}/send", headers=headers)).json()
    assert [r["status"] for r in runs] == ["success"], runs
    assert len(sent) == 1
    mail = sent[0]
    assert sorted(mail.to) == sorted(["pm@example.com", test_user_2["email"]])
    assert mail.attachments[0].filename.endswith(".xlsx")
    load_workbook(io.BytesIO(mail.attachments[0].content))

    no_recipients = await client.post(
        "/api/v1/reporting/schedules/",
        json={"name": "x", "template_id": template["id"], "project_ids": [project.id]},
        headers=headers,
    )
    assert no_recipients.status_code == 422

    row = await db_session.get(ReportSchedule, schedule["id"])
    assert row is not None
    await db_session.refresh(row)
    due_at = row.next_run_at
    assert due_at is not None
    assert await schedules.run_due(db_session, due_at - timedelta(minutes=1)) == 0
    assert await schedules.run_due(db_session, due_at + timedelta(minutes=5)) == 1
    assert len(sent) == 2
    await db_session.refresh(row)
    assert row.next_run_at == due_at + timedelta(days=7)

    history = (await client.get(f"/api/v1/reporting/schedules/{schedule['id']}/runs/")).json()
    assert history["total_count"] == 2
    assert [r["trigger"] for r in history["data"]] == ["schedule", "manual"]
    listed = (await client.get("/api/v1/reporting/schedules/")).json()["data"][0]
    assert listed["last_status"] == "success" and listed["template_name"] == template["name"]


# --- pivot ---------------------------------------------------------------------------------------------


async def test_pivot_aggregates_on_the_server(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    project = await _project(db_session, "P-1", A1=(100, 0, 0, 0, 0), A2=(300, 0, 0, 0, 0))
    for i, (status, priority) in enumerate([("todo", "high"), ("todo", "low"), ("done", "high"), ("todo", "high")]):
        db_session.add(Task(project_id=project.id, code=f"T{i}", title=f"T{i}", status=status, priority=priority))
    await db_session.commit()
    headers = await _as(client, db_session, test_user, *EVERYTHING)

    result = (
        await client.post(
            "/api/v1/reporting/pivot",
            json={"dataset": "tasks", "project_id": project.id, "rows": ["status"], "columns": ["priority"]},
            headers=headers,
        )
    ).json()
    assert result["row_keys"] == [["done"], ["todo"]]
    assert result["column_keys"] == [["high"], ["low"]]
    assert result["cells"] == [[[1.0], [None]], [[2.0], [1.0]]]
    assert result["row_totals"] == [[1.0], [3.0]] and result["grand_total"] == [4.0]

    avg = (
        await client.post(
            "/api/v1/reporting/pivot",
            json={"dataset": "cvr_cost_heads", "project_id": project.id, "values": [{"field": "budget", "agg": "avg"}]},
            headers=headers,
        )
    ).json()
    assert avg["grand_total"] == [200.0]

    exported = await client.post(
        "/api/v1/reporting/pivot/export",
        json={"dataset": "tasks", "project_id": project.id, "rows": ["status"], "columns": ["priority"]},
        headers=headers,
    )
    sheet = load_workbook(io.BytesIO(exported.content)).active
    assert [c.value for c in sheet[1]] == ["Status", "high · Rows (count)", "low · Rows (count)", "Total · Rows (count)"]
    assert [c.value for c in sheet[sheet.max_row]] == ["Total", 3, 1, 4]

    bad = await client.post(
        "/api/v1/reporting/pivot", json={"dataset": "tasks", "project_id": project.id, "rows": ["nope"]}, headers=headers
    )
    assert bad.status_code == 422

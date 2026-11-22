# Writing a module

Every business feature is a module: a self-contained backend package plus a frontend folder, discovered at startup and switched on or off without touching the core. The contract is modelled on OpenConstructionERP's (a manifest, a router mounted at `/api/v1/<name>`, a frontend registry), but implemented independently on Fastro and shadcn-admin, so no AGPL code is involved.

## Quick start

```bash
python scripts/new_module.py punch_list --display "Punch List" --depends projects
cd backend && uv run alembic revision --autogenerate -m "punch_list module" && uv run alembic upgrade head
cd ../frontend && pnpm gen:api
```

That gives you a working list-and-add page at `/punch-list`, an API at `/api/v1/punch-list/items/`, two permissions (`punch_list.read`, `punch_list.edit`) and a passing integration test. Grant the permissions to a role, or map an Entra app role to that role, and the page appears in the menu.

The reference modules are `projects` (a plain module, and project visibility for clients) and `cvr` (project-scoped, editable AG Grid, chart, events).

## Backend: `backend/src/modules/<name>/`

```
manifest.py      REQUIRED  manifest = ModuleManifest(...)
router.py                  router = APIRouter(...)  -> mounted at /api/v1/<name with hyphens>
models.py                  SQLAlchemy models (tables named <name>_<entity>)
schemas.py                 Pydantic models; request bodies subclass EncodableText
permissions.py             @register_permissions("<name>") StrEnum of "<name>.<action>"
service.py                 business logic, no FastAPI imports
events.py                  @subscribe("other.entity.verb") handlers, imported at startup
tasks.py                   Taskiq tasks (with a cron schedule if periodic), registered with the worker
__init__.py                optional async on_startup() / on_shutdown()
```

### The manifest

```python
from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="punch_list",            # must equal the folder name
    version="0.1.0",
    display_name="Punch List",
    description="Snags and defects with photo evidence.",
    depends=("projects",),        # loaded first; app refuses to start if missing
    optional_depends=(),          # loaded first when present
    enabled=True,                 # ship it switched off with False
    route_prefix=None,            # default "/punch-list"
    extra_routers={},             # {"/other-prefix": "attribute_in_router_py"}
)
```

The loader (`src/infrastructure/modules/loader.py`) orders modules by dependency and refuses to start on a missing dependency or a cycle. `MODULES_DISABLED=cvr,portal` switches modules off per deployment; anything that depends on a disabled module is switched off too. `GET /api/v1/modules` reports what's running, and the frontend hides menus for modules that are off.

Models are always imported, enabled or not, so Alembic sees every table and switching a module back on needs no migration.

### Rules the test suite enforces

- A request body subclasses `EncodableText` (refuses text a column can't hold).
- A `GET` path ending in `/` is a listing and must paginate (`PageDep`, `ItemsPerPageDep`, `PaginatedListResponse`).
- Permission names are `<resource>.<action>`, lower snake case.

### Access control

- **Permissions** come from roles (`roles`, `role_permissions`, `user_roles`). Gate a route with `dependencies=[require_permissions("punch_list.edit")]`. Superusers hold every permission.
- **Project data**: call `readable_project(db, project_id, user_id, held)` from `modules.projects.service` before serving anything that belongs to a project. Staff with `projects.read` see every project; external users see the projects whose `client_team_id` is a team they're in.
- **Team-scoped rules**: `TeamService.role_in(db, team_id, user_id)` gives `member`, `lead` or `manager`.

### Events

```python
from ...infrastructure.modules import publish, subscribe

await publish("punch_list.item.closed", {"project_id": 3, "item_id": 9})

@subscribe("projects.project.deleted")
async def tidy_up(event: str, payload: dict) -> None: ...
```

Handlers run in-process after the publisher's work; one that fails is logged and doesn't affect the others. Anything that must survive a restart should enqueue a Taskiq task from the handler.

## Frontend: `frontend/src/modules/<id>/`

```ts
// manifest.ts
export const manifest: ModuleManifest = {
  id: 'punch_list',                       // the backend module name, so the menu follows MODULES_DISABLED
  name: 'Punch List',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    { path: '/punch-list', component: lazy(() => import('./punch-list-page')), permission: 'punch_list.read' },
    { path: '/punch-list/:itemId', component: lazy(() => import('./item-page')), permission: 'punch_list.read' },
  ],
  navItems: [
    { labelKey: 'nav.punch_list', to: '/punch-list', icon: ClipboardCheck, group: 'quality', permission: 'punch_list.read' },
  ],
  messages: { en: { 'nav.punch_list': 'Punch List', 'nav.group.quality': 'Quality' } },
}
```

Add it to `src/modules/_registry.ts` (the scaffold does this). Nothing else changes: routes resolve through the `_authenticated/$` catch-all, and the sidebar and ⌘K menu are built from `navItems`.

- `permission` hides a page or menu item from accounts without it. `accountTypes: ['staff']` hides it from external portal users. The backend still enforces both.
- `useModuleParams()` gives a route's `:params`.
- Render pages inside `<Page title=… actions=… projectScoped>`; `projectScoped` shows the project selector, and `useCurrentProject()` returns the selected project.
- Dense tables use `<DataGrid>` (AG Grid Community, themed for light and dark); format money with `money(currency)` from `@/lib/format`.
- Call the API with `api.GET('/api/v1/...')` from `@/api/client`; paths and bodies are typed from the backend's OpenAPI document. Run `pnpm gen:api` after changing the backend.
- User-visible text goes through `t('key')`, with the English in `messages.en`.

## Platform services every module uses

Reach for these instead of building your own. Reference modules: `tasks` and `contacts` (backend and data model), `cvr` and `team` (frontend grids), `files` (uploads).

### Backend

| Need | Use |
|---|---|
| Project visibility | `await readable_project(db, project_id, user["id"], held)` from `modules.projects.service`. Call it on every project-scoped route; it answers 404 for projects the caller can't see. |
| Reference numbers | `await next_reference(db, "RFI", project_id)` → `RFI-001` (`infrastructure.records`). Commit with the record. |
| Status workflows | Declare `FLOW = {"draft": {"open"}, ...}`; `assert_transition(FLOW, current, target)` (422 if not allowed), then `await record_transition(db, "rfi", id, old, new, user_id, note)`. Expose `GET /{id}/history` with `history_of(db, "rfi", id)`. |
| Notify people | `await notify(db, user_ids, Category.ASSIGNMENT, title, body=..., link="/rfi?project=1&id=4", entity=("rfi", 4), actor_id=me)` from `modules.notifications.service`. Joins your transaction; emails users whose preferences ask for it. |
| Tasks from your module | `await create_task(db, project_id=..., title=..., created_by_id=..., entity=("meeting", 7), assignee_id=..., due_date=...)` from `modules.tasks.service`. |
| Contacts | Store `contact_id` ints; display with `await contact_names(db, ids)`; email with `contact_emails(db, ids)` (`modules.contacts.service`). |
| Attachments | Nothing to build: the frontend's `<Attachments>` uploads to `files` with your `entity_type`/`entity_id`. To list them server-side, query `StoredFile` by entity. |
| Comments | Nothing to build: `<Comments>` stores them against your `entity_type`/`entity_id`. |
| Email | `await deliver(Mail(to=[...], subject=..., text=..., attachments=[Attachment(name, bytes, type)]))` from `infrastructure.mail`. Queued on the worker; pluggable backends. |
| PDF | `Document(...)` + `render_pdf(doc)` from `infrastructure.pdf` (fields, headings, ruled tables, page numbers). Return with `Response(pdf, media_type="application/pdf", headers={"Content-Disposition": ...})`. |
| Excel / CSV | `read_table(bytes, filename)` and `write_table(columns, rows, "xlsx"|"csv")` from `infrastructure.tabular`. |
| Events | `await publish("rfi.rfi.answered", {...})` / `@subscribe("tasks.*")` from `infrastructure.modules`. |
| Scheduled work | A `@default_broker.task(task_name="mod:job", schedule=[{"cron": "..."}])` in your `tasks.py`. |

Permissions: name actions `read`, `create`, `update`, `delete`, plus domain verbs from this list where they fit: `respond`, `submit`, `review`, `transition`, `import`, `export`, `upload`, `assign`. The per-user access grid treats `read`/`export` as View, those verbs as Edit, and anything else (`approve`, `delete`, `manage`) as Full only.

Module manifests: set `depends` on every module you import from. Modules switched off at runtime answer 404 automatically; don't add your own check.

### Frontend

| Need | Use |
|---|---|
| Page shell | `<Page title description actions projectScoped>`; `useCurrentProject()` for the selected project. |
| Dense tables | `<DataGrid>` (AG Grid, themed). `money(currency)` from `@/lib/format`. Editable cells → PATCH one field. |
| Record detail | `<RecordSheet title badges record={{ projectId, entityType, entityId }} tabs={{ History: ... }}>` gives Details + your tabs + Comments + Files. |
| Status / priority pills | `<StatusBadge status="under_review" />` colours by meaning. |
| API | `api.GET('/api/v1/...')` + `unwrap()` from `@/api/client`, typed after `pnpm gen:api`. Multipart: `fetch` with `csrfHeaders()`. |
| Permissions in UI | `can(useSession(), 'rfi.respond')`. |
| Charts | Recharts. |
| Menu | `navItems` with a `group` from the shell's list (`project_management`, `quality_safety`, `documents`, `procurement`, `planning`, `cost_control`, `commercial`, `assets`, `reporting`, `estimating`), `advancedOnly` for specialist screens. |

## Reporting and export providers

A module exposes its records to the export hub (`/data`), the report builder and the pivot explorer (`/reporting`) by registering **datasets**, **KPIs** and **importers** in a `reporting.py` in its package. Nothing else is needed: the registry (`src/infrastructure/reporting`) imports `reporting.py` of every module enabled at startup, and filters by the runtime switches (global and per project) and by permission on every request. A module switched off disappears from every list, export, dashboard and report section; a report section that names it prints "Not available" instead of failing.

```python
# src/modules/rfi/reporting.py
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .models import Rfi


async def rfi_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Rfi).where(Rfi.project_id == project_id))).scalars()
    return [{"project_id": r.project_id, "code": r.code, "subject": r.subject, "status": r.status,
             "raised": r.created_at.date(), "days_open": r.days_open, "rfis": 1} for r in rows]


register_dataset(Dataset(
    name="rfis", module="rfi", title="RFIs", permission="rfi.read",
    columns=[Column("code", "No."), Column("subject", "Subject"), Column("status", "Status"),
             Column("raised", "Raised", "date"), Column("days_open", "Days open", "number"), Column("rfis", "Count", "number")],
    rows=rfi_rows,
))


async def open_rfis(db: AsyncSession, project_id: int) -> int:
    return await db.scalar(select(func.count()).where(Rfi.project_id == project_id, Rfi.status != "closed")) or 0


register_kpi(Kpi("rfi.open", "rfi", "Open RFIs", open_rfis, unit="count", good="down", thresholds=(5, 20),
                 permission="rfi.read", portfolio=True))
```

**Dataset** `Dataset(name, module, title, columns, rows, project_scoped=True, permission="", description="")`

- `name` is unique across the app (snake_case); `module` is your module's name, so the switches apply.
- `columns`: `Column(key, label, type, aggregatable=None)` with `type` one of `text`, `number`, `money`, `date`, `bool`. `aggregatable` defaults to true for `number` and `money` (sum/avg make sense); set it false for ids and percentages. A constant `1` column (`"rfis": 1`) makes counting easy in charts.
- `rows(db, project_id, filters)` returns a list of dicts keyed by column key, with plain values (`str`, numbers, `Decimal`, `date`, `datetime`, `bool`, lists). `project_id` is always set for a `project_scoped` dataset; for a cross-project one (`project_scoped=False`) it is the project the caller picked, or `None`. `filters` are the caller's filters; you may use them to narrow your query, but the hub applies them to your rows afterwards anyway.
- Visibility: the route checks `readable_project` for the project asked for. A row that carries a `project_id` key is also dropped when the caller can't read that project, so cross-project datasets just include `project_id`.
- `permission`: what the caller must hold (comma-separate several), usually `<module>.read`.

**KPI** `Kpi(key, module, label, fn, unit="", good="up"|"down", thresholds=None, permission="", description="", portfolio=False)`

- `fn(db, project_id)` returns a number or `None` (shown as "–").
- `unit`: `money`, `%`, `count`, or a free label.
- `thresholds=(target, limit)`: with `good="up"` a value at or above `target` is green, below `limit` red, otherwise amber; with `good="down"` at or below `target` is green, above `limit` red. Without thresholds the KPI is neutral (grey).
- `portfolio=True` also shows it as a column of the portfolio table (computed per page of projects, so keep it to one or two cheap queries).

**Importer** `Importer(name, module, title, fields, apply, project_scoped=True, permission="", description="", options={})`

- `fields`: `ImportField(key, label, required=False, aliases=(...))`. The wizard guesses each field's column from its key, label and aliases (case and punctuation ignored); people can change the mapping.
- `apply(db, job) -> ImportReport`. `job` is an `ImportJob` with `project_id`, `rows` (already mapped to your field keys), `dry_run`, `user_id`, `options`, and the raw `columns`, `mapping` and `raw_rows` for an importer that hands over to an existing one (see `contacts/reporting.py`).
- Validate every row; report problems in `ImportReport.errors` as `"Row 7: ..."` (spreadsheet line numbers start at 2) and skip that row; put non-blocking notes in `warnings`. Count `created`, `updated`, `unchanged`, `skipped`. On a dry run write nothing; otherwise commit once at the end. The budget importer (`cvr/reporting.py`) is the reference.
- `options={"on_duplicate": ["skip", "create"]}`: choices the wizard offers; the first is the default.
- `permission`: what the importer needs on top of `data_exchange.import` (e.g. `rfi.create`).

Shipped providers: `projects` (projects), `cvr` (cost heads, cashflow; budget, cost, value, margin %, forecast margin %, cost/value %, budget variance %; the budget importer), `tasks` (tasks; open, overdue, completion %; the task importer), `contacts` (contacts, companies; the contacts importer), `files` (documents; document count), `team` (teams, team members), `people` (users).

What the platform does with them:

| Endpoint | |
|---|---|
| `GET /api/v1/data/datasets/`, `GET /api/v1/reporting/datasets/` | Datasets the caller may use (optionally for a project). |
| `GET /api/v1/data/export/{dataset}?project_id=&format=xlsx\|csv\|pdf&columns=a,b&filters={json}` | The file. Excel carries number and date formats and an "About" sheet (dataset, project, who, when, filters); CSV puts that in `#` lines above the header (`metadata=false` leaves it out); PDF prints landscape above six columns. |
| `GET /api/v1/data/importers/`, `POST /api/v1/data/import/{importer}/preview`, `POST /api/v1/data/import/{importer}` | The import wizard: upload, guess the mapping, dry run, apply. |
| `GET /api/v1/reporting/kpi/{project_id}` | Every KPI for the project, with `status` good/warning/bad/neutral. |
| `GET /api/v1/reporting/portfolio/`, `/portfolio/summary` | Projects with CVR figures and portfolio KPIs; filters `region`, `status`, `budget=over\|on\|none`, `search`. |
| `POST /api/v1/reporting/pivot`, `/pivot/export` | Server-side pivot (rows × columns × sum/avg/count/min/max) with totals; Excel/CSV export. |
| `/api/v1/reporting/templates/`, `POST /api/v1/reporting/generate` | Report templates (sections: KPI cards, table, chart, pivot, text) rendered as PDF or Excel. |
| `/api/v1/reporting/schedules/` | Scheduled reports: daily/weekly/monthly at a local time (Australia/Perth by default), emailed with the file attached by the `reporting:run_due` task every 15 minutes, with run history and "send now". A schedule runs with its owner's (last editor's) access. |

Filters are JSON: `{"status": "open"}` equals, `{"status": ["open", "review"]}` any of, `{"due": {"gte": "2026-01-01", "lt": "2026-02-01"}}` with `eq`, `ne`, `in`, `gt`, `gte`, `lt`, `lte`, `contains`, `empty`. Text compares without case; `number`/`money` and `date` columns compare as numbers and dates.

The pivot is computed on the server, for up to 50,000 source rows, 5,000 row groups and 200 column groups; totals are aggregated from the raw values (an average of averages is never shown).

## Saved register views

Any register grid can offer saved views (columns, order, widths, hidden/pinned, sort, filters, quick search; personal, shared with the project or with teams; a default per register) with two lines. The backend module is `saved_views` (`/api/v1/saved-views/`); nothing to add server-side.

```tsx
import { useSavedViews } from '@/hooks/use-saved-views'
import { SavedViewsMenu } from '@/components/saved-views'

const views = useSavedViews<Ncr>('ncr.register', projectId)   // register key: '<module>.<register>'
<SavedViewsMenu views={views} />                               // in the toolbar
<DataGrid<Ncr> onGridReady={views.onGridReady} ... />          // the grid opens with the caller's default view
```

- Give every column a stable id (`field`, or `colId` for computed columns); a view naming a column the grid no longer has skips it.
- Who sees what: `private` (owner), `project` (everyone who can read the project), `team` (owner, members of the named teams, managers). Permissions: `saved_views.read` (use), `.create` (own views), `.share` (share), `.manage` (edit any shared view, set the project default).
- `group_by` is stored but AG Grid Community has no row grouping; a register that groups rows itself reads `views.current?.config.group_by`.
- Wired in: `rfi.register`, `issues.punch`, `issues.ncr`, `asset_tree.items`.

## Numbering schemes

`next_reference(db, "RFI", project_id)` keeps working. A module opts in to per-project numbering schemes by calling `next_number` instead (`infrastructure.records`):

```python
from ...infrastructure.records import NumberingError, link_allocation, next_number

code = await next_number(db, "rfi", project_id, fallback_prefix="RFI",
                         values={"discipline": body.discipline}, user_id=user["id"])   # 422-able NumberingError
db.add(rfi); await db.flush()
await link_allocation(db, project_id, "rfi", code, ("rfi", rfi.id))   # optional: the register shows the record
```

With no active scheme for `(project, record_kind)` it answers what `next_reference(fallback_prefix)` would. A scheme (`/numbering`, permission `numbering.manage`) is a pattern of whitelisted tokens: `{project}`, `{year}`, exactly one `{seq:N}` (zero-padded to at least N), and code tokens `{discipline}`, `{type}`, `{doc_type}`, `{area}`, `{originator}`, `{system}`, `{unit}`, `{level}`, `{package}`, `{role}` whose values the caller passes and the scheme's code list checks (an empty list accepts any 1-20 letters/digits). The counter is one per scheme, or one per combination of the code tokens in `counter_scope` (which must appear in the pattern). Counters are row-locked in the caller's transaction (commit with the record), every number is recorded in `numbering_allocations` (unique per project and kind) and never reused, voided ones included; a clash after a scheme edit skips to the next free value. Revision and status are never part of a number: keep them in their own columns. `POST /api/v1/numbering/preview` shows the next number without allocating it. Shipped user: `mdr` (kind `mdr`, fallback `MDR`).

## Audit ledger

`audit_ledger` is one append-only, hash-chained sequence: each entry stores `prev_hash` and `hash = sha256("qcm-audit-ledger\n" + canonical JSON of {v, seq, created_at, actor_id, action, entity_type, entity_id, project_id, summary, before, after, prev_hash})`. Record high-value actions in the same transaction as the change:

```python
from ...infrastructure.audit_ledger import changes, record_audit

before, after = changes({"status": old}, {"status": new})          # only what changed
await record_audit(db, "rfi.rfi.closed", "rfi", rfi.id, actor_id=user["id"], project_id=rfi.project_id,
                   summary=f"{rfi.code} closed", before=before, after=after)
await db.commit()
```

Keep `before`/`after` small (a summary, not the record). The ORM refuses to update or delete entries; the migration creating the table should also run `APPEND_ONLY_SQL` (triggers refusing UPDATE/DELETE/TRUNCATE). `GET /api/v1/audit/verify` walks the chain and reports the first broken link; `/api/v1/audit/entries/` and `/export` are the explorer (`audit.read`, `audit.export`). Wired today: module switches, per-project module overrides, access levels, asset tree move/split/merge/retire, numbering scheme changes and voids, MDR dossier creation and revision issue/sign/accept/reject.

## MDR providers and gate checks

The dossier builder (`mdr`) collects records through providers and readiness facts through checks, registered from an `mdr.py` in a module's package (imported for every enabled module); modules never import `mdr`, only `infrastructure.dossier`.

```python
from ...infrastructure.dossier import Finding, MdrCheck, MdrContext, MdrRecord, register_mdr_check, register_mdr_provider

async def nde_reports(db, ctx: MdrContext) -> list[MdrRecord]:
    rows = ...   # ctx.project_id; ctx.node_ids = scope nodes with subtrees and lineage, None = whole project
    return [MdrRecord(reference=r.code, title=r.title, status=r.result, date=r.tested_on.isoformat(),
                      notes="RT", pdf=render_pdf(doc), file_ids=[r.report_file_id])
            for r in rows if ctx.in_scope(r.asset_node_id)]

register_mdr_provider("nde_reports", nde_reports, module="welding")
register_mdr_check(MdrCheck("welds_accepted", "Every weld in scope is accepted", "welding", open_welds))  # -> list[Finding]
```

Sections: `itp`, `inspections`, `ncr_register`, `material_certs`, `nde_reports`, `calibration_certs`, `as_built`, `custom` (`index` is generated). In `material_certs` and `calibration_certs` the `file_ids` are certificates: each stored file is attached once per dossier, identified by its SHA-256, and the appendix index lists every record that refers to it. Elsewhere PDFs in `file_ids` are merged after the record and other files are listed. A section with no enabled provider prints "Not available". A check whose module is off, that raises `CheckUnavailable`, or that crashes reports `not_available` and never blocks. Guarded hooks in `mdr/gate.py` call `ncr.service.blocking_issues`, `inspections.eligibility.unsigned_hold_points` and `calibration.service.uncalibrated_equipment` (all live: issues in `ncr`, Hold points in `inspections`) as `await fn(db, project_id, node_ids)` (returning `Finding`s, dicts or strings) when those modules exist; adjust `HOOKS` if they land elsewhere. Shipped providers: `files` (tagged `as-built`, `mtr`, `nde`, `calibration`), `cde` (published containers with suitability CR), `inspections` (completed inspection reports + check for open inspections), `ncr` (client-visible issues register; blocking issues come from the `ncr.service.blocking_issues` hook), `mdr` (files uploaded to the dossier).

## Quality gates other modules call

| Need | Use |
|---|---|
| A reading taken with an instrument | `await assert_calibrated(db, equipment_ids, reading_date, project_id=...)` from `modules.calibration.service` (guard with `is_enabled(db, "calibration", project_id)` and list `calibration` in `optional_depends`). Raises 422 naming each overdue, quarantined or uncalibrated piece. Pickers use `GET /api/v1/calibration/available`. |
| An MDR's material certificate appendix | `await certificates_for(db, node_ids, verified_only=False)` from `modules.materials.service`; expand a node with `asset_tree.service.subtree_ids` first. One row per certificate with heat, grade, `file_id` and the `node_ids` it was issued to. |
| Client-supplied material late for work | `await readiness_warnings(db, project_id, node_ids)` from `modules.materials.service`: warnings, never blocks. |

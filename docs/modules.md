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

# QC Manager

A modular business platform: a FastAPI backend and a React frontend where every feature is a module you can add, switch off or replace, with Microsoft Entra ID sign-in for staff and invitation-based email/password accounts for clients and partners.

| Layer | Built on |
|---|---|
| Backend | [Fastro](https://github.com/benavlabs/FastAPI-boilerplate) (MIT): async FastAPI, SQLAlchemy 2, PostgreSQL, Redis, Taskiq workers, server-side sessions, RBAC |
| Frontend | [shadcn-admin](https://github.com/satnaing/shadcn-admin) (MIT): React 19, TypeScript, Vite, Tailwind, TanStack Router and Query |
| Dense tables | AG Grid Community |
| Charts | Recharts |
| API types | `openapi-typescript` + `openapi-fetch`, generated from the backend |
| i18n | i18next, strings declared per module |

## Run it

To host it on a Coolify server, see [docs/deploy-coolify.md](docs/deploy-coolify.md) (Docker Compose build pack, `docker-compose.coolify.yml`).

With Docker:

```bash
# create backend/.env from docs/configuration.md first
docker compose up --build
docker compose exec -w /app api python scripts/create_first_superuser.py
docker compose exec -w /app api python -m scripts.seed_demo     # optional demo project
```

Without Docker (Postgres and Redis running locally):

```bash
uv sync --frozen --all-packages --all-extras
cd backend
uv run alembic upgrade head
uv run python scripts/create_first_superuser.py
uv run python -m scripts.seed_demo
uv run fastapi dev src/interfaces/main.py                                   # API on :8000
uv run taskiq worker src.infrastructure.taskiq.worker:default_broker       # background jobs
uv run taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler      # hourly Entra sync

cd ../frontend && pnpm install && pnpm dev                                 # app on :5173, /api proxied
```

Sign in at http://localhost:5173 with the `ADMIN_*` credentials, or with Microsoft once [Entra is set up](docs/entra-setup.md).


## Screenshots

Demo project P-24017 (LNG Train 3 Insulation). Full-size images are in [docs/screenshots](docs/screenshots).

| | |
|---|---|
| ![Asset hierarchy: Site / Area / Asset / RSW with work anchors](docs/screenshots/asset-tree.png)<br>Asset hierarchy: Site / Area / Asset / RSW with work anchors | ![Spreadsheet import with column mapping](docs/screenshots/asset-import.png)<br>Spreadsheet import with column mapping |
| ![Punch list, Cat A/B/C](docs/screenshots/issues-punch.png)<br>Punch list, Cat A/B/C | ![NCR workflow: containment to close](docs/screenshots/issues-ncr.png)<br>NCR workflow: containment to close |
| ![ITP with Hold/Witness points](docs/screenshots/itp.png)<br>ITP with Hold/Witness points | ![Inspection request with witness parties](docs/screenshots/inspection-requests.png)<br>Inspection request with witness parties |
| ![Inspection register](docs/screenshots/inspections.png)<br>Inspection register | ![Welding and NDE](docs/screenshots/welding.png)<br>Welding and NDE |
| ![Heats, mill certificates and holds](docs/screenshots/materials.png)<br>Heats, mill certificates and holds | ![Calibration register](docs/screenshots/calibration.png)<br>Calibration register |
| ![Scaffolds with tags](docs/screenshots/scaffolds.png)<br>Scaffolds with tags | ![Coating hold points, dew point, DFT](docs/screenshots/coatings.png)<br>Coating hold points, dew point, DFT |
| ![Planner look-ahead board](docs/screenshots/planner-board.png)<br>Planner look-ahead board | ![Daily workface log](docs/screenshots/workface-log.png)<br>Daily workface log |
| ![Shift handover](docs/screenshots/handover.png)<br>Shift handover | ![P6 import preview](docs/screenshots/p6-import.png)<br>P6 import preview |
| ![Gantt with critical path](docs/screenshots/schedule-gantt.png)<br>Gantt with critical path | ![Earned value (hours)](docs/screenshots/evm.png)<br>Earned value (hours) |
| ![Change of scope cards](docs/screenshots/change-of-scope.png)<br>Change of scope cards | ![Progress claim](docs/screenshots/claims.png)<br>Progress claim |
| ![MDR dossier, compiled draft](docs/screenshots/mdr.png)<br>MDR dossier, compiled draft | ![Numbering schemes](docs/screenshots/numbering.png)<br>Numbering schemes |
| ![Audit ledger](docs/screenshots/audit.png)<br>Audit ledger | ![KPI dashboard](docs/screenshots/dashboard.png)<br>KPI dashboard |
| ![RFIs](docs/screenshots/rfi.png)<br>RFIs | ![Task board](docs/screenshots/tasks-board.png)<br>Task board |
| ![Contacts](docs/screenshots/contacts.png)<br>Contacts | ![Client plan review](docs/screenshots/plan-reviews.png)<br>Client plan review |
| ![Project access and invites](docs/screenshots/lobby.png)<br>Project access and invites | ![Module switches](docs/screenshots/modules-settings.png)<br>Module switches |
| ![Users](docs/screenshots/users.png)<br>Users | ![User detail](docs/screenshots/users-detail.png)<br>User detail |
| ![App-managed team](docs/screenshots/teams-manual.png)<br>App-managed team | ![Entra-linked team](docs/screenshots/teams-entra.png)<br>Entra-linked team |
| ![Profile](docs/screenshots/settings-profile.png)<br>Profile | ![Security](docs/screenshots/settings-security.png)<br>Security |

## Sign-in

| Who | How | Accounts come from |
|---|---|---|
| Staff | **Sign in with Microsoft** (Entra ID, single tenant, MFA and conditional access apply) | Created at first sign-in; roles from Entra app roles, teams from Entra groups |
| Clients and partners | Email and password | Invited by staff (`portal.invite`); the email link sets the first password |
| Break-glass admin | Password | `scripts/create_first_superuser.py` |

Both paths end in the same server-side session cookie with CSRF protection, login lockout and session limits from Fastro. An account linked to Entra can't sign in with a password, so disabling someone in Entra always locks them out. Self-service signup is off (`LOCAL_SIGNUP_ENABLED=false`).

## Access model

- **Permissions** (`projects.read`, `cvr.edit`, …) are declared by each module and carried by **roles**. Entra app roles map onto roles (`/api/v1/entra/role-mappings`); unmapped roles are assigned by hand.
- **Teams** group people. A team linked to an Entra group takes its members from it; other teams, such as a client's team of portal users, are managed in the app. Each membership has a role: member, lead or manager.
- **Projects** are visible to staff holding `projects.read`, and to the members of the project's client team. That is how the client portal is scoped.

## Modules

Each module is a backend package with a `manifest.py` plus a frontend folder with a `manifest.ts`. The loader mounts the routes, registers permissions, tasks and event handlers, and builds the menu. The pattern follows OpenConstructionERP's module contract, written independently, so no AGPL code is used.

```bash
python scripts/new_module.py punch_list --display "Punch List" --depends projects
```

Read **[docs/modules.md](docs/modules.md)** before writing one. Shipped modules:

Platform modules (always on): `projects`, `team`, `people`, `platform` (module switches, per-user access matrix, roles, onboarding), `portal` (external users, client plan review), `files`, `comments`, `notifications`, `audit` (hash-chained audit ledger), `saved_views`, `numbering`, `lobby` (request or be invited to a project).

| Area | Modules |
|---|---|
| Asset breakdown | `asset_tree` (Site → Area → Asset → RSW → Item, work anchors, packs, terminology, spreadsheet import with mapping profiles, scan tags), `assets` (asset register, COBie) |
| Quality | `inspections` (checklists and ITPs with Hold/Witness points, inspection requests, sign-off and client co-sign, competencies), `ncr` (punch list Cat A/B/C and NCR workflow, client visibility), `welding` (WPS/PQR, welder qualifications, NDE sampling and repairs, bolted joints), `materials` (heats, mill certs, PMI, holds, traceability), `calibration` (equipment, certificates, calibration gate), `coatings` (hold points, dew point, DFT), `submittals`, `markups` |
| Turnover | `mdr` (dossier builder: scope, section providers, readiness gate, compiled and signed revisions), `cde` (ISO 19650), `transmittals`, `correspondence` |
| Field and planning | `planner` (work plans, work packs, crews, readiness), `workface_log` (daily log, hours by work anchor, sign-off), `handover` (shift handover), `scaffolds` (requests, tags, inspections, hire), `safety`, `tasks` (Kanban), `meetings`, `rfi`, `contacts` |
| Schedule and cost | `schedule` (Gantt, CPM, Monte Carlo, P6 import with RSW matching, verified progress, export back to P6), `evm` (hours-based earned value, pulls actual hours from signed workface logs), `cvr`, `boq`, `change_orders`, `change_of_scope`, `claims` (progress claims from verified completion), `procurement`, `risk` |
| Reporting | `reporting` (KPIs, pivots, charts, scheduled reports), `data_exchange` (import/export hub) |

The site-execution modules (asset hierarchy, ITP, issues, welding, materials, calibration, MDR, planner, workface log, handover, P6 matching, claims, scaffolds, coatings, lobby) follow the KERP specification, adapted to this codebase: integer ids, project visibility instead of row-level security, permissions instead of personas, plain Python checks instead of a rule engine. Offline/PWA capture, the Android app, CEL rules and AI features are not built.

## Repository layout

```
backend/                  Fastro: src/infrastructure (platform), src/modules (features), migrations, tests
  src/infrastructure/modules/   module loader, manifest contract, event bus
  src/infrastructure/auth/entra.py   Entra ID provider (ID token verified against the tenant's keys)
frontend/                 shadcn-admin shell
  src/modules/            frontend modules and _registry.ts
  src/api/                generated OpenAPI types and the typed client
cli/                      Fastro's `bp` CLI (compose scaffolding, env audit)
scripts/new_module.py     full-stack module scaffold
docs/                     modules, Entra setup, configuration
```

## Tests

```bash
cd backend
uv run pytest tests/unit -n auto
uv run pytest tests/integration        # Docker for testcontainers, or TEST_POSTGRES_URL=postgresql+asyncpg://...
cd ../frontend
pnpm lint && pnpm exec tsc -b && pnpm test     # PLAYWRIGHT_CHROMIUM=/path/to/chromium to use a local browser
```

## Licences

Backend from Fastro (MIT, `backend/LICENSE.fastro.md`); frontend from shadcn-admin (MIT, `frontend/LICENSE`). AG Grid Community is MIT. No OpenConstructionERP (AGPL-3.0) code is included.

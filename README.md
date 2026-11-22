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

| Module | What it does |
|---|---|
| `team` | Teams, memberships, Entra group and app-role sync |
| `portal` | Invitations and management of external users |
| `projects` | Projects, and which client team may see each |
| `cvr` | Cost-Value Reconciliation: editable cost-head grid, margins, totals, CSV export, cashflow chart |

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

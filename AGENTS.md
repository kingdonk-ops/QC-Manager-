# Working notes

Module conventions are in `docs/modules.md`; follow them for any new backend package or frontend module folder.

## Commands

Run from the repository root.

Backend (uv, CPython 3.12):

- Unit tests (no database): `uv --directory backend run --no-sync pytest tests/unit -q`
- Integration tests need PostgreSQL and Redis running and the test database variable set; run them without parallel workers, for example `uv --directory backend run --no-sync pytest tests/integration/quality_safety -q`
- Lint and format check: `uv --directory backend run --no-sync ruff check src tests migrations` and `... ruff format --check` (line length 128, isort ordering)
- Types: `uv --directory backend run --no-sync mypy src/modules/<module>`
- Migrations: `uv --directory backend run --no-sync alembic heads` must print exactly one head

Frontend (pnpm):

- Regenerate the typed API client after any backend route or schema change: `pnpm --dir frontend run gen:api` (never edit `src/api/openapi.json` or `src/api/schema.d.ts` by hand)
- Type-check: `frontend/node_modules/.bin/tsc -b frontend`
- Lint: `pnpm --dir frontend run lint`
- Tests (vitest browser mode, headless Chromium): `pnpm --dir frontend run test -- src/modules/inspections src/modules/as_built`

## Gotchas

- Code files stay under 500 lines and test files under 800; split by extraction before a file grows past the limit.
- Only `ag-grid-community`; never `ag-grid-enterprise`.
- Pure rule files (`gate_rules.py`, `rules.py`, `tolerance.py`) must not import the web framework or the database layer.
- Anything that changes a pending gate or an as-built record (edit, release, waive, void, survey, verify, sign, delete) loads the row under a row lock in its router, so two concurrent decisions run one after the other. Keep that when adding a new action.
- Automatic non-conformance reports are created without committing, inside the caller's unit of work; the caller commits and only then publishes the raised event. If the report cannot be created the whole action rolls back.
- Gate lookups for an inspection match a gate attached to the record or naming it in its linked-inspection field; use `inspection_gate_match` instead of filtering on one column.
- Criterion limits are stored as text and judged as exact decimals; a criterion's rule, unit, nominal and limits freeze once any record is judged against it.
- Component tests find controls by message keys, which holds only while the test setup leaves the translation function returning keys.
- The layout test in `templates-layout.test.tsx` needs a 1440 pixel viewport and the app stylesheet.

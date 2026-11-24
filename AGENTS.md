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
- ITP signatories: a line's required signatory count (1 to 10, default 1, set on the template activity and copied to the line) counts distinct people, never signatures. Only valid signatures over the record's current content count; provisional, void and rejected ones and the hold release do not. The approver counts at approval time. Signing as additional signatory twice in the same role is a conflict (row lock, then the partial unique index as backstop); the same person in another role is accepted but still counts once. The client shows the server's counts and never counts signers.
- Dossier override: it is a separate action (`mdr.override`) that annotates pending quality gates and never releases, waives or closes them; an annotated gate stays pending and blocking. Only gates and findings listed on the override are covered, so a hold created later still refuses issue. Covered checks report the status `overridden`, which does not fail the gate; the frontend must render it as its own state, not pass or fail. For can-proceed, overridden-pending gates are listed apart and stop blocking only for a dossier attachment. The documentation report an override raises is on the library `documentation` category and is raised with the register-only MDR effect and no completion effect, so it stays open and visible but never blocks any dossier; it is not part of the override's snapshot. Automatic reports can set both effects through `raise_automatic`.
- Temporary works: deleting is draft-only and soft. A record with no history beyond creation goes to the recycle bin (purged by the daily job after the project retention, 1 to 60 days, default 30); anything else goes to the hidden Deleted folder and is never purged. Every trash route needs `temporary_works.restore`. A deleted item's reference and a deleted permit's number stay reserved until the purge removes the row.
- Temporary works: any action on an item or permit takes a row lock first (`service.lock_item`, `permits.lock_permit`, or a locked select where the row may have been purged) and rolls back before raising. Restoring a permit also locks its item, because deleting an item counts live permits under that lock.
- Temporary works: gate, breach, overdue and percentage figures are computed at read time for an as-of day (default the Australia/Perth day) and are never stored. The scaffolds module is reached only through `scaffolds/breach.py`, which never commits; the red-tag write-back is switched by `RED_TAG_WRITE_BACK`.
- Frontend lint forbids reading the clock during render: take `Date.now()` in a lazy `useState` initialiser or pass the time in.

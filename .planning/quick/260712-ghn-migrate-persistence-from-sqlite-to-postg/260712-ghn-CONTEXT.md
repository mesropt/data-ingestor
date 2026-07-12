# Quick Task 260712-ghn: Migrate persistence from SQLite to PostgreSQL - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Task Boundary

Replace the SQLite persistence layer with PostgreSQL. Six tables (`users`, `profiles`,
`field_set_templates`, `schema`, `canonical_field`, `alias`) move from raw `sqlite3`
to SQLAlchemy models with Alembic migrations, backed by a Postgres container.

In scope: the four `sqlite_*.py` store implementations, their DI wiring, the test
fixtures that construct them, Docker Compose, Alembic, README/.env.example.

Out of scope: the domain layer and the store *interfaces* (they contain zero SQL and
must not change), the mapper, the parser, the frontend.
</domain>

<decisions>
## Implementation Decisions

All four were chosen explicitly by the user via AskUserQuestion on 2026-07-12.
They are LOCKED — the planner must not revisit them.

### D-1: Where Postgres runs
- **Docker Compose**, `postgres:17`, named volume, healthcheck.
- Not a local apt install. Not a cloud/hosted instance.

### D-2: Replace or coexist
- **Postgres only. SQLite is deleted.** No dual implementation, no per-env switch.
- The user was told the cost and accepted it explicitly: every test that touches
  storage will now require a live Postgres, the suite gets slower, and CI needs a
  Postgres service. Do not "helpfully" reintroduce SQLite for tests.

### D-3: Data access layer
- **SQLAlchemy + Alembic** (ORM + versioned migrations). Not raw psycopg.
- The user was told this is a larger refactor of all four stores plus a significant
  new dependency, and accepted it.

### D-4: Existing data
- **Start clean. No data-migration script.**
- The current dev rows (3 users, 1 profile, 6 field-set templates in
  `.assayingest/profiles.db`) are disposable: presets re-seed at startup and the user
  will re-register accounts.

### Claude's Discretion
- Test fixture strategy (e.g. session-scoped database + per-test transaction rollback
  vs. create/drop per test). Must be justified in the plan; correctness and speed both
  matter given the whole suite now depends on it.
- SQLAlchemy style (2.0 declarative / `Mapped[...]`) and sync-vs-async engine. Note the
  codebase is synchronous today (`architecture: single-threaded, synchronous`), so a
  sync engine is the conservative match unless there is a strong reason otherwise.
- Connection/session lifecycle and where the engine is constructed (composition root).
- Whether `.assayingest/profiles.db` and its `_DEFAULT_DB_PATH` wiring are deleted
  outright or left as dead files to remove (prefer: delete).
</decisions>

<specifics>
## Specific Ideas

- Clean Architecture is ALREADY respected and is the key enabler: the store interfaces
  (`auth/store.py`, `learning/store.py`, `learning/field_set_store.py`,
  `learning/schema_store.py`) contain **zero SQL**. All ~33 SQL statements live in
  exactly four files (`auth/sqlite_store.py`, `learning/sqlite_store.py`,
  `learning/sqlite_field_set_store.py`, `learning/sqlite_schema_store.py`).
  Postgres slots in behind the same interfaces; the domain must not change.
- DI runs through `src/assayingest/api/deps.py` (`get_profile_store`,
  `get_field_set_store`, `get_schema_store`) — all call sites must be updated.
- `users` is in scope, so this touches auth. Password hashes and column semantics must
  survive the port unchanged; do not silently swap the hashing scheme.
- Env config lands as `DATABASE_URL`, loaded through the existing
  `src/assayingest/env.py::load_project_env()` composition-root loader
  (`override=False`, added in quick task 260712-ekj).

## Environment gotcha (blocking, verified)

The `docker` CLI only works wrapped in `sg docker -c "..."`. The user IS in the
`docker` group (`docker:x:1001:mesrop_custom_user`) but the running shell session
predates the group addition, so a bare `docker ...` fails with
`permission denied ... /var/run/docker.sock`. Every docker/compose call must be
written e.g. `sg docker -c "docker compose up -d"`. Docker Compose is v5.3.0.
</specifics>

<canonical_refs>
## Canonical References

- `CLAUDE.md` / `.claude/CLAUDE.md` — coding conventions (Clean Architecture,
  single level of abstraction, log-or-raise never both, error messages describe the
  consequence).
- Prior quick task `260712-ekj` — introduced `src/assayingest/env.py` and the
  `.env`-at-composition-root pattern that `DATABASE_URL` should reuse.

## Hard safety rules

- **Secrets:** `.env` is gitignored and holds a real `ANTHROPIC_API_KEY`. Never read,
  echo, print, or commit its contents. Postgres dev credentials go in
  `docker-compose.yml` / `.env.example` as non-secret defaults only.
- **Money:** the 4 live-Claude tests are gated behind `ASSAYINGEST_LIVE_TESTS=1` and
  MUST stay skipped. Never set that variable — an earlier task set it inadvertently and
  made 8 real billed API calls.
- **No weakened assertions** to make tests pass. Baseline: 620 backend passed /
  4 skipped, 141 frontend passed, frontend build typechecks clean.
</canonical_refs>

---
phase: quick-260712-ghn
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: false
requirements: [D-1, D-2, D-3, D-4]
files_modified:
  - docker-compose.yml
  - .env.example
  - pyproject.toml
  - src/assayingest/persistence/base.py
  - src/assayingest/persistence/models.py
  - src/assayingest/persistence/engine.py
  - alembic.ini
  - alembic/env.py
  - src/assayingest/auth/postgres_store.py
  - src/assayingest/learning/postgres_store.py
  - src/assayingest/learning/postgres_field_set_store.py
  - src/assayingest/learning/postgres_schema_store.py
  - src/assayingest/api/deps.py
  - src/assayingest/api/app.py
  - src/assayingest/cli.py
  - tests/conftest.py
  - README.md

must_haves:
  truths:
    - "A curator can sign up, upload a file, and confirm a mapping with all data persisted in PostgreSQL."
    - "Canonical fields and aliases come back in insertion order, every time (no rowid)."
    - "A re-observed alias keeps its first-seen provenance actor and timestamp (ALIAS-03)."
    - "A curator's recorded created_at string round-trips byte-identically (no timezone reformatting)."
    - "If the database schema is missing, the app refuses to start with an actionable error -- it never boots with a blank field-set picker."
    - "If Postgres is down, the test suite fails loudly in seconds -- it never hangs and never silently skips."
  artifacts:
    - docker-compose.yml
    - src/assayingest/persistence/models.py
    - src/assayingest/persistence/engine.py
    - alembic/versions/ (one initial migration creating six tables)
    - src/assayingest/auth/postgres_store.py
    - src/assayingest/learning/postgres_store.py
    - src/assayingest/learning/postgres_field_set_store.py
    - src/assayingest/learning/postgres_schema_store.py
    - tests/conftest.py
  key_links:
    - "api/deps.py -> get_session -> a Session injected into each store constructor (NOT an engine -- see Task 3)."
    - "tests/conftest.py -> AUTOUSE override of get_session itself -> every app-resolved store (even ones a test never overrode) binds to the test transaction, not the dev DB. THE isolation keystone (DR-4)."
    - "api/app.py::_lifespan -> constructs its OWN session + store directly, NEVER via get_field_set_store() -- calling a Depends-typed factory as a plain function binds the Depends object and seeding dies silently (Blocker 1)."
    - "api/app.py::_lifespan -> schema-at-head check RAISES before seed_presets' broad except can swallow it."
    - "cli.py::run(store: ProfileStore | None = None) -> the CLI's test-injection seam; only the --profiles-db FLAG is dropped, not the seam (Blocker 3)."
    - "canonical_field.seq / alias.seq Identity columns -> ORDER BY seq -> deterministic Schema.fields and alias order (pinned by an UPDATE-then-read canary, not a naive insert-order test)."
---

<objective>
Replace the raw-`sqlite3` persistence layer with PostgreSQL 17 (Docker Compose) behind
SQLAlchemy 2.0 ORM + Alembic migrations. Six tables move: `users`, `profiles`,
`field_set_templates`, `canonical_schema` (renamed from `schema`), `canonical_field`,
`alias`.

Purpose: SQLite is a single-file local store; the product needs a real server database.
The store *interfaces* already contain zero SQL, so the domain does not change at all --
this is an infrastructure swap behind an existing seam.

Output: four `postgres_*.py` stores, a `persistence/` package, an Alembic migration, a
Compose service, a transactional test-fixture harness, and four deleted `sqlite_*.py`
files.

Locked decisions (CONTEXT.md -- do NOT revisit): D-1 Docker Compose `postgres:17` ·
D-2 Postgres only, SQLite deleted, no dual impl, no SQLite-for-tests · D-3 SQLAlchemy +
Alembic · D-4 start clean, no data migration.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/quick/260712-ghn-migrate-persistence-from-sqlite-to-postg/260712-ghn-CONTEXT.md
@.planning/quick/260712-ghn-migrate-persistence-from-sqlite-to-postg/260712-ghn-RESEARCH.md
@CLAUDE.md
@src/assayingest/learning/sqlite_schema_store.py
@src/assayingest/api/deps.py
@src/assayingest/api/app.py
@src/assayingest/env.py
</context>

<hard_rules>
Read these before touching anything. Each has already cost this project real money or a
silent regression.

1. **Docker:** every docker call MUST be wrapped: `sg docker -c "docker compose ..."`.
   A bare `docker` fails on the socket (the shell session predates the user's
   docker-group membership). Compose is v5.3.0.
2. **Money:** the 4 live-Claude tests are gated behind an env flag and MUST stay
   skipped. NEVER set that flag. An earlier task did and made 8 real billed API calls.
   The final suite must still report **4 skipped**.
3. **Secrets:** `.env` is gitignored and holds a real `ANTHROPIC_API_KEY`. Never read,
   echo, `cat`, or commit it. You may APPEND to it, but never print its contents.
   Postgres dev credentials are non-secret defaults and belong in `docker-compose.yml`
   and `.env.example`.
4. **No weakened assertions.** Baseline to preserve or beat: **620 backend passed /
   4 skipped**, **141 frontend passed**, frontend build clean.
5. **Auth is in scope.** `users` moves too. Password hashes and column semantics survive
   verbatim -- do NOT swap the hashing scheme (pwdlib/Argon2 stays).
6. **The four store INTERFACES do not change.** `auth/store.py`, `learning/store.py`,
   `learning/field_set_store.py`, `learning/schema_store.py` contain zero SQL and must
   keep containing zero SQL. (Their *docstrings* mention SQLite; those are updated in
   Task 7.)
</hard_rules>

<the_five_traps>
The researcher verified each of these against the real source. Each silently corrupts
behaviour if ported naively. Every task below that touches one names it.

**TRAP 1 -- `ORDER BY rowid` (sqlite_schema_store.py lines 167, 222, 244).**
`rowid` does not exist in Postgres. Deleting the ORDER BY makes canonical-field and
alias order NONDETERMINISTIC -- silently breaking `test_schema_store.py`'s order
assertions and the reconstructed `Schema.fields` tuple. Fix: an explicit
`seq BIGINT ... IDENTITY` column on `canonical_field` and `alias`, and `ORDER BY seq`.

**TRAP 2 -- `created_at` MUST stay TEXT, never TIMESTAMPTZ.**
`tests/test_schema_service.py:217` asserts an exact `...Z`-suffixed string. TIMESTAMPTZ
round-trips that to `...+00:00`. Every domain model declares `created_at: str`. Beyond
the test: silently re-formatting a curator's recorded timestamp is an ALIAS-03
provenance violation. Do NOT "modernize" this column.

**TRAP 3 -- the startup preset-seeding race is SILENT.**
`app.py::_lifespan` swallows exceptions by design (T-e0e-03: a bad preset YAML must not
brick the server). Under Alembic the stores no longer run `CREATE TABLE IF NOT EXISTS`,
so if migrations have not run, `seed_presets` raises `UndefinedTable`, gets logged as a
*warning*, and the app boots with a blank field-set picker -- regressing exactly what
quick task 260712-e0e fixed. Fix: a separate, LOUD schema check that RAISES, placed
before seeding and outside its `except`.

**TRAP 4 -- Booleans.** The stores write `int(is_verified)` / `int(field.required)` and
read `bool(row[...])`. Postgres BOOLEAN does not coerce `1` to true; psycopg raises.
Delete all four casts -- the write-path cast raises, the read-path cast is dead.

**TRAP 5 -- `INSERT OR IGNORE` becomes `on_conflict_do_nothing`, NEVER `do_update`.**
The four stores are deliberately ASYMMETRIC: three upsert, but `add_alias` and
`_insert_missing_fields` rely on first-write-wins to make ALIAS-03 (immutable
provenance) and P3/D-07-03 (augment-only) *structural* invariants rather than
conventional ones. A symmetric "tidy" port destroys both. Preserve the asymmetry and
pin it with a test (Task 5).
</the_five_traps>

<decisions_against_research>
Four deliberate deviations. Each is a correction, not a preference. DR-1 and DR-4 are
presented together because DR-4 is the defect that DR-1's original (wrong) rationale
concealed -- an adversarial review caught it, and the pairing is the lesson.

**DR-1 -- tests run `alembic upgrade head`, NOT `Base.metadata.create_all`.**
The research recommended `create_all` in the session fixture. Use the real migration
instead, for two reasons that hold up: it **proves the migration on every suite run**,
and it **eliminates model-vs-migration drift** (a `create_all` suite is green against
models that the migration may not actually produce). Cost is ~1s once per session.

**Correction to an earlier draft of this rationale (it was wrong, and the error was
load-bearing).** A previous version justified DR-1 by claiming `create_all` "would raise
for every one of the ~600 tests that build a TestClient" because it does not stamp
`alembic_version`. That is FALSE, twice over:
  - `_lifespan` only runs under `with TestClient(app) as client:` -- there are **4** such
    sites (all in `tests/api/test_preset_seeding.py`) against **29** bare
    `TestClient(app)` sites that never trigger lifespan at all.
  - More importantly, the startup check reads `DATABASE_URL` (the DEV database), not the
    test database conftest migrates -- so "conftest stamped `alembic_version`, therefore
    the check passes" is a non-sequitur regardless.

That false comfort is exactly what concealed the fact that **nothing was pointing the
app's own session at the test database** (see DR-4). Keep the decision; do not reuse the
old reason.

**DR-4 -- conftest MUST override `get_session`, not just the four store factories.**
This is the isolation keystone, and it is easy to get subtly wrong. "Every store holds a
Session" (research Pitfall 8) is necessary but NOT sufficient: it says nothing about
*which* engine that Session came from. `persistence/engine.py` builds a module-level
engine from `DATABASE_URL` (dev); conftest builds a separate engine from
`DATABASE_URL_TEST`. A test that overrides only *some* store factories leaves the others
resolving `Depends(get_session)` through the module engine -- a different connection to a
DIFFERENT (dev) database, outside the test's outer transaction, so `trans.rollback()`
rolls back nothing and rows accumulate in the dev DB across runs.

This is not hypothetical. `tests/api/test_upload.py` overrides `get_profile_store` and
`get_anthropic_client`, but the upload route also depends on `get_field_set_store`,
`get_schema_store`, and `get_user_store` (transitively, via `get_current_user`).
`test_confirm_gate.py`, `test_money_shot.py`, and `test_hint_and_export.py` each override
only `get_profile_store` while also reaching `get_schema_store`.

The fix is one line, and it is the RIGHT layer: override `get_session` itself (autouse),
so every store the app resolves -- overridden or not -- is bound to the test's
`db_session`. Task 3 does this. It also makes most of the ~33 explicit store overrides
redundant, which shrinks Task 6's churn rather than growing it.

**DR-2 -- `/.assayingest/` STAYS in `.gitignore`.**
The research's file table says to remove the "now-dead SQLite dir". It is not dead:
`api/routes/confirm.py` sets `EXPORT_BASE_DIR = Path(".assayingest/exports")` and still
writes confirmed-run exports there. Only `profiles.db` goes away. Removing the gitignore
entry would start committing curator export artifacts. Keep the entry; update
confirm.py's comment that calls the directory a sibling of the old default DB path.

**DR-3 -- three tests are deleted, not two.**
The research found 2 db-file-existence tests. There is also
`tests/test_schema_store.py:40::test_store_uses_the_same_shared_db_file_as_the_profile_store`
-- a file-coupling assertion that is meaningless once both stores share a Session. All
three assert on SQLite file layout; none assert on behaviour. The 2 raw-`sqlite3`
SQL-injection tests are still **PORTED, not deleted** -- they are the ASVS V5 proof.

Adopted from research unchanged: `postgresql+psycopg://` (psycopg3 -- the bare prefix
silently means psycopg2); `Text` not `JSONB` for the `*_json` columns (psycopg3
pre-parses JSONB, so the existing `json.loads()` would receive a `list` and raise);
`String` not native `UUID` for ids (domain models declare `id: str`); rename `schema` to
`canonical_schema`; keep `users` plural (`USER` singular is reserved in Postgres);
testcontainers REJECTED (it drives the docker socket via the Python docker SDK and would
hit the exact permission wall -- a test suite cannot re-exec itself under `sg docker`).
</decisions_against_research>

<sequencing>
Eight tasks. The order exists so every task ends at a green, committable state.

The rule that makes this work: the SQLite stores stay alive and wired until every
Postgres store is proven. Tasks 1-2 add infrastructure and change no behaviour. Tasks
3-5 add one Postgres store at a time, porting only that store's own unit tests -- the
app still runs on SQLite, so the suite stays green throughout. Task 6 flips the DI in
one atomic move, now that all four stores are proven. Task 7 retires SQLite. Task 8
proves it end-to-end against the real running app.

**Honesty note on that claim.** An adversarial review of an earlier draft proved T1-T5
end green as written, but T6 and T7 did NOT -- they each contained a defect that a green
suite would not have caught:
  - T6 wired the DI in a way that made the *production* seeding path raise
    `AttributeError` while all four seeding tests still passed (they overrode the defect
    away). Green suite, blank field-set picker.
  - T7 deleted the CLI's only test-injection seam, which would have sent `run()` to the
    dev database while the assertions read the test database.
Both are fixed below (T6's `_lifespan` no longer calls the DI factory; T7 keeps a
constructor-injection seam). "Ends green" is a claim this plan now EARNS through the
specific verifications in T6 and T7 -- which deliberately exercise the un-overridden
paths -- not one it asserts.
</sequencing>

<tasks>

<task type="auto">
  <name>Task 1: Stand up Postgres and add the dependencies (no code change)</name>
  <files>docker-compose.yml, .env.example, .env (append only), pyproject.toml</files>
  <action>
Create `docker-compose.yml` with a single `db` service: image `postgres:17` (D-1),
container_name `data-ingestor-db`, named volume `pgdata:/var/lib/postgresql/data`, port
`5432:5432`, env `POSTGRES_USER=assayingest` / `POSTGRES_PASSWORD=assayingest` /
`POSTGRES_DB=assayingest`. These are dev-only non-secret literals, committed on purpose.
No top-level `version:` key -- Compose v5 treats it as obsolete.

The healthcheck MUST be `["CMD-SHELL", "pg_isready -U assayingest -d assayingest"]`,
interval 2s, timeout 3s, retries 15, start_period 5s. The `-U`/`-d` flags are
load-bearing: a bare `pg_isready` checks the *server*, which reports ready during initdb
BEFORE the application database exists.

Add to `pyproject.toml` `[project].dependencies` (runtime, NOT dev):
`sqlalchemy>=2.0.51`, `alembic>=1.18.5`, `psycopg[binary]>=3.3.4`.

They are runtime deps because `sqlalchemy` and `psycopg` are imported by the shipped
package at request time. `alembic` is runtime because `api/app.py`'s startup schema check
(Task 6) reads the `alembic_version` table. Be precise about what this does NOT buy:
`alembic.ini` and `alembic/versions/` live at the REPO ROOT and the wheel ships only
`src/assayingest` (`[tool.hatch.build.targets.wheel] packages`), so
`alembic upgrade head` does **not** work from a bare `pip install` of this package -- it
works from a checkout. Migrations are a repo-level operation for now. Do not write a
comment claiming otherwise. (Packaging the migrations into the wheel is a real option
later; it is out of scope here and D-4 makes it unnecessary.)

Add to `.env.example` as a non-secret template: a `DATABASE_URL` and a
`DATABASE_URL_TEST`, both using the `postgresql+psycopg://` prefix, user/password
`assayingest`, host `localhost:5432`, databases `assayingest` and `assayingest_test`
respectively. The `+psycopg` is MANDATORY -- a bare `postgresql://` prefix resolves to
psycopg2 and fails with a confusing `ModuleNotFoundError` that looks like a missing
dependency (TRAP: research Pitfall 5).

APPEND those same two variables to the gitignored `.env`. Append only -- never read,
echo, or print that file; it holds a real API key.

Create the test database once (the image only auto-creates `POSTGRES_DB`):
`sg docker -c "docker compose exec -T db createdb -U assayingest assayingest_test"`.

Change no Python source in this task.
  </action>
  <verify>
    <automated>sg docker -c "docker compose up -d" &amp;&amp; sleep 8 &amp;&amp; sg docker -c "docker compose exec -T db pg_isready -U assayingest -d assayingest" &amp;&amp; sg docker -c "docker compose exec -T db psql -U assayingest -d postgres -c '\l'" &amp;&amp; uv sync &amp;&amp; uv run python -c "import sqlalchemy, alembic, psycopg; print(sqlalchemy.__version__, alembic.__version__, psycopg.__version__)" &amp;&amp; uv run pytest -q 2>&amp;1 | tail -3</automated>
  </verify>
  <done>
`pg_isready` reports "accepting connections". The `\l` listing shows BOTH `assayingest`
and `assayingest_test`. The three new libraries import at their expected major versions.
The existing suite is UNCHANGED at 620 passed / 4 skipped (this task touched no Python).
  </done>
</task>

<task type="auto">
  <name>Task 2: The persistence package and the initial Alembic migration</name>
  <files>src/assayingest/persistence/__init__.py, src/assayingest/persistence/base.py, src/assayingest/persistence/models.py, src/assayingest/persistence/engine.py, alembic.ini, alembic/env.py, alembic/versions/</files>
  <action>
Create `src/assayingest/persistence/` with SQLAlchemy 2.0 declarative style
(`DeclarativeBase`, `Mapped[...]`, `mapped_column`). Sync engine, not async: the app is
single-threaded and synchronous, all four stores are sync, and FastAPI runs sync `def`
endpoints in a threadpool. An async port would touch every route. Do NOT go async.

`base.py`: a single `Base(DeclarativeBase)` -- one MetaData, so autogenerate has one
target.

`models.py`: the six ORM entities. All `id` columns are `String` (uuid4 *strings*), NOT
native `UUID` -- every domain model declares `id: str`, and psycopg would hand back
`uuid.UUID` objects, breaking equality across the boundary. All `created_at` columns are
`String` (TRAP 2). All `*_json` columns are `Text`, never `JSONB` (the stores call
`json.dumps`/`json.loads` themselves; psycopg3 pre-parses JSONB and `json.loads(list)`
raises `TypeError`).

  - `users`: id PK · email unique NOT NULL · password_hash nullable · **is_verified
    Boolean** NOT NULL default False (TRAP 4) · auth_provider String NOT NULL default
    "password" · created_at String NOT NULL. Keep the table name PLURAL -- `USER`
    singular is a RESERVED word in Postgres.
  - `profiles`: id PK · field_set_signature NOT NULL · column_signature NOT NULL ·
    mapping_json Text NOT NULL · structural_hint_json Text nullable · created_at String
    NOT NULL · `UniqueConstraint(field_set_signature, column_signature)`. DROP the old
    `idx_profiles_lookup` index -- the UNIQUE constraint already creates a btree index
    on exactly those two columns.
  - `field_set_templates`: id PK · name NOT NULL unique · field_set_json Text NOT NULL ·
    signature String NOT NULL · created_at String NOT NULL · index on `signature` (KEEP
    this one -- it is not covered by the UNIQUE on `name`).
  - `canonical_schema` (renamed from `schema`): id PK · name NOT NULL unique ·
    created_by nullable · created_at String NOT NULL. The domain class stays `Schema`;
    only the table name changes. `SCHEMA` is non-reserved so this is hygiene, not a bug
    fix -- but it is free on a fresh DB (D-4) and removes permanent confusion with
    Postgres's own SCHEMA namespace, `information_schema`, and SQLAlchemy's `schema=`
    kwarg.
  - `canonical_field`: id PK · **seq BigInteger, Identity(), unique** (TRAP 1) ·
    schema_id FK to `canonical_schema.id` NOT NULL, indexed · name NOT NULL ·
    description / type / unit / date_format nullable · allowed_values_json Text nullable
    · **required Boolean** NOT NULL default True (TRAP 4) · min / max `Double` nullable ·
    `UniqueConstraint(schema_id, name)`.
  - `alias`: id PK · **seq BigInteger, Identity(), unique** (TRAP 1) · canonical_field_id
    FK to `canonical_field.id` NOT NULL, indexed · vendor / source_column /
    provenance_kind / provenance_actor String NOT NULL · created_at String NOT NULL ·
    `UniqueConstraint(canonical_field_id, vendor, source_column)`.

The `seq` columns are the ONLY thing that makes ordering deterministic. Add a comment on
each saying so, and naming `rowid` as what it replaces.

Note the FK gain: Postgres enforces foreign keys ALWAYS, so the old
`PRAGMA foreign_keys = ON` line disappears and the SCHEMA-04 isolation invariant gets
*stronger*, not weaker.

`engine.py` (the composition root): a lazily-built module-level engine + `sessionmaker`,
and a `get_session()` generator for FastAPI (one Session per request). Read the URL from
`DATABASE_URL` after calling the existing `env.load_project_env()` (override=False -- a
real env var always wins, per quick task 260712-ekj). If `DATABASE_URL` is unset, raise
a consequence-shaped error naming the fix (copy `.env.example`, then
`sg docker -c 'docker compose up -d db'`) -- do not fall back to any default. Pass
`pool_pre_ping=True` (a container restart kills pooled connections) and
`connect_args={"connect_timeout": 3}`. That timeout is load-bearing: psycopg's default
is the OS TCP timeout (~2 min), so without it a run against a stopped Postgres *hangs*
instead of failing.

Scaffold Alembic (`uv run alembic init alembic`), then rewrite `alembic/env.py` to build
the engine DIRECTLY from `os.environ["DATABASE_URL"]` (after `load_project_env()`) with
`poolclass=pool.NullPool`. Do NOT use the scaffolded
`config.set_main_option("sqlalchemy.url", ...)` + `engine_from_config` path: it routes
the URL through ConfigParser, which treats `%` as interpolation and would raise
`InterpolationSyntaxError` on a password containing `%`.

`alembic/env.py` MUST `import assayingest.persistence.models` for its side effect
(registering all six tables on `Base.metadata`) and set `target_metadata = Base.metadata`.
Without that import, `Base.metadata` is empty and `--autogenerate` cheerfully emits an
EMPTY migration.

Generate the migration (`uv run alembic revision --autogenerate -m "initial schema"`) and
OPEN the generated file to confirm it contains six `op.create_table` calls before
committing it.

Nothing imports `persistence/` yet -- the app still runs on SQLite after this task.
  </action>
  <verify>
    <automated>uv run alembic upgrade head &amp;&amp; sg docker -c "docker compose exec -T db psql -U assayingest -d assayingest -c '\dt'" &amp;&amp; sg docker -c "docker compose exec -T db psql -U assayingest -d assayingest -c \"SELECT table_name, column_name, data_type, is_identity FROM information_schema.columns WHERE column_name IN ('created_at','is_verified','required','seq') ORDER BY table_name, column_name;\"" &amp;&amp; uv run alembic check &amp;&amp; uv run pytest -q 2>&amp;1 | tail -3</automated>
  </verify>
  <done>
`\dt` lists exactly seven tables: the six domain tables (`users`, `profiles`,
`field_set_templates`, `canonical_schema`, `canonical_field`, `alias`) plus
`alembic_version`. The `information_schema` query proves, in real output: every
`created_at` is a **text/character-varying** type and NOT `timestamp with time zone`
(TRAP 2); `users.is_verified` and `canonical_field.required` are **boolean** (TRAP 4);
`canonical_field.seq` and `alias.seq` exist with `is_identity = YES` (TRAP 1).
`alembic check` reports no new upgrade operations (the migration matches the models --
no drift). The existing suite is still 620 passed / 4 skipped.
  </done>
</task>

<task type="auto">
  <name>Task 3: The test harness (conftest) and PostgresProfileStore</name>
  <files>tests/conftest.py, src/assayingest/learning/postgres_store.py, tests/test_profile_store.py</files>
  <action>
Create `tests/conftest.py` (none exists today). This is the load-bearing file for the
whole migration -- get it right once and the remaining ~30 call sites are mechanical.

**Session-scoped `engine` fixture.** Build an engine against `DATABASE_URL_TEST` (the
SEPARATE `assayingest_test` database -- never the dev DB) with
`connect_args={"connect_timeout": 3}`. Immediately execute `SELECT 1`. If it fails,
raise `pytest.UsageError` with an actionable message naming the fix
(`sg docker -c 'docker compose up -d db'`) and the underlying error. Fail LOUDLY: never
`pytest.skip` here -- a green suite that tested nothing is the worst possible outcome and
would violate the no-weakened-assertions rule. The 3s connect timeout is what makes this
a fast failure instead of a two-minute hang.

Then run **`alembic upgrade head` against the test database**, once per session -- NOT
`Base.metadata.create_all` (decision DR-1). Invoke it programmatically via
`alembic.config.Config` + `alembic.command.upgrade`, with the test URL injected. Rationale
for the docstring: running the real migration proves it on every suite run and eliminates
model-vs-migration drift. (Do NOT justify it by claiming `create_all` would break the
TestClient tests -- that reasoning is false; see DR-1.)

**Function-scoped `db_session` fixture.** The official SQLAlchemy 2.0 recipe for joining
a Session into an external transaction: open a connection, `begin()` an outer
transaction, construct `Session(bind=connection,
join_transaction_mode="create_savepoint")`, yield it, then close the session and
**ROLL BACK the outer transaction** and close the connection. `create_savepoint` is what
lets a store call `session.commit()` (which it must, to preserve today's write-then-read
semantics) while the outer transaction stays open, so the rollback still wipes
everything. The 2.0 docs note the old event-listener "restart savepoint" recipe is no
longer required.

**AUTOUSE `get_session` override -- the isolation keystone (DR-4).** Add an autouse
fixture that sets `app.dependency_overrides[get_session] = lambda: db_session` and tears
it down afterwards. This is NOT optional and it is NOT a convenience.

Why it is the only correct layer: "every store holds a Session" guarantees the store does
not open its own connection, but it says nothing about WHICH ENGINE that Session came
from. Without this override, any store factory a test does not explicitly override
resolves `Depends(get_session)` through the module-level engine in `persistence/engine.py`
-- which is built from `DATABASE_URL`, the **DEV** database. That connection sits outside
the test's outer transaction, so `trans.rollback()` rolls back nothing and rows quietly
pile up in the dev DB run after run.

Tests genuinely do under-override today, so this WILL bite: `tests/api/test_upload.py`
overrides `get_profile_store` + `get_anthropic_client`, but the upload route also depends
on `get_field_set_store`, `get_schema_store`, and `get_user_store` (transitively via
`get_current_user`). `test_confirm_gate.py`, `test_money_shot.py`, and
`test_hint_and_export.py` each override only `get_profile_store` while also reaching
`get_schema_store`. Overriding `get_session` once covers all of them, present and future.

Prove it, do not assume it. Add a test that asserts the app's OWN dependency-resolved
store and the test's `db_session` see the same transaction: write a row through a route
(or through `deps.get_profile_store()` resolved via the app), read it back through
`db_session`, and assert it is visible. Then, after the test, assert the DEV database was
never touched. If the override is missing or mis-scoped, this test fails.

**Store fixtures.** Add a `profile_store` fixture returning
`PostgresProfileStore(db_session)`. (The other three stores get their fixtures in Tasks
4-5.)

Now write `src/assayingest/learning/postgres_store.py` -- `PostgresProfileStore`,
implementing the UNCHANGED `ProfileStore` interface.

**The constructor takes a `Session`. Not an engine, not a sessionmaker.** This is the
single most load-bearing design choice in the migration: a store that opens its own
connection per method checks out a *different* pooled connection, lands OUTSIDE the
test's outer transaction, and `trans.rollback()` then rolls back nothing. Rows leak
between tests and the failures look random. Store `self._session` and use only that.

Port the three methods 1:1 from `sqlite_store.py`:
  - `save`: `sqlalchemy.dialects.postgresql.insert(...)` +
    `on_conflict_do_update(index_elements=["field_set_signature", "column_signature"],
    set_={id, mapping_json, structural_hint_json, created_at})`. This store is one of the
    three that DO upsert (TRAP 5 -- the asymmetry is deliberate). Updating the PK `id` in
    the SET clause is legal in Postgres and preserves today's semantics. Then
    `self._session.commit()`.
  - `find`, `list_for_field_set`: unchanged query semantics.
Keep `json.dumps`/`json.loads` exactly where they are today (the columns are Text).
Rename the boundary translator `_row_to_profile` to `_entity_to_profile`, preserving its
shape and its docstring's role as the wire-to-domain translator.

Port `tests/test_profile_store.py` (8 store-construction sites): swap
`SqliteProfileStore(tmp_path / "profiles.db")` for the `profile_store` fixture.
  - DELETE `test_sqlite_store_creates_the_db_file_and_parent_dir_on_construction` (line
    141) -- it asserts on SQLite file layout, which no longer exists.
  - **PORT, do not delete, the SQL-injection test at line 159.** It is the ASVS V5 proof
    that queries are parameterised. Replace the raw `sqlite3.connect(db_path)` assertion
    with a `db_session.execute(text("SELECT COUNT(*) FROM profiles")).scalar()` check --
    the malicious signature round-trips as data and the table still stands.
  - Remove the now-unused `import sqlite3` from the file.

The SQLite profile store stays on disk and stays wired into `deps.py` and `cli.py` after
this task -- so the rest of the suite is untouched and still green.
  </action>
  <verify>
    <automated>uv run pytest tests/test_profile_store.py -v 2>&amp;1 | tail -20 &amp;&amp; uv run pytest -q 2>&amp;1 | tail -3 &amp;&amp; grep -rn "sqlite3" tests/test_profile_store.py; test $? -eq 1 &amp;&amp; echo "PROFILE-STORE-TEST-IS-SQLITE-FREE"</automated>
  </verify>
  <done>
`tests/test_profile_store.py` passes entirely against Postgres, including the ported
SQL-injection test. The file-existence test is gone; no `sqlite3` import remains in it.
The full suite is green with 4 skipped (everything else still runs on the still-wired
SQLite stores). Isolation is proven: running `tests/test_profile_store.py` twice in a row
gives identical results (the outer-transaction rollback wiped the rows -- if the store had
held an engine instead of a Session, the second run would fail on a unique constraint).
  </done>
</task>

<task type="auto">
  <name>Task 4: PostgresUserStore and PostgresFieldSetStore</name>
  <files>src/assayingest/auth/postgres_store.py, src/assayingest/learning/postgres_field_set_store.py, tests/conftest.py, tests/auth/test_user_store.py, tests/learning/test_field_set_store.py</files>
  <action>
Two more stores, same shape as Task 3: constructor takes a `Session`, interface
unchanged, boundary translator renamed `_row_to_X` to `_entity_to_X`.

**`auth/postgres_store.py` -- `PostgresUserStore`.** Auth is in scope; the hashing scheme
does NOT change (pwdlib/Argon2 hashes carry through as opaque strings).
  - `save`: `insert(...).on_conflict_do_update(index_elements=["email"], set_={password_hash,
    is_verified, auth_provider})`. `id` is deliberately NOT in the SET clause -- an
    existing user's stable id must survive a credential change. Preserve that.
  - **TRAP 4:** delete `int(user.is_verified)` on the write path and `bool(row[...])` on
    the read path. Pass the Python `bool` straight through -- Postgres BOOLEAN rejects the
    integer `1` and psycopg raises.
  - `mark_verified`: the old raw SQL sets `is_verified = 1`; it must now set the boolean
    `True`.
  - `get`, `get_by_email`, `get_or_create_by_email`: semantics unchanged (the
    Google-provisioned branch still mints a uuid4 string id, `is_verified=True`,
    `auth_provider="google"`, no password).

**`learning/postgres_field_set_store.py` -- `PostgresFieldSetStore`.**
  - `save`: `on_conflict_do_update(index_elements=["name"], set_={id, field_set_json,
    signature, created_at})` -- an upsert, matching today. Still mints a fresh uuid4
    `template_id` per call and returns it.
  - `get`, `list`: unchanged (`list` still `ORDER BY name`).
  - Keep rebuilding the `FieldSet` through `fields.loader.from_dict`, never a bare
    `FieldSet(**...)` -- a round-tripped template must get the exact same name/length/type
    guards a freshly-saved one did, never a second weaker reconstruction path.

Add `user_store` and `field_set_store` fixtures to `tests/conftest.py`, both taking
`db_session`.

Port `tests/auth/test_user_store.py` to the `user_store` fixture.

The field-set store has NO dedicated unit-test file today -- its coverage is indirect,
through `tests/api/test_field_sets.py` and `tests/api/test_preset_seeding.py`, which do
not port until Task 6. That would leave the store that STARTUP SEEDING depends on
completely unproven at the moment Task 6 flips the DI. Close that gap: create
`tests/learning/test_field_set_store.py` with a small, honest set of behavioural tests --
save-then-get round-trips the FieldSet; `list` returns `(id, name)` ordered by name;
saving twice under the same name UPDATES rather than duplicating (the upsert), and the
returned id is the fresh one. This is new coverage, not a re-litigation of scope: it is
the minimum needed to make Task 6 safe.
  </action>
  <verify>
    <automated>uv run pytest tests/auth/test_user_store.py tests/learning/test_field_set_store.py -v 2>&amp;1 | tail -25 &amp;&amp; uv run pytest -q 2>&amp;1 | tail -3</automated>
  </verify>
  <done>
Both store test files pass against Postgres. The boolean round-trip is proven in real
output: a user saved with `is_verified=False` then run through `mark_verified` reads back
as Python `True` (not `1`), with no `int()`/`bool()` casts anywhere in the new store. A
re-saved email updates the credentials but keeps the original `id`. The field-set store
has behavioural coverage of save/get/list/upsert. Full suite still green, 4 skipped.
  </done>
</task>

<task type="auto">
  <name>Task 5: PostgresSchemaStore -- the dangerous one (seq ordering + first-write-wins)</name>
  <files>src/assayingest/learning/postgres_schema_store.py, tests/conftest.py, tests/test_schema_store.py</files>
  <action>
This is the store where three of the five traps live. Port it with the most care.

`learning/postgres_schema_store.py` -- `PostgresSchemaStore`, `Session` in the
constructor, `SchemaStore` interface unchanged.

**TRAP 1 -- ordering.** The old store's three `ORDER BY rowid` clauses (lines 167, 222,
244) become **`ORDER BY seq`** against the Identity columns added in Task 2. Do NOT drop
the ORDER BY: without it Postgres returns rows in whatever order it likes, `Schema.fields`
is silently non-deterministic, and the order assertions in `test_schema_store.py` fail
intermittently rather than cleanly. The three sites are: `list_aliases_for` (aliases
joined via canonical_field), `_row_to_schema`'s canonical-field query, and
`_aliases_for_field`.

**TRAP 5 -- the deliberate asymmetry. This store does NOT upsert.**
  - `add_alias`: `INSERT OR IGNORE` becomes
    `on_conflict_do_nothing(index_elements=["canonical_field_id", "vendor",
    "source_column"])`. **NEVER `on_conflict_do_update`.** First-write-wins is what makes
    ALIAS-03 (immutable first-seen provenance) a STRUCTURAL invariant rather than a
    conventional one. The existing store's docstring says so explicitly -- carry that
    docstring across, it is the warning for the next reader.
  - `_insert_missing_fields`: same --
    `on_conflict_do_nothing(index_elements=["schema_id", "name"])`. Augment-only: a field
    whose `(schema_id, name)` already exists is left UNTOUCHED, so a benign constraint
    difference never overwrites a stored definition and nothing is ever deleted (P3,
    D-07-03/04).
  - `add_alias` still raises a consequence-shaped `ValueError` when the named canonical
    field does not exist in that schema.
  Note the stricter semantics, and accept them: SQLite's `INSERT OR IGNORE` also swallowed
  NOT NULL and CHECK violations, whereas `DO NOTHING` swallows ONLY unique/exclusion
  conflicts. Every NOT NULL column here is always supplied, so this is a tightening with
  no behavioural cost.

**TRAP 4 -- booleans.** Delete `int(field.required)` on write and `bool(row["required"])`
on read.

**TRAP 2 -- `created_at`** is carried through verbatim as a string, both for the schema
row and for every alias (`alias.created_at` comes from the domain object, not from
`now()`).

Table rename: queries target `canonical_schema`. The domain class stays `Schema`.
`get_schema` still matches on `id` OR `name`. The `PRAGMA foreign_keys = ON` line
disappears -- Postgres enforces FKs unconditionally, so SCHEMA-04 isolation gets stronger.

Keep `_row_to_field` rebuilding through `fields.loader.from_dict` (one field at a time, so
the 50-field loader cap never applies to a read) -- never a bare `Field(**...)`.

Add a `schema_store` fixture to `tests/conftest.py`.

Port `tests/test_schema_store.py` (10 sites) to the fixture, and:
  - DELETE `test_store_creates_the_db_file_and_parent_dir_on_construction` (line 210).
  - DELETE `test_store_uses_the_same_shared_db_file_as_the_profile_store` (line 40) --
    file-coupling, meaningless once both stores share a Session (decision DR-3).
  - **PORT, do not delete, the SQL-injection test at line 206** -- swap the raw
    `sqlite3.connect` assertion for a `db_session.execute(text(...))` count. ASVS V5 proof.
  - Remove the now-unused `import sqlite3`.

Then ADD three tests that pin the traps, because nothing else in the suite would catch a
regression on them:
  1. **Ordering (TRAP 1) -- and it must be a REAL canary.** The naive version of this test
     (insert fields in non-alphabetical order, read back, assert declaration order) is
     WORTHLESS: it would pass even with `ORDER BY seq` deleted, because a small,
     freshly-inserted heap is returned in physical order by a seq scan, and physical order
     == insertion order at that point. It would assert the trap in prose while pinning
     nothing.

     Force the heap to disagree with insertion order: after inserting the fields,
     **`UPDATE` an EARLY row** (change a description, say). Postgres MVCC writes the new
     tuple version at the END of the heap, so physical order no longer matches insertion
     order. THEN read the schema back and assert `Schema.fields` is still in DECLARATION
     order. Without `ORDER BY seq` the updated field comes back last and the test fails;
     with it, order holds. Same construction for the alias ordering test.

     Add a comment in the test saying exactly this, or a future reader will "simplify" the
     UPDATE away and silently defang the canary.
  2. **ALIAS-03 first-write-wins (TRAP 5):** add an alias, then add the SAME
     `(vendor, source_column)` again with a DIFFERENT `provenance_actor` and
     `created_at`. Assert the stored alias still carries the FIRST actor and the FIRST
     timestamp, and that there is exactly one row. This test fails loudly if anyone ever
     "tidies" `do_nothing` into `do_update`.
  3. **Augment-only (P3):** call `add_or_update_fields` with a field name that already
     exists but a changed constraint (e.g. a different `min`), and assert the STORED
     definition is unchanged.
  </action>
  <verify>
    <automated>uv run pytest tests/test_schema_store.py -v 2>&amp;1 | tail -30 &amp;&amp; uv run pytest -q 2>&amp;1 | tail -3</automated>
  </verify>
  <done>
`tests/test_schema_store.py` passes fully against Postgres, including the ported
SQL-injection test. The three new tests pass and are meaningful: the ordering test would
fail if `ORDER BY seq` were dropped; the ALIAS-03 test would fail if `do_nothing` became
`do_update`; the augment-only test would fail if `_insert_missing_fields` started
overwriting. Neither the new store nor the ported test file mentions `rowid` or `sqlite3`.
Full suite still green, 4 skipped.
  </done>
</task>

<task type="auto">
  <name>Task 6: Flip the DI and add the LOUD startup schema check</name>
  <files>src/assayingest/api/deps.py, src/assayingest/api/app.py, tests/api/*.py, tests/test_service.py, tests/test_reconcile_service.py, tests/test_schema_service.py, tests/test_confirm_records_aliases.py</files>
  <action>
All four Postgres stores are now proven. Flip the app over in one atomic move.

**`api/deps.py`.** Each of the four store factories now takes the session as a FastAPI
dependency and hands it to the Postgres store:
`def get_profile_store(session: Session = Depends(get_session)) -> ProfileStore: return
PostgresProfileStore(session)` -- and the same for `get_field_set_store`,
`get_schema_store`, `get_user_store`. The RETURN types stay the abstract interfaces
(`ProfileStore`, `FieldSetTemplateStore`, `SchemaStore`, `UserStore`) -- dependencies
point at the domain, never at infrastructure. Delete the four `Sqlite*Store` imports.
Update the docstrings, which currently promise "the project's standard local SQLite path".
`get_current_user`, `require_user`, `require_verified_user` are untouched -- they depend
on `get_user_store`, not on any concrete store.

**`api/app.py` -- TRAP 3, the silent seeding race. Read this section twice.**

Today every store constructor runs `CREATE TABLE IF NOT EXISTS`, so the tables always
exist by the time `_lifespan` seeds presets. Under Alembic that safety net is GONE. If
migrations have not run, `seed_presets` raises `UndefinedTable`, the existing
`except Exception` logs a warning, and the app starts anyway -- with an EMPTY field-set
picker and an "Upload and Map" button that silently does nothing. That is exactly the
regression quick task 260712-e0e fixed.

**`_lifespan` MUST NOT call `get_field_set_store()`.** An earlier draft of this plan said
to make the factories take `session: Session = Depends(get_session)` and left `_lifespan`
as-is. That is a defect, and an adversarial review REPRODUCED it. Lines 64-65 today are:

    factory = _app.dependency_overrides.get(get_field_set_store, get_field_set_store)
    seed_presets(factory())

That calls the factory as a **plain Python function**, outside FastAPI's DI resolution. In
production there is no override, so `factory` IS `get_field_set_store` and `session` binds
to the **`Depends` object itself**. Then `seed_presets` -> `store.list()` ->
`session.execute()` raises `AttributeError: 'Depends' object has no attribute 'execute'`.
`_lifespan`'s `except Exception` swallows it, logs a warning, and the app boots with a
blank picker. `_require_schema_at_head()` does NOT catch this -- the schema IS at head.
And every seeding test still passes, because all four lifespan tests in
`tests/api/test_preset_seeding.py` override with a zero-arg `lambda: store`, bypassing the
defect entirely. **Green suite, broken product.** This is the single most dangerous failure
mode in the whole migration precisely because the tests are blind to it.

So: `_lifespan` constructs its OWN session and store, directly, from the composition root
-- never through a DI factory. Roughly:

    with SessionFactory() as session:
        seed_presets(PostgresFieldSetStore(session))

wrapped in the existing `try/except` (a bad preset YAML must still not brick the server).
Keep the `dependency_overrides` lookup ONLY if tests still need to substitute a store at
lifespan time -- but if so, the override must be honoured in a way that does not depend on
DI resolution. The simplest correct shape: check for an override, and fall back to
constructing the real store on a real session. Lifespan runs outside the request cycle;
FastAPI never resolves `Depends` for us here, and the code must stop pretending it does.

Add a `_require_schema_at_head()` function that connects and asserts the schema is present
and migrated (read `alembic_version`, confirm it holds a revision). On failure raise a
consequence-shaped `RuntimeError` naming the fix: the database schema is missing, run
`uv run alembic upgrade head` (and start Postgres with
`sg docker -c 'docker compose up -d db'`).

Call it in `_lifespan` **BEFORE** seeding and **OUTSIDE** the `try/except`. Do not widen
that `except` to cover it. The two failures are genuinely different and must behave
differently -- say so in the docstring: a missing SCHEMA is a deployment error and must be
LOUD (refuse to start); a malformed preset YAML is a data hiccup and must NOT brick the
server (warn, start anyway -- T-e0e-03). Both rules survive. Log-or-raise, never both: the
schema check raises and does not log.

**The new startup tests MUST exercise the UN-OVERRIDDEN lifespan path** -- otherwise they
reproduce exactly the blindness described above. Two tests:
  1. With the schema present and NO `dependency_overrides` for the field-set store, enter
     `with TestClient(app):` and assert the presets ACTUALLY SEEDED (query the table
     through `db_session` and see rows). This test fails with `AttributeError` against the
     naive `Depends`-in-lifespan version -- it is the regression gate for this blocker.
  2. With the schema absent (or `alembic_version` empty), assert startup RAISES rather
     than warning-and-continuing. Keep it isolated so it cannot damage the shared test
     database -- point it at a throwaway database.

**Port the remaining API/service test call sites.** Every test file that constructs a
concrete store for a `dependency_overrides` entry now builds a Postgres store on the
`db_session` fixture instead of a `Sqlite*Store(tmp_path / ...)`. Files:
`tests/api/test_field_sets.py`, `tests/api/test_preset_seeding.py`, `tests/api/test_upload.py`,
`tests/api/test_reconcile.py`, `tests/api/test_confirm_aliases_route.py`,
`tests/api/test_confirm_auth_gate.py`, `tests/api/test_confirm_gate.py`,
`tests/api/test_auth_routes.py`, `tests/api/test_money_shot.py`,
`tests/api/test_hint_and_export.py`, `tests/api/test_schemas_routes.py`,
`tests/test_service.py`, `tests/test_reconcile_service.py`, `tests/test_schema_service.py`,
`tests/test_confirm_records_aliases.py`.

The override IDIOM does not change (`app.dependency_overrides[get_profile_store] = lambda:
store`) -- only what `store` is. Where a test overrides a store, the override must return
a store bound to the SAME `db_session` the test asserts against, or the assertion reads a
different transaction and sees nothing.

**Most of these overrides are now REDUNDANT and should be deleted, not ported.** Task 3's
autouse `get_session` override (DR-4) already binds every app-resolved store to the test's
`db_session`. An explicit `dependency_overrides[get_profile_store] = lambda: store` is
only needed where a test substitutes DIFFERENT BEHAVIOUR (a fake/spy store), not merely a
different database. Delete the pure-plumbing overrides; keep the behavioural ones. This
SHRINKS the churn rather than growing it, and it removes the class of bug that Blocker 2
came from -- a test that overrides three of the four stores a route touches, and silently
sends the fourth to the dev database.

This is mechanical churn, but it is where a weakened assertion could slip in unnoticed.
Change ONLY store construction and override plumbing. Do not touch a single assertion. If
a test now fails, the port is wrong -- fix the port, never the assertion.

`tests/test_schema_service.py:217` (the exact `created_at` string assertion) is the
canary for TRAP 2: if it fails, `created_at` became a TIMESTAMPTZ somewhere. Do not
"fix" it by relaxing the string.
  </action>
  <verify>
    <automated>uv run pytest tests/api -q 2>&amp;1 | tail -5 &amp;&amp; uv run pytest -q 2>&amp;1 | tail -5 &amp;&amp; uv run pytest tests/test_schema_service.py -q 2>&amp;1 | tail -3 &amp;&amp; sg docker -c "docker compose exec -T db psql -U assayingest -d assayingest -c 'SELECT count(*) AS dev_profiles FROM profiles;'"</automated>
  </verify>
  <done>
The whole backend suite passes on Postgres with the SQLite stores no longer wired
anywhere: **620+ passed, exactly 4 skipped** (the live-Claude tests remain skipped -- the
gating env var was never set). `tests/test_schema_service.py` passes, proving `created_at`
round-trips byte-identically.

The two new startup tests pass, and BOTH exercise the un-overridden lifespan path: presets
actually seed through the real `_lifespan` (Blocker 1's regression gate -- this fails with
`AttributeError` if anyone reintroduces `Depends` resolution into lifespan), and a missing
schema RAISES rather than booting with a blank picker.

**Isolation is proven, not assumed:** the `dev_profiles` count in the DEV database is
unchanged by a full suite run (run the suite twice and compare). If it grows, a store
escaped the test transaction and the `get_session` override is wrong.

Zero assertions were weakened; `git diff` on the test files shows only store-construction
and override-plumbing lines changed.
  </done>
</task>

<task type="auto">
  <name>Task 7: Retire SQLite</name>
  <files>src/assayingest/cli.py, src/assayingest/learning/sqlite_store.py (delete), src/assayingest/learning/sqlite_field_set_store.py (delete), src/assayingest/learning/sqlite_schema_store.py (delete), src/assayingest/auth/sqlite_store.py (delete), src/assayingest/learning/store.py, src/assayingest/learning/field_set_store.py, src/assayingest/learning/schema_store.py, src/assayingest/auth/store.py, src/assayingest/learning/profile.py, src/assayingest/auth/passwords.py, src/assayingest/api/routes/confirm.py, src/assayingest/learning/seed.py, tests/test_learning_loop_cli.py, tests/test_export_cli.py, tests/test_hint_replay_cli.py, tests/test_validator_cli.py, tests/test_cli_run.py, README.md</files>
  <action>
Nothing depends on the SQLite stores except the CLI. Cut that last cord, then delete them.

**`cli.py` -- drop the FLAG, but KEEP an injection seam.**

Drop the `--profiles-db PATH` **argparse flag** (line ~723): a filesystem path to a SQLite
file is meaningless now. Do NOT replace it with a `--database-url` flag -- the env var is
the one documented way in, and a second path is a second thing to keep correct.

But do **NOT** simply delete the `profiles_db` parameter threaded through `run()` (line
~172) and `_resolve_store()` (lines 251-258, 778). An earlier draft said to, and that is a
defect: `run(..., profiles_db=str(db_path))` is how **~30 call sites across the four CLI
test files** isolate the store. Delete the parameter with nothing in its place and
`_resolve_store(field_set)` builds a store on the composition-root engine -> the **DEV**
database, while the tests construct their store on `db_session` -> the test database.
`run()` writes to one database and the assertion reads another. The tests fail, and this
task's own "never change an assertion" rule makes them unfixable as written -- the executor
would be trapped between two rules.

Replace the parameter with **constructor injection**, which is what the project's Clean
Architecture convention calls for anyway (dependencies point toward the domain; the caller
supplies infrastructure):

  - `run(..., store: ProfileStore | None = None)` -- typed as the ABSTRACT interface, never
    the concrete store.
  - Tests pass `store=PostgresProfileStore(db_session)`.
  - Production passes nothing; `_resolve_store` builds the real one.

`_resolve_store` becomes: if a `store` was injected, use it; else if there is no field set,
no store; else build a `PostgresProfileStore` on a session from the composition root.

**Session lifecycle (be explicit -- `get_session` is a GENERATOR).** `PostgresProfileStore(get_session())`
would hand the store a generator object, and every call would fail on
`generator.execute(...)`. `get_session` exists for FastAPI's `Depends` protocol and is for
FastAPI only. The CLI must use the `sessionmaker` directly: open `with SessionFactory() as
session:` in `run()` (or `main()`), construct the store on that session, and let the `with`
block close it when the command finishes. State in the docstring that the session's
lifetime is the CLI invocation. The CLI already calls `load_project_env()` at its
composition root, so `DATABASE_URL` resolves exactly as it does for the app.

**Delete the four store files:** `learning/sqlite_store.py` (which also takes
`_DEFAULT_DB_PATH` with it), `learning/sqlite_field_set_store.py`,
`learning/sqlite_schema_store.py`, `auth/sqlite_store.py`.

**Purge the stale references in the surviving modules.** These are docstrings and comments
that name SQLite as the implementation; every one is now false, and the negative grep gate
below will catch any that are missed:
  - `learning/store.py`, `learning/field_set_store.py`, `learning/schema_store.py`,
    `auth/store.py` -- the four INTERFACES. Their docstrings say things like "A local
    SQLite file is v1's only implementation". Rewrite to name the Postgres store. The
    interfaces' CODE still contains zero SQL -- that invariant is unchanged and is the
    reason this migration was cheap. Say that.
  - `learning/profile.py` and `auth/passwords.py` -- docstrings referencing the "only
    module allowed to import sqlite3" convention. The convention survives, but the module
    it names has changed.
  - `api/routes/confirm.py` -- the `EXPORT_BASE_DIR` comment calls the directory "a
    sibling of `_DEFAULT_DB_PATH`", a symbol that no longer exists. Rewrite the comment.
    **Do NOT change `EXPORT_BASE_DIR` itself, and do NOT remove `/.assayingest/` from
    `.gitignore`** (decision DR-2): confirmed-run exports still live there. The directory
    is not dead, only the database file inside it is.
  - `learning/seed.py` -- its docstring names `SqliteFieldSetStore.save` when explaining
    the insert-if-absent rule. The rule is unchanged (the Postgres field-set store also
    upserts and also mints a fresh id per call, so unconditional seeding would still
    re-mint preset ids); just rename the store it cites.

**Port the CLI test files** off `Sqlite*Store(tmp_path / ...)` and onto
`run(..., store=PostgresProfileStore(db_session))`. There are **FIVE**, not four:
`test_learning_loop_cli.py`, `test_export_cli.py`, `test_hint_replay_cli.py`,
`test_validator_cli.py`, and **`tests/test_cli_run.py`** -- the last one was missing from
an earlier draft's file list. Its line ~150 calls `run(csv, field_set=field_set)` with no
`profiles_db` at all, so after the port it would quietly open a live connection to the DEV
database. It needs the injected store like the others.

Same rule as Task 6: change only the construction, never an assertion.

**`README.md` -- fix the lie.** Line ~84 still says persistence is "SQLite now, swappable
later". That sentence becomes false the moment this task lands, and the `grep src/` gate
below would never catch it. Rewrite it (the swap HAPPENED; the seam is what made it
cheap), and extend the gate to cover the README.
  </action>
  <verify>
    <automated>grep -rni "sqlite" src/ README.md ; grep -rn "profiles-db\|profiles_db\|_DEFAULT_DB_PATH" src/ ; grep -n "assayingest" .gitignore ; uv run pytest -q 2>&amp;1 | tail -5</automated>
  </verify>
  <done>
`grep -rni "sqlite" src/ README.md` returns NOTHING -- not a store, not an import, not a
stale docstring, not the README's "SQLite now, swappable later" line. The `--profiles-db`
flag and `_DEFAULT_DB_PATH` are gone from source, but `run()` still accepts an injected
`store: ProfileStore | None` so the CLI tests can isolate. The four `sqlite_*.py` files no
longer exist. `/.assayingest/` is STILL in `.gitignore` (exports live there -- DR-2). Full
suite green: 620+ passed, exactly 4 skipped -- including all five CLI test files, none of
which touched the dev database.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 8: Prove it end-to-end against the real running app</name>
  <what-built>
The full migration: Postgres 17 in Compose, six tables under Alembic, four Postgres
stores behind unchanged interfaces, a transactional test harness, SQLite deleted.

Before requesting review, Claude runs the automated proofs below and PASTES THE REAL
OUTPUT. Every one of these is a gate the plan requires actual output for -- a claim of
success without the output is not acceptable.

  1. **Frontend untouched.** `cd frontend && npm run test -- --run` (expect **141
     passed**) and `npm run build` (expect a clean typecheck). Persistence is a backend
     concern; any frontend movement here means something is wrong.

  2. **Postgres DOWN is a loud, actionable failure -- not a hang, not a silent skip.**
     `sg docker -c "docker compose stop db"`, then `uv run pytest tests/test_profile_store.py`.
     It must abort within a few SECONDS (the `connect_timeout=3`) with the
     `pytest.UsageError` naming `sg docker -c 'docker compose up -d db'`. It must NOT
     hang for two minutes and must NOT report a green suite. Then
     `sg docker -c "docker compose start db"` and confirm green again. Paste both.

  3. **Migration from scratch.** Prove the migration works on a genuinely clean database,
     not just an incrementally-built one: `sg docker -c "docker compose down -v"` (drops
     the volume), `sg docker -c "docker compose up -d"`, recreate `assayingest_test`,
     `uv run alembic upgrade head`, then `\dt` to LIST the tables. All six plus
     `alembic_version` must appear.

  4. **End-to-end against the real app, with the rows shown in Postgres.** Restart the
     server -- it currently runs as PID 78623 on :8000 via the flagless
     `uv run uvicorn assayingest.api.app:app --host 0.0.0.0 --port 8000`. Kill and
     relaunch it; NEVER start a second server on :8000. Then:
       a. Sign up a new user through the API.
       b. POST a real file to `/api/upload` (use a synthetic file from
          `data/synthetic/` -- never a real file from the user's desktop).
       c. SHOW the resulting rows in Postgres:
          `sg docker -c "docker compose exec -T db psql -U assayingest -d assayingest -c 'SELECT id, email, is_verified, auth_provider, created_at FROM users;'"`
          and the same for `field_set_templates` (the presets must have SEEDED -- a
          non-empty table here is the direct refutation of TRAP 3).
       Paste the real psql output. Rows in the terminal are the proof; a passing test is
       not.

  5. **The startup check actually fires.** With the schema dropped, start the app and show
     that it REFUSES to start with the actionable error -- rather than booting with an
     empty field-set picker.

  6. **The suite did not write to the dev database.** Snapshot the row counts of
     `profiles`, `users`, and `canonical_schema` in the DEV database; run the full suite;
     snapshot again. The numbers must be IDENTICAL. Paste both. A single incremented count
     means a store escaped the test transaction (Blocker 2 / DR-4) -- stop and fix the
     `get_session` override before continuing.

Then finish `README.md` (Task 7 already removed the false "SQLite now, swappable later"
line): the quickstart gains `sg docker -c "docker compose up -d"` and
`uv run alembic upgrade head` as required steps before running the app, plus the
`createdb assayingest_test` one-liner for contributors running the suite, and the
`DATABASE_URL` env var. Remove the `--profiles-db` flag from any documented CLI usage.
  </what-built>
  <how-to-verify>
Claude has pasted the outputs above. What needs YOUR eyes -- the things no assertion can
check:

  1. Open http://localhost:8000 in a browser. The **field-set picker is POPULATED** with
     the starter presets (not blank). This is the human-visible refutation of TRAP 3.
  2. Sign in as the user created in step 4a, upload a synthetic file from
     `data/synthetic/`, and confirm a mapping. It behaves exactly as it did on SQLite --
     yellow flags on uncertain fields, the confirm gate blocking while any remain.
  3. Restart the app once more and confirm your data is STILL THERE (the named volume
     persists across restarts -- this is the thing SQLite gave for free and the migration
     must not have lost).
  4. Confirm the 620+/4-skipped and 141-frontend numbers in the pasted output match or
     beat the baseline, and that the 4 skips are still the live-Claude tests (no real API
     calls were made, no billing).
  </how-to-verify>
  <resume-signal>Type "approved" to commit, or describe what is off.</resume-signal>
</task>

</tasks>

<verification>
Run at the end of the phase, all against real output:

  - `uv run pytest -q` -> 620+ passed, **exactly 4 skipped**, 0 failed.
  - `cd frontend && npm run test -- --run` -> 141 passed. `npm run build` -> clean.
  - `grep -rni "sqlite" src/ README.md` -> nothing.
  - **Dev DB untouched by the suite:** `SELECT count(*)` on `profiles`, `users`,
    `canonical_schema` in the DEV database is IDENTICAL before and after a full `pytest`
    run. If any count moved, a store escaped the test transaction (the `get_session`
    override is missing or mis-scoped) -- see DR-4.
  - **Un-overridden lifespan seeds for real:** `with TestClient(app):` with NO field-set
    store override actually populates `field_set_templates`. This is the Blocker-1 gate.
  - `uv run alembic check` -> no drift between models and migration.
  - `uv run alembic upgrade head` on a `down -v` clean database -> six tables +
    `alembic_version`, listed via `\dt`.
  - Suite against a stopped Postgres -> aborts in seconds with an actionable
    `pytest.UsageError`. Never hangs. Never green.
  - Real `psql` rows shown for `users` and `field_set_templates` after a real signup and
    a real upload through the running app.
</verification>

<success_criteria>
  - All six tables live in PostgreSQL 17 under Alembic; the four `sqlite_*.py` files are
    deleted and nothing in `src/` mentions SQLite.
  - The four store INTERFACES are byte-identical in their CODE (docstrings updated only)
    -- the domain never learned that the database changed.
  - TRAP 1: `canonical_field.seq` / `alias.seq` Identity columns exist; ordering is
    deterministic and pinned by a test.
  - TRAP 2: every `created_at` is a text column; the exact-string assertion in
    `test_schema_service.py` passes unmodified.
  - TRAP 3: a missing schema makes the app REFUSE to start, loudly; a bad preset YAML
    still does not brick it. Both rules hold simultaneously. AND `_lifespan` seeds through
    a directly-constructed session/store -- never through a DI factory -- so the
    un-overridden production path actually works, proven by a test that does not override
    it (Blocker 1).
  - Isolation is real, not nominal: `get_session` itself is overridden in conftest, so
    every app-resolved store -- including ones a given test never thought to override --
    is bound to the test transaction. The dev database's row counts are unchanged by a
    full suite run (Blocker 2, DR-4).
  - The CLI keeps a test-injection seam (`run(..., store: ProfileStore | None = None)`,
    constructor injection on the abstract interface). Only the `--profiles-db` argparse
    flag is gone. No CLI test touches the dev database (Blocker 3).
  - TRAP 4: no `int()`/`bool()` boolean casts remain in any store.
  - TRAP 5: `add_alias` and `_insert_missing_fields` use `on_conflict_do_nothing`;
    ALIAS-03 first-write-wins and P3 augment-only are each pinned by a test that would
    fail if someone "tidied" them into an upsert.
  - Every store holds a `Session`, never an engine -- so the test suite genuinely isolates
    (proven by a repeated run of the same file passing twice).
  - Zero weakened assertions. Zero live-Claude API calls.
</success_criteria>

<output>
Commit after each task (English, capitalized, one short imperative line, <=150 chars).
Suggested sequence:

  1. `Add PostgreSQL 17 Compose service and SQLAlchemy/Alembic/psycopg dependencies`
  2. `Add persistence package with six ORM models and the initial Alembic migration`
  3. `Add transactional Postgres test harness and PostgresProfileStore`
  4. `Port the user and field-set stores to PostgreSQL`
  5. `Port the schema store to PostgreSQL with seq ordering and first-write-wins aliases`
  6. `Wire the API to PostgreSQL and refuse to start when the schema is missing`
  7. `Delete the SQLite stores and the --profiles-db flag`
  8. `Document the PostgreSQL quickstart`

Write `.planning/quick/260712-ghn-migrate-persistence-from-sqlite-to-postg/260712-ghn-SUMMARY.md`
when done.
</output>
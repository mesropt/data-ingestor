---
task: quick-260712-ghn
verified: 2026-07-12T13:35:00Z
status: human_needed
score: 6/6 must-have truths present-and-wired; 5/6 fully behaviorally proven; 1/6 needs a human browser pass
overrides_applied: 0
human_verification:
  - test: "Open http://localhost:8000 in a browser, confirm the field-set/Schema picker is populated with the starter presets (not blank)."
    expected: "Presets visible immediately, no manual seeding needed."
    why_human: "Visual UI state; the backend seeding is proven by test and by psql row count, but no one has looked at the rendered page in this verification pass."
  - test: "Sign in as the user created during the executor's end-to-end run, upload a synthetic file from data/synthetic/, and confirm a mapping through the UI."
    expected: "Yellow flags on uncertain fields, confirm gate blocks while any remain, and a new row lands in `profiles` after confirming."
    why_human: "The dev-DB snapshot taken during this verification shows `profiles = 0` -- the confirm step has not actually been exercised end-to-end by anyone yet. This is the one must-have truth ('...confirm a mapping with all data persisted') not yet behaviorally closed."
  - test: "Restart the app (kill and relaunch the uvicorn process) and confirm the signed-up user and any confirmed profile are still present."
    expected: "Named Docker volume `pgdata` persists data across restarts, exactly as SQLite's on-disk file did."
    why_human: "Requires driving the running server and reading it back after a restart; not something a static repo check can prove."
---

# Quick Task 260712-ghn: SQLite -> PostgreSQL Migration Verification

**Goal:** Persistence moved from SQLite to PostgreSQL: Docker Compose (postgres:17) +
SQLAlchemy + Alembic. Postgres-only -- SQLite DELETED. Fresh DB, no data migration. All
four stores ported behind UNCHANGED interfaces. Auth (`users`) intact.

**Verified:** 2026-07-12
**Status:** human_needed (no gaps found; three items from the plan's own Task-8 human
checkpoint have not yet been exercised by a human)

## Verdict

**GOAL ACHIEVED** at the code/infrastructure level, with **outstanding human UI
verification** (explicitly gated by the plan's own Task 8, `checkpoint:human-verify`, which
has not yet been walked by a person). Every claim I could independently exercise -- running
the suite, mutating the two highest-risk traps, diffing the four store interfaces and
`passwords.py`, stopping Postgres, checking `img.png`, running the frontend suite and build
-- checked out exactly as SUMMARY.md claims. Nothing was taken on faith.

---

## 1. Tests

```
uv run pytest -q
634 passed, 4 skipped, 1 warning in 20.69s
```

Skip reasons (`-rs`), all four are the live-Claude money tests, gated correctly:

```
SKIPPED tests/test_cli_run.py:124   -- ASSAYINGEST_LIVE_TESTS=1
SKIPPED tests/test_cli_run.py:143   -- ASSAYINGEST_LIVE_TESTS=1
SKIPPED tests/test_cross_domain.py:78 -- ASSAYINGEST_LIVE_TESTS=1
SKIPPED tests/test_max_tokens_live.py:45 -- ASSAYINGEST_LIVE_TESTS=1
```

`ASSAYINGEST_LIVE_TESTS` is referenced only as the `os.environ.get(...) != "1"` skip
condition in those three test files (plus docs/STATE.md history). `env | grep
ASSAYINGEST_LIVE_TESTS` in the shell returns nothing -- **it is not set anywhere**. I did
not set it.

**Status: VERIFIED.**

## 2. No weakened assertions

`git diff 6478751^..cbe4b0b -- tests/` across the full migration range:

- 28 `assert` lines removed, 64 added (net +36 -- consistent with the claimed 14 net-new
  tests: 3 session-isolation, 5 field-set-store, 4 trap canaries, 3 startup-schema-check,
  1 boolean/id-stability test, plus the ported SQL-injection assertions rewritten against
  `db_session` instead of raw `sqlite3.connect`).
- Full diffs read for `test_profile_store.py` and `test_schema_store.py`: every removal is
  either (a) a pure fixture rename (`store` -> `profile_store`/`schema_store`, mechanical),
  or (b) one of the sanctioned DR-3 file-existence-test deletions
  (`test_sqlite_store_creates_the_db_file_and_parent_dir_on_construction`,
  `test_store_creates_the_db_file_and_parent_dir_on_construction`,
  `test_store_uses_the_same_shared_db_file_as_the_profile_store`), plus the 4th deviation
  test (`test_tmp_store_creates_table_and_touches_no_other_file`) -- 4 file-layout tests
  total, matching the SUMMARY's stated deviation #2. No assertion inside a still-existing
  test was loosened.
- The two SQL-injection tests (ASVS V5 proof) were ported, not deleted, and now assert via
  `db_session.execute(text("SELECT COUNT(*) FROM ..."))` instead of raw `sqlite3.connect`.

**Status: VERIFIED.**

## 3. Store interfaces unchanged

`git diff 6478751^..cbe4b0b` on `auth/store.py`, `learning/store.py`,
`learning/field_set_store.py`, `learning/schema_store.py`: every changed line is a
docstring sentence naming the new implementation (`PostgresXStore` instead of `sqlite_*`);
**zero method signatures, zero code lines changed.** The domain genuinely never learned the
database moved.

**Status: VERIFIED.**

## 4. Mutation-tested the two highest-risk traps

**TRAP 1 (ordering).** Removed all three `.order_by(*.seq)` clauses from
`postgres_schema_store.py` (`list_aliases_for`, `_entity_to_schema`, `_aliases_for_field`).
Re-ran the two ordering canaries:

```
FAILED tests/test_schema_store.py::test_canonical_fields_come_back_in_declaration_order_even_after_an_update
FAILED tests/test_schema_store.py::test_aliases_come_back_in_insertion_order_even_after_an_update
AssertionError: assert ['VendorB', 'VendorC', 'VendorA'] == ['VendorA', 'VendorB', 'VendorC']
```

Both canaries bite as claimed -- they are not the worthless first-attempt version the
executor describes catching itself. Reverted (`cp` from a pre-mutation backup);
`git status --porcelain src/assayingest/learning/postgres_schema_store.py` is empty; the 13
tests in `test_schema_store.py` pass again.

**TRAP 5 (first-write-wins).** Changed `add_alias`'s `on_conflict_do_nothing` to
`on_conflict_do_update` (with a `set_` clause covering `provenance_kind`,
`provenance_actor`, `created_at`). Re-ran the ALIAS-03 canaries:

```
FAILED tests/test_schema_store.py::test_add_alias_is_idempotent_and_provenance_is_immutable
FAILED tests/test_schema_store.py::test_a_re_observed_alias_keeps_its_first_seen_provenance_row
AssertionError: assert 'from_map_file' == 'manual'
```

Both fail as claimed. Reverted; tree clean; suite green again.

**Status: VERIFIED by direct mutation (not merely re-reading the executor's claim).**

## 5. Postgres-down behaviour

```
$ sg docker -c "docker compose stop db"
Container data-ingestor-db Stopped

$ time (uv run pytest tests/test_profile_store.py -q)
pytest.UsageError: PostgreSQL is not reachable at
'postgresql+psycopg://assayingest:assayingest@localhost:5432/assayingest_test', so the
test suite cannot run against a database.
Start it with:  sg docker -c 'docker compose up -d db'
Create the test database once with:  sg docker -c 'docker compose exec -T db createdb -U
assayingest assayingest_test'
Underlying error: ... connection to server at "127.0.0.1", port 5432 failed: Connection
refused
8 errors in 2.28s
real  0m4.76s
```

Loud, actionable, ~2.3s pytest-internal (under 5s wall including `uv` startup overhead) --
never a hang, never a silent skip, never green. Restarted the container
(`docker compose start db`), confirmed `pg_isready` reports "accepting connections", and
re-ran the full suite: `634 passed, 4 skipped` again.

**Status: VERIFIED.**

## 6. Auth intact

`git diff 6478751^..cbe4b0b -- src/assayingest/auth/passwords.py`: one docstring word
change (`sqlite3` -> `a driver`), zero code changes -- Argon2/pwdlib hashing scheme
untouched.

`PostgresUserStore` (read directly): no `int()`/`bool()` casts anywhere;
`is_verified`/`auth_provider` pass through as native Python values; `save()`'s upsert
`SET` clause deliberately omits `id`, so a re-registered email keeps its original id.
Dev-DB snapshot (below) shows a real `users` row with `is_verified` as boolean `count=1`,
consistent with the coordinator's independently-confirmed `is_verified = f` (not `0`).

**Status: VERIFIED** (code-level; the human-facing signup/verify flow is covered in
`human_verification` above since it hasn't been walked in a browser during this pass).

## 7. `img.png` deviation

```
$ git status --porcelain
 M .planning/REQUIREMENTS.md   <- unrelated, pre-existing, out of this task's scope
?? img.png

$ ls -la img.png
-rw-r--r-- ... 192794 ... img.png   (present on disk, 192794 bytes -- matches the committed blob size)

$ git ls-tree -r HEAD --name-only | grep -i img.png
(no output -- absent from the tree)

$ git show --stat 610d9a0   (the "untrack" commit)
 img.png | Bin 192794 -> 0 bytes
 1 file changed, 0 insertions(+), 0 deletions(-)
```

`img.png` is untracked, present on disk, and absent from the final tree, exactly as
claimed. Checked the commit that swept it in (`870c595`, Task 7): its 26 changed files are
all on the plan's declared Task-7 file list (the four deleted `sqlite_*.py` files, CLI,
interface docstrings, the five/six CLI test files, README) plus `img.png` -- nothing else
extraneous rode along.

**Note (informational, not a gap):** `.planning/REQUIREMENTS.md` is currently modified in
the working tree. This is unrelated to the migration (it edits Phase-10 INGEST
requirements) and predates this verification session -- flagging for the human's awareness
only, not counted against this task's goal.

**Status: VERIFIED.**

## 8. Frontend unaffected

```
$ cd frontend && npm run test -- --run
Test Files  9 passed (9)
     Tests  141 passed (141)

$ npm run build
✓ built in 671ms
(only a pre-existing >500kB chunk-size advisory, not a typecheck error)
```

**Status: VERIFIED.**

---

## Additional checks run beyond the 8 requested items

- `uv run alembic check` -> `No new upgrade operations detected.` (no model/migration
  drift).
- `\dt` -> all 6 domain tables + `alembic_version`, 7 relations total.
- `grep -rn "from .*engine import .*SessionFactory" src/` -> one hit, and it is the
  WARNING COMMENT in `persistence/engine.py`'s own docstring telling the reader never to
  do this -- no real import-time capture, confirming the coordinator's finding directly.
- Dev-DB leak gate: snapshotted all six tables' row counts, ran the full 634-test suite,
  snapshotted again -- **identical** (`users=1, field_set_templates=4`, all others `0`,
  before and after).
- `tests/test_session_isolation.py` (3 tests) and `tests/api/test_preset_seeding.py`
  (7 tests, including `test_the_un_overridden_lifespan_really_wrote_rows_to_the_database`,
  which contains **no** `dependency_overrides` for the field-set store) all pass.
- `tests/api/test_startup_schema_check.py` (3 tests) pass: missing-schema raises, unreachable-DB
  raises, bad-preset-YAML still boots (TRAP 3's two rules hold simultaneously).
- Read `api/app.py`, `api/deps.py`, `persistence/engine.py`, `cli.py` directly: `_lifespan`
  and `_require_schema_at_head` both go through `new_session()` (the seam), never
  `Depends`; `_lifespan` takes no dependency override; the CLI's `run()` opens a session
  only on the `store is None` branch, confirmed by reading the `if store is not None or
  field_set is None: return ...` guard.
- Repeated `tests/test_profile_store.py` twice in a row: `8 passed` both times (isolation
  genuinely holds, not merely claimed).
- `docker-compose.yml` matches D-1 exactly (image, healthcheck flags/timings, named
  volume, no `version:` key).
- `.gitignore` still has `/.assayingest/` (DR-2 preserved).

---

## Requirements coverage (D-1..D-4, CONTEXT.md)

| Decision | Status | Evidence |
|---|---|---|
| D-1 Docker Compose postgres:17 | SATISFIED | `docker-compose.yml` content confirmed |
| D-2 Postgres-only, SQLite deleted | SATISFIED | 4 files deleted; `grep -rni sqlite src/ README.md` empty |
| D-3 SQLAlchemy + Alembic | SATISFIED | `persistence/models.py`, `alembic/` present and exercised |
| D-4 Fresh DB, no data migration | SATISFIED | No migration script found or claimed; dev DB rows are from live post-migration usage, not migrated legacy data |

## Human Verification Required

See frontmatter `human_verification`. All three items map to the plan's own Task 8
(`checkpoint:human-verify`), which the plan explicitly defers to a human's eyes and which
SUMMARY.md itself lists under "Outstanding (for the human)". This is not a gap in the
executor's work -- it is the plan's designed handoff point. The one substantive open
question: the dev-DB `profiles` count is currently `0`, so the "confirm a mapping" half of
must-have truth #1 has not yet been exercised by anyone (LLM or human) in this repo state.

---

_Verified: 2026-07-12T13:35:00Z_
_Verifier: Claude (gsd-verifier)_

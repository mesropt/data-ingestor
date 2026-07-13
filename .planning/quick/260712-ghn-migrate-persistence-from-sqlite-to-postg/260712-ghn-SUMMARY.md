# Quick Task 260712-ghn: SQLite → PostgreSQL — Summary

**Executed:** 2026-07-12
**Status:** Complete — all 8 tasks, 9 commits, every gate green.
**Baseline preserved:** 620 → **634 backend passed / exactly 4 skipped**; **141 frontend passed**; frontend build clean.

---

## What shipped

PostgreSQL 17 (Docker Compose) behind SQLAlchemy 2.0 ORM + Alembic, replacing raw `sqlite3`.
Six tables moved: `users`, `profiles`, `field_set_templates`, `canonical_schema` (renamed from
`schema`), `canonical_field`, `alias`. Four `sqlite_*.py` stores deleted; nothing in `src/` or
`README.md` mentions SQLite. **The four store interfaces' CODE is unchanged** — the domain never
learned the database moved.

| Commit | Task |
|---|---|
| `6478751` | Add PostgreSQL 17 Compose service and SQLAlchemy/Alembic/psycopg dependencies |
| `51394d4` | Add persistence package with six ORM models and the initial Alembic migration |
| `6b75931` | Add transactional Postgres test harness and PostgresProfileStore |
| `5474fbb` | Port the user and field-set stores to PostgreSQL |
| `119e1ab` | Port the schema store to PostgreSQL with seq ordering and first-write-wins aliases |
| `0fcaa4c` | Wire the API to PostgreSQL and refuse to start when the schema is missing |
| `870c595` | Delete the SQLite stores and the --profiles-db flag |
| `9ab2eaa` | Document the PostgreSQL quickstart |
| `e0d1b76` | Untrack img.png — an unrelated working file swept in by mistake |

---

## The five traps — each pinned, each proven by MUTATION

I did not trust a passing test. For every trap I broke the fix and confirmed the canary screams.

| Trap | Fix | Mutation result |
|---|---|---|
| **1. `ORDER BY rowid`** | `seq BIGINT IDENTITY` + `ORDER BY seq` (3 sites) | Deleting `ORDER BY seq` → **2 ordering canaries FAIL** |
| **2. `created_at` → TIMESTAMPTZ** | `created_at` stays `String` everywhere | `information_schema` shows every `created_at` = `character varying`; `test_schema_service.py:212`'s exact `...Z` assertion passes **unmodified** |
| **3. Silent seeding race** | `_require_schema_at_head()` RAISES, before seeding, outside its `except` | Real app against an unmigrated DB **refuses to start** with an actionable error |
| **4. Boolean `int()`/`bool()` casts** | All four casts deleted | `is_verified`/`required` are real `boolean`; prod row shows `is_verified = f`, not `0` |
| **5. `INSERT OR IGNORE` asymmetry** | `on_conflict_do_nothing` on `add_alias` + `_insert_missing_fields`; the other three stores upsert | "Tidying" `do_nothing` → `do_update` → **4 canaries FAIL** (ALIAS-03 ×2, augment-only ×2) |

### The ordering canary was wrong on the first attempt — and I caught it

My first TRAP-1 canary (insert out of order → UPDATE an early row → assert declaration order)
**passed with `ORDER BY seq` deleted**. The plan predicted a worthless canary; this was one, for a
reason the plan did not anticipate.

Diagnosis (real `ctid` probe, not speculation): the UPDATE *did* relocate the tuple
(`(0,29)` → `(0,33)`), but because `description` is not indexed it was a **HOT update** — the index
entry kept pointing at the original line pointer, which merely *redirects* to the relocated tuple.
The planner chose `Index Scan using ix_canonical_field_schema_id`, so the row came back in its
original position and insertion order survived **by accident**.

Fix: force the **seq scan** Postgres legitimately picks once the table is non-trivial
(`SET LOCAL enable_indexscan/bitmapscan/indexonlyscan = off`). Then physical heap order governs, the
updated row genuinely comes back last, and the canary bites. Both halves — the UPDATE *and* the
forced seq scan — are load-bearing and documented in `_disagree_physical_order_with_insertion_order`.

---

## DR-4: one Session seam, all four paths

`persistence/engine.py` is the single rebindable, **lazily-dereferenced** seam. All four Session
paths route through it: FastAPI DI (`Depends(get_session)`), `_lifespan` seeding,
`_require_schema_at_head()`, and the CLI. Gates:

- `grep -rnE "^\s*from .*engine import .*SessionFactory" src/` → **nothing** (no import-time capture).
- `tests/test_session_isolation.py` proves the composition-root door directly, and asserts
  `engine._engine is None` — the dev engine is never even built under test.
- **Blocker-1 regression gate proven by mutation:** reintroducing `Depends`-resolution into
  `_lifespan` makes 3 un-overridden lifespan tests **FAIL**. Under the *old* test form (which
  overrode the factory) those same tests passed against the defect. The blindness is gone.

**Warning 2 (savepoint friction) never materialised.** Two Sessions on one connection, both with
`join_transaction_mode="create_savepoint"`, worked first try. No `InvalidRequestError`, no fallback.

---

## Warning 1 — how the alembic test-URL injection was resolved

**As instructed, and NOT via the vacuous route.**

- `alembic/env.py` reads `config.attributes.get("db_url") or os.environ["DATABASE_URL"]`.
  `config.attributes` is a plain dict — no ConfigParser, so the forbidden `set_main_option` `%`-
  interpolation path is sidestepped entirely.
- `tests/conftest.py::_migrate_to_head` sets `cfg.attributes["db_url"] = TEST_DATABASE_URL` before
  `command.upgrade(cfg, "head")`.
- **`os.environ["DATABASE_URL"]` was never touched.** The test process therefore *could* still reach
  the dev database — which is precisely what keeps the six-table leak gate a real proof rather than a
  tautology. It didn't reach it, and that is a finding, not a definition.

**Leak gate, first meaningful run (pristine dev DB, never seeded by a test):**

```
BEFORE:  alias 0 | canonical_field 0 | canonical_schema 0 | field_set_templates 0 | profiles 0 | users 0
         → 634 passed, 4 skipped
AFTER:   alias 0 | canonical_field 0 | canonical_schema 0 | field_set_templates 0 | profiles 0 | users 0
```

Zero movement on all six tables, `field_set_templates` included.

---

## Verification gates (all real output)

- **Postgres up + healthy** — `pg_isready` → `accepting connections`.
- **Migration from a `down -v` clean volume** — `\dt` lists all six tables + `alembic_version`.
- **`alembic check`** → `No new upgrade operations detected` (zero model/migration drift).
- **`uv run pytest`** → **634 passed, exactly 4 skipped**. The 4 skips are exactly the live-Claude
  money tests (`test_cli_run` ×2, `test_cross_domain`, `test_max_tokens_live`).
  **`ASSAYINGEST_LIVE_TESTS` was never set. No billed test calls.**
- **Postgres DOWN** → aborts in **2.07s** with a `pytest.UsageError` naming
  `sg docker -c 'docker compose up -d db'`. Never hangs (`connect_timeout=3`), never green.
- **Frontend** → 141 passed, `npm run build` clean. Untouched, as expected.
- **`grep -rni "sqlite" src/ README.md`** → nothing.
- **End-to-end on the real server** (killed PID 78623, relaunched flagless on :8000): presets seeded
  (4 rows — TRAP 3 refuted in production), real signup → `users` row, real `/api/upload` →
  `fresh-claude` mapping, 6 clear + 1 honest yellow (`unit`, conf 0.30). Rows shown via `psql`.

---

## Deviations from the plan

1. **`alembic/env.py` needed `fileConfig(..., disable_existing_loggers=False)`** *(Rule 1 — bug)*.
   The scaffold defaults to `True`, which **disabled the `assayingest` logger** when conftest ran the
   migration in-process, silently killing AUTH-03's console verification link. Caught by 3 real test
   failures. Not in the plan or research.

2. **A 4th file-layout test was deleted** (plan's DR-3 listed 3):
   `test_user_store.py::test_tmp_store_creates_table_and_touches_no_other_file` asserted on the
   SQLite file and the absence of `.assayingest/`. Both are meaningless under Postgres; its
   behavioural core was already covered. Its *intent* ("no test touches the real store") now lives at
   a better layer — the six-table leak gate.

3. **A 6th CLI test file needed porting:** `tests/test_headers_only.py` used `profiles_db=`. The plan
   listed five. Ported identically.

4. **The plan's docstring guidance collided with its own `grep -rni "sqlite"` gate.** Task 2 asked for
   comments naming `rowid`/SQLite; Task 7 demanded zero "sqlite" in `src/`. I honoured the literal
   gate and kept every warning's meaning by naming `rowid` and "the previous store" without the brand.

5. **Net-new tests (+14, none weakened):** 3 session-isolation, 5 field-set store (the plan's mandated
   coverage gap), 4 trap canaries, 3 startup schema check, plus 2 boolean/id-stability user tests.

6. **`img.png` was accidentally committed** by a `git add -A` in Task 7 (it was untracked at session
   start). Untracked again in `e0d1b76`; the file is intact on disk. My fault, and reported rather
   than buried.

**Zero assertions weakened.** `git diff` across the 14 mechanically-ported test files shows **0**
changed `assert` lines — only store construction, imports, and fixture plumbing.

---

## Outstanding (for the human)

The plan's Task 8 is a `checkpoint:human-verify`. Still needs your eyes:

1. Open <http://localhost:8000> — confirm the field-set picker is **populated**, not blank.
2. Sign in as `curator@example.com`, upload a synthetic file, confirm a mapping — yellow flags and
   the confirm gate should behave exactly as they did on SQLite.
3. Restart the app and confirm your data is **still there** (the named volume persists).

The server is running on :8000 against Postgres now.

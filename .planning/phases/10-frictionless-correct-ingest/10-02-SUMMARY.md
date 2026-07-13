---
phase: 10-frictionless-correct-ingest
plan: 02
subsystem: persistence
tags: [postgres, alembic, soft-delete, tombstone, schema-store, sql-injection, tdd]

# Dependency graph
requires: []
provides:
  - "alembic migration 8d7f8c21e1cd -- removed_at/removed_by columns + partial unique indexes (uq_canonical_field_live, uq_alias_live)"
  - "SchemaStore.update_field(schema_id, field_name, field) -> Schema"
  - "SchemaStore.remove_field(schema_id, field_name, *, removed_by, removed_at) -> Schema"
  - "SchemaStore.remove_alias(schema_id, field_name, vendor, source_column, *, removed_by, removed_at) -> None"
affects: [10-frictionless-correct-ingest plan 03 (HTTP edit endpoints), plan 04, plan 06 (Schemas page UI)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Soft delete via tombstone columns (removed_at/removed_by, String ISO-8601, never TIMESTAMPTZ) instead of physical DELETE (D-10-15)."
    - "Partial unique indexes (postgresql_where=text('removed_at IS NULL')) so a tombstoned row never permanently occupies its unique key -- required for ON CONFLICT DO NOTHING re-adds to work (T-10-09)."
    - "Four-query structural filtering: every SchemaStore read path funnels through _entity_to_schema/_aliases_for_field/list_aliases_for/_canonical_field_id, so filtering removed_at IS NULL in exactly those four covers every caller with zero per-caller filter code."
    - "One commit per cascading write: remove_field tombstones dependent aliases and the field itself in the same transaction before a single commit()."

key-files:
  created:
    - alembic/versions/8d7f8c21e1cd_soft_delete_canonical_field_and_alias.py
    - tests/test_schema_store_tombstones.py
  modified:
    - src/assayingest/persistence/models.py
    - src/assayingest/learning/schema_store.py
    - src/assayingest/learning/postgres_schema_store.py

key-decisions:
  - "index_where fix (on_conflict_do_nothing's index_where matching the now-partial indexes) was folded into Task 1's commit rather than deferred to Task 3, because dropping the full UNIQUE constraints alone (Task 1's literal scope) broke the pre-existing tests/test_schema_store.py suite immediately -- Postgres raises 'no unique or exclusion constraint matching the ON CONFLICT specification' when an ON CONFLICT target no longer matches any index. This is a Rule 3 (auto-fix blocking issue) deviation, not a scope change: it is exactly the fix Task 3's own action text (3c) already specified for these two lines, just applied one task earlier so Task 1's own acceptance criterion ('the entire existing test_schema_store.py is still green with no edits') could actually be verified true."
  - "_canonical_field_id (used by add_alias, update_field, remove_field, remove_alias) now excludes tombstoned fields structurally -- a double-remove or an update/alias-add against a tombstoned field name correctly raises ValueError via the existing 'field not found' path, with no separate tombstone-check branch needed."
  - "remove_field's alias cascade runs BEFORE the field's own tombstone UPDATE, both inside one transaction ending in a single commit() -- a partial cascade (aliases tombstoned but the field left live, or vice versa) is structurally impossible."

requirements-completed: [INGEST-05]

coverage:
  - id: D1
    description: "Removing a canonical field or alias marks it removed (who + when) and keeps the physical row -- never a DELETE"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_remove_field_hides_it_from_every_read_but_keeps_the_physical_row"
        status: pass
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_remove_alias_hides_it_from_every_read_but_keeps_the_physical_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tombstoning a field cascades to every alias hanging off it, atomically, in one transaction"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_remove_field_cascades_a_tombstone_to_every_alias_in_one_transaction"
        status: pass
    human_judgment: false
  - id: D3
    description: "All four SchemaStore reads filter tombstones structurally -- no per-caller filter code needed anywhere downstream"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py (16 tests, all reads exercised via get_schema/list_schemas/list_aliases_for)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A tombstoned field/alias can be re-added and becomes live again via the partial unique indexes -- the load-bearing trap this plan exists to close"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_a_tombstoned_alias_can_be_re_added_and_becomes_live_with_new_provenance"
        status: pass
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_a_tombstoned_field_can_be_re_added_via_add_or_update_fields_and_becomes_live"
        status: pass
    human_judgment: false
  - id: D5
    description: "update_field is a genuine UPDATE, scoped by schema_id (SCHEMA-04), never crossing into a different Schema's same-named field"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_update_field_overwrites_stored_constraints"
        status: pass
      - kind: unit
        ref: "tests/test_schema_store_tombstones.py#test_update_field_never_touches_a_same_named_field_in_a_different_schema"
        status: pass
    human_judgment: false

duration: ~12min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 02: Crosswalk Soft Delete + SchemaStore Edit Methods Summary

**Alembic migration adds `removed_at`/`removed_by` tombstone columns and replaces both full UNIQUE constraints with partial unique indexes (`WHERE removed_at IS NULL`); `SchemaStore` gains `update_field`/`remove_field`/`remove_alias`, with the field-removal cascade tombstoning dependent aliases atomically and all four store reads filtering tombstones structurally.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-07-12
- **Tasks:** 3
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- New Alembic migration `8d7f8c21e1cd` (revises `1403186caa00`): adds `removed_at`/`removed_by` (String, nullable) to `canonical_field` and `alias`; drops the two full `UniqueConstraint`s (`canonical_field_schema_id_name_key`, `alias_canonical_field_id_vendor_source_column_key`, names read directly off the live database, not guessed); creates `uq_canonical_field_live` and `uq_alias_live` as partial unique indexes (`postgresql_where=text("removed_at IS NULL")`). Verified reversible: `upgrade head` -> `downgrade -1` -> `upgrade head` round-trips cleanly on both the dev and test databases.
- `persistence/models.py`: the module docstring's "three pinned column choices" note is extended to name `removed_at` as following the SAME String-not-TIMESTAMPTZ rule as `created_at`, so a future reader does not "modernize" it.
- Discovered and fixed a genuine blocking issue during Task 1's own verification (see Deviations): dropping the full UNIQUE constraints alone broke every existing `add_alias`/`_insert_missing_fields` call, because `ON CONFLICT (col...) DO NOTHING` cannot match a partial index without a matching `index_where`. Fixed inline as part of Task 1's commit.
- `SchemaStore` ABC gains three abstract methods -- `update_field`, `remove_field`, `remove_alias` -- each documented with the exact invariant it upholds; the class docstring now states the augment-vs-edit rule precisely (a machine may only add; only a human, through the edit path, may update or remove, and every removal is a tombstone carrying who and when).
- `PostgresSchemaStore` implements all three with SQLAlchemy Core `update()`, bound parameters, `schema_id`-scoped WHERE clauses. `remove_field`'s cascade (tombstone every live alias, THEN the field) runs as two `execute()` calls inside one transaction ending in a single `commit()` -- a partial cascade is structurally impossible.
- The four read paths every caller in the app funnels through -- `_entity_to_schema`, `_aliases_for_field`, `list_aliases_for` (both the alias's own and its field's `removed_at`), and `_canonical_field_id` -- each now filter `removed_at IS NULL`. This is the structural payoff: every downstream consumer (Schemas page, master-map export, Python-first alias match, mapper field list, learning-store lookup, reconcile) is covered with zero per-caller filter code, verified by the fact that no file outside `persistence/`, the two store files, the migration, and the two test files was touched.
- 16 new tests in `tests/test_schema_store_tombstones.py`: tombstone-not-delete (physical row survives with actor+timestamp) for both field and alias, the field->alias cascade, `ValueError` on every miss (unknown name, already-tombstoned, unknown alias pair), the two re-add/partial-index traps (field and alias), `update_field`'s constraint overwrite and rename-preserves-aliases behavior, three dedicated SCHEMA-04 isolation tests (one per new method), `update_field`'s two `ValueError` paths (tombstoned field, cross-schema name), and a SQL-injection round-trip test extending the existing idiom to all three new methods.

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration + tombstone columns + partial unique indexes** - `25737fc` (feat) -- includes the index_where fix to the two pre-existing `on_conflict_do_nothing` calls (see Deviations)
2. **Task 2: Failing tests for tombstone semantics on every store read** - `d733ad6` (test) -- 16 tests, all RED with `AttributeError` (methods not yet implemented)
3. **Task 3: SchemaStore ABC + Postgres implementation until GREEN** - `9399b26` (feat)

_TDD Gate Compliance: `test(10-02)` commit (`d733ad6`) precedes the `feat(10-02)` commit that implements the tested behavior (`9399b26`) -- RED then GREEN, verified in git log order. Task 1's `feat(10-02)` commit precedes the RED commit because it is infrastructure (migration + schema columns), not an implementation of the behavior the new tests exercise -- exactly the plan's own stated task ordering (migration, then RED tests, then GREEN implementation)._

## Files Created/Modified

- `alembic/versions/8d7f8c21e1cd_soft_delete_canonical_field_and_alias.py` - New migration: 4 columns, 2 dropped unique constraints, 2 new partial unique indexes, reversible downgrade
- `src/assayingest/persistence/models.py` - `removed_at`/`removed_by` on `CanonicalFieldRow`/`AliasRow`; `UniqueConstraint` replaced by `Index(..., postgresql_where=text("removed_at IS NULL"))` on both rows
- `src/assayingest/learning/schema_store.py` - `update_field`/`remove_field`/`remove_alias` added to the ABC, each with an invariant-stating docstring; class docstring updated for the augment-vs-edit rule
- `src/assayingest/learning/postgres_schema_store.py` - the three new method implementations; four read-path tombstone filters; `index_where` added to both existing `on_conflict_do_nothing` calls
- `tests/test_schema_store_tombstones.py` - 16 new tests (created)

## Decisions Made

- **The index_where fix moved from Task 3 to Task 1** (documented above under key-decisions) -- a Rule 3 auto-fix, not a scope change, since Task 1's own acceptance criterion (existing suite green with no edits) could not otherwise be satisfied, and Task 3's action text already specified this exact fix for these two call sites.
- **`_canonical_field_id` is the single tombstone gate for all four new/existing write paths** (`add_alias`, `update_field`, `remove_field`, `remove_alias`) -- excluding tombstoned fields there means every one of those callers gets "field not found" `ValueError` semantics on a tombstoned target for free, with no separate `if row.removed_at: raise` branch duplicated four times.
- **`remove_field`'s cascade order is aliases-then-field, not field-then-aliases** -- both statements execute before the single `commit()`, so the two orderings are equivalent for correctness, but aliases-first was chosen to match the plan's literal action text and to keep the "resolve the field id via `_canonical_field_id`, which now excludes tombstoned fields" framing intact for a double-remove.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `on_conflict_do_nothing` needed `index_where` immediately, not deferred to Task 3**
- **Found during:** Task 1's own verification step (`uv run pytest tests/test_schema_store.py -q`, run per Task 1's acceptance criteria before moving to Task 2)
- **Issue:** Dropping the two full `UniqueConstraint`s and replacing them with partial unique indexes (Task 1's literal scope: `persistence/models.py` + migration only) broke every pre-existing test that calls `add_alias` or `add_or_update_fields`. Postgres raised `psycopg.errors.InvalidColumnReference: there is no unique or exclusion constraint matching the ON CONFLICT specification` -- `ON CONFLICT (col1, col2) DO NOTHING` cannot match a partial index unless the same `WHERE` predicate is named on the `ON CONFLICT` clause itself.
- **Fix:** Added `index_where=AliasRow.removed_at.is_(None)` / `index_where=CanonicalFieldRow.removed_at.is_(None)` to the two existing `on_conflict_do_nothing(...)` calls in `postgres_schema_store.py` -- exactly the fix the plan's own Task 3 action text (item 3c) already specifies for these two lines, applied one task earlier because Task 1's acceptance criteria required the pre-existing suite to be green as a verification gate before Task 2 could proceed.
- **Files modified:** `src/assayingest/learning/postgres_schema_store.py`
- **Commit:** `25737fc` (folded into Task 1's commit, not a separate one, since it was required for Task 1's own stated acceptance criteria)

None of Rules 1/2/4 applied -- no bugs found, no missing critical functionality beyond what the plan specified, and no architectural change was needed.

## Issues Encountered

None beyond the index_where deviation above, which was resolved inline before Task 1's commit.

## User Setup Required

None -- no external service configuration required. The migration was applied to both the dev database and (via `conftest.py`'s session-scoped `_migrate_to_head`) the test database as part of this plan's own verification.

## Next Phase Readiness

- `SchemaStore.update_field`/`remove_field`/`remove_alias` are ready for Plan 03/04's HTTP edit endpoints (`PATCH`/`DELETE` routes gated by `require_verified_user`, per 10-RESEARCH.md's recommended shape) -- callers must be aware of the `ValueError` conditions: `update_field` and `remove_field` raise when `field_name` is absent from the named `schema_id` OR already tombstoned; `remove_alias` raises when no LIVE alias matches `(field_name, vendor, source_column)` in that schema. None of the three ever raise a bare `IntegrityError` or silently no-op.
- Every SchemaStore read path (`get_schema`, `list_schemas`, `list_aliases_for`) already filters tombstones structurally -- Plan 03/04's service/API layer needs NO additional filtering; a tombstoned field/alias is invisible by construction.
- This plan touched exactly the files declared in `files_modified` (migration, `persistence/models.py`, the two store files, two test files) -- confirmed via `git diff --stat` on every commit. `service.py`, `api/`, and the frontend remain completely untouched.
- No blockers.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 3 task commit hashes (25737fc, d733ad6, 9399b26) confirmed present in git log. Full suite re-verified green: 686 passed, 4 skipped (670 baseline + 16 new tombstone tests, zero regressions).

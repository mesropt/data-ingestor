---
phase: 07-canonical-schema-vendor-alias-crosswalk
plan: 03
subsystem: api
tags: [crosswalk, alias, provenance, confirm, fastapi, sqlite, tdd]

# Dependency graph
requires:
  - phase: 07-01
    provides: Alias/Schema domain models + SchemaStore.add_alias INSERT-OR-IGNORE idempotency
  - phase: 07-02
    provides: service.promote + get_schema_store DI + SqliteSchemaStore
  - phase: 06
    provides: require_verified_user + confirmed_by (server-resolved user.email) threaded into confirm
provides:
  - service.confirm additively records manual, user-attributed crosswalk aliases when a target Schema + vendor are supplied
  - ConfirmRequest optional schema_name + vendor fields (backward compatible)
  - POST /api/confirm accretes the crosswalk from the same confirm the curator already runs
affects: [07-04, master-map export/import, crosswalk UI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive keyword-only seam: absent params => nothing written (mirrors Phase 06 confirmed_by threading)"
    - "Crosswalk write gated behind confirm success and stamped with server-resolved actor, never a client body field"

key-files:
  created:
    - tests/test_confirm_records_aliases.py
    - tests/api/test_confirm_aliases_route.py
  modified:
    - src/assayingest/service.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/routes/confirm.py

key-decisions:
  - "All three of schema_store/target_schema_name/vendor must be present for any alias write; any absent => no-op (CLI path and existing tests unchanged)."
  - "provenance_actor is always the caller-supplied confirmed_by (server-resolved user.email on the API path), never re-derived and never a client body field."
  - "Aliases are recorded only AFTER the coverage+validate+is_ready gate passes; a rejected mapping writes nothing."
  - "Recording relies on the 07-01 store's idempotent INSERT-OR-IGNORE, so re-confirm keeps first-seen provenance (ALIAS-03)."

patterns-established:
  - "Pattern: _record_aliases private helper keeps service.confirm at a single level of abstraction."
  - "Pattern: additive optional wire fields (default None) extend a request contract without reshaping it."

requirements-completed: [ALIAS-04, ALIAS-01, ALIAS-02, ALIAS-03]

coverage:
  - id: D1
    description: "Confirming a reviewed mapping with a target Schema + vendor records each resolved source column as a manual, user-attributed alias on the matching canonical field."
    requirement: "ALIAS-04"
    verification:
      - kind: unit
        ref: "tests/test_confirm_records_aliases.py#test_confirm_records_manual_actor_aliases_for_each_resolved_column"
        status: pass
      - kind: integration
        ref: "tests/api/test_confirm_aliases_route.py#test_confirm_with_schema_and_vendor_records_manual_server_attributed_aliases"
        status: pass
    human_judgment: false
  - id: D2
    description: "A confirm with no target Schema / no vendor (the CLI path and current UI default) writes no alias; existing confirm behavior is unchanged."
    requirement: "ALIAS-04"
    verification:
      - kind: unit
        ref: "tests/test_confirm_records_aliases.py#test_confirm_without_schema_or_vendor_records_nothing"
        status: pass
      - kind: integration
        ref: "tests/api/test_confirm_aliases_route.py#test_confirm_without_schema_name_or_vendor_records_no_alias"
        status: pass
      - kind: integration
        ref: "tests/api/test_confirm_gate.py (full existing confirm-route suite, unchanged)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A recorded alias's provenance actor is the server-resolved user.email, never a client body field; recording is idempotent and gated behind confirm success."
    requirement: "ALIAS-03"
    verification:
      - kind: integration
        ref: "tests/api/test_confirm_aliases_route.py#test_confirm_with_schema_and_vendor_records_manual_server_attributed_aliases (asserts actor=curator@example.com despite client-sent provenance_actor=attacker@evil.com)"
        status: pass
      - kind: unit
        ref: "tests/test_confirm_records_aliases.py#test_confirm_records_aliases_idempotently_keeping_first_provenance"
        status: pass
      - kind: unit
        ref: "tests/test_confirm_records_aliases.py#test_confirm_records_no_alias_when_the_gate_rejects_a_yellow_field"
        status: pass
    human_judgment: false

# Metrics
duration: 5min
completed: 2026-07-11
status: complete
---

# Phase 07 Plan 03: Confirm Records Crosswalk Aliases Summary

**The existing curator confirm now additively accretes the governed crosswalk — each resolved (canonical field ← source column) becomes a manual, user-attributed Alias when a target Schema + vendor are supplied, and nothing at all when they are not (ALIAS-04).**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-11T14:37:38Z
- **Completed:** 2026-07-11T14:42Z
- **Tasks:** 2 completed
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `service.confirm` gained keyword-only additive params `schema_store` / `target_schema_name` / `vendor`; a new `_record_aliases` helper upserts one `manual` `Alias` per resolved source column with `provenance_actor=confirmed_by`, recorded only after the P1 gate passes.
- `ConfirmRequest` gained optional `schema_name` + `vendor` (default `None`), and `POST /api/confirm` now threads `get_schema_store` + those fields into the service call — the alias actor flows from the already-present server-resolved `user.email`, never a body field.
- Proven purely additive: the full existing confirm surface (service `test_service.py` + all `tests/api`) stays green, and the whole suite is 560 passed / 4 skipped.

## Task Commits

1. **Task 1 (RED): failing test for confirm recording aliases** - `4596d43` (test)
2. **Task 1 (GREEN): service.confirm records crosswalk aliases** - `85d239f` (feat)
3. **Task 2 (RED): failing route test for confirm recording aliases** - `5c9fbdd` (test)
4. **Task 2 (GREEN): confirm route records crosswalk aliases** - `2f731df` (feat)

_TDD RED→GREEN gates observed for both tasks (test commit precedes feat commit)._

## Files Created/Modified
- `tests/test_confirm_records_aliases.py` - Service-level ALIAS-04 tests (records manual+actor aliases; inferred-only field records nothing; no-schema/no-vendor writes nothing; idempotent first-seen provenance; no write on NotReadyError/FieldCoverageError).
- `tests/api/test_confirm_aliases_route.py` - TestClient tests: schema_name+vendor records server-attributed manual aliases (client-sent actor ignored); no schema_name/vendor writes nothing.
- `src/assayingest/service.py` - Additive keyword-only params on `confirm` + `_record_aliases` helper.
- `src/assayingest/api/wire.py` - Optional `schema_name` / `vendor` on `ConfirmRequest`.
- `src/assayingest/api/routes/confirm.py` - `get_schema_store` dependency threaded; body fields + server actor passed to `service.confirm`.

## Decisions Made
- All three of `schema_store` / `target_schema_name` / `vendor` must be present for any alias write; any absent → no-op. This keeps the CLI path and every existing confirm test byte-identical.
- `provenance_actor` is always the caller-supplied `confirmed_by` (server-resolved `user.email` on the API path), never re-derived, never a client body field — a client-sent `provenance_actor` is silently ignored (extra keys dropped).
- Aliases are recorded only after the coverage+validate+is_ready gate passes; a `NotReadyError`/`FieldCoverageError` path writes nothing.
- Idempotency delegated to the 07-01 store's `INSERT OR IGNORE`; re-confirm keeps first-seen provenance (ALIAS-03).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Threat Model Compliance
- **T-07-10 (Spoofing):** provenance_actor = server-resolved user.email; a client-supplied `provenance_actor` is ignored. Verified by the route test asserting `curator@example.com` despite `attacker@evil.com` in the body.
- **T-07-11 (Tampering — write on rejected mapping):** `_record_aliases` runs only after the gate passes; verified by the NotReadyError and FieldCoverageError tests asserting an empty store.
- **T-07-12 (Repudiation — overwritten provenance):** idempotent INSERT-OR-IGNORE; verified by the double-confirm test keeping `first@b.com`.
- **T-07-13 (EoP — unauthenticated alias write):** route inherits the existing `require_verified_user` gate; no new unauthenticated surface. Existing 401/403 auth-gate tests remain green.
- **T-07-SC:** no new package installs — additive edits to existing modules only.

## Self-Check: PASSED

- All 2 created files and 3 modified files present on disk.
- All 4 task commits (`4596d43`, `85d239f`, `5c9fbdd`, `2f731df`) present in git history.
- Full suite: 560 passed, 4 skipped (live API-key tests) — existing confirm/money-shot tests unchanged.

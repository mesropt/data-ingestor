---
phase: 10-frictionless-correct-ingest
plan: 04
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, governance, soft-delete, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 02
    provides: "SchemaStore.update_field/remove_field/remove_alias tombstones + four structurally-filtered read paths"
  - phase: 10-frictionless-correct-ingest plan 03
    provides: "field_set_from_schema / Python-first pre-fill escalation wiring (unrelated file scope, satisfies wave ordering)"
provides:
  - "POST /api/schemas/{name}/fields -- add a canonical field (verified-user)"
  - "PATCH /api/schemas/{name}/fields/{field_name} -- edit constraints / rename (verified-user)"
  - "DELETE /api/schemas/{name}/fields/{field_name} -- tombstone a field + cascade (verified-user)"
  - "POST /api/schemas/{name}/fields/{field_name}/aliases -- manual alias (verified-user)"
  - "DELETE /api/schemas/{name}/fields/{field_name}/aliases?vendor=&source_column= -- tombstone an alias (verified-user)"
  - "service.add_schema_field / update_schema_field / remove_schema_field / add_schema_alias / remove_schema_alias"
  - "service.SchemaFieldNotFoundError (-> 404)"
  - "wire.SchemaFieldIn, wire.SchemaAliasIn (neither carries an actor field, by design)"
  - "learning.seed.seed_schemas(store) -> list[str] -- the 4 presets as governed Schemas at startup"
affects: [10-frictionless-correct-ingest plan 06 (Schemas page UI), 10-frictionless-correct-ingest plan 07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit edit routes live BESIDE the augment-only master-map import route, never through it (D-07-04/D-10-12) -- five new routes, zero changes to import_master_map's behavior."
    - "Every field dict (POST/PATCH) is parsed through the SAME fields.loader.from_dict -> _validated_name guard a CLI-loaded or promoted field gets, wrapped in a single-field FieldSet envelope ({\"fields\": [field_dict]}) since from_dict is a FieldSet loader, not a single-Field one -- never a second, weaker route-layer check."
    - "removed_by/actor are keyword-only and required on every service edit function; the timestamp is always minted server-side (datetime.now(UTC).isoformat()), never taken from a caller -- structurally prevents a missing-attribution removal."
    - "SchemaFieldNotFoundError wraps the store's own ValueError (whose message already names the exact consequence) so a route maps it to 404 instead of letting a bare ValueError surface as a 500."
    - "seed_schemas mirrors seed_presets' insert-if-absent-by-NAME-only discipline (T-e0e-02) onto a SchemaStore -- never add_or_update_fields on an existing Schema, so a curator's tombstoned/edited field structurally cannot be resurrected by a restart."

key-files:
  created:
    - tests/api/test_schema_edit_routes.py
  modified:
    - src/assayingest/service.py
    - src/assayingest/api/routes/schemas.py
    - src/assayingest/api/wire.py
    - src/assayingest/learning/seed.py
    - src/assayingest/api/app.py
    - tests/api/test_preset_seeding.py

key-decisions:
  - "SchemaNotFoundError's message was generalized from the import_master_map-specific 'Cannot import master map: no Schema named ... to augment.' to the action-agnostic 'No Schema named ... exists.', since the exception is now raised from six call sites instead of one and CLAUDE.md requires an error to describe the actual consequence, not a copy-pasted unrelated one. No test asserts the exact message text (only status_code), verified via full-suite green + a diff showing import_master_map's own body is byte-for-byte untouched."
  - "add_schema_field's MAX_FIELDS(50) cap check lives in service.py, checked against the Schema's current LIVE field count (len(schema.fields), already tombstone-filtered by the store) BEFORE any field is built -- distinct from fields.loader.from_dict's own 50-field-per-FieldSet cap, which never fires here since exactly one field is ever wrapped per call."
  - "add_schema_alias reuses store.add_alias directly (the same manual-provenance path confirm's _record_aliases already exercises) rather than a second alias-recording mechanism -- provenance_kind='manual', provenance_actor=the server-resolved user.email, timestamp minted in the service function."
  - "seed_schemas skips a Schema by NAME alone, with zero field-level write call against an already-present Schema under any circumstance -- the structural guarantee behind 'a tombstoned field is never resurrected by a restart', verified by a dedicated test that tombstones a field, reseeds, and asserts it stays gone."

requirements-completed: [INGEST-05, INGEST-06]

coverage:
  - id: D1
    description: "A verified user can add, edit, and remove a Schema's canonical fields and their vendor aliases through five explicit endpoints, each gated by require_verified_user (401 signed-out, 403 unverified, before any store work)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/api/test_schema_edit_routes.py (32 tests: happy paths, 10 auth-gate tests across all 5 routes/both tiers, validation, misses, SCHEMA-04 cross-schema isolation)"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /api/schemas/{name}/master-map stays byte-for-byte augment-only (D-07-04) -- the edit path is a separate route, never a widening of the augment path"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/api/test_schema_edit_routes.py#test_the_master_map_import_route_is_still_augment_only"
        status: pass
      - kind: unit
        ref: "tests/api/test_schemas_routes.py (11 pre-existing tests, unmodified, all green)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A removal records who removed it and when, from the server-resolved session user, never a client body field"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/api/test_schema_edit_routes.py#test_post_alias_records_manual_provenance_from_the_signed_in_user_ignoring_body_actor"
        status: pass
    human_judgment: false
  - id: D4
    description: "The four shipped presets exist as Schemas on a fresh start, idempotent and id-stable across restarts, never overwriting a curator's Schema or resurrecting a tombstoned field"
    requirement: "INGEST-06"
    verification:
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_schemas_on_an_empty_store_seeds_all_4_with_zero_aliases"
        status: pass
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_schemas_is_idempotent_and_id_stable"
        status: pass
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_schemas_leaves_a_curator_created_schema_under_a_preset_name_untouched"
        status: pass
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_schemas_does_not_resurrect_a_tombstoned_field_on_restart"
        status: pass
      - kind: integration
        ref: "tests/api/test_preset_seeding.py#test_get_schemas_returns_the_4_preset_schemas_after_a_fresh_startup"
        status: pass
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_a_bad_preset_yaml_still_does_not_brick_startup"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 04: Explicit Governed-Schema Edit Endpoints + Presets-as-Schemas Seeding Summary

**Five verified-user-gated HTTP routes (add/edit/remove a canonical field, add/remove a vendor alias) backed by five new `service.py` functions delegating to Plan 02's tombstone-aware `SchemaStore` methods, plus `seed_schemas()` re-targeting the four shipped presets from field-set-template rows onto governed Schemas at every startup -- the augment-only `POST .../master-map` route is provably untouched.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-12
- **Tasks:** 3
- **Files modified:** 7 (1 created, 6 modified)

## Accomplishments

- `tests/api/test_schema_edit_routes.py` (new, 32 tests): every happy path for the five routes, one auth-gate test per route per tier (10 parametrized cases proving 401 signed-out / 403 unverified, nothing persisted in either case), input validation (control-character field names, an invalid `type`, the `MAX_FIELDS` cap naming the limit in its 422 detail), every documented miss (unknown Schema per route, unknown/already-tombstoned field, unknown alias), two dedicated SCHEMA-04 cross-schema isolation tests (PATCH and DELETE), and the load-bearing `test_the_master_map_import_route_is_still_augment_only` regression pin.
- `service.py` gained a `# --- Phase 10: explicit governed-Schema edit (D-10-12) ---` section: `add_schema_field`/`update_schema_field`/`remove_schema_field`/`add_schema_alias`/`remove_schema_alias`, each resolving the Schema by name (`SchemaNotFoundError` on a miss), routing any incoming field dict through the shared `fields.loader.from_dict` guard, and wrapping the store's own `ValueError` into a new `SchemaFieldNotFoundError` a route maps to 404. `removed_by`/`actor` are keyword-only and required on every function that attributes a change; every timestamp is minted server-side.
- `api/wire.py` gained `SchemaFieldIn` (`field: dict`) and `SchemaAliasIn` (`vendor: str`, `source_column: str`) -- neither carries an actor field, by design (T-07-06); the DELETE-alias route takes `vendor`/`source_column` as query params instead of a body.
- `api/routes/schemas.py` gained the five routes as thin adapters (deserialize -> service -> map typed error/result to HTTP), each depending on `Depends(require_verified_user)` unconditionally. A restating comment was added directly above the existing `POST .../master-map` route naming D-07-04; the route's own body is byte-for-byte unchanged (verified via `git diff`).
- `learning/seed.py` gained `seed_schemas(store: SchemaStore) -> list[str]`, mirroring `seed_presets`' insert-if-absent-by-name discipline onto a `SchemaStore`: `create_schema(name, field_set.fields, None)` only when the name is genuinely absent -- never a field-level write against an already-present Schema, structurally preventing a curator's tombstoned/edited field from ever being resurrected by a restart.
- `api/app.py::_lifespan` now calls `seed_schemas(PostgresSchemaStore(session))` immediately after `seed_presets`, inside the SAME warn-not-crash `try`/`except`; `_require_schema_at_head()` stays outside and loud, unchanged. The docstring was extended to name both seeding steps.
- `tests/api/test_preset_seeding.py` gained 6 tests: the empty-store 4-Schema seed with zero aliases, idempotent/id-stable restart, a curator-created Schema under a preset name left completely untouched, a tombstoned field never resurrected by a restart, the fresh-startup `GET /api/schemas` HTTP-level gate (INGEST-06, mirrors the field-set-store regression gate with no dependency override), and a T-e0e-03-style malformed-preset warn-not-crash pin (`monkeypatch.setattr(seed_module, "load_presets", ...)` affects both seeding calls, since they share the same imported name).

## Task Commits

Each task was committed atomically (TDD RED then GREEN per task):

1. **Task 1: Failing route tests for the explicit Schema edit surface** - `f3e6981` (test) -- 32 tests, 31 genuinely RED (404 "Not Found" from FastAPI, the routes do not exist), 1 pre-passing (the augment-only invariant pin, which is a regression guard for existing, untouched behavior -- not a test of new functionality)
2. **Task 2: Service functions + routes + wire models until GREEN** - `341b4b1` (feat)
3. **Task 3: Seed the four presets as Schemas at startup** - test `66c9819` (RED: `ImportError`, `seed_schemas` did not exist), feat `13220fd` (GREEN)

_TDD Gate Compliance: every task's `test(10-04)` commit precedes its `feat(10-04)` commit, verified in git log order for both TDD tasks (Task 1/2 pair and Task 3's own pair)._

## Files Created/Modified

- `tests/api/test_schema_edit_routes.py` - 32 new tests covering all five edit routes (created)
- `src/assayingest/service.py` - `SchemaFieldNotFoundError`, `_resolve_schema`, `_field_from_raw`, `add_schema_field`/`update_schema_field`/`remove_schema_field`/`add_schema_alias`/`remove_schema_alias`; `SchemaNotFoundError`'s message generalized (see Decisions)
- `src/assayingest/api/routes/schemas.py` - five new routes; a restating comment above the untouched `POST .../master-map` route
- `src/assayingest/api/wire.py` - `SchemaFieldIn`, `SchemaAliasIn`
- `src/assayingest/learning/seed.py` - `seed_schemas(store: SchemaStore) -> list[str]`; module docstring extended to describe both seeding steps
- `src/assayingest/api/app.py` - `_lifespan` calls `seed_schemas` beside `seed_presets`, inside the same warn-not-crash block; docstring extended
- `tests/api/test_preset_seeding.py` - 6 new tests for `seed_schemas` (store-level + HTTP-level)

## Decisions Made

- `SchemaNotFoundError`'s message generalized from an `import_master_map`-specific sentence to an action-agnostic one, since the exception is now shared across six raise sites (Phase 07's import plus five Phase 10 edit functions) and CLAUDE.md requires an error message to describe the actual consequence, never a copy-pasted unrelated one. No test anywhere asserts the exact message text (only `status_code`), confirmed by running the full suite green and diffing `import_master_map`'s own body (unchanged).
- The `MAX_FIELDS` (50) cap for `add_schema_field` is enforced in `service.py` against the Schema's current LIVE field count, distinct from `fields.loader.from_dict`'s own per-`FieldSet` 50-field cap (which never fires here, since exactly one field is ever wrapped per call).
- `add_schema_alias` calls `store.add_alias` directly -- the same manual-provenance mechanism `confirm`'s `_record_aliases` already exercises -- rather than introducing a second alias-recording path.
- `seed_schemas` skips by Schema NAME alone with zero field-level write against an existing Schema under any circumstance, verified by a dedicated regression test (tombstone a field, reseed, assert it stays gone).

## Deviations from Plan

None beyond the `SchemaNotFoundError` message generalization documented above (a Rule 1-adjacent correctness tidy-up required by CLAUDE.md's own error-message convention once the exception became shared across six call sites, not an architectural change and not a behavior change to any existing route).

## Issues Encountered

None. All three tasks executed RED-then-GREEN on the first attempt; the full suite was green throughout with zero regressions (763 -> 769 passed as the two TDD tasks landed, +32 then +6 new tests, 4 skipped unchanged throughout).

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- Final public surface for Plan 06 (Schemas page UI) to build `lib/api.ts` against, exactly:
  - `POST /api/schemas/{name}/fields` body `{"field": {...}}` -> `SchemaOut`
  - `PATCH /api/schemas/{name}/fields/{field_name}` body `{"field": {...}}` -> `SchemaOut` (field's `name` may differ from the URL segment -- the rename affordance)
  - `DELETE /api/schemas/{name}/fields/{field_name}` -> `SchemaOut`
  - `POST /api/schemas/{name}/fields/{field_name}/aliases` body `{"vendor": str, "source_column": str}` -> `SchemaOut`
  - `DELETE /api/schemas/{name}/fields/{field_name}/aliases?vendor=&source_column=` -> `SchemaOut`
  - Error shape on every route: 404 `{"detail": "..."}` for an unknown Schema/field/alias, 422 `{"detail": "..."}` for an invalid field name/type or the `MAX_FIELDS` cap, 401/403 for the auth gate -- identical to every existing Schema route's error contract.
  - `service.SchemaFieldNotFoundError` (-> 404) joins `service.SchemaNotFoundError` (-> 404) as the two typed misses a route must catch.
- A fresh `docker compose up` + `alembic upgrade head` + boot yields 4 selectable Schemas immediately (INGEST-06) -- Plan 06's Upload-screen Schema selector has something to show on a truly cold start.
- `git diff --stat` for this plan's commits touches exactly the 7 files declared in `files_modified`; `import_master_map` and its route's own logic are untouched (only a restating comment above the route, and the shared exception's message text).
- No blockers.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 7 created/modified files confirmed present on disk; all 4 task commit hashes (f3e6981, 341b4b1, 66c9819, 13220fd) confirmed present in git log. Full suite re-verified green: 769 passed, 4 skipped (731 baseline + 32 + 6 new tests, zero regressions). `tests/api/test_schemas_routes.py` confirmed byte-for-byte unmodified via `git diff HEAD~4`.

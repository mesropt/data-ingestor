---
phase: 07-canonical-schema-vendor-alias-crosswalk
plan: 02
subsystem: service + api (promote / master-map / gated schemas surface)
tags: [schema, promote, master-map, crosswalk, provenance, auth-gate, tdd, api]
status: complete
requires:
  - domain.models.Schema / CanonicalField / Alias (07-01 — master-map round-trip)
  - learning.schema_store.SchemaStore / sqlite_schema_store.SqliteSchemaStore (07-01)
  - fields.loader.from_dict (name-safety guard reused at the HTTP boundary)
  - api.deps.require_verified_user (Phase 6 — P1 governance gate)
provides:
  - service.promote / export_master_map / import_master_map (+ SchemaNotFoundError)
  - api.deps.get_schema_store (DI seam, overridable in tests)
  - api.wire.PromoteRequest / SchemaOut
  - api.routes.schemas (create/list/export/import), registered in api.app
affects:
  - Plan 07-03 (confirm-records-aliases — reuses get_schema_store + the store seam)
  - Plan 07-04 (UI — consumes /api/schemas + master-map endpoints and SchemaOut)
tech-stack:
  added: []
  patterns:
    - "Service functions decide/never render; typed exceptions name the consequence"
    - "Thin route: deserialize -> service -> map typed error to HTTP (mirrors field_sets/confirm)"
    - "DI factory get_schema_store mirrors get_profile_store/get_user_store (dependency_overrides in tests)"
    - "Wire model has NO created_by field — actor is server-resolved (T-07-06)"
    - "Augment-only import relies on store INSERT-OR-IGNORE idempotency (never overwrite/discard)"
key-files:
  created:
    - src/assayingest/api/routes/schemas.py
    - tests/test_schema_service.py
    - tests/api/test_schemas_routes.py
  modified:
    - src/assayingest/service.py
    - src/assayingest/api/deps.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/app.py
decisions:
  - "promote name = explicit name arg else field_set.name; raises ValueError when neither resolvable (domain identity, D-07-03)"
  - "import re-stamps every incoming alias as provenance_kind=from_map_file, provenance_actor=source_name; store idempotency preserves any pre-existing manual provenance (ALIAS-03, D-07-04)"
  - "source_name = envelope's declared name (envelope['name']) else the target path name — the map file's declared source, never a client-trusted actor field"
  - "SchemaNotFoundError (service) -> 404; ValueError/KeyError from a malformed envelope/field set -> 422 (mirrors field_sets/confirm typed-error mapping)"
  - "Master-map export is a plain JSON body the client saves (no streaming file) — Discretion per plan"
metrics:
  duration: ~12m
  completed: 2026-07-11
  tasks: 2
  files_created: 3
  files_modified: 4
  commits: 4
  tests_added: 19
requirements: [SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04]
---

# Phase 7 Plan 02: Promote to Schema + Master-Map Export/Import Summary

Turns a field set into a governed `Schema` and makes that Schema a portable
master-map file: a `promote` service, an augment-only master-map
`export`/`import`, and the `require_verified_user`-gated `/api/schemas` HTTP
surface — the user-facing half of the Phase 07 crosswalk backbone, built
entirely on 07-01's domain models + `SchemaStore`.

## What was built

**Task 1 — services (`service.py`)**
- `promote(field_set, *, created_by, store, name=None) -> Schema` — creates a
  governed Schema whose canonical fields ARE the field set's fields (each with
  an empty alias list), stamped `created_by`. Schema name is the explicit
  `name` arg else `field_set.name`; raises `ValueError` (naming the
  consequence) when neither is resolvable. Two differently-named field sets
  yield two isolated Schemas (SCHEMA-01/04).
- `export_master_map(schema) -> dict` — returns `schema.to_master_map()` (the
  versioned `schema_version:1` envelope, SCHEMA-02).
- `import_master_map(store, target_schema_name, envelope, *, source_name) ->
  Schema` — parses the envelope through `Schema.from_master_map` (the shared
  `fields.loader` name-safety guard, T-07-08), adds missing canonical fields
  via `add_or_update_fields`, then records each incoming alias with
  `provenance_kind="from_map_file"` / `provenance_actor=source_name`. Fields
  are added before their aliases so `add_alias` always finds its field. Relies
  on the store's INSERT-OR-IGNORE idempotency: an already-present alias keeps
  its first-seen (possibly manual) provenance — nothing is overwritten or
  deleted (SCHEMA-03, ALIAS-03 augment-never-discard). `SchemaNotFoundError`
  when the target name is unknown.

**Task 2 — gated HTTP surface**
- `deps.get_schema_store()` — DI factory returning `SqliteSchemaStore()`,
  mirroring `get_profile_store`/`get_user_store`; tests override it via
  `dependency_overrides` with a tmp-path store.
- `wire.PromoteRequest` (`name` + raw `field_set` dict, built into a validated
  `FieldSet` via `from_dict` at the route — no `created_by` field to trust)
  and `wire.SchemaOut` (`id`/`name`/`created_by`/`fields` with embedded
  aliases, the `to_master_map` shape).
- `api/routes/schemas.py` — `POST /api/schemas` (gated, `created_by =
  user.email`), `GET /api/schemas` (list), `GET /api/schemas/{name}/master-map`
  (export envelope, 404 when absent), `POST /api/schemas/{name}/master-map`
  (gated, augment import; `source_name` = the envelope's declared name).
  Typed errors map to HTTP: `SchemaNotFoundError` -> 404, malformed
  envelope/field set (`ValueError`/`KeyError`) -> 422. Registered in `app.py`.

## Invariants proven by tests

- **SCHEMA-01** — promote's canonical fields equal the field set's fields,
  each starting alias-empty, `created_by` set.
- **SCHEMA-04** — two promoted schemas share no fields or aliases; both coexist
  in `list_schemas`.
- **SCHEMA-02** — export returns the `schema_version==1` envelope; the GET
  route returns it for download.
- **SCHEMA-03 / ALIAS-03** — import adds A's missing fields+aliases into B and
  stamps `from_map_file`, while B's pre-existing manual alias on the same
  `(field, vendor, source_column)` keeps its original `manual` provenance,
  actor, and timestamp (augment-never-discard round-trip).
- **P1 gate (T-07-05)** — `POST /api/schemas` and `POST .../master-map` return
  401 signed-out and 403 unverified, persisting nothing.
- **T-07-06** — a client body `created_by` is ignored; `created_by` is the
  server-resolved `user.email`.
- **T-07-08** — an invalid field name in the posted field set is a 422 via the
  shared loader guard, nothing persisted.

## Tests

- `tests/test_schema_service.py` — 8 tests (promote isolation/naming, export
  envelope, import augment + from_map_file stamping, round-trip provenance
  preservation, unknown-target error).
- `tests/api/test_schemas_routes.py` — 11 tests (401/403 gate on both
  mutations, server-resolved created_by, 422 invalid field, list, export
  envelope + 404, import augment provenance + 404).
- Full suite: **551 passed, 4 skipped** (skips are pre-existing live-API
  tests) via `uv run python -m pytest -q`.

## TDD Gate Compliance

Both tasks followed RED→GREEN with distinct commits:
- Task 1: `test(07-02)` 2644b64 (RED) → `feat(07-02)` de21e4c (GREEN)
- Task 2: `test(07-02)` 312f5a6 (RED) → `feat(07-02)` 2c33179 (GREEN)

## Deviations from Plan

None — plan executed exactly as written. Notes on discretionary choices the
plan left open: `source_name` is derived from the envelope's declared `name`
(the map file's own source identity) falling back to the target path name;
malformed-envelope errors (`KeyError` for a missing envelope key, `ValueError`
from the loader name guard) map to 422, mirroring the existing
`field_sets.py`/`confirm.py` typed-error handling.

## Notes for later plans

- Plan 07-03 (confirm-records-aliases) reuses `deps.get_schema_store()` and the
  same store seam; it will call `store.add_alias(..., provenance_kind="manual",
  provenance_actor=confirmed_by)` — the complement of this plan's import path.
- `SchemaOut.fields` carries the full `CanonicalField.to_dict()` shape
  (constraints + embedded `aliases`), which the Plan 07-04 crosswalk selector
  can render directly.
- Master-map export is a plain JSON response body (not a streamed file
  download); the UI saves it client-side.

## Self-Check: PASSED

All created/modified files exist; all four task commits (2644b64, de21e4c,
312f5a6, 2c33179) present in history.

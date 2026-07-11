---
phase: 07-canonical-schema-vendor-alias-crosswalk
plan: 01
subsystem: domain + learning (governed schema store)
tags: [schema, crosswalk, alias, provenance, sqlite, tdd]
status: complete
requires:
  - fields.models.Field / fields.loader.from_dict (canonical-field shape + name-safety guard)
  - learning.sqlite_store._DEFAULT_DB_PATH (shared local DB file)
provides:
  - domain.models.Alias / CanonicalField / Schema (frozen dataclasses + master-map round-trip)
  - learning.schema_store.SchemaStore (repository seam ABC)
  - learning.sqlite_schema_store.SqliteSchemaStore (local SQLite impl on shared DB)
affects:
  - Phase 07 later plans (promote service, master-map export/import, confirm-records-aliases, UI)
tech-stack:
  added: []
  patterns:
    - "Repository seam (ABC) + local SQLite impl mirroring ProfileStore/FieldSetTemplateStore"
    - "Versioned JSON envelope (schema_version:1) for the downloadable master map"
    - "Boundary translators (_row_to_schema/_row_to_field/_row_to_alias) map SQLite rows to domain"
    - "Augment-only writes via INSERT OR IGNORE against UNIQUE constraints"
key-files:
  created:
    - src/assayingest/learning/schema_store.py
    - src/assayingest/learning/sqlite_schema_store.py
    - tests/test_schema_domain.py
    - tests/test_schema_store.py
  modified:
    - src/assayingest/domain/models.py
decisions:
  - "CanonicalField composes an untouched Field + parallel alias tuple (composition, not subclassing) — D-07-01"
  - "Master map is a versioned envelope {schema_version:1, id, name, created_by, created_at, fields[]} so a future VER-* milestone can bump it — D-07-01 Discretion"
  - "SchemaStore is a NEW seam on the SAME _DEFAULT_DB_PATH file, not a widening of ProfileStore — D-07-02"
  - "Alias provenance is first-seen-immutable via INSERT OR IGNORE on UNIQUE(canonical_field_id,vendor,source_column); no ON CONFLICT DO UPDATE — ALIAS-03/T-07-02"
  - "SCHEMA-04 isolation enforced structurally by schema_id/canonical_field_id foreign keys + WHERE filtering, plus PRAGMA foreign_keys=ON — never Python-side name filtering — T-07-04"
  - "from_master_map and _row_to_field both rebuild Fields through fields.loader.from_dict so imported/persisted names get the SAME name-safety guard the CLI --fields flag enforces — T-07-03"
metrics:
  duration: ~5m
  completed: 2026-07-11
  tasks: 2
  files_created: 4
  files_modified: 1
  commits: 4
  tests_added: 22
requirements: [SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03]
---

# Phase 7 Plan 01: Canonical Schema Store Backbone Summary

Pure-domain `Schema` / `CanonicalField` / `Alias` frozen dataclasses with a versioned JSON master-map round-trip, plus a `SchemaStore` repository seam and `SqliteSchemaStore` implementation on the same local SQLite file the profile/field-set/user stores already use — the governed, auditable crosswalk store every later Phase 07 plan builds on.

## What was built

**Task 1 — Domain models (`domain/models.py`)**
- `Alias` (frozen): `vendor`, `source_column`, `provenance_kind: Literal["manual","from_map_file"]`, `provenance_actor`, `created_at`, optional `confidence`/`note`. `to_dict()` emits exactly the five provenance keys plus optionals only when set; `Alias(**d)` round-trips losslessly.
- `CanonicalField` (frozen): composes an existing `fields.models.Field` (left entirely untouched — no subclassing) plus an `aliases: tuple[Alias, ...]`. `to_dict()` merges `Field.to_dict()` with an embedded `"aliases"` list.
- `Schema` (frozen): `id`, `name`, `fields: tuple[CanonicalField, ...]`, `created_by`, `created_at`. `to_master_map()` produces the versioned envelope `{"schema_version":1, "id", "name", "created_by", "created_at", "fields":[...]}`; `from_master_map()` re-validates each field name through `fields.loader.from_dict` (the shared `_validated_name` guard) before rebuilding, then re-attaches aliases by field name. `from_master_map(to_master_map(s))` reconstructs an equal Schema.

**Task 2 — Store seam + SQLite impl (`learning/schema_store.py`, `learning/sqlite_schema_store.py`)**
- `SchemaStore` ABC mirroring `ProfileStore`: `create_schema`, `get_schema` (by id OR name), `list_schemas`, `add_or_update_fields`, `add_alias`, `list_aliases_for`.
- `SqliteSchemaStore` imports `_DEFAULT_DB_PATH` from `sqlite_store.py` (same `.assayingest/profiles.db` file — no second DB). Tables `schema` / `canonical_field` / `alias` with `schema_id` / `canonical_field_id` foreign keys and `UNIQUE(canonical_field_id, vendor, source_column)`. All queries parameterised; `PRAGMA foreign_keys = ON` per connection.
- `add_or_update_fields` is augment-only (INSERT OR IGNORE on `UNIQUE(schema_id, name)` — existing definition kept, nothing deleted). `add_alias` is idempotent and provenance-immutable (INSERT OR IGNORE — first-seen actor/timestamp preserved). Boundary translators `_row_to_schema`/`_row_to_field`/`_row_to_alias` map rows to domain; `_row_to_field` rebuilds one field at a time through `fields.loader` so the 50-field loader cap never applies to reads.

## Invariants proven by tests

- **SCHEMA-04 isolation** — two schemas in the same store never share fields or aliases; verified structurally via the `schema_id` foreign key, not name filtering.
- **Master-map round-trip (SCHEMA-02/03 serialization contract)** — `from_master_map(to_master_map(s))` preserves name, canonical field names, field constraints, and aliases (order-insensitive per field), with `ALIAS-03` provenance intact.
- **Augment-never-discard** — re-adding an existing field neither duplicates nor overwrites; a new field appends; nothing is deleted.
- **ALIAS-03 immutable provenance** — a re-observed `(vendor, source_column)` keeps a single row with the first-seen `provenance_actor`/`created_at`.
- **T-07-01 SQLi** — hostile schema name/vendor/column round-trips safely (parameterised placeholders).
- **T-07-03** — an imported field name with a newline/control char raises `ValueError` via the shared loader guard.

## Tests

- `tests/test_schema_domain.py` — 11 tests (Alias/CanonicalField/Schema + envelope round-trip + name-safety).
- `tests/test_schema_store.py` — 11 tests (create/get/list, isolation, augment-only, provenance immutability, SQLi safety).
- Full suite: **532 passed, 4 skipped** (skips are pre-existing live-API tests) via `uv run python -m pytest -q`.

## TDD Gate Compliance

Both tasks followed RED→GREEN with distinct commits:
- Task 1: `test(07-01)` 7c0dbe1 (RED) → `feat(07-01)` 2f4f9aa (GREEN)
- Task 2: `test(07-01)` 17a0751 (RED) → `feat(07-01)` 92f93c5 (GREEN)

## Deviations from Plan

None — plan executed exactly as written. `list_aliases_for` was implemented to take a `schema_id` (the plan wrote `list_aliases_for(schema)`); it returns a flat `list[Alias]` for the schema, and per-field aliases also surface on `get_schema(...).fields[*].aliases`. A fail-closed `ValueError` was added to `add_alias` when the named canonical field does not exist in the schema (Rule 2 — correctness guard, consistent with the log-or-raise consequence-message convention); no test required changing.

## Notes for later plans

- `add_alias(schema_id, field_name, alias)` resolves the canonical field by `(schema_id, name)` — the promote / confirm-records-aliases plans call this with `provenance_kind="manual"`, `provenance_actor=confirmed_by`; the import plan uses `provenance_kind="from_map_file"`.
- A `deps.get_schema_store()` DI factory (mentioned in D-07-02 / P2) is NOT added here — this plan is store + domain only, no HTTP. The API-facing plan adds the factory in the Phase 6 `get_user_store` style.
- `Schema.name` is `UNIQUE` in the store (domain identity); org/owner scoping is FUTURE.

## Self-Check: PASSED

All created/modified files exist; all four task commits (7c0dbe1, 2f4f9aa, 17a0751, 92f93c5) present in history.

---
phase: 08-reconcile-on-upload
plan: 01
subsystem: reconcile-service-core
tags: [reconcile, crosswalk, alias-prefill, conflict-detection, service-layer, tdd]
requires:
  - Phase 07 Schema/Alias/CanonicalField + Schema.from_master_map (map-file parse)
  - Phase 07 service.import_master_map (augment) + SchemaStore/SqliteSchemaStore
  - learning.signature._normalise_header (exact-signature normalisation)
  - mapping.mapper.propose_mapping (the mapper seam) + validation.validator.validate
provides:
  - domain.models.ReconcileConflict + ReconcileQuestion (wire-ready to_dict)
  - service.detect_reconcile_conflicts (alias-target disagreement detection)
  - service._reconcile_map (exact-alias pre-fill that seeds/short-circuits the mapper)
  - service.reconcile_or_map (parse -> ask|augment -> prefill -> map -> validate)
  - service.apply_reconcile_resolution (per-conflict keep_master/take_map_file for this run)
affects:
  - 08-02 (API transport) reuses ReconcileQuestion.to_dict + both service entrypoints verbatim
tech-stack:
  added: []
  patterns:
    - "Deterministic pre-fill layer seeds/short-circuits the existing mapper (no second engine)"
    - "Conflict detection is decides-never-renders; returns a question, mutates nothing (P1)"
    - "Resolution override is resolved explicitly from the human choice, never via store row order"
key-files:
  created:
    - tests/test_reconcile_service.py
  modified:
    - src/assayingest/domain/models.py
    - src/assayingest/service.py
decisions:
  - "Resolution override_index is built EXPLICITLY for BOTH keep_master and take_map_file (deviation from the plan's 'keep_master needs no override') to avoid a latent ordering-dependent bug: after augment the store can hold two alias rows for one (vendor, source_column) pair (distinct canonical_field_id), so relying on dict/SQLite row order to make 'master win' is fragile. The explicit override makes the human choice deterministic regardless of row order."
  - "reconcile_or_map/apply_reconcile_resolution take the parsed map-file envelope as a keyword arg (envelope: dict) rather than a path, keeping parsing at the caller/route boundary (08-02) and the service focused."
  - "source_name (augment provenance label) defaults to the envelope's declared name so the caller need not repeat it; 08-02 can pass the uploaded filename."
metrics:
  duration_minutes: 8
  tasks_completed: 3
  tests_added: 18
  files_created: 1
  files_modified: 2
  completed: 2026-07-11
status: complete
---

# Phase 8 Plan 01: Reconcile-on-Upload Service Core Summary

Deterministic exact-alias pre-fill + map-file-vs-master conflict detection that seeds the existing Phase-07 crosswalk and mapper — a known-vendor second file maps at confidence 1.0 with zero Claude calls, a disagreeing map file forces a human `ReconcileQuestion` and mutates nothing, and everything works from column names alone (headers-only safe).

## What was built

Three TDD tasks (RED→GREEN each), proving the reconcile layer at the `service` seam independent of any HTTP route (08-02 is now pure transport wiring):

1. **Conflict-detection domain types + `detect_reconcile_conflicts`** — `ReconcileConflict`/`ReconcileQuestion` frozen dataclasses (each with `to_dict()` + `has_conflicts`), and a service function that flags EXACTLY the alias-target disagreements: the master already crosswalks a `(vendor, source_column)` pair to field A while the map file asserts field B (A≠B). Novel pairs (augment-safe), same-target pairs (agreement), and different-vendor pairs (a distinct identity per D-08-04) are NOT conflicts. The uploaded envelope is parsed through the REUSED `Schema.from_master_map` — same `fields.loader` name-safety guard (T-08-01), no weaker parser.

2. **`_reconcile_map` exact-alias pre-fill** — builds a `(vendor, normalised source_column) -> canonical field` index from the target Schema's crosswalk (reusing `learning.signature._normalise_header` for case/whitespace symmetry, D-08-04), pre-maps every matching uploaded header to its canonical field at confidence 1.0 / `needs_confirmation=False`, and calls the mapper on a REDUCED field set holding only the uncovered fields. When every field is covered it never constructs a client or calls the mapper at all (the money shot). Matching uses column NAMES only, so a headers-only table (rows empty) yields the identical pre-fill (P4/T-08-04). An `override_index` seam layers per-conflict human choices on top.

3. **`reconcile_or_map` + `apply_reconcile_resolution` orchestration** — `reconcile_or_map` sequences parse → (StructureQuestion passthrough) → load Schema (`SchemaNotFoundError` on miss) → `detect_reconcile_conflicts` → on conflict return the `ReconcileQuestion` mutating nothing (P1), else `import_master_map` augment (REUSED, `from_map_file` provenance, P3) → `_reconcile_map` → `validate()` on the merged proposal against the FULL field set (D-03) → one `MapResult`. `apply_reconcile_resolution` continues after human resolution: augments, builds an explicit override from the `(vendor, source_column, decision)` choices, pre-fills accordingly, validates — without ever overwriting the master's immutable alias (P3/T-08-05).

## Key links (as-built)

`reconcile_or_map` → `import_master_map` (augment reuse) → `SchemaStore.get_schema` (re-read augmented crosswalk) → `_reconcile_map` (alias pre-fill + reduced-set mapper call) → `validate`. `Schema.from_master_map` parses the uploaded map file (reused name-safety guard). No second mapping engine, no second parser.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Latent bug] Explicit `keep_master` override instead of relying on store/dict row order**
- **Found during:** Task 3 (apply_reconcile_resolution)
- **Issue:** The plan states "keep_master choices need no override (master's stored value already wins)." But `import_master_map` on the resolution path uses INSERT-OR-IGNORE keyed on `(canonical_field_id, vendor, source_column)` — so importing the map file's conflicting alias adds a SECOND alias row (different `canonical_field_id`) rather than being ignored. The master and map-file targets then coexist for one `(vendor, source_column)` pair, and which one "wins" in `_alias_index` would depend on Schema field row order + dict insertion order — a fragile, non-deterministic basis for a conflict resolution (this project's memory flags accuracy/fail-closed as lives-at-stake).
- **Fix:** `_resolution_override_index` builds the override EXPLICITLY for both decisions — `take_map_file` → the map file's asserted field, `keep_master` → the master's stored field (read from the pre-augment master Schema). The human's choice now governs deterministically regardless of row order. The override is a per-run local dict; it never touches the store, so master aliases stay immutable (P3).
- **Files modified:** src/assayingest/service.py
- **Commit:** 0c7d4ce

**2. [Rule 2 - Interface hygiene] `envelope: dict` + `source_name` keyword params**
- The plan left the map-file ingress shape to Claude's discretion ("have the CALLER pass the parsed envelope; add an `envelope: dict` keyword param"). Implemented exactly that: both entrypoints take the already-parsed envelope (parsing stays at the route boundary for 08-02), and an optional `source_name` (augment provenance label) that defaults to the envelope's declared name.
- **Files modified:** src/assayingest/service.py
- **Commit:** 0c7d4ce

## Tests

`tests/test_reconcile_service.py` — 18 tests, all green; full backend suite **578 passed, 4 skipped** (the 4 skips are pre-existing credential-gated live tests), zero regressions to `resolve_or_map` / `confirm` / schema store. No live Claude call is ever made — the mapper seam is always monkeypatched or spied (conflict/short-circuit paths assert a spy count of 0).

Coverage: conflict detection (disagreement / novel / same-target / different-vendor / aliasless / serialization); pre-fill (covered-at-1.0 + mapper-asked-for-the-rest, all-covered short-circuit, headers_only parity, no-coverage fall-through, case/whitespace normalisation); orchestration (conflict mutates-nothing + mapper-never-called, no-conflict augment+prefill+validate, SchemaNotFoundError, structural-question passthrough, take_map_file / keep_master resolution without overwriting master, validate() flags a constraint violation on the merged proposal).

## Threat surface

All plan-registered mitigations are satisfied by reuse (T-08-01 via `Schema.from_master_map`, T-08-02 via refuse-and-ask, T-08-03 via unchanged `import_master_map`, T-08-04 via names-only pre-fill). No new network endpoints, auth paths, or trust-boundary surface introduced (this plan is pure service/domain; the route + auth gate D-08-05 land in 08-02).

## Self-Check: PASSED

All created/modified files present on disk; all 6 task commits (3 RED test + 3 GREEN feat) verified in git history. TDD gate satisfied per task (test → feat). Full suite: 578 passed, 4 skipped, 0 regressions.

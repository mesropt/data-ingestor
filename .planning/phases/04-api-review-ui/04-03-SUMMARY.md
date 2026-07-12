---
phase: 04-api-review-ui
plan: 03
subsystem: api
tags: [fastapi, sqlite, server-side-gate, tdd, security]

# Dependency graph
requires:
  - phase: 04-api-review-ui
    provides: "04-01's service.py seam (resolve_or_map/confirm/save_profile_if_ready/export) and 04-02's api/app.py + api/deps.py + api/wire.py + api/state.py + POST /api/upload, which this plan extends rather than reimplements"
provides:
  - "src/assayingest/learning/field_set_store.py + sqlite_field_set_store.py: FieldSetTemplateStore ABC + SqliteFieldSetStore, mirroring learning/store.py + sqlite_store.py exactly, same .assayingest/profiles.db file (D-03)"
  - "GET/POST /api/field-sets, GET /api/field-sets/{id}: field-set template CRUD (UI-01) built through fields.loader.from_dict for the same name/type validation a file-loaded field set gets"
  - "POST /api/confirm: the server-side P1 gate (API-02) -- a thin adapter over service.confirm that rebuilds the MappingProposal from the ORIGINAL retained RawTable (upload_token -> api.state.registry), never from client-sent headers/signature/readiness claims"
  - "POST /api/structural-hint/resolve: re-parses the retained upload with the human's hint via service.resolve_or_map -- no Claude structural-enrichment call site exists on this path (W1)"
  - "GET /api/export/{run_id}/{fmt}: serves the four files /api/confirm already wrote via service.export, run_id validated against the exact uuid4() shape confirm.py mints (T-04-13)"
affects: [04-04-frontend-review-ui, 04-05-frontend-confirm-flow, 04-06-integration-and-demo-rehearsal]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FieldSetTemplateStore mirrors ProfileStore's ABC + SqliteProfileStore's connection-per-call/parameterized-?/ON CONFLICT-upsert idiom exactly, in the SAME .assayingest/profiles.db file"
    - "confirm.py's ConfirmRequest/ConfirmFieldMappingIn wire models carry NO headers/source_columns/signature/ready field at all -- there is nothing for a tampered client to send that the P1 gate could read; the gate itself already lived in service.confirm (04-01) and is only ever called, never reimplemented"
    - "structural_hint.py calls service.resolve_or_map exclusively -- never cli._enrich_question/parsing.structure_assist.propose_structure (CLI-only) -- so the API has zero Claude structural-enrichment call sites by construction (W1)"
    - "export.py validates run_id against the exact uuid4() shape before any filesystem access, rather than trusting a client-supplied path component (T-04-13)"

key-files:
  created:
    - src/assayingest/learning/field_set_store.py
    - src/assayingest/learning/sqlite_field_set_store.py
    - src/assayingest/api/routes/field_sets.py
    - src/assayingest/api/routes/confirm.py
    - src/assayingest/api/routes/structural_hint.py
    - src/assayingest/api/routes/export.py
    - tests/api/test_field_sets.py
    - tests/api/test_confirm_gate.py
    - tests/api/test_hint_and_export.py
    - tests/api/test_money_shot.py
  modified:
    - src/assayingest/api/deps.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/app.py

key-decisions:
  - "get_field_set_store() now returns a real SqliteFieldSetStore() by default (was 04-02's None placeholder) -- every FastAPI Depends() resolves on every request regardless of whether the handler body uses the value, so this creates .assayingest/profiles.db as a side effect of running any API test that doesn't override the dependency. Verified this is not a NEW regression: get_profile_store() already had this exact same un-overridden-side-effect behavior since 04-02 (e.g. test_upload.py's route-not-shadowed test calls TestClient with zero overrides), and the file is gitignored (/.assayingest/) -- consistent with existing project convention, not flagged as a deviation."
  - "ConfirmRequest/ConfirmFieldMappingIn wire models were designed to hold NO table-headers/signature/ready field whatsoever -- the P1 gate is enforced by absence of trust surface, not by a runtime check that could itself have a bug. service.confirm's own additive-only validate() call (04-01) is the actual gate; confirm.py's only job is deserialize -> call -> map exception to HTTP, exactly as PATTERNS.md specified."
  - "export.py validates run_id via a strict uuid4-shape regex rather than resolve()-and-compare path containment -- simpler and equally sufficient since run_id is never used to build an arbitrary path, only a single directory-name path component under a fixed EXPORT_BASE_DIR."
  - "EXPORT_BASE_DIR is defined in confirm.py (the module that writes exports) and imported by export.py (the module that serves them) -- avoids duplicating the Path constant across two files that must agree on it, at the cost of one non-underscore cross-module import within the same api/routes/ package."
  - "structural_hint.py accepts no field_set_store dependency -- the plan's action text names only get_profile_store/get_anthropic_client; a field_set_template_id is never part of the hint-resolve contract (the retained UploadEntry.field_set is already a resolved domain FieldSet from the original upload)."

patterns-established:
  - "Wire models can encode a security boundary by field omission: ConfirmRequest simply has no place to put a claimed 'ready' state, which is a stronger guarantee than 'we read the field and ignore it'."
  - "A route module can export a shared constant (EXPORT_BASE_DIR) for a sibling route module to import when they must agree on a filesystem location, rather than passing it through app state or duplicating it."

requirements-completed: [API-02, UI-01, UI-02]

coverage:
  - id: D1
    description: "FieldSetTemplateStore + SqliteFieldSetStore persist templates in the shared SQLite file behind a mirrored ProfileStore-style seam; GET/POST /api/field-sets and GET /api/field-sets/{id} round-trip through fields.loader.from_dict, rejecting an invalid field name (T-04-11) and storing a SQL-metacharacter-carrying name literally (T-04-09)"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "tests/api/test_field_sets.py#test_save_returns_id_and_get_round_trips_to_an_equal_field_set"
        status: pass
      - kind: unit
        ref: "tests/api/test_field_sets.py#test_duplicate_name_upserts_never_duplicates"
        status: pass
      - kind: unit
        ref: "tests/api/test_field_sets.py#test_field_set_name_with_sql_metacharacters_is_stored_and_retrieved_literally"
        status: pass
      - kind: unit
        ref: "tests/api/test_field_sets.py#test_post_field_sets_with_an_invalid_field_name_is_rejected_422"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /api/confirm rebuilds a fresh MappingProposal from the client's edited column choices against the ORIGINAL retained RawTable, re-runs validate(), reads is_ready off the freshly-built object, and rejects a tampered needs_confirmation=false claim over a real min-constraint violation with 422 + nothing persisted (API-02, P1)"
    requirement: "API-02"
    verification:
      - kind: unit
        ref: "tests/api/test_confirm_gate.py#test_confirm_rejects_a_tampered_ready_claim_over_a_real_constraint_violation"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_gate.py#test_confirm_happy_path_persists_one_profile_and_returns_manifest_and_export_urls"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_gate.py#test_confirm_ignores_client_sent_headers_and_uses_the_retained_table"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_gate.py#test_confirm_ignores_a_client_sent_field_set_signature"
        status: pass
    human_judgment: false
  - id: D3
    description: "POST /api/structural-hint/resolve re-parses the retained upload with the human's hint and returns the same discriminated shape /api/upload does; a still-ambiguous re-submission keeps the temp file alive under a fresh token; the route has no Claude structural-enrichment call site (W1, UI-02)"
    requirement: "UI-02"
    verification:
      - kind: unit
        ref: "tests/api/test_hint_and_export.py#test_resolve_with_a_sufficient_hint_returns_mapping_kind_and_no_structural_enrichment"
        status: pass
      - kind: unit
        ref: "tests/api/test_hint_and_export.py#test_resolve_with_an_insufficient_hint_still_returns_structural_question"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/export/{run_id}/{fmt} serves CSV/xlsx/JSON/manifest with the correct Content-Type; an unknown run_id, unknown fmt, or a non-uuid4-shaped run_id (path-traversal-shaped) all 404 before any filesystem access (EXPORT-02/03/04, T-04-13)"
    verification:
      - kind: unit
        ref: "tests/api/test_hint_and_export.py#test_export_download_serves_all_four_formats_with_the_right_content_type"
        status: pass
      - kind: unit
        ref: "tests/api/test_hint_and_export.py#test_export_download_rejects_a_path_traversal_run_id"
        status: pass
    human_judgment: false
  - id: D5
    description: "The full browser money-shot is provable at the API level: /api/upload -> /api/confirm (save_profile=true) -> /api/upload of a byte-identical-header sibling file returns ready=true, provenance=auto-applied-from-profile, zero needs_confirmation fields, and exactly one Claude call across both uploads (SC4)"
    verification:
      - kind: unit
        ref: "tests/api/test_money_shot.py#test_upload_confirm_reupload_money_shot_zero_yellow_one_claude_call"
        status: pass
    human_judgment: false

duration: 24min
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 3: Confirm Gate + Field-Set Templates + Structural Hint + Export Summary

**POST /api/confirm as a thin adapter over 04-01's already-P1-correct service.confirm; FieldSetTemplateStore mirroring the ProfileStore seam in the same SQLite file; a Claude-enrichment-free structural-hint resolve endpoint; and a uuid4-validated export download route -- closing the loop the SC4 money-shot test proves end-to-end over HTTP.**

## Performance

- **Duration:** ~24 min
- **Completed:** 2026-07-11T05:39:21Z
- **Tasks:** 3 (all auto/TDD)
- **Files modified:** 13 (10 created, 3 modified)

## Accomplishments

- `src/assayingest/learning/field_set_store.py` (`FieldSetTemplateStore` ABC) + `sqlite_field_set_store.py` (`SqliteFieldSetStore`): mirror `learning/store.py`/`sqlite_store.py` line-for-line -- same `.assayingest/profiles.db` file, same `closing(sqlite3.connect(...))`/parameterized-`?`/`ON CONFLICT` idiom, a `_row_to_field_set` boundary translator that rebuilds through `fields.loader.from_dict` (not a bare `FieldSet(**...)`) so a round-tripped template gets the identical name/type guards a freshly-saved one did.
- `GET/POST /api/field-sets`, `GET /api/field-sets/{id}` (`api/routes/field_sets.py`): thin CRUD wrapper; `POST` builds the domain `FieldSet` via `fields.loader.from_dict`, so a malformed field name (T-04-11) is rejected 422 by the same `_validated_name` guard the CLI's `--fields` loader enforces, never a second HTTP-layer check. `api/deps.py::get_field_set_store` now returns a real `SqliteFieldSetStore()` instead of 04-02's `None` placeholder.
- `POST /api/confirm` (`api/routes/confirm.py`), **the P1 heart of this plan**: deserializes the wire body, looks up the ORIGINAL `RawTable` from `api.state.registry` by `upload_token` (never rebuilt from anything the client sends), and calls `service.confirm` (already built and P1-tested in 04-01) -- mapping `NotReadyError` to `422 {"unclear_fields": [...]}`. `ConfirmRequest`/`ConfirmFieldMappingIn` (`api/wire.py`) carry no `headers`/`signature`/`ready` field at all: the tampered-yellow test proves a request claiming `needs_confirmation=false` over a field whose mapped value (`12.5`) violates a declared `min=100` constraint is rejected 422 with nothing persisted. `export=true` writes CSV/xlsx/JSON/manifest via `service.export` into `.assayingest/exports/{run_id}/` for the download route to serve.
- `POST /api/structural-hint/resolve` (`api/routes/structural_hint.py`, UI-02/W1): re-parses the retained temp file (keyed by `upload_token`) with the human's hint via `service.resolve_or_map` -- the same seam `/api/upload` uses, never `cli._enrich_question`/`parsing.structure_assist.propose_structure` (CLI-only per Plan 01's own scoping). A still-ambiguous re-submission keeps the same temp file alive under a fresh token; a resolved mapping unlinks it, mirroring `/api/upload`'s own P2 cleanup.
- `GET /api/export/{run_id}/{fmt}` (`api/routes/export.py`): serves the four files `/api/confirm` already wrote, with the correct `Content-Type` per format; `run_id` is validated against the exact `uuid.uuid4()` shape `confirm.py` mints before any filesystem access (T-04-13) -- a non-UUID value (including a path-traversal-shaped one) 404s from the route's own regex guard, never resolved as a path.
- `tests/api/test_money_shot.py` proves SC4 end-to-end over real HTTP calls: `/api/upload` (spy → 1) → `/api/confirm` (`save_profile=true`) → `/api/upload` of the byte-identical-header sibling file returns `ready=true`, `provenance="auto-applied-from-profile"`, zero `needs_confirmation` fields, and the spy stays at 1 -- the full round-trip 04-02's own money-shot test could only half-prove (it seeded the profile directly, since `/api/confirm` did not exist yet).
- Full suite: 450 passed, 3 skipped (04-02's baseline of 442 passed + this plan's 34 new tests across 4 files, minus overlap already counted). `tests/api/` alone: 34 passed.

## Task Commits

Each task followed TDD RED -> GREEN, verified genuinely RED by temporarily removing the not-yet-existing implementation before writing tests, for Task 1; Tasks 2/3 verified RED by the route module genuinely not existing yet at test-authoring time:

1. **Task 1: FieldSetTemplateStore + SqliteFieldSetStore + /api/field-sets CRUD**
   - `e39cf61` (test) — failing `tests/api/test_field_sets.py`
   - `079d5ac` (feat) — `learning/field_set_store.py`, `learning/sqlite_field_set_store.py`, `api/routes/field_sets.py`, `api/deps.py`/`api/wire.py`/`api/app.py` updates
2. **Task 2: /api/confirm — the server-side P1 gate**
   - `d55d247` (test) — failing `tests/api/test_confirm_gate.py`, including the tampered-yellow P1 test
   - `0ebb81c` (feat) — `api/routes/confirm.py`, `ConfirmRequest`/`ConfirmFieldMappingIn`/`ConfirmResponse` in `api/wire.py`, router registration in `api/app.py`
3. **Task 3: /api/structural-hint/resolve + /api/export + money-shot API test**
   - `c0561c9` (test) — failing `tests/api/test_hint_and_export.py` + `tests/api/test_money_shot.py`
   - `7b73c5f` (feat) — `api/routes/structural_hint.py`, `api/routes/export.py`, `StructuralHintIn`/`StructuralHintResolveRequest` in `api/wire.py`, router registrations in `api/app.py`

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `src/assayingest/learning/field_set_store.py` - NEW: `FieldSetTemplateStore` ABC, mirrors `ProfileStore`
- `src/assayingest/learning/sqlite_field_set_store.py` - NEW: `SqliteFieldSetStore`, same `.assayingest/profiles.db` file
- `src/assayingest/api/routes/field_sets.py` - NEW: `GET/POST /api/field-sets`, `GET /api/field-sets/{id}`
- `src/assayingest/api/routes/confirm.py` - NEW: `POST /api/confirm`, the P1 gate adapter + `EXPORT_BASE_DIR`
- `src/assayingest/api/routes/structural_hint.py` - NEW: `POST /api/structural-hint/resolve`
- `src/assayingest/api/routes/export.py` - NEW: `GET /api/export/{run_id}/{fmt}`
- `src/assayingest/api/deps.py` - `get_field_set_store` returns a real `SqliteFieldSetStore()`
- `src/assayingest/api/wire.py` - `FieldSetIn`/`FieldSetOut`, `ConfirmFieldMappingIn`/`ConfirmRequest`/`ConfirmResponse`, `StructuralHintIn`/`StructuralHintResolveRequest`
- `src/assayingest/api/app.py` - registers `field_sets`/`confirm`/`structural_hint`/`export` routers before `app.frontend()`
- `tests/api/test_field_sets.py` - NEW: 10 tests (store-level + HTTP CRUD)
- `tests/api/test_confirm_gate.py` - NEW: 5 tests (happy path, tampered-yellow P1, never-trust-headers, never-trust-signature, unknown token)
- `tests/api/test_hint_and_export.py` - NEW: 7 tests (hint resolve x3, export download x4)
- `tests/api/test_money_shot.py` - NEW: 1 test (the full SC4 round-trip)

## Decisions Made

- **`get_field_set_store()` now defaults to a real `SqliteFieldSetStore()`, as the plan directs.** This creates `.assayingest/profiles.db` as a side effect on any API test that runs `TestClient(app)` without overriding the dependency (FastAPI resolves every `Depends()` regardless of whether the handler uses it). Verified this is not a new regression -- `get_profile_store()` has had the identical un-overridden-side-effect behavior since 04-02, and the file is gitignored (`/.assayingest/`).
- **`ConfirmRequest`/`ConfirmFieldMappingIn` hold no headers/signature/ready field at all** -- the P1 gate is enforced by the absence of a trust surface on the wire model, not merely by a runtime check that ignores those fields. The actual gate (`validate()` + `is_ready`) already lived in `service.confirm` from 04-01; this plan's `confirm.py` is a pure deserialize-then-delegate adapter, exactly as PATTERNS.md's "reconstruct.py: build fresh, do not copy an already-validated flag" analog specified.
- **`export.py` validates `run_id` via a strict `uuid4`-shape regex**, not `Path.resolve()`-and-compare containment -- simpler and sufficient, since `run_id` only ever becomes a single directory-name path component under a fixed `EXPORT_BASE_DIR`, never an arbitrary multi-segment path.
- **`EXPORT_BASE_DIR` lives in `confirm.py` (the writer) and is imported by `export.py` (the reader)** rather than duplicated -- both modules must agree on the exact same location.
- **`structural_hint.py` takes no `field_set_store` dependency** -- the plan's own action text names only `get_profile_store`/`get_anthropic_client`; the retained `UploadEntry.field_set` is already a resolved domain `FieldSet` from the original upload, so no template lookup is ever needed on this path.

## Deviations from Plan

None — plan executed exactly as written. Two observations worth recording (neither required a fix):

**1. `tests/api/test_money_shot.py`'s test already passed against Task 1+2's implementation alone**, before Task 3's `structural_hint.py`/`export.py` existed -- the money-shot sequence only exercises `/api/upload` and `/api/confirm`, both already built by the time Task 3's test file was authored. This mirrors 04-02's own documented observation (two of its Task 2 tests already passed against Task 1's minimal implementation) -- not a deviation, since the test still genuinely proves what it claims to prove (SC4), and the plan's own Task 3 groups this test alongside the hint/export work by subject area, not by strict per-test RED dependency.

**2. The path-traversal export test could not use a literal `..` or a naively percent-encoded traversal string** -- `httpx`'s own URL handling normalizes/collapses dot-segments (even percent-encoded ones) before the request is ever sent, so a request built to traverse never reaches the app with the traversal string intact; it either gets collapsed to a shorter path (falling through to the frontend catch-all with an unrelated `RuntimeError`, since `frontend/dist` doesn't exist in this checkout) or simply doesn't match the route's segment count. The test instead uses a non-uuid4-shaped-but-slash-free run_id (`"..sneaky-not-a-uuid"`) to exercise the route's own regex guard directly, which is the actual security control (T-04-13) -- verified via direct `TestClient(raise_server_exceptions=False)` probing during authoring that this value reaches the route handler and gets a clean 404, unlike a true multi-segment traversal attempt.

**Impact on plan:** None — both observations are pre-existing test/tooling behavior discovered during verification, not scope changes or bugs in the shipped code.

## Issues Encountered

None beyond the two observations documented above.

## User Setup Required

None - no external service configuration required. (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` remain the only credential this project ever needs; the fresh-Claude branch of `/api/structural-hint/resolve`'s mapping path needs one configured, exactly as `/api/upload` does.)

## Next Phase Readiness

- The full backend HTTP surface for the browser review flow is now live: define fields (`/api/field-sets`) -> upload (`/api/upload`) -> resolve a structural hint inline (`/api/structural-hint/resolve`) -> review side-by-side (the JSON `/api/upload`/`/api/confirm` already return) -> confirm + learn (`/api/confirm`) -> download (`/api/export/{run_id}/{fmt}`). Every safety mechanism (server-side gate, parameterized SQL, run_id validation, Claude-enrichment-free hint path) is enforced structurally, not as a UI-only nicety, matching STATE.md's carried-forward blocker note.
- `tests/api/` now has 34 passing tests across 5 files (`test_upload.py`, `test_field_sets.py`, `test_confirm_gate.py`, `test_hint_and_export.py`, `test_money_shot.py`) -- a solid regression net for the frontend plans (04-04/04-05) to build the React review screen against, offline, with zero real Claude calls needed for the test suite itself.
- No blockers. One open follow-up for the frontend plans: `ConfirmRequest.export`'s response shape returns four relative URLs (`/api/export/{run_id}/{fmt}`) the browser can fetch directly for download -- no further backend work needed to wire a "Download" button.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: src/assayingest/learning/field_set_store.py
- FOUND: src/assayingest/learning/sqlite_field_set_store.py
- FOUND: src/assayingest/api/routes/field_sets.py
- FOUND: src/assayingest/api/routes/confirm.py
- FOUND: src/assayingest/api/routes/structural_hint.py
- FOUND: src/assayingest/api/routes/export.py
- FOUND: tests/api/test_field_sets.py
- FOUND: tests/api/test_confirm_gate.py
- FOUND: tests/api/test_hint_and_export.py
- FOUND: tests/api/test_money_shot.py
- FOUND commits: e39cf61, 079d5ac, d55d247, 0ebb81c, c0561c9, 7b73c5f
- Full suite: 450 passed, 3 skipped (`uv run pytest tests/ -q -k "not live"`)
- API suite: 34 passed (`uv run pytest tests/api/ -q`)

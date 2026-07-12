---
phase: 08-reconcile-on-upload
plan: 02
subsystem: reconcile-api-transport
tags: [reconcile, api, fastapi, upload, two-step, auth-gate, tdd]
requires:
  - 08-01 service.reconcile_or_map / apply_reconcile_resolution / detect_reconcile_conflicts
  - 08-01 domain.models.ReconcileQuestion.to_dict (wire-ready conflict shape)
  - Phase 07 Schema/Alias + service.promote + SchemaStore (governed crosswalk)
  - Phase 06 deps.require_verified_user / get_current_user (401/403 gate)
  - Phase 04 api.state.registry two-step + upload.py bounded temp-file idiom
provides:
  - api.wire.ReconcileQuestionResponse / ReconcileChoiceIn / ReconcileResolveRequest
  - api.state.UploadEntry map_envelope/target_schema_name/vendor retention fields
  - "/api/upload optional map-file branch (reconcile_question | mapping | structural_question)"
  - "POST /api/reconcile/resolve (verified-user gated two-step)"
affects:
  - "Frontend (future): a third kind=reconcile_question arm + a resolve POST to wire into the review UI"
tech-stack:
  added: []
  patterns:
    - "Route is a pure transport adapter: deserialize -> service seam -> serialize -> map exceptions to HTTP"
    - "Discriminated response kind = mapping | structural_question | reconcile_question (Pattern 5)"
    - "Two-step reuses the api.state token registry verbatim (never forked), mirroring structural_hint"
    - "Conditional inline auth on the upload map-file branch vs unconditional require_verified_user dependency on resolve"
key-files:
  created:
    - src/assayingest/api/routes/reconcile.py
    - tests/api/test_reconcile.py
  modified:
    - src/assayingest/api/wire.py
    - src/assayingest/api/state.py
    - src/assayingest/api/routes/upload.py
    - src/assayingest/api/app.py
decisions:
  - "Map file read fully into memory under _MAX_UPLOAD_BYTES (chunked, 413 on overflow) then json.loads -- a master-map envelope is small and the whole dict is needed at once, unlike the streamed-to-disk DATA file (T-08-07)."
  - "Upload map-file branch applies the 401/403 gate INLINE (conditional) since a plain upload must stay open; /api/reconcile/resolve uses require_verified_user as an unconditional dependency since resolve ALWAYS augments (D-08-05)."
  - "Both routes handle a defensive StructureQuestion arm -- a reconcile re-parse can still be structurally ambiguous, so the discriminated shape stays consistent with /api/upload."
metrics:
  duration_minutes: 9
  tasks_completed: 3
  tests_added: 17
  files_created: 2
  files_modified: 4
  completed: 2026-07-11
status: complete
---

# Phase 8 Plan 02: Reconcile-on-Upload API Transport Summary

Pure FastAPI adapter wiring the 08-01 reconcile core into HTTP: `/api/upload`
grows an optional map-file + target-Schema + vendor branch that returns a third
discriminated `kind="reconcile_question"` arm on a map-file-vs-master conflict
(augmenting/mapping NOTHING until the human resolves), a new verified-user-gated
`POST /api/reconcile/resolve` applies the human's per-conflict choice and returns
the terminal `kind="mapping"` MappingResponse into the existing yellow-flag
review under the unchanged `/api/confirm` gate, and the augmenting path is gated
on a signed-in verified user while a plain upload stays open as today.

## What was built

Three TDD tasks (RED -> GREEN each), all transport-only -- every conflict /
augment / pre-fill decision stays in `service` (08-01):

1. **Reconcile wire models + UploadEntry retention fields** -- `ReconcileChoiceIn`
   (decision is a `Literal["keep_master","take_map_file"]` so an invalid value is
   a 422 at the boundary, never a silent mis-apply), `ReconcileResolveRequest`,
   and `ReconcileQuestionResponse.from_question` which spreads
   `ReconcileQuestion.to_dict()["conflicts"]` VERBATIM (mirroring
   `StructuralQuestionResponse.from_question`, never a second hand-derived
   shape). `UploadEntry` gains three additive `None`-defaulted fields
   (`map_envelope`, `target_schema_name`, `vendor`) retained ONLY while a
   reconcile question is pending -- purely additive, existing constructor calls
   unchanged.

2. **`/api/upload` map-file branch + verified-user gate** -- when a `map_file`
   is supplied the route switches onto `_reconcile_upload`: the 401 (signed
   out) / 403 (unverified) gate runs BEFORE any work (T-08-06, mirroring
   `require_verified_user`'s semantics inline so it stays conditional), then it
   requires `schema_name`/`vendor` (422 naming the consequence), reads the map
   file under the `_MAX_UPLOAD_BYTES` bound (413 overflow / 422 invalid JSON,
   T-08-07), writes the DATA file to a bounded temp path exactly as today, and
   calls `service.reconcile_or_map`. On `ReconcileQuestion` it retains the temp
   file + envelope + schema/vendor under a token and returns
   `ReconcileQuestionResponse` (augmenting NOTHING); on `StructureQuestion` it
   uses the existing structural retention path; on `MapResult` the existing
   happy path. A plain upload (no map file) keeps the EXISTING open contract
   byte-for-byte -- no auth required.

3. **`POST /api/reconcile/resolve` + router registration** -- a pure adapter
   over `service.apply_reconcile_resolution` mirroring `structural_hint.py`'s
   structure (D-08-03): unconditional `require_verified_user` gate (resolve
   ALWAYS augments), `registry.pop(token)` -> 404 when no retained pending
   reconcile, wire choices mapped to `(vendor, source_column, decision)` triples,
   temp file unlinked on EVERY branch (success + all error paths, T-08-10). The
   terminal `MappingResponse` carries a fresh `upload_token` that feeds the
   unchanged `/api/confirm` gate (RECON-03). Router registered in `app.py`
   before the frontend catch-all like every other route.

## Key links (as-built)

`/api/upload` (map file present) -> inline 401/403 gate -> bounded JSON envelope
parse -> `service.reconcile_or_map` -> `ReconcileQuestionResponse` (retain
envelope/schema/vendor under token, mutate nothing) | `MappingResponse` (augment
+ pre-fill, into the review UI). `/api/reconcile/resolve` -> `require_verified_user`
-> `registry.pop(token)` -> `service.apply_reconcile_resolution` -> `MappingResponse`
-> existing `/api/confirm` server-side gate. No conflict/augment/pre-fill logic in
either route -- all of it is 08-01's `service`.

## Deviations from Plan

None -- plan executed exactly as written. The plan explicitly left the map-file
ingress read strategy to Claude's discretion ("read under the same
`_MAX_UPLOAD_BYTES` bound"); implemented as a chunked, bounded in-memory read
(the envelope dict is needed whole for `json.loads`, unlike the streamed DATA
file) with 413 on overflow and 422 on invalid JSON, both naming the consequence.

## Tests

`tests/api/test_reconcile.py` -- 17 TestClient/wire tests, all green:
- Task 1 (6): `ReconcileQuestionResponse.from_question` wire shape;
  `ReconcileResolveRequest`/`ReconcileChoiceIn` decision-Literal validation
  (valid parse + `ValidationError` on unknown decision); `UploadEntry` additive
  retention fields (present + defaulting to None).
- Task 2 (5): conflicting map file -> `reconcile_question` retaining
  envelope/schema/vendor/tmp_path and augmenting NOTHING; clean map file ->
  `mapping` + crosswalk augmented (`from_map_file` provenance); 401 signed-out /
  403 unverified on the augment path (mutating nothing); plain upload stays open
  + returns `mapping` (regression guard).
- Task 3 (6): `take_map_file`/`keep_master` resolve -> `mapping` reflecting the
  human's choice + temp file cleaned up; unconditional 401/403 gate; unknown
  token -> 404 mutating nothing; reconciled mapping confirms 200 through the
  unchanged `/api/confirm` gate.

Suite results: `tests/api` 97 passed; full backend `uv run pytest -q` **595
passed, 4 skipped** (the 4 skips are the pre-existing credential-gated live
tests), zero regressions to upload / structural-hint / confirm / schemas. No
live Claude call is ever made -- `service.propose_mapping` is always
monkeypatched (conflict / gated-out paths assert it is never called).

## TDD Gate Compliance

Each task has a `test(08-02)` RED commit immediately followed by its `feat(08-02)`
GREEN commit:
- Task 1: f5a415f (test) -> 824724a (feat)
- Task 2: d909fd9 (test) -> 04b62a3 (feat)
- Task 3: db3960f (test) -> 2b4efb2 (feat)

## Threat surface

All plan-registered mitigations satisfied: T-08-06 (inline 401/403 on the upload
augment path + unconditional `require_verified_user` on resolve), T-08-07
(map-file + data-file reads both bounded by `_MAX_UPLOAD_BYTES`, no unbounded
`.read()`), T-08-08 (the real map envelope/schema/vendor are server-retained
under the token; the client only picks a per-conflict side), T-08-10 (every
resolve branch unlinks the retained temp file; the registry LRU still owns any
orphan). The new `/api/reconcile/resolve` endpoint is the plan's registered
surface -- no threat surface beyond the register was introduced.

## Self-Check: PASSED

All created/modified files present on disk; all 6 task commits (3 RED test + 3
GREEN feat) verified in git history. Full suite: 595 passed, 4 skipped, 0
regressions.

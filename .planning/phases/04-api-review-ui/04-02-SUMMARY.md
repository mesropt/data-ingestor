---
phase: 04-api-review-ui
plan: 02
subsystem: api
tags: [fastapi, testclient, dependency-injection, wire-models, tdd]

# Dependency graph
requires:
  - phase: 04-api-review-ui
    provides: "04-01's service.py seam (resolve_or_map/resolve_table_mapping/confirm/save_profile_if_ready/export + typed exceptions) that every route here calls, never reimplements"
provides:
  - "src/assayingest/api/app.py: FastAPI() instance, upload router include, dev-only CORS, app.frontend() mount for the one-command demo"
  - "src/assayingest/api/deps.py: get_profile_store/get_field_set_store/get_anthropic_client DI seams, overridable via app.dependency_overrides"
  - "src/assayingest/api/wire.py: MappingResponse/FieldMappingOut/StructuralQuestionResponse -- HTTP wire models built from cli.proposal_to_dict, extended with validator_note"
  - "src/assayingest/api/state.py: in-memory UploadRegistry (upload_token -> table/field_set/headers_only/tmp_path), max-count eviction"
  - "src/assayingest/api/routes/upload.py: POST /api/upload -- the browser-reachable walking skeleton (API-01/03, UI-02)"
affects: [04-03-api-confirm-fieldsets-routes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin-adapter routes: every route handler only translates HTTP<->domain via service.py; no mapping/validation/signature/gate logic in api/"
    - "Discriminated /api/upload response contract on a `kind` field (mapping | structural_question), per RESEARCH.md Pattern 5"
    - "Typed service exceptions mapped to HTTP status per route (MissingCredentialsError->503, AuthenticationError->401, APIError/ValueError->500)"
    - "FastAPI Depends() DI seams for store/client, overridable in tests via app.dependency_overrides -- distinct from the propose_mapping monkeypatch seam, which stays a plain module attribute"

key-files:
  created:
    - src/assayingest/api/__init__.py
    - src/assayingest/api/app.py
    - src/assayingest/api/deps.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/state.py
    - src/assayingest/api/routes/__init__.py
    - src/assayingest/api/routes/upload.py
    - tests/api/__init__.py
    - tests/api/test_upload.py
  modified: []

key-decisions:
  - "Task 1 built a MINIMAL routes/upload.py (no extension/size guards, no structural-question branch, no cleanup, no exception mapping) even though the plan's own Task 1 file list omits routes/upload.py entirely -- its action text ('including the upload router (Task 2)') and its own e2e RED test both require a working POST /api/upload to exist. Task 2 then extended the SAME file to full robustness, keeping genuine RED->GREEN for the guard-driving tests rather than either skipping Task 1's e2e test or pre-building guards Task 2's tests were supposed to drive."
  - "The P2 headers_only privacy test exercises the REAL propose_mapping/_render_table chain (not a monkeypatched fake) via a fake Anthropic client injected through the get_anthropic_client DI seam -- proves no cell value reaches the actual outbound Claude request payload at the HTTP boundary, matching the plan's own 'the REAL privacy guard' phrasing, not merely that a headers_only flag was threaded through."
  - "field_set_template_id is accepted as a Form field and routed to get_field_set_store(), but that dependency still returns None (04-01's placeholder) -- resolving by template id currently returns 501 'not available yet' rather than crashing; Plan 03 wires the real FieldSetTemplateStore."

patterns-established:
  - "api/wire.py: MappingResponse.from_proposal(proposal, provenance, upload_token) builds the HTTP body FROM cli.proposal_to_dict()'s dict, never a second hand-derived shape -- the one addition (validator_note) is looked up by target_field from the domain proposal, since that dict omits it"
  - "api/state.py: UploadRegistry.put()/get()/pop() around a module-level OrderedDict singleton with oldest-first eviction -- the pattern any future per-session state (Plan 03's structural-hint resolve, confirm) reuses"

requirements-completed: [API-01, API-03]

coverage:
  - id: D1
    description: "POST /api/upload accepts a file + field_set JSON, returns a 200 discriminated body (kind=mapping or kind=structural_question) carrying an upload_token"
    requirement: "API-01"
    verification:
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_happy_path_returns_mapping_kind_with_upload_token"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_returns_structural_question_and_retains_temp_file"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_mapping_response_from_proposal_includes_validator_note"
        status: pass
    human_judgment: false
  - id: D2
    description: "A second upload whose headers match a saved profile auto-applies with zero needs_confirmation fields and makes zero Claude calls (the SC4 demo money shot)"
    requirement: "API-03"
    verification:
      - kind: unit
        ref: "tests/api/test_upload.py#test_second_same_signature_upload_auto_applies_with_no_second_claude_call"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_dependency_seams_are_overridable_and_auto_apply_reaches_a_tmp_path_store"
        status: pass
    human_judgment: false
  - id: D3
    description: "headers_only=true reaches the real mapper with zero cell values in the outbound Claude request (P2 privacy at the HTTP boundary)"
    verification:
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_headers_only_reaches_the_real_mapper_with_no_cell_values"
        status: pass
    human_judgment: false
  - id: D4
    description: "Upload guards: extension allowlist (400), oversized-upload bounded read (413), path-traversal-safe temp path, and happy-path temp-file cleanup"
    verification:
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_rejects_disallowed_extension_before_parsing"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_rejects_oversized_file"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_never_uses_client_filename_as_a_path_component"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload.py#test_upload_deletes_temp_file_on_the_happy_path"
        status: pass
    human_judgment: false
  - id: D5
    description: "One uvicorn process serves both /api/* and the built frontend bundle; /api/* is never shadowed by the frontend fallback, even with frontend/dist absent"
    verification:
      - kind: unit
        ref: "tests/api/test_upload.py#test_api_route_not_shadowed_by_frontend_fallback_when_dist_absent"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 2: FastAPI Upload Route Summary

**POST /api/upload -- the browser-reachable walking skeleton: a file + field-set JSON in, a validated-and-confirmed-clean-or-flagged mapping (or a deterministic structural question) out, with a same-signature second upload auto-applying at zero Claude calls (SC4).**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-11
- **Tasks:** 3 (2 TDD, 1 auto)
- **Files modified:** 9 (9 created, 0 modified)

## Accomplishments

- New `src/assayingest/api/` package: `app.py` (FastAPI instance, upload router, dev-only CORS behind `ASSAYINGEST_DEV_CORS`, `app.frontend("/", directory="frontend/dist", check_dir=False)` mounted last), `deps.py` (three `Depends()` seams, overridable via `app.dependency_overrides`), `wire.py` (`MappingResponse`/`FieldMappingOut`/`StructuralQuestionResponse`, built from `cli.proposal_to_dict` and extended with `validator_note`), `state.py` (in-memory `UploadRegistry` with max-count eviction).
- `POST /api/upload` (`api/routes/upload.py`): a thin, synchronous (`def`, not `async def`) adapter over `service.resolve_or_map` — materializes the `UploadFile` to a bounded, extension-checked temp file; returns the discriminated `kind="mapping"`/`kind="structural_question"` body with an `upload_token`; unlinks the temp file on the happy path, retains it (keyed by token) on the structural-question branch for a future `/api/structural-hint/resolve`; maps `MissingCredentialsError`/`AuthenticationError`/`APIError`/`ValueError` to 503/401/500.
- The SC4 demo money shot proven end-to-end over HTTP: a spy on `service.propose_mapping` counts exactly 1 call across two uploads of `novascreen_batch01.csv`/`novascreen_batch02.csv` — the second (byte-identical headers, profile saved directly into an injected tmp-path store) returns `provenance="auto-applied-from-profile"`, `ready=true`, zero `needs_confirmation` fields, and the spy count stays at 1.
- P2 privacy proven through the REAL mapper: a fake `anthropic.Anthropic`-shaped client injected via `get_anthropic_client` captures the exact outbound request content under `headers_only=true` — no cell value (`"12.5"`, `"NVS-0012"`) appears, only headers (`"cmpd"`).
- Upload guards: `.csv`/`.xlsx`/`.xls` extension allowlist (400 otherwise, before any bytes reach `parse()`), a bounded chunked read rejecting an oversized upload (413) without buffering it unbounded, and a filename like `"../../etc/passwd.csv"` proven to never become a path component (only its extension is read; the actual temp path is always `tempfile`-generated).
- `grep -rn "hashlib" src/assayingest/api/` returns nothing (Pitfall 3 — no re-derived signature at the HTTP layer).
- Full suite: 427 passed, 4 skipped (04-01's baseline of 416 passed / 4 skipped + this plan's 11 new tests in `tests/api/test_upload.py`).

## Task Commits

1. **Task 1: App wiring + DI seams + HTTP wire models**
   - `8193859` (test) — failing e2e/wire-model/DI-seam tests for the not-yet-existing `api/` package
   - `3495d0f` (feat) — `api/app.py`, `api/deps.py`, `api/wire.py`, `api/state.py`, minimal `api/routes/upload.py`
2. **Task 2: /api/upload route -- temp-file handling, discriminated response, auto-apply spy**
   - `e7e842c` (test) — failing tests for the structural-question branch, real-mapper headers_only privacy, cleanup, extension/size guards, path traversal, and the SC4 spy (path-traversal and SC4 already passed under Task 1's implementation — see Deviations)
   - `c67c9f3` (feat) — full `api/routes/upload.py`: extension allowlist, bounded-read size limit, structural-question branch with temp-file retention, typed-exception-to-HTTP mapping
3. **Task 3: app.frontend() serving + route-not-shadowed regression test**
   - `2032319` (test) — regression test proving `/api/upload` is reached (422 on an empty POST) rather than shadowed by the SPA fallback; `app.py`'s ordering and docstring already satisfied this task's other requirements from Task 1

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `src/assayingest/api/__init__.py` - NEW: package docstring, thin-adapter discipline statement
- `src/assayingest/api/app.py` - NEW: `FastAPI()` instance, upload router, dev-only CORS, `app.frontend()` mount
- `src/assayingest/api/deps.py` - NEW: `get_profile_store`/`get_field_set_store`/`get_anthropic_client` DI seams
- `src/assayingest/api/wire.py` - NEW: `AlternativeOut`/`FieldMappingOut`/`MappingResponse`/`StructuralQuestionResponse`
- `src/assayingest/api/state.py` - NEW: `UploadEntry`/`UploadRegistry`, module-level `registry` singleton
- `src/assayingest/api/routes/__init__.py` - NEW: empty
- `src/assayingest/api/routes/upload.py` - NEW: `POST /api/upload` handler + upload guards
- `tests/api/__init__.py` - NEW: empty
- `tests/api/test_upload.py` - NEW: 11 tests covering the walking skeleton, DI seams, guards, privacy, and SC4

## Decisions Made

- **Task 1's `routes/upload.py` was intentionally minimal** (no extension/size guards, no structural-question branch, no cleanup, no exception mapping) so Task 2's own RED tests for those specific behaviors would genuinely fail first. The plan's Task 1 file list technically omits `routes/upload.py`, but Task 1's action text ("including the upload router (Task 2)") and its own e2e RED test both require a working `POST /api/upload` — resolved by building a real-but-minimal version in Task 1 and extending the same file in Task 2.
- **The P2 headers_only privacy test exercises the real `propose_mapping`/`_render_table` chain**, not a monkeypatched fake — a fake `anthropic.Anthropic`-shaped client is injected via the `get_anthropic_client` DI seam instead, so the test proves no cell value reaches the *actual* outbound Claude request payload, matching the plan's "the REAL privacy guard" phrasing literally.
- **`field_set_template_id` is accepted but not yet resolvable** — `get_field_set_store()` still returns `None` (04-01's placeholder), so a request using it gets a clear 501 "not available yet" rather than an `AttributeError`; Plan 03 is expected to wire the real `FieldSetTemplateStore`.

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing-critical-functionality, or blocking issues were found during execution.

**Observed but not a deviation:** two of Task 2's newly-added tests (`test_upload_never_uses_client_filename_as_a_path_component` and `test_second_same_signature_upload_auto_applies_with_no_second_claude_call`) already passed against Task 1's minimal implementation, because `tempfile.NamedTemporaryFile` inherently generates a safe path regardless of the client-supplied filename, and `service.resolve_table_mapping`'s auto-apply routing (built in 04-01) was already correct. This is expected — those two tests are regression guards for behavior the design already guarantees structurally, not features Task 2 needed to newly implement. The other 5 of Task 2's 7 new tests were genuinely RED against Task 1's code (confirmed by running the suite immediately after the RED commit) and only passed once Task 2's guards/branch/exception-mapping were added.

---

**Total deviations:** 0 auto-fixed. Two pre-existing-correctness observations documented above, no scope change.
**Impact on plan:** None — plan executed as specified.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` remain the only credential this project ever needs, unchanged by this plan; the fresh-Claude branch of `/api/upload` needs one configured, exactly as the CLI does.)

## Next Phase Readiness

- `POST /api/upload` is a real, browser-reachable capability: a curator can define fields, `curl`/fetch a file, and get back a validated mapping or a structural question with an `upload_token` — the phase's walking-skeleton slice is live.
- Plan 03 (confirm + field-sets routes) has everything it needs: `api/deps.py`'s `get_field_set_store` seam is already wired into `upload.py` (returning 501 until filled), `api/state.py`'s `UploadRegistry` already retains `{field_set, headers_only, tmp_path}` for the structural-question branch (Plan 03's `/api/structural-hint/resolve` re-parses via the retained `tmp_path`), and `api/wire.py`'s `MappingResponse`/`FieldMappingOut` shapes are ready for `/api/confirm`'s request body to mirror.
- `UploadEntry.table` is populated on the mapping-success branch but not yet consumed by anything — Plan 03's `/api/confirm` is expected to look it up by `upload_token` (per RESEARCH.md's Server-Side Gate: "the table the server never re-derives from a client-editable field") rather than re-parsing or trusting client-sent headers.
- No blockers. One open follow-up for Plan 03: `UploadRegistry` currently has no `/api/structural-hint/resolve`-shaped consumer yet, so its retention path is exercised only by this plan's own structural-question test — Plan 03 should add an end-to-end test that actually pops a retained entry and re-parses its `tmp_path`.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: src/assayingest/api/__init__.py
- FOUND: src/assayingest/api/app.py
- FOUND: src/assayingest/api/deps.py
- FOUND: src/assayingest/api/wire.py
- FOUND: src/assayingest/api/state.py
- FOUND: src/assayingest/api/routes/__init__.py
- FOUND: src/assayingest/api/routes/upload.py
- FOUND: tests/api/__init__.py
- FOUND: tests/api/test_upload.py
- FOUND commits: 8193859, 3495d0f, e7e842c, c67c9f3, 2032319

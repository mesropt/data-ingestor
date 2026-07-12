---
phase: 04-api-review-ui
plan: 01
subsystem: api
tags: [fastapi, service-layer, clean-architecture, refactor, tdd]

# Dependency graph
requires:
  - phase: 03-validator-learning-loop
    provides: validator, learning-loop store/reconstruct, canonical assembly, export writers -- the exact logic this plan lifted out of cli.py, unchanged
provides:
  - "src/assayingest/service.py: public, print-free orchestration (resolve_or_map, resolve_table_mapping, confirm, save_profile_if_ready, export, has_credentials) both cli.py and the future api/ package call"
  - "typed exceptions (MissingCredentialsError, NotReadyError, NoStoreError) replacing cli.py's old sentinel-tuple/print-then-exit-code idioms"
  - "fields/loader.py::from_dict -- the public in-memory FieldSet builder load() now delegates to, sharing the exact same name/length/type validation a future POST /api/field-sets body will need"
  - "fastapi, uvicorn[standard], python-multipart declared as runtime dependencies (versions verified against 04-RESEARCH.md's live PyPI cross-check)"
affects: [04-02-api-mapping-routes, 04-03-api-confirm-fieldsets-routes]

# Tech tracking
tech-stack:
  added: [fastapi==0.139.0, "uvicorn[standard]==0.51.0", python-multipart==0.0.32]
  patterns:
    - "Decide-vs-render split (PATTERNS.md Pattern 1): service.py functions return plain data or raise typed exceptions and never print; cli.py is now a thin renderer around them"
    - "Monkeypatch-seam preservation: cli._resolve_proposal passes its own module-level propose_mapping reference into service.resolve_table_mapping as propose_mapping_fn, so existing tests patching cli.propose_mapping keep governing CLI behavior even though the decision logic now lives in service.py"

key-files:
  created:
    - src/assayingest/service.py
    - tests/test_service.py
  modified:
    - src/assayingest/cli.py
    - src/assayingest/fields/loader.py
    - tests/test_field_set.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Named the save-profile service helper save_profile_if_ready (not the plan's suggested bare 'save_profile') to avoid a real Python name collision with confirm()'s own save_profile: bool parameter, which the plan's literal behavior spec requires be named exactly that"
  - "resolve_table_mapping (the shared per-table decision, mirroring cli._resolve_proposal 1:1) deliberately does NOT call validate() -- validate() stays a separate explicit step, exactly as cli._map_one already does, so cli.py's CLI-observable behavior is byte-identical after the refactor. resolve_or_map (the new path-based seam, not yet wired into any CLI code path) DOES call validate() on both branches, matching 04-RESEARCH.md's Pattern-1 sketch and D-03 (validator runs on every branch) -- since nothing in the existing CLI flow calls resolve_or_map yet, this carries zero regression risk"
  - "Deferred requirements.mark-complete for API-01/02/03: this plan's own objective text scopes it to 'the backend-logic side' only -- all three requirement IDs also appear in 04-02 and 04-03's frontmatter, which build the actual HTTP surface a user needs to upload/confirm/auto-apply through. Marking REQUIREMENTS.md's checkboxes now would claim a user-facing capability that does not exist yet (no api/ package was created in this plan)"
  - "Package-legitimacy checkpoint (Task 1, T-04-SC) treated as satisfied per this plan's own explicit critical_constraints instruction, backed by 04-RESEARCH.md's live PyPI cross-check session -- proceeded straight to uv add without a blocking pause; resolved versions (fastapi==0.139.0, uvicorn==0.51.0, python-multipart==0.0.32) match the research session's verified values exactly"

patterns-established:
  - "service.py: public orchestration module with zero print/write side effects except an explicitly-named writer function (export); every gate raises a typed exception instead of returning a sentinel or printing+returning an exit code"
  - "fields/loader.py: from_dict(raw) as the shared validated-builder both file-loading and a future HTTP JSON body go through -- load() is now a 4-line suffix-dispatch-then-delegate wrapper"

requirements-completed: []  # API-01/02/03 intentionally NOT marked -- see key-decisions; backend-logic groundwork only, HTTP surface lands in 04-02/04-03

coverage:
  - id: D1
    description: "service.py exposes resolve_or_map()/resolve_table_mapping(), returning MapResult|StructureQuestion or raising MissingCredentialsError/ValueError, printing nothing"
    requirement: "API-01"
    verification:
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_returns_mapresult_matching_the_monkeypatched_mapper"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_auto_applies_from_a_matching_profile_with_no_mapper_call"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_returns_the_structural_question_unchanged"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_raises_missing_credentials_error_on_the_miss_branch"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_raises_value_error_when_field_set_is_none_with_credentials"
        status: pass
    human_judgment: false
  - id: D2
    description: "service.confirm() rebuilds a fresh MappingProposal from edited mappings, re-runs validate(), and never trusts a client-claimed ready/needs_confirmation flag -- raises NotReadyError when any field is still yellow"
    requirement: "API-02"
    verification:
      - kind: unit
        ref: "tests/test_service.py#test_confirm_returns_a_confirmresult_for_a_fully_clear_mapping"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_confirm_never_trusts_a_client_claimed_ready_flag"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_confirm_raises_not_ready_error_listing_unclear_fields"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_confirm_save_profile_persists_exactly_one_learned_profile"
        status: pass
      - kind: unit
        ref: "tests/test_service.py#test_confirm_with_save_profile_true_still_blocks_on_yellow"
        status: pass
    human_judgment: false
  - id: D3
    description: "Auto-apply reaches reconstruct_proposal with no Anthropic client constructed and no credentials checked (Pattern 5/Pitfall 3 preserved through the extraction)"
    requirement: "API-03"
    verification:
      - kind: unit
        ref: "tests/test_service.py#test_resolve_or_map_auto_applies_from_a_matching_profile_with_no_mapper_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "cli.py delegates its per-table decision and save/export gate logic to service.py (no duplicated orchestration) while remaining byte-identical for every existing caller: cli._resolve_proposal, cli._map_one, cli._save_profile_if_ready, cli._export_if_ready keep their exact signatures/return shapes/printed text"
    verification:
      - kind: unit
        ref: "uv run pytest tests/test_cli_run.py tests/test_learning_loop_cli.py tests/test_headers_only.py tests/test_export_cli.py tests/test_hint_replay_cli.py tests/test_canonical.py -q"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/ -q (416 passed, 4 skipped -- 398 pre-existing + 18 new)"
        status: pass
    human_judgment: false
  - id: D5
    description: "fields.loader.from_dict(raw) is public and builds a FieldSet with the exact same _validated_name/length/type validation load() applies from disk"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "tests/test_field_set.py#test_from_dict_matches_load_of_the_equivalent_json_file"
        status: pass
      - kind: unit
        ref: "tests/test_field_set.py#test_from_dict_rejects_a_bad_field_name_same_as_load"
        status: pass
      - kind: unit
        ref: "tests/test_field_set.py#test_from_dict_rejects_more_than_fifty_fields"
        status: pass
    human_judgment: false
  - id: D6
    description: "fastapi, uvicorn[standard], python-multipart declared as dependencies at the exact versions 04-RESEARCH.md verified live against PyPI; httpx resolves transitively for fastapi.testclient.TestClient"
    verification:
      - kind: unit
        ref: "uv run python -c \"import fastapi, uvicorn, multipart, httpx\" (exit 0, versions printed: fastapi 0.139.0, uvicorn 0.51.0, httpx 0.28.1)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 1: Service Seam Extraction Summary

**Lifted cli.py's print-coupled orchestration (`_resolve_proposal`, `_map_one`'s save/export gates) into a public, print-free `service.py` that both the CLI and the coming FastAPI routes call, and added fastapi/uvicorn/python-multipart as verified dependencies.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-11T04:54:53Z
- **Tasks:** 3 (1 checkpoint, 2 auto/TDD)
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments

- New `src/assayingest/service.py`: public `resolve_or_map`/`resolve_table_mapping`/`confirm`/`save_profile_if_ready`/`export`/`has_credentials`, `MapResult`/`ConfirmResult` frozen dataclasses, and three typed exceptions (`MissingCredentialsError`, `NotReadyError`, `NoStoreError`) — zero `print()` calls, verified by `grep -rn "print(" src/assayingest/service.py` returning nothing.
- `cli.py` refactored to delegate: `_resolve_proposal` now calls `service.resolve_table_mapping` (passing its own monkeypatchable `propose_mapping` reference through so `monkeypatch.setattr(cli, "propose_mapping", ...)` keeps governing CLI behavior); `_save_profile_if_ready`/`_export_if_ready` now call `service.save_profile_if_ready`/`service.export` and translate the typed exceptions back into the CLI's existing printed messages. `cli._enrich_question` now calls the single shared `service.has_credentials()` instead of a locally duplicated copy.
- `fields/loader.py`: `_build_field_set` renamed to the public `from_dict(raw)`; `load()` is now a 4-line suffix-dispatch-then-delegate wrapper — the seam a future `POST /api/field-sets` body will build a validated `FieldSet` through.
- `pyproject.toml`/`uv.lock`: added `fastapi>=0.139.0`, `uvicorn[standard]>=0.51.0`, `python-multipart>=0.0.32`; resolved versions match 04-RESEARCH.md's live PyPI cross-check exactly. `httpx` (needed for `fastapi.testclient.TestClient`) resolves transitively — no extra dev dependency needed.
- The entire pre-existing test suite (398 passed / 4 skipped) stays green, plus 18 new tests (14 in `tests/test_service.py`, 4 in `tests/test_field_set.py`) — 416 passed / 4 skipped total.

## Task Commits

Each task was committed atomically (TDD RED→GREEN for both behavior-adding pieces):

1. **Task 1: Package legitimacy checkpoint** — no code commit (see "Checkpoint Handling" below); satisfied by `chore(04-01)` commit `7010e41`.
2. **Task 2: Extract resolve_or_map into service.py (RED first) and delegate cli.py:**
   - `dc3e97f` (test) — failing `tests/test_service.py`
   - `57f91e6` (feat) — `service.py` with `resolve_or_map`/`resolve_table_mapping`/`confirm`/`save_profile_if_ready`/`export`
   - `cc4deea` (refactor) — `cli._resolve_proposal` delegates to `service.resolve_table_mapping`
3. **Task 3: Extract confirm/save/export service functions + loader.from_dict + add deps:**
   - `53f25df` (test) — failing `tests/test_field_set.py::test_from_dict_*`
   - `90132d9` (feat) — `fields/loader.py::from_dict`, `load()` delegates
   - `f930619` (refactor) — `cli._save_profile_if_ready`/`_export_if_ready` delegate to `service.py`
   - `7010e41` (chore) — `uv add fastapi "uvicorn[standard]" python-multipart`
   - `f791712` (docs) — reworded a `service.py` docstring sentence that literally contained the substring `print(` and would have tripped the plan's own `grep -rn "print("` verification command

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `src/assayingest/service.py` - NEW: public orchestration seam (resolve_or_map, confirm, save_profile_if_ready, export, has_credentials) + MapResult/ConfirmResult + typed exceptions
- `tests/test_service.py` - NEW: 14 tests proving the seam decides/never-renders, the P1 gate, and the auto-apply/no-client invariant
- `src/assayingest/cli.py` - `_resolve_proposal`/`_save_profile_if_ready`/`_export_if_ready` become thin wrappers around `service.py`; removed now-dead `_has_credentials`/`_CREDENTIAL_ENV_VARS`/`os`/`uuid`/`datetime`/`LearnedProfile`/`stored_mapping_from`/`build_manifest`/`write_csv`/`write_json`/`write_xlsx` imports (moved to service.py)
- `src/assayingest/fields/loader.py` - `_build_field_set` → public `from_dict`; `load()` delegates
- `tests/test_field_set.py` - 4 new tests for `from_dict`
- `pyproject.toml` / `uv.lock` - fastapi, uvicorn[standard], python-multipart added

## Decisions Made

- **`save_profile_if_ready` naming (not bare `save_profile`):** the plan's literal action text says "Add save_profile helper", but `confirm()`'s own parameter is required to be named `save_profile: bool` by the plan's own behavior spec — a module-level function named `save_profile` would be shadowed by that parameter inside `confirm()`'s scope, an unresolvable Python name collision. Kept the CLI-mirroring name `save_profile_if_ready` (matches `cli._save_profile_if_ready` minus the underscore) instead.
- **`resolve_table_mapping` has no `validate()` call; `resolve_or_map` does.** `resolve_table_mapping` mirrors `cli._resolve_proposal` 1:1 (which never called `validate()` — that happens once, separately, in `_map_one`) so the CLI refactor carries zero behavior-change risk. `resolve_or_map` (the new path-based seam for the future API, not yet called from any CLI code path) calls `validate()` on both branches per D-03 and 04-RESEARCH.md's Pattern-1 sketch — since it isn't wired into `cli.run()` in this plan, this addition has no regression surface.
- **API-01/02/03 left unmarked in REQUIREMENTS.md.** These IDs also appear in 04-02 and 04-03's frontmatter (the plans that build the actual `api/` HTTP package); this plan's own objective text scopes itself to "the backend-logic side" only. Checking the box now would claim an unbuilt user-facing capability (no HTTP endpoint exists yet).
- **Task 1's package-legitimacy checkpoint was not paused on** — see "Checkpoint Handling" below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed a docstring sentence that would fail the plan's own `print(` grep verification**
- **Found during:** Task 3, final self-verification pass
- **Issue:** `service.py`'s module docstring used the word `print()` in prose ("...several of those functions `print()`, which is wrong..."), and the plan's `<verification>` block runs `grep -rn "print(" src/assayingest/service.py` expecting zero matches — the docstring text literally contained the substring `print(` and would have failed that check.
- **Fix:** Reworded to "print to stdout" — no code or behavior change.
- **Files modified:** `src/assayingest/service.py`
- **Verification:** `grep -rn "print(" src/assayingest/service.py` now returns nothing; full suite re-run green (416 passed / 4 skipped).
- **Committed in:** `f791712`

---

**Total deviations:** 1 auto-fixed (1 bug/wording fix), plus 3 documented design decisions (see "Decisions Made" above — naming collision avoidance, validate() placement, deferred requirements marking) that were necessary interpretations of the plan's own literal text, not scope changes.
**Impact on plan:** No scope creep; all changes were required for correctness (avoiding a name collision, matching the plan's own verification command) or for accurately reflecting what this plan actually delivers (backend seam only, not the HTTP surface).

## Checkpoint Handling

**Task 1 (package-legitimacy, `gate="blocking-human"`)** was not paused on. Per this plan's own `<critical_constraints>` instruction: "these are the project's declared stack and were verified legitimate in 04-RESEARCH.md (live PyPI cross-check). Proceed with the install — treat the legitimacy checkpoint as satisfied by the research finding; note it in the SUMMARY." Proceeded directly to `uv add fastapi "uvicorn[standard]" python-multipart`; the resolved versions (`fastapi==0.139.0`, `uvicorn==0.51.0`, `python-multipart==0.0.32`, `starlette==1.3.1`) match 04-RESEARCH.md's verified live-PyPI resolution exactly, confirming the research session's findings held at install time.

## Issues Encountered

None beyond the docstring/grep issue documented above.

## User Setup Required

None - no external service configuration required. (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` remain the only credential this project ever needs, unchanged by this plan.)

## Next Phase Readiness

- `service.py` is the seam 04-02 (mapping/upload routes) and 04-03 (confirm/field-sets routes) both build on — `resolve_or_map`, `confirm`, `export`, and `fields.loader.from_dict` are ready to be called from `api/routes/*.py` with zero further backend-logic changes needed.
- `fastapi`/`uvicorn[standard]`/`python-multipart` are installed and importable; `httpx` resolves transitively for `TestClient`-based route tests.
- No blockers. One open follow-up for 04-02/04-03: `resolve_or_map`'s new `validate()`-on-both-branches behavior is untested against `cli.run()`'s own flow (by design, since `cli.run()` doesn't call it) — the future API route wiring should exercise it end-to-end via `TestClient`, per 04-RESEARCH.md's "Testing the API" section.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: src/assayingest/service.py
- FOUND: tests/test_service.py
- FOUND: .planning/phases/04-api-review-ui/04-01-SUMMARY.md
- FOUND commits: dc3e97f, 57f91e6, cc4deea, 53f25df, 90132d9, f930619, 7010e41, f791712

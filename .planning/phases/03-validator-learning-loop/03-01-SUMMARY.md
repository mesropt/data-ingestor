---
phase: 03-validator-learning-loop
plan: 01
subsystem: learning-loop
tags: [sqlite, hashlib, unicodedata, repository-pattern, cli]

# Dependency graph
requires:
  - phase: 02-user-defined-fields-dynamic-mapper
    provides: FieldSet/FieldSet.signature, propose_mapping's optional-client seam, FieldMapping/MappingProposal domain shape
provides:
  - "column_signature(): order-independent, duplicate/blank-preserving, NFC+casefold+whitespace-collapsed column fingerprint (LEARN-01)"
  - "LearnedProfile / StoredFieldMapping: pure-domain profile model with manifest-shaped to_dict() (LEARN-02/06)"
  - "ProfileStore(ABC) repository seam + SqliteProfileStore: the ONLY module importing sqlite3 (D-01)"
  - "reconstruct_proposal()/_resolve_new_header(): normalised-lookup + occurrence-rank auto-apply reconstruction (LEARN-03, Pitfall 2/P1)"
  - "cli.py: --save-profile/--profiles-db flags, per-table auto-apply-or-fresh-Claude branch returning provenance, credential check relocated off the profile-hit path (LEARN-04/05, Pitfall 3/P2)"
affects: [03-02-validator, 03-03-export-manifest]

# Tech tracking
tech-stack:
  added: []  # stdlib only -- sqlite3, hashlib, json, unicodedata, uuid, datetime
  patterns:
    - "Repository seam (ProfileStore ABC) isolating sqlite3 to one infrastructure module, mirroring mapper.py's wire/domain boundary style"
    - "Save-time and lookup-time normalisation computed by the SAME private _normalise_header function (imported across the learning/ package) to guarantee bit-identical signatures"
    - "Per-table branch function (_resolve_proposal) returns provenance as a value, not just a printed line, so a later plan can thread it into an export manifest"

key-files:
  created:
    - src/assayingest/learning/signature.py
    - src/assayingest/learning/profile.py
    - src/assayingest/learning/store.py
    - src/assayingest/learning/sqlite_store.py
    - src/assayingest/learning/reconstruct.py
    - tests/test_signature.py
    - tests/test_profile_store.py
    - tests/test_learning_loop_cli.py
  modified:
    - src/assayingest/cli.py
    - .gitignore
    - tests/test_canonical.py
    - tests/test_cli_run.py

key-decisions:
  - "column_signature sorts a LIST of normalised headers, never a set -- preserves duplicate/blank header counts per D-02 (a set would silently collapse them)"
  - "StoredFieldMapping persists the NORMALISED source column + an occurrence rank, not the raw original-cased header -- reconstruction resolves against the new file's headers via normalised equality, never canonical._column_index's exact headers.index() (Pitfall 2)"
  - "The credential check moved from run() (unconditional) into _map_one's no-profile branch only -- a profile hit builds no Anthropic client and checks no credentials at all (Pitfall 3, D-10/P2)"
  - "_resolve_proposal is the per-table auto-apply/fresh-Claude branch and RETURNS (proposal, provenance) rather than only printing the D-08 transparency line, so 03-03's export manifest can consume it"
  - "SqliteProfileStore is constructed only when field_set is not None -- avoids touching disk (.assayingest/profiles.db) on early-exit run() paths that never do any learning-loop lookup"

patterns-established:
  - "learning/ package: signature.py + profile.py + store.py (pure domain, zero sqlite3) vs sqlite_store.py (the one infra module, isolated by grep gate in CI-equivalent verify)"
  - "reconstruct.py hosts both directions of the normalisation boundary (stored_mapping_from at save time, _resolve_new_header at apply time) so they can never drift apart"

requirements-completed: [LEARN-01, LEARN-02, LEARN-03, LEARN-04, LEARN-05, LEARN-06]

coverage:
  - id: D1
    description: "Order-independent, duplicate/blank-preserving, cross-process-stable column signature (LEARN-01)"
    requirement: "LEARN-01"
    verification:
      - kind: unit
        ref: "tests/test_signature.py -- all 6 tests"
        status: pass
    human_judgment: false
  - id: D2
    description: "LearnedProfile/StoredFieldMapping domain model with round-trip persistence, structural-hint carriage, one-field-set-many-profiles, and upsert-on-identical-key via SqliteProfileStore (LEARN-02/05/06, D-01)"
    requirement: "LEARN-02"
    verification:
      - kind: unit
        ref: "tests/test_profile_store.py -- all 9 tests"
        status: pass
    human_judgment: false
  - id: D3
    description: "Auto-apply reconstruction resolves a stored profile's columns against a case/whitespace-varied new file via normalised lookup + occurrence rank, never exact-string matching (LEARN-03, Pitfall 2/P1)"
    requirement: "LEARN-03"
    verification:
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_reconstruction_resolves_case_and_whitespace_varied_headers"
        status: pass
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_resolve_new_header_disambiguates_by_left_to_right_occurrence"
        status: pass
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_reconstruct_proposal_uses_occurrence_to_pick_the_right_duplicate"
        status: pass
    human_judgment: false
  - id: D4
    description: "End-to-end CLI money shot: a seeded profile auto-applies offline with zero yellow at confidence 1.0, propose_mapping never called, no Anthropic client built, no credentials checked (LEARN-03, D-08, Pitfall 3)"
    requirement: "LEARN-03"
    verification:
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_money_shot_auto_applies_offline_zero_yellow_no_claude_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "--save-profile refuses a not-ready mapping and persists a fully-clear one (LEARN-02, D-06); a signature mismatch (including no seeded profile) always falls back to the Claude path and still requires credentials there (LEARN-04/05)"
    requirement: "LEARN-04"
    verification:
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_save_profile_flag_refuses_to_save_a_blocked_mapping"
        status: pass
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_save_profile_flag_saves_a_fully_clear_mapping"
        status: pass
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_no_seeded_profile_falls_back_to_claude_and_still_requires_credentials"
        status: pass
      - kind: unit
        ref: "tests/test_learning_loop_cli.py::test_a_seeded_profile_for_a_different_signature_never_auto_applies"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-07-10
status: complete
---

# Phase 3 Plan 1: Learning Loop Summary

**SQLite-backed column-signature learning loop: a fully-clear mapping saves as a profile, and any later file with an exact-matching (order/case/whitespace-tolerant) column signature auto-maps at confidence 1.0 with zero Claude calls and zero credential checks.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-10T16:07:19Z
- **Completed:** 2026-07-10T16:23:50Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments
- `column_signature()` fingerprints a file's headers order-independently while still catching genuine format drift (typo, added/removed column, or a different duplicate/blank-column count) -- verified stable across a fresh subprocess, never the salted builtin `hash()`.
- `LearnedProfile`/`StoredFieldMapping` (pure domain) + `ProfileStore` ABC + `SqliteProfileStore` give the learning loop a local, gitignored SQLite store with sqlite3 isolated to exactly one module, parameterised queries throughout, and upsert-on-identical-key semantics.
- `reconstruct_proposal()` closes the P1 correctness hazard RESEARCH.md flagged: a saved profile's columns resolve onto a NEW file via normalised-header equality + left-to-right occurrence rank, not `canonical._column_index`'s exact `headers.index()` -- proven with a deliberately case/whitespace-varied fixture, not a byte-identical reuse.
- The CLI's `_map_one` now branches per table: a profile hit auto-applies with no Anthropic client built and no credential check at all (the money shot runs fully offline, unset `ANTHROPIC_API_KEY`, `propose_mapping` monkeypatched to raise if called); a miss falls back to Claude and only then checks credentials. `--save-profile` persists a fully-clear mapping (refused when any field is yellow, D-06); `--profiles-db PATH` overrides the default `.assayingest/profiles.db`.

## Task Commits

Each task followed the TDD RED -> GREEN cycle (MVP+TDD mode: `test(...)` then `feat(...)`):

1. **Task 1: Column signature** -- `0dfa639` (test), `83ecba8` (feat)
2. **Task 2: Profile domain model + repository seam + SQLite store** -- `2516cb9` (test), `f42d073` (feat)
3. **Task 3: Auto-apply reconstruction + CLI wiring + money-shot integration test** -- `82fd967` (test), `ccb580b` (feat)

_No refactor commits were needed -- each GREEN implementation passed on the first or second (test-fixture-bug) pass._

## Files Created/Modified
- `src/assayingest/learning/__init__.py` - empty package marker
- `src/assayingest/learning/signature.py` - `column_signature()`/`_normalise_header()` (LEARN-01)
- `src/assayingest/learning/profile.py` - `LearnedProfile`/`StoredFieldMapping` frozen dataclasses + `to_dict()`
- `src/assayingest/learning/store.py` - `ProfileStore(ABC)` repository seam, zero sqlite3 import
- `src/assayingest/learning/sqlite_store.py` - `SqliteProfileStore`, the ONLY module importing sqlite3
- `src/assayingest/learning/reconstruct.py` - `reconstruct_proposal()`/`_resolve_new_header()`/`stored_mapping_from()`
- `src/assayingest/cli.py` - `_resolve_proposal`, `_save_profile_if_ready`, `_resolve_store`; `run()`/`_map_and_report`/`_map_one` threaded with `store`/`save_profile`/`hint`; `--profiles-db`/`--save-profile` flags; credential check relocated
- `.gitignore` - `/.assayingest/` directory-level ignore (Pitfall 4: WAL/-shm/-journal side files)
- `tests/test_signature.py` - new, 6 tests
- `tests/test_profile_store.py` - new, 9 tests
- `tests/test_learning_loop_cli.py` - new, 10 tests
- `tests/test_canonical.py` - 2 existing `_map_one` tests updated (see Deviations)
- `tests/test_cli_run.py` - 2 existing `_map_one` tests updated (see Deviations)

## Decisions Made
- **Occurrence-rank disambiguation is tested at the unit level, not via an end-to-end duplicate-blank data value.** `FieldMapping.source_column` is just a string (matching the project's existing `canonical._column_index` design), so two fields mapped to the SAME literal duplicate/blank header string are indistinguishable by string comparison alone downstream. The occurrence-rank mechanism itself is proven directly against `_resolve_new_header` and `reconstruct_proposal` using headers with distinguishable literal casing per occurrence (`["A","DUP","b","dup","C","Dup"]`) -- this is a known, RESEARCH-acknowledged residual scope boundary (Assumption A3), not a gap introduced here.
- **`_save_profile_if_ready` and `_resolve_store` were added as private CLI helpers** (not explicitly named in the plan's action text) to keep `_map_one` at a single level of abstraction and to guard against constructing a real `SqliteProfileStore` (a disk write) on any `run()` path where `field_set is None` -- several pre-existing tests call `run()` without a field set and must stay side-effect-free.
- **`proposal_to_dict()` gained an optional `provenance` parameter** (default `None`) so the printed JSON draft also carries `"auto-applied-from-profile"` / `"fresh-claude"` for any consumer reading the printed output, in addition to `_resolve_proposal`'s programmatic return value.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture reused the same `profile_id` across two profiles in `test_profile_store.py`**
- **Found during:** Task 2 (Profile domain model + SQLite store) GREEN run
- **Issue:** `test_one_field_set_may_hold_several_profiles` built both profiles via the shared `_profile()` helper, which hardcoded `profile_id="p-1"`; saving two profiles with the same `id` PRIMARY KEY under different signatures raised `sqlite3.IntegrityError`, not a real implementation bug.
- **Fix:** Added a `profile_id` parameter to the `_profile()` test helper (default `"p-1"`), and passed distinct ids (`"p-a"`/`"p-b"`) in that one test.
- **Files modified:** `tests/test_profile_store.py`
- **Verification:** `python -m pytest tests/test_profile_store.py -x -q` -- 9/9 pass
- **Committed in:** `f42d073` (Task 2 GREEN commit)

**2. [Rule 3 - Blocking] Relocating the credential check off `run()` broke two existing direct `_map_one` unit tests**
- **Found during:** Task 3 (CLI wiring) GREEN run, full-suite verification
- **Issue:** The plan explicitly requires the credential check to move from `run()`'s unconditional gate into `_map_one`'s no-profile branch (Pitfall 3, D-10/P2), so a profile hit never checks credentials. Four pre-existing tests (`test_cli_run.py::test_map_one_exits_5_when_the_proposal_is_blocked`, `test_map_one_exits_0_only_when_the_proposal_is_ready`, and `test_canonical.py`'s two `_map_one` tests) call `_map_one` directly with a monkeypatched `propose_mapping` and no `store` -- meaning they now always take the credential-gated no-profile branch, and none of them set `ANTHROPIC_API_KEY`, so they started failing with exit 3 instead of the expected 5/0.
- **Fix:** Added `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")` to each of the four tests -- `propose_mapping` was already monkeypatched, so no real credential is needed, only a truthy env var to pass the (now-relocated) gate.
- **Files modified:** `tests/test_cli_run.py`, `tests/test_canonical.py`
- **Verification:** `python -m pytest -q` -- 337 passed, 4 skipped (unchanged skip count, all live-API-key tests)
- **Committed in:** `ccb580b` (Task 3 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes were direct, foreseen consequences of the plan's own required design (per-table credential relocation, upsert-key test correctness). No scope creep; no production behavior changed beyond what the plan specified.

## Issues Encountered
None beyond the two deviations above.

## User Setup Required
None - no external service configuration required. The profile store is a local SQLite file created on first use; no new dependencies were added (stdlib `sqlite3`/`hashlib`/`json`/`unicodedata`/`uuid` only).

## Next Phase Readiness
- `_resolve_proposal`'s `(proposal, provenance)` return value is ready for 03-03 (export manifest) to consume directly -- provenance is already threaded into the printed JSON draft via `proposal_to_dict(proposal, provenance)`.
- `LearnedProfile.to_dict()` is already the exact shape D-09's manifest is meant to reuse as its base.
- 03-02 (validator) can run its checks on either path (auto-applied or fresh-Claude) since both produce an ordinary `MappingProposal` -- `reconstruct_proposal` is a drop-in sibling of `propose_mapping`, not a special case downstream code needs to branch on.
- No blockers. The Assumption A3 residual risk (duplicate/blank column reordering across repeat vendor exports) remains accepted for v1 per RESEARCH.md's resolution and is unaffected by this plan's scope.

---
*Phase: 03-validator-learning-loop*
*Completed: 2026-07-10*

## Self-Check: PASSED

- All 10 created/referenced files verified present on disk.
- All 6 task commit hashes (`0dfa639`, `83ecba8`, `2516cb9`, `f42d073`, `82fd967`, `ccb580b`) verified present in `git log`.

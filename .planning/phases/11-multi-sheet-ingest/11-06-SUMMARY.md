---
phase: 11-multi-sheet-ingest
plan: "06"
subsystem: api
tags: [fastapi, structural-hint, crosswalk, date-question, vendor-memory, upload-registry]

# Dependency graph
requires:
  - phase: 11-multi-sheet-ingest (11-03)
    provides: row provenance / origin_sheet round-trip the retention boundary
  - phase: 10-frictionless-correct-ingest
    provides: Python-first crosswalk prefill (D-10-03), date question (D-10-07), recall_vendor (10-09), require_user gate (D-10-13)
provides:
  - "UploadEntry.sheet — the human's explicit worksheet choice, retained across a structural question and round-tripped through pending_uploads with the .get() idiom"
  - "/api/upload's structural-question branch retains schema_name, sheet and strictness alongside the temp file"
  - "/api/structural-hint/resolve re-fetches the Schema by retained name and passes schema=, sheet=, strictness= into resolve_or_map — crosswalk prefill, escalation line and vendor pre-fill now identical to the direct upload path"
  - "/api/structural-hint/resolve checks result.date_question and returns kind=date_question — the 260712-qgc Confirm dead-end is pinned closed on this route too"
affects: [11-07 sheet groups, 11-08, structural-hint flow, review screen]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Resolve routes re-fetch the Schema by the RETAINED name via get_schema_store (date_format.py idiom), never retain the object"
    - "Every question-branch UploadEntry re-put must carry the full resolution context forward (schema_name/sheet/strictness) so a second ask never re-enters the hole"

key-files:
  created:
    - tests/api/test_structural_hint_context.py
  modified:
    - src/assayingest/api/state.py
    - src/assayingest/api/routes/upload.py
    - src/assayingest/api/routes/structural_hint.py

key-decisions:
  - "upload.py's structural-question entry relies on UploadEntry's strictness default ('strict') rather than passing a nonexistent route variable — identical value to what resolve_or_map ran under, pinned by test"
  - "The still-ambiguous re-put in structural_hint.py also retains schema_name/sheet/strictness, so a SECOND hint attempt keeps the context (Rule 2)"

patterns-established:
  - "Retained-context resolve: pop entry -> re-fetch Schema by name -> resolve with schema/sheet/strictness -> branch on date_question -> recall_vendor on the mapping tail"

requirements-completed: [SHEET-04]

coverage:
  - id: D1
    description: "A structural question retains schema_name, sheet and strictness on the UploadEntry; sheet round-trips pending_uploads and an old row without the key rehydrates"
    requirement: SHEET-04
    verification:
      - kind: unit
        ref: "tests/api/test_structural_hint_context.py#test_structural_question_entry_retains_schema_name_sheet_and_strictness"
        status: pass
      - kind: unit
        ref: "tests/api/test_structural_hint_context.py#test_entry_json_round_trip_preserves_the_retained_sheet"
        status: pass
      - kind: unit
        ref: "tests/api/test_structural_hint_context.py#test_an_old_persisted_row_without_the_sheet_key_still_rehydrates"
        status: pass
    human_judgment: false
  - id: D2
    description: "Resolving a structural hint runs the Python-first crosswalk prefill (zero Claude calls on full coverage) and carries the escalation line"
    requirement: SHEET-04
    verification:
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_resolve_prefills_from_the_crosswalk_and_never_calls_claude"
        status: pass
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_resolve_carries_the_escalation_line"
        status: pass
    human_judgment: false
  - id: D3
    description: "The resolved response pre-fills the vendor from the crosswalk, and a subsequent /api/confirm with it succeeds instead of 422-ing"
    requirement: SHEET-04
    verification:
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_resolve_prefills_the_vendor_and_confirm_accepts_it"
        status: pass
    human_judgment: false
  - id: D4
    description: "An ambiguous date column behind a structural question raises the date question (never a permanently-amber mapping), and answering it completes normally — the 260712-qgc dead-end pinned closed"
    requirement: SHEET-04
    verification:
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_ambiguous_date_behind_a_structural_question_raises_the_date_question"
        status: pass
    human_judgment: false
  - id: D5
    description: "Resolving a hint on a multi-sheet workbook re-parses the retained sheet, never the workbook's re-ranked winner (T-11-21)"
    requirement: SHEET-04
    verification:
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_resolve_reparses_the_retained_sheet_never_the_reranked_winner"
        status: pass
    human_judgment: false

# Metrics
duration: 11min
completed: 2026-07-13
status: complete
---

# Phase 11 Plan 06: Structural-Hint Resolve Context Summary

**The structural-hint resolve route now runs the identical resolution the direct upload path does — retained schema/sheet/strictness restore the crosswalk prefill, escalation line, vendor pre-fill and the date question, and a multi-sheet resolve stays on the human's chosen sheet (D-11-22)**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-13T07:42:19Z
- **Completed:** 2026-07-13T07:53:30Z
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files modified:** 4

## Accomplishments
- `UploadEntry.sheet` added (additive, defaulted, `.get()` rehydration) and the structural-question branch of `/api/upload` now retains `schema_name`, `sheet` and `strictness` — the context the resolve route needs is no longer thrown away when the question is asked.
- `/api/structural-hint/resolve` re-fetches the Schema by the retained name (the `date_format.py` idiom) and passes `schema=`, `sheet=entry.sheet`, `strictness=entry.strictness` into `service.resolve_or_map` — the D-10-03 Python-first prefill runs, so a fully-covered file pre-fills at confidence 1.0 with ZERO Claude calls.
- The mapping tail now mirrors `/api/upload`'s exactly: `escalation=result.escalation` and `vendor_memory` via `recall_vendor`, so Confirm (which REQUIRES a vendor) is reachable after a structural question.
- `result.date_question` is checked: an ambiguous date column behind a structural question returns `kind: "date_question"` with the table+proposal retained (no re-parse), and answering it completes normally — the exact Confirm dead-end quick task 260712-qgc fixed on `/api/upload` can no longer be re-entered here.
- Resolving a hint on a multi-sheet workbook re-parses the sheet the human is on (`parse(path, sheet=...)` short-circuits ranking) — the prerequisite 11-07's sheet groups build on.

## Task Commits

Each task was committed atomically (TDD: test then feat):

1. **Task 1: retain the Schema, the sheet and the strictness across a structural question**
   - RED: `bcf1dc4` (test)
   - GREEN: `c8c447f` (feat)
2. **Task 2: structural_hint.py resolves with the full context, and asks the date question**
   - RED: `ca427be` (test)
   - GREEN: `800b5e2` (feat)

## Files Created/Modified
- `src/assayingest/api/state.py` - `UploadEntry.sheet: str | None = None`; serialized in `_entry_to_json`, rehydrated with `raw.get("sheet")` in `_entry_from_json`
- `src/assayingest/api/routes/upload.py` - structural-question `UploadEntry` retains `schema_name=schema_name, sheet=sheet`
- `src/assayingest/api/routes/structural_hint.py` - `get_schema_store` dependency; full-context `resolve_or_map` call; date-question branch; escalation/vendor tail; still-ambiguous re-put keeps the context
- `tests/api/test_structural_hint_context.py` - 8 tests: 3 retention/persistence, 4 consequence regressions, 1 retained-sheet re-parse

## Decisions Made
- **upload.py does not pass `strictness=` explicitly:** the plan's literal text (`strictness=strictness`) names a variable the route does not have — no route lets a client vary strictness today. The `UploadEntry` default (`"strict"`) is byte-identical to what the route's own `resolve_or_map` call ran under, and the retention test pins `entry.strictness == "strict"`.
- **The date-question entry retains `strictness=entry.strictness` explicitly** (upload.py leaves the default) so whatever mode the original upload retained is preserved through the second hop.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Still-ambiguous re-put also retains the context**
- **Found during:** Task 2 (structural_hint.py resolve)
- **Issue:** The plan specified retention on `/api/upload`'s question branch and consumption in the resolve route, but the resolve route's own still-ambiguous branch (a hint that does not resolve the parse, Pattern 5) re-puts a fresh `UploadEntry` that dropped `schema_name`/`sheet`/`strictness` — a SECOND hint attempt would re-enter the exact hole this plan closes.
- **Fix:** The re-put entry carries `schema_name=entry.schema_name, sheet=entry.sheet, strictness=entry.strictness` forward.
- **Files modified:** src/assayingest/api/routes/structural_hint.py
- **Verification:** `uv run pytest tests/ -q` green; the must-have truth "the sheet survives the structural question" holds across repeated asks.
- **Committed in:** `800b5e2` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical). Plus one plan-literalism adjustment (no `strictness` variable exists in upload.py; the default carries the identical value — documented under Decisions Made).
**Impact on plan:** Correctness-only; no scope creep. All must-have truths, artifacts and key links delivered as specified.

## TDD Gate Compliance
- RED gate: `bcf1dc4`, `ca427be` (test commits, each verified failing before implementation — the four consequence tests failed on the real bug: Claude called for fully-covered fields, `mapping` returned instead of `date_question`, workbook re-ranked instead of the retained sheet).
- GREEN gate: `c8c447f`, `800b5e2` (feat commits after their RED).
- REFACTOR: not needed — no cleanup beyond the GREEN implementations.

## Known Stubs
None — no placeholders, hardcoded empty values, or unwired data paths introduced.

## Threat Flags
None — no new security surface. All four `mitigate` dispositions from the plan's threat register applied: `require_user` unchanged (T-11-18), `headers_only=entry.headers_only` still passed and the `schema=` prefill REDUCES what reaches Claude (T-11-19), the date-question branch mirrors `/api/upload` (T-11-20), `sheet=entry.sheet` short-circuits re-ranking (T-11-21). Zero packages installed (T-11-SC).

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 11-07 (sheet groups) can now safely route every sheet-group member through `/api/structural-hint/resolve` with an explicit retained `sheet` — the route resolves with full context and never re-ranks the workbook.
- Full suite: 1020 passed, 4 skipped (live-API opt-ins), no existing test modified.

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

## Self-Check: PASSED

- Created file exists: tests/api/test_structural_hint_context.py
- All four task commits present: bcf1dc4, c8c447f, ca427be, 800b5e2
- No file deletions in the task commits
- Full suite green: 1020 passed, 4 skipped

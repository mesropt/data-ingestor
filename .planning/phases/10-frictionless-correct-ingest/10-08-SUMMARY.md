---
phase: 10-frictionless-correct-ingest
plan: 08
subsystem: api
tags: [fastapi, pydantic, date-order, schema-governance, gap-closure, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 03
    provides: "service.resolve_date_formats/DateResolution/UnresolvedDateColumnsError"
  - phase: 10-frictionless-correct-ingest plan 05
    provides: "kind=\"date_question\" 4th arm + POST /api/date-format/resolve; the honestly-reported gap this plan closes"
  - phase: 10-frictionless-correct-ingest plan 06
    provides: "the editable Schemas page whose Create Schema button needed this plan's empty-Schema fix; the honestly-reported second gap"
provides:
  - "service.confirm(date_answers=) -- re-derives resolve_date_formats from the retained table + the human's answered order, threading the resolution into BOTH validate() and canonical.assemble()"
  - "UploadEntry.date_answers -- the human's per-column order, retained by /api/date-format/resolve, read ONLY by /api/confirm, never a format string"
  - "fields.loader.from_dict(allow_empty=False) -- POST /api/schemas is the single opt-in call site for creating a brand-new, empty Schema"
affects: [10-frictionless-correct-ingest plan 07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "confirm() re-derives the date resolution itself (resolve_date_formats(answers=entry.date_answers)) rather than accepting a stashed format dict -- the P1 gate's 'rebuild fresh, never trust a caller's claim' discipline extended one hop further, and it survives a human re-pointing a date field at a different column at review time."
    - "date_answers is keyword-only and defaulted None on both UploadEntry and service.confirm, so every existing construction/call site is untouched byte-for-byte -- the same additive-defaulting idiom every other Phase 10 UploadEntry field already uses."
    - "fields.loader.from_dict(allow_empty=False) opts a SINGLE named call site (schemas.py::create_schema) out of a guard written for field-set uploads, rather than weakening the guard or forking a second loader -- the other five callers keep the exact same ValueError on an empty fields: []."

key-files:
  created:
    - tests/api/test_confirm_dates.py
    - tests/api/test_schema_create_empty.py
  modified:
    - src/assayingest/service.py
    - src/assayingest/api/state.py
    - src/assayingest/api/routes/date_format.py
    - src/assayingest/api/routes/confirm.py
    - src/assayingest/fields/loader.py
    - src/assayingest/api/routes/schemas.py

key-decisions:
  - "Gap 1 fixed per the plan's Decision 1 exactly as written: retained the human's ORDER (day_first/month_first) on UploadEntry.date_answers, never a stashed formats dict -- confirm() re-derives the concrete strptime format itself via resolve_date_formats(answers=entry.date_answers) against the retained table and its own freshly-rebuilt proposal."
  - "Gap 2 fixed per Decision 2 exactly as written: from_dict gained allow_empty (keyword-only, default False); POST /api/schemas is the one caller that opts in. Verified zero frontend files needed changing (git diff --name-only HEAD -- frontend/ is empty) -- the planning premise that Schemas.tsx already sends the correct body held."
  - "The plan's own verify gate (grep for 'canonical.assemble' + the next 120 chars containing 'date_formats=resolution.formats') initially failed because confirm()'s own docstring ALSO contains the literal substring 'canonical.assemble()' before the real call -- str.split() matched the docstring occurrence, not the code. Fixed by rephrasing the docstring to refer to 'the canonical assembly step below' instead of repeating the literal function name, so the grep-style check targets the actual call. No behavior changed; this is a test/verification-script fix, not a deviation from the design."

requirements-completed: [INGEST-04, INGEST-05]

coverage:
  - id: D1
    description: "A curator who answers the ambiguous-date question can press Confirm and it SUCCEEDS -- the date field stays clear and is never re-asked; the exported value is ISO 8601 under the order they chose"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_resolve_then_confirm_succeeds_with_date_field_clear"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_confirm_exports_iso_date_converted_under_the_chosen_order"
        status: pass
    human_judgment: false
  - id: D2
    description: "An ambiguous, unanswered date column still fails closed at confirm (422) -- no bypass opened; a client cannot smuggle a date_format into the gate"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_confirm_without_resolving_an_ambiguous_date_still_422s"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_confirm_request_has_no_date_field_and_ignores_an_injected_one"
        status: pass
    human_judgment: false
  - id: D3
    description: "An unambiguous, undeclared-format date column (never raised as a question) also confirms and exports ISO -- the second half of the 10-05 gap, fixed for free by re-deriving rather than retaining"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_unambiguous_undeclared_date_column_confirms_and_exports_iso"
        status: pass
      - kind: unit
        ref: "tests/api/test_confirm_dates.py#test_confirm_with_no_date_field_behaves_exactly_as_today"
        status: pass
    human_judgment: false
  - id: D4
    description: "A verified user creates a brand-new, empty Schema on the Schemas page (the exact body Schemas.tsx already sends) and populates it via add_schema_field"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_post_schemas_with_an_empty_field_set_creates_an_empty_schema"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_an_empty_schema_can_then_be_populated_with_add_schema_field"
        status: pass
    human_judgment: false
  - id: D5
    description: "from_dict's empty-fields guard is intact on every path it was written for (field-set upload, POST /api/field-sets, the confirm drift-check); exactly one call site opts out; the verified-user gate on Schema creation is unchanged"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_post_field_sets_with_an_empty_field_set_still_422s"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_from_dict_direct_call_with_an_empty_fields_list_still_raises"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_confirm_drift_check_with_an_empty_field_set_still_422s"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_post_schemas_empty_field_set_signed_out_returns_401"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_post_schemas_empty_field_set_unverified_returns_403"
        status: pass
      - kind: unit
        ref: "tests/api/test_schema_create_empty.py#test_post_schemas_with_a_non_empty_field_set_still_works"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 08: Gap Closure -- Dates Survive Confirm, Empty Schemas Are Creatable Summary

**`service.confirm()` now re-derives the human's resolved date order from the retained upload and threads it into both the validation gate and the canonical export (closing the INGEST-04 loop 10-05/10-06 reported), and `POST /api/schemas` can create a brand-new, empty governed Schema via a single named opt-in on `fields.loader.from_dict` (closing the INGEST-05 gap 10-06 reported) -- zero frontend changes required.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-12T17:13:48+04:00 (first commit)
- **Completed:** 2026-07-12T17:20:29+04:00
- **Tasks:** 2
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments

- `UploadEntry` gained `date_answers: dict[str, DateOrder] | None = None` -- the one thing the server cannot re-derive: the human's per-column date ORDER, never a strptime format string. `POST /api/date-format/resolve` retains the answer it just applied onto the fresh entry it re-puts.
- `service.confirm` gained a keyword-only, defaulted `date_answers` parameter. It calls `resolve_date_formats(table, proposal, field_set, answers=date_answers)` against the retained table and the FRESH `MappingProposal` it just rebuilt, then threads the resolution into BOTH `validate()` (so the gate agrees a resolved date field is clear) AND `canonical.assemble()` (so the exported cell is actually ISO 8601) -- threading only the first would have produced a green gate and a wrong file.
- `api/routes/confirm.py` passes `date_answers=entry.date_answers` -- read only from the server-retained upload, never from the request body (`ConfirmRequest` carries no date field of any kind) -- and maps a newly-possible `service.UnresolvedDateColumnsError` to 422 (only reachable if a human re-points a date field at a different, still-ambiguous column after already resolving one).
- Because the fix re-derives from evidence rather than replaying a stashed format, it also closes the *second* half of the 10-05 gap for free: an unambiguous-but-undeclared-format date column (no question ever raised) now also survives confirm and exports as ISO, proven by `test_unambiguous_undeclared_date_column_confirms_and_exports_iso`.
- `fields/loader.py::from_dict` gained a keyword-only `allow_empty: bool = False`. `POST /api/schemas` (`create_schema`) is the single caller that opts in with `allow_empty=True` -- an empty Schema is now a legitimate starting state, created via the exact `{"name": null, "fields": []}` body `Schemas.tsx:152` already sends, then populated field-by-field via `add_schema_field` (Plan 04). All five other callers (`load()`, the field_set upload path, `POST /api/field-sets`, the confirm drift-check, the stored-profile rehydrate) keep the guard byte-identical.

## Task Commits

Each task was committed atomically (TDD RED then GREEN per task):

1. **Task 1: The human's answered date order survives the confirm gate (INGEST-04)** - test `ed80ceb`, feat `564b87d`
2. **Task 2: A verified user can create a new (empty) Schema (INGEST-05)** - test `c247b64`, feat `9ae67d8`

_TDD Gate Compliance: both tasks' `test(10-08)` commits precede their `feat(10-08)` commits, verified in git log order._

## Files Created/Modified

- `src/assayingest/service.py` - `confirm()` gains keyword-only `date_answers`; re-derives `resolve_date_formats` and threads the resolution into both `validate()` and `canonical.assemble()`
- `src/assayingest/api/state.py` - `UploadEntry.date_answers: dict[str, DateOrder] | None = None`
- `src/assayingest/api/routes/date_format.py` - retains `date_answers=answers` onto the fresh re-put `UploadEntry`
- `src/assayingest/api/routes/confirm.py` - passes `date_answers=entry.date_answers`; maps `UnresolvedDateColumnsError` -> 422
- `src/assayingest/fields/loader.py` - `from_dict(raw, *, allow_empty: bool = False)`
- `src/assayingest/api/routes/schemas.py` - `create_schema` calls `from_dict(body.field_set, allow_empty=True)`
- `tests/api/test_confirm_dates.py` (new) - 6 tests: the resolve->confirm->ISO-export gap, fail-closed pin, no-smuggling pin, the free unambiguous-column fix, regression pin
- `tests/api/test_schema_create_empty.py` (new) - 8 tests: empty-Schema creation + population, guard-intact pins (field-sets route, direct `from_dict` call, confirm drift-check), auth-gate pins, non-empty-promote pin

## Decisions Made

- Implemented both gaps exactly per the plan's two locked design decisions -- no deviation from either. See `key-decisions` in the frontmatter for the two substantive ones (re-derive vs retain; the single opt-in call site) plus the one incidental fix to the plan's own verify-gate wording (a docstring literal collided with the grep-style check; rephrased, no behavior change).
- `_confirm_mappings_from_response` (test helper) strips `validator_note` from a `MappingResponse`'s `field_mappings` before replaying them into a confirm body -- proves the whole wire round-trip (resolve's response -> confirm's request) rather than hand-rolling a synthetic mapping.

## Deviations from Plan

None - plan executed exactly as written. Both fixes match the plan's `<the_two_design_decisions>` section precisely: `UploadEntry.date_answers` retains an order, never a format; `confirm()` re-derives via `resolve_date_formats` and threads into both `validate()` and `canonical.assemble()`; `from_dict(allow_empty=False)` defaults to the guard everywhere except the one named opt-in.

## Issues Encountered

- The plan's own verify command (`python -c "... assert 'date_formats=resolution.formats' in src.split('canonical.assemble')[1][:120] ..."`) initially failed for a benign reason: `confirm()`'s own new docstring, written to explain the fix, contained the literal substring `canonical.assemble()` in its prose -- `str.split()` matched that occurrence before the real code line. Fixed by rephrasing the docstring sentence to say "the canonical assembly step below" instead of repeating the function name literally. No source behavior changed; re-ran the verify command afterward and it passed cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Both requirements flagged `requirements-partial`/gap by 10-05 and 10-06 are now fully delivered end-to-end: INGEST-04 (resolve -> confirm -> ISO export, fail-closed preserved) and INGEST-05 (create + populate a Schema on the Schemas page).
- Plan 10-07 (which 10-06's summary flagged as BLOCKED on this plan) can now proceed -- the Review/Confirm UI's date handling and the Schemas page's Create button both have a working backend path.
- Full suite: backend 806 passed, 4 skipped (792 baseline + 6 + 8 new tests, zero regressions). Frontend 164 passed, unchanged; `git diff --name-only HEAD -- frontend/` is empty -- zero frontend files touched, confirming the plan's own premise.
- Dev servers were left running (Postgres via docker compose, uvicorn on :8000, Vite on :5173) per the execution environment's instruction.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 9 created/modified files confirmed present on disk; all 4 task commit hashes (`ed80ceb`, `564b87d`, `c247b64`, `9ae67d8`) confirmed present in git log. Full suite re-verified green: backend 806 passed, 4 skipped (792 baseline + 6 + 8 new tests, zero regressions). Frontend 164 passed, unchanged; `git diff --name-only HEAD -- frontend/` empty.

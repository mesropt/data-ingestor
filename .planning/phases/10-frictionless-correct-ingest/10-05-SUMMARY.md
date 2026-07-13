---
phase: 10-frictionless-correct-ingest
plan: 05
subsystem: api
tags: [fastapi, pydantic, wire-models, date-order, escalation, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 03
    provides: "service.resolve_date_formats/DateResolution/UnresolvedDateColumnsError, service.field_set_from_schema/Escalation/_python_first_prefill, resolve_or_map(schema=...) already wired"
  - phase: 10-frictionless-correct-ingest plan 04
    provides: "the four presets seeded as governed Schemas at startup, so a real schema_name exists to target"
provides:
  - "POST /api/upload accepts schema_name (first in precedence) and derives the FieldSet from a governed Schema (D-10-02); field_set/field_set_template_id remain fully supported"
  - "MappingResponse.escalation: dict | None -- {python, claude, total} on the wire, None when no Schema was targeted"
  - "POST /api/upload's 4th discriminated arm, kind=\"date_question\", for a genuinely order-ambiguous mapped date column"
  - "POST /api/date-format/resolve -- apply the human's per-column order (never a format string), re-validate from the retained table with NO re-parse"
  - "UploadEntry grows proposal/schema_name/strictness/escalation, retained only while a date question is pending"
  - "wire.DateFormatColumnOut/DateFormatQuestionResponse/DateFormatChoiceIn/DateFormatResolveRequest"
affects: [10-frictionless-correct-ingest plan 06, 10-frictionless-correct-ingest plan 07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_resolve_field_set returns a small frozen dataclass (_ResolvedTarget: field_set + schema|None) rather than two parallel lookups, so the route can thread schema= into resolve_or_map's Python-first pre-fill without a second Schema fetch."
    - "schema_name is checked FIRST in _resolve_field_set's precedence (D-10-02); field_set/field_set_template_id are unchanged fallback branches -- purely additive, verified by running test_upload.py/test_reconcile.py completely unmodified."
    - "The date_question retention shape mirrors the structural/reconcile ones (tmp_path=None, table+proposal retained) -- a THIRD shape on UploadEntry, distinguished by carrying proposal/schema_name/strictness/escalation instead of tmp_path/map_envelope."
    - "date_format.py resets every retained mapping's needs_confirmation to False before re-validating with the resolved date_formats override -- required because validate() is additive-only (may only OR a violation in, never clear one), so re-validating the STALE (already-flagged-ambiguous) proposal as-is would permanently carry the pre-resolution flag forward even once the order is known."
    - "Escalation is carried forward on UploadEntry (not recomputed) from the original resolve_or_map call -- the crosswalk coverage does not change between the date question and its answer, so /api/date-format/resolve's response reports the exact same counts, never a second computation."

key-files:
  created:
    - src/assayingest/api/routes/date_format.py
    - tests/api/test_upload_schema_target.py
    - tests/api/test_date_format_route.py
    - .planning/phases/10-frictionless-correct-ingest/deferred-items.md
    - .planning/todos/pending/parser-hash-comment-truncation.md
  modified:
    - src/assayingest/api/routes/upload.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/state.py
    - src/assayingest/api/app.py

key-decisions:
  - "schema_name wins precedence in _resolve_field_set even on the map-file/reconcile branch (the single call site upstream of the map_file/plain-path split) -- verified this does not change test_reconcile.py's behavior since every test there sends a schema_name whose Schema's fields are content-identical to the field_set it also sends (same names/types); reconcile_or_map/apply_reconcile_resolution themselves are untouched and never receive schema=."
  - "MappingResponse.escalation is a plain dict ({python, claude, total}), not a nested Pydantic submodel, matching the plan's literal 'gains escalation: dict | None' instruction -- built from service.Escalation only inside MappingResponse.from_proposal, never re-derived elsewhere."
  - "UploadEntry.escalation is a field the plan's own action text did not explicitly enumerate (only proposal/schema_name/strictness were named) but is required to satisfy the acceptance criterion 'the resolve response carries the same escalation counts... the original mapping would have' without recomputing anything or touching service.py (out of this plan's files_modified) -- treated as a Rule 2 (missing critical functionality) addition within state.py, which IS in scope."
  - "date_format.py resets needs_confirmation on every retained mapping before calling validate() with the resolved date_formats override (see tech-stack pattern above) -- discovered via a failing test (test_resolve_with_a_valid_order_returns_mapping_resolved_cleanly initially asserted needs_confirmation is False and got True), root-caused to the validator's documented additive-only discipline, fixed as a Rule 1 bug rather than weakening the test."
  - "The 'assembled dates are ISO under the chosen order' claim in the plan's Task 2 <behavior> text could not be proven at the HTTP boundary via /api/confirm + export: service.confirm() (out of this plan's files_modified) calls validate()/canonical.assemble() WITHOUT threading resolution.formats/date_contradictions through at all, so a resolved-but-undeclared date field would be RE-FLAGGED as needing confirmation at confirm time, undoing the date-question resolution entirely. This is a genuine, real architecture gap spanning confirm.py/service.py (neither in files_modified) -- logged as a new deferred item rather than silently expanding scope or fixing it inline. Verified instead at the boundary the wire CAN prove: the resolve response's field_mappings show needs_confirmation=False / a clean validator_note for the resolved date field, proving resolve_date_formats + validate() resolved correctly server-side."

requirements-completed: [INGEST-01, INGEST-02, INGEST-04]

coverage:
  - id: D1
    description: "POST /api/upload accepts schema_name and derives the target field set from a governed Schema (D-10-02); field_set/field_set_template_id remain fully supported and unmodified"
    requirement: "INGEST-01"
    verification:
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_upload_with_schema_name_targets_exactly_that_schemas_fields"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_field_set_json_with_no_schema_name_behaves_as_today"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_schema_name_wins_precedence_over_field_set_when_both_are_sent"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_unknown_schema_name_is_404"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_no_target_provided_is_422_and_names_schema_name"
        status: pass
      - kind: integration
        ref: "tests/api/test_upload.py (21 pre-existing tests, unmodified, all green)"
        status: pass
      - kind: integration
        ref: "tests/api/test_reconcile.py (pre-existing tests, unmodified, all green)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A fully-crosswalked upload calls propose_mapping zero times and reports escalation={python,claude,total}; a partially-covered one calls the mapper only for the uncovered remainder; a tombstoned field/alias is honoured on both read paths"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_full_crosswalk_coverage_calls_the_mapper_zero_times_and_reports_escalation"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_partial_crosswalk_coverage_calls_the_mapper_only_for_the_uncovered_remainder"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_a_tombstoned_field_is_absent_from_the_target_field_list"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_schema_target.py#test_a_tombstoned_alias_no_longer_prefills_and_escalates_to_claude"
        status: pass
    human_judgment: false
  - id: D3
    description: "An ambiguous mapped date column with no declared/agreeing format returns kind=\"date_question\" (never a mapping); multiple ambiguous columns bundle into ONE question; a structural question still takes precedence"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_ambiguous_date_column_returns_date_question_not_mapping"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_multiple_ambiguous_date_columns_are_bundled_into_one_question"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_unambiguous_date_column_maps_straight_through_with_no_question"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_structural_question_still_takes_precedence_over_date_question"
        status: pass
    human_judgment: false
  - id: D4
    description: "headers_only strips example_values from the date_question wire response (redaction lives in wire.py's from_question, in exactly one place) while detection and ambiguous_row_count are unaffected"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_headers_only_strips_the_evidence_values_from_the_date_question"
        status: pass
      - kind: integration
        ref: "tests/test_headers_only.py (pre-existing tests, unmodified, all green)"
        status: pass
    human_judgment: false
  - id: D5
    description: "POST /api/date-format/resolve applies an ORDER (never a format string) and re-validates the retained table/proposal with NO re-parse; an unanswered ambiguous column fails closed at 422; an unknown token is 404"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_with_a_valid_order_returns_mapping_resolved_cleanly"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_rejects_an_invalid_order_literal_at_the_boundary"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_a_client_supplied_date_format_extra_key_is_dropped_and_ignored"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_date_format_choice_in_has_no_date_format_field_by_design"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_fails_closed_when_a_column_is_left_undecided"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_with_an_empty_choices_list_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_unknown_token_is_404"
        status: pass
      - kind: unit
        ref: "tests/api/test_date_format_route.py#test_resolve_returns_a_fresh_token_whose_entry_still_carries_no_tmp_path"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 05: The date_question Response Arm + Schema-Targeted /api/upload Summary

**`/api/upload` now targets a governed Schema by name (deriving its FieldSet and reporting a `{python, claude, total}` escalation split) and surfaces a 4th `kind="date_question"` arm for a genuinely order-ambiguous mapped date column, resolved via a new no-reparse `POST /api/date-format/resolve` that accepts only an order (never a format string).**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-07-12T16:10:43+04:00 (first commit)
- **Completed:** 2026-07-12T16:27:47+04:00
- **Tasks:** 2
- **Files modified:** 9 (5 created, 4 modified)

## Accomplishments

- `upload.py::_resolve_field_set` gained a `schema_name` branch, checked FIRST in precedence (D-10-02): it looks up the named governed Schema (404 on a miss), derives the target `FieldSet` via `service.field_set_from_schema`, and returns both wrapped in a new `_ResolvedTarget` frozen dataclass so the route can thread `schema=` into `service.resolve_or_map`'s Python-first crosswalk pre-fill without a second lookup. `field_set`/`field_set_template_id` remain fully supported, unchanged branches beneath it — verified by running `tests/api/test_upload.py` and `tests/api/test_reconcile.py` completely UNMODIFIED and green.
- `wire.MappingResponse` gained an `escalation: dict | None` field, built inside `from_proposal` from a `service.Escalation` object into `{python, claude, total}` — `None` whenever no Schema was targeted or the profile auto-apply already short-circuited everything. A fully-crosswalked upload calls `propose_mapping` zero times (proven via an `AssertionError`-raising spy) and reports `{python: N, claude: 0, total: N}`; a partially-covered one calls the mapper only for the uncovered remainder.
- Tombstones are honoured end-to-end at the HTTP boundary through the already-tombstone-aware `service.field_set_from_schema`/`_vendor_agnostic_alias_index` (Plan 03): a removed canonical field is absent from `field_mappings`, and a removed alias no longer pre-fills its column (it escalates to Claude instead).
- `api/state.py::UploadEntry` gained a THIRD retention shape (`proposal`, `schema_name`, `strictness`, `escalation`), distinct from the structural-question (`tmp_path`) and reconcile-question (`map_envelope`/`target_schema_name`/`vendor`) shapes: on the date-question branch `tmp_path` stays `None` (the data file already left disk at parse time), so `/api/date-format/resolve` needs no re-parse and touches no filesystem at all.
- `wire.py` gained `DateFormatColumnOut`, `DateFormatQuestionResponse` (the 4th `kind="date_question"` arm — `from_question`'s `headers_only` kwarg is the ONE place `example_values` is redacted, never in the detector or the panel), `DateFormatChoiceIn` (an `order: Literal["day_first","month_first"]` with deliberately NO `date_format` field, T-10-21), and `DateFormatResolveRequest`.
- `upload.py` branches on `result.date_question.has_conflicts` before returning a `MappingResponse` — retains the already-parsed table + resolved proposal, unlinks the (already-otherwise-unneeded) temp file, and returns the `date_question` response. Multiple ambiguous columns bundle into ONE question (verified with a 2-date-column fixture). A structural question still takes precedence, by construction (`resolve_or_map` returns a bare `StructureQuestion` before any date resolution ever runs).
- `routes/date_format.py` (new): pops the retained entry, converts the human's `choices` into a `{target_field: DateOrder}` mapping, calls `service.resolve_date_formats(..., answers=...)` (raising `UnresolvedDateColumnsError` → 422 on any unanswered column, fail-closed), then re-validates a FRESH proposal (needs_confirmation reset — see Decisions) with the resolved `date_formats`/`date_contradictions` override, and returns a `MappingResponse` carrying the SAME `escalation`/`provenance` the original mapping had. Registered in `app.py`.

## Task Commits

Each task was committed atomically (TDD RED then GREEN per task):

1. **Task 1: /api/upload targets a Schema, and reports escalation counts** - test `f40f386`, feat `6627b5c`
2. **Task 2: The kind="date_question" 4th arm + retained state** - test `6db2329`, feat `08975a0`

_TDD Gate Compliance: both tasks' `test(10-05)` commits precede their `feat(10-05)` commits, verified in git log order._

## Files Created/Modified

- `src/assayingest/api/routes/upload.py` - `_resolve_field_set` gains a `schema_name` branch (first in precedence) + `_ResolvedTarget`; threads `schema=` into `resolve_or_map`; branches on `result.date_question.has_conflicts` before the happy path
- `src/assayingest/api/wire.py` - `MappingResponse.escalation`; `DateFormatColumnOut`, `DateFormatQuestionResponse`, `DateFormatChoiceIn`, `DateFormatResolveRequest`
- `src/assayingest/api/state.py` - `UploadEntry` grows `proposal`/`schema_name`/`strictness`/`escalation`
- `src/assayingest/api/routes/date_format.py` (new) - `POST /api/date-format/resolve`
- `src/assayingest/api/app.py` - registers `date_format.router`
- `tests/api/test_upload_schema_target.py` (new) - 9 tests: schema targeting, escalation counts, tombstones, 404/422, precedence
- `tests/api/test_date_format_route.py` (new) - 14 tests: the 4th arm, multiple-column bundling, structural precedence, headers_only redaction, resolve happy/invalid/fail-closed/404/no-reparse
- `.planning/phases/10-frictionless-correct-ingest/deferred-items.md` (new) - the discovered CSV comment-truncation parser bug
- `.planning/todos/pending/parser-hash-comment-truncation.md` (new) - the same bug, filed for a future parser-hardening phase

## Decisions Made

- `schema_name`'s precedence check runs at the single `_resolve_field_set` call site upstream of the plain-vs-map-file branch, so it also governs what `_reconcile_upload` receives when a map-file upload also names a `schema_name` (which every existing reconcile test does, since `_reconcile_upload` requires it). Verified this changes nothing observable: every `test_reconcile.py` scenario's explicit `field_set` and its `schema_name`-derived one are field-for-field identical (same names, same default types), and `_reconcile_upload`'s own body — `reconcile_or_map`/`apply_reconcile_resolution` — is untouched and never receives `schema=`.
- `MappingResponse.escalation` is a plain `dict` (`{python, claude, total}`), matching the plan's literal instruction, built only inside `from_proposal` from a `service.Escalation` object — never re-derived a second way.
- `UploadEntry.escalation` was added even though the plan's Task 2 action text enumerated only `proposal`/`schema_name`/`strictness` — required to satisfy the acceptance criterion that the resolve response carries the SAME escalation counts the original mapping had, without recomputing anything (which would require reaching into `service.py`'s private `_prefill_coverage`, out of this plan's `files_modified`). Carrying the already-computed value forward is cheaper and more honest than a second computation.
- `date_format.py` resets `needs_confirmation=False` on every retained mapping before calling `validate()` with the resolved `date_formats` override (see Deviations below) — required because `validate()` is additive-only (documented in `validation/validator.py`: "may only OR a `True` into `needs_confirmation`, never clear one back to `False`"), and the retained `entry.proposal` already carries `needs_confirmation=True` for the ambiguous column from the FIRST `validate()` pass inside `resolve_or_map` (which ran before the order was known). Mirrors `service.confirm`'s "rebuild fresh, never trust a stale readiness claim" discipline, applied to this route's own re-validation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `/api/date-format/resolve` re-flagged a correctly-resolved date field as still needing confirmation**
- **Found during:** Task 2, writing `test_resolve_with_a_valid_order_returns_mapping_resolved_cleanly`
- **Issue:** Calling `validate(entry.table, entry.proposal, entry.field_set, date_formats=resolution.formats, ...)` directly on the RETAINED proposal left `needs_confirmation=True` on the resolved date field, because `validate()` is additive-only and the retained proposal already carried that flag from the pre-resolution `validate()` call inside the original `resolve_or_map`.
- **Fix:** Build a fresh `MappingProposal` with every mapping's `needs_confirmation` reset to `False` (via `dataclasses.replace`) before re-validating with the resolved `date_formats`/`date_contradictions` override — mirrors `service.confirm`'s "rebuild fresh" discipline.
- **Files modified:** `src/assayingest/api/routes/date_format.py`
- **Verification:** `test_resolve_with_a_valid_order_returns_mapping_resolved_cleanly` and `test_a_client_supplied_date_format_extra_key_is_dropped_and_ignored` both assert `needs_confirmation is False` after resolve; full suite stayed green.
- **Committed in:** `08975a0` (Task 2 feat commit)

**2. [Rule 2-adjacent - out-of-scope discovery, NOT fixed] `parse()`'s CSV comment stripping truncates a line at any mid-line `#`**
- **Found during:** Task 2, writing an HTTP-level integration test that uploads `data/synthetic/helixbio_export.csv` (which has a `# Reps` header column) through the real `/api/upload` pipeline
- **Issue:** `parsing/structure/delimiter.py`'s `pd.read_csv(..., comment="#", ...)` truncates ANY line at its first `#`, not only a leading one — silently dropping the file's `compound_id` column and misplacing every remaining header by one position. Reproduced directly (see `deferred-items.md`).
- **Why NOT fixed:** `parsing/structure/delimiter.py` is not in this plan's `files_modified` — it is a pre-existing, unrelated bug in a different subsystem, not something this task's own changes caused. Per the executor's Scope Boundary, logged rather than fixed.
- **Files:** none modified for the bug itself; `.planning/phases/10-frictionless-correct-ingest/deferred-items.md` and `.planning/todos/pending/parser-hash-comment-truncation.md` created to record it.
- **Workaround in this plan's own tests:** `tests/api/test_date_format_route.py` uses an inline CSV fixture carrying the SAME real ambiguous `Experiment Date` values, with a 2-column header that has no `#` in it, instead of reading the real fixture file through the upload pipeline.

---

**Total deviations:** 1 auto-fixed (Rule 1 bug), 1 logged-not-fixed (out-of-scope discovery)
**Impact on plan:** The Rule 1 fix was necessary for the date-resolution feature to actually work end-to-end at the wire boundary (a resolved date column must actually clear, not just NOT be flagged as ambiguous). The logged parser bug is unrelated to this plan's scope and does not block anything this plan delivers — it was worked around in this plan's own test fixtures.

## Issues Encountered

- A second, related architecture gap was discovered (not a bug in THIS plan's own code, and not auto-fixed — see Decisions/coverage above): `service.confirm()` (in `service.py`, out of this plan's `files_modified`) calls `validate()`/`canonical.assemble()` WITHOUT threading any `date_formats`/`date_contradictions` override through at all. This means that today, a date field resolved via the NEW `/api/date-format/resolve` step (or even via `resolve_or_map`'s own first-pass resolution of an unambiguous-but-undeclared-format column) would be RE-FLAGGED as needing confirmation the moment `/api/confirm` re-validates it from scratch — silently undoing the whole point of D-10-04..08's date-order resolution once a curator tries to actually confirm and export. This is a real, structural gap that a future plan must close (most likely: thread the resolved `date_formats` through `UploadEntry` → `ConfirmRequest`/`confirm.py` → `service.confirm`, or have `confirm()` re-run `resolve_date_formats` itself against the final edited mappings). Filed as a discovery in this SUMMARY rather than a separate todo file, since fixing it requires touching `confirm.py`/`service.py`, which are out of every plan in this phase's currently-declared file scope — the next phase's planner should decide where it lands.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Final public surface for Plan 06/07 (frontend) to build `lib/api.ts`/`lib/types.ts` against, exactly:

- `POST /api/upload` — `schema_name` (Form field, optional) is now the PRIMARY way to target a mapping; `field_set`/`field_set_template_id` remain supported for backward compatibility. Precedence: `schema_name` > `field_set` > `field_set_template_id`. Neither given → 422 naming `schema_name` as the primary path.
- `MappingResponse` gains `escalation: {python: int, claude: int, total: int} | None` — `None` when no Schema was targeted.
- A 4th discriminated arm: `{"kind": "date_question", "upload_token": str, "columns": [{"target_field", "source_column", "day_first_format", "month_first_format", "example_values": [str], "ambiguous_row_count": int}]}` — `example_values` is `[]` under `headers_only`.
- `POST /api/date-format/resolve` — body `{"upload_token": str, "choices": [{"target_field": str, "order": "day_first" | "month_first"}]}` → the SAME `MappingResponse` shape (`kind: "mapping"`) on success; 422 `{"detail": "..."}` naming every still-undecided column on a partial/empty `choices`; 404 on an unknown/expired token.
- The 4th `kind` value WILL break `Upload.tsx`'s `assertNever(response)` at compile time in Plan 07 — that is the intended safety net, not a bug to route around.
- **Known gap for a future plan to close:** `/api/confirm` does not yet thread a resolved date order through to its own re-validation (see Issues Encountered) — a curator confirming a date-question-resolved mapping today would see that field re-flagged amber at confirm time. Flag this explicitly to whichever plan builds the Review/Confirm UI's date handling (likely Plan 07, or a dedicated follow-on).
- `git diff --stat` for this plan's commits touches only `upload.py`, `wire.py`, `state.py`, `app.py`, the new `date_format.py`, and the two new test files — `test_upload.py`, `test_reconcile.py`, and `test_headers_only.py` are all byte-for-byte unmodified.
- Full suite: 792 passed, 4 skipped (769 baseline + 9 + 14 new tests, zero regressions).

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 10 created/modified files confirmed present on disk; all 4 task commit hashes (f40f386, 6627b5c, 6db2329, 08975a0) confirmed present in git log. Full suite re-verified green: 792 passed, 4 skipped (769 baseline + 9 + 14 new tests, zero regressions).

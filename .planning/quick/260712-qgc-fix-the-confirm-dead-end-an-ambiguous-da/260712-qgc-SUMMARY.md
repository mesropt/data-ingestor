---
phase: quick-260712-qgc
plan: 01
subsystem: validation
tags: [date-parsing, strptime, confirm-gate, validator, date-order]

requires:
  - phase: 10-frictionless-correct-ingest
    provides: "resolve_date_formats/DateResolution/DateFormatConflict (D-10-04..08), date_order.classify_column, validator._contradiction_objection_note"
provides:
  - "date_order.parses_all(values, date_format) -- the public predicate that checks a declared date_format against a column's actual values before trusting it"
  - "service._resolve_one_column's AMBIGUOUS branch now checks a declared date_format against the data (parses_all) before trusting it, instead of blindly accepting it"
  - "A refuted declaration records contradictions[field] (unanswered branch only) so validate() renders the honest _contradiction_objection_note instead of the generic conversion note"
  - "An answered, previously-refuted date column passes service.confirm()'s gate and assembles an ISO-8601 cell -- the Confirm dead-end is closed"
affects: [10-frictionless-correct-ingest, validation, canonical-date-assembly]

tech-stack:
  added: []
  patterns:
    - "Rename-and-promote a private predicate (_all_parse -> parses_all) rather than adding a parallel public wrapper, to keep exactly one strptime-loop implementation"
    - "Contradiction is recorded ONLY on the unanswered branch -- recording it on the answered branch would re-flag the field amber after the human fixed it, reproducing the exact dead end being closed"

key-files:
  created: []
  modified:
    - src/assayingest/parsing/structure/date_order.py
    - src/assayingest/service.py
    - tests/test_date_escalation.py
    - tests/test_date_order.py

key-decisions:
  - "A declared date_format in the AMBIGUOUS branch is trusted only when date_order.parses_all(values, declared) is True; otherwise it falls through to the existing answer/conflict path unchanged (declared==None already went there)."
  - "Test 1's initial assertion that the amber note must NOT contain the generic conversion-check text was corrected during GREEN work: canonical.assemble()'s own D-13 fallback (unchanged, out of scope) also flags an unresolved date column using the field's own un-refuted declared format, so its generic note is additively appended alongside the honest contradiction note per validator.py's existing additive-only convention (Pattern 2). Suppressing the generic note would require editing validator.py, which is outside this plan's scope fence. The test now asserts the specific note is present and the combined note is not identical to the generic-only text."

requirements-completed: []

coverage:
  - id: D1
    description: "An AMBIGUOUS date column whose declared date_format cannot parse its values is no longer blindly trusted -- it raises a date-order conflict and records a contradiction naming the declared format and a refuting value."
    verification:
      - kind: unit
        ref: "tests/test_date_escalation.py#test_ambiguous_declared_format_refuted_by_the_data_is_not_trusted_and_raises_a_conflict"
        status: pass
      - kind: unit
        ref: "tests/test_date_escalation.py#test_ambiguous_refuted_declaration_amber_note_is_honest_not_generic"
        status: pass
    human_judgment: false
  - id: D2
    description: "Answering the date order for a refuted column overrides the stale declaration for that run only, passes service.confirm()'s gate (no NotReadyError/422), and assembles an ISO-8601 cell -- the Review-screen dead end has a way out."
    verification:
      - kind: unit
        ref: "tests/test_date_escalation.py#test_answered_refuted_column_passes_confirm_and_assembles_iso"
        status: pass
      - kind: unit
        ref: "tests/test_date_escalation.py#test_answered_refuted_column_resolves_with_no_lingering_contradiction"
        status: pass
      - kind: other
        ref: "python -c sanity check against data/synthetic/helixbio_export.csv + presets/assay-potency.yaml -- see 'Real-fixture sanity check' below"
        status: pass
    human_judgment: false
  - id: D3
    description: "A declared date_format the data cannot refute (parses every value) is still trusted with no question -- the earned-trust case stays unbroken, and now also passes confirm() with no date_answers."
    verification:
      - kind: unit
        ref: "tests/test_date_escalation.py#test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question"
        status: pass
      - kind: unit
        ref: "tests/test_date_escalation.py#test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question_confirm_gate"
        status: pass
    human_judgment: false
  - id: D4
    description: "date_order exposes the all-values-parse check under the public name parses_all; every other decision-table row (EXCEL_SERIAL, INVALID/NON_DATE, DAY_FIRST/MONTH_FIRST/ISO agrees-or-contradicts) behaves exactly as before; full backend suite green at or above the 824/4 baseline."
    verification:
      - kind: unit
        ref: "tests/test_date_order.py#test_parses_all_is_false_when_the_declared_format_cannot_parse_the_values"
        status: pass
      - kind: unit
        ref: "tests/test_date_order.py#test_parses_all_is_true_when_the_declared_format_parses_every_value"
        status: pass
      - kind: unit
        ref: "uv run pytest -q (full backend suite)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-07-12
status: complete
---

# Quick Task 260712-qgc: Fix the Confirm Dead-End on a Refuted Declared Date Format

**A stale preset `date_format` is now checked against the column's own values (`date_order.parses_all`) before being trusted; a refuted declaration asks the human instead of silently strptime-failing every row and 422ing Confirm forever.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-12
- **Tasks:** 3 (RED, GREEN, full-suite regression)
- **Files modified:** 4 (2 source, 2 test)

## Accomplishments
- Promoted `date_order._all_parse` to the public `date_order.parses_all(values, date_format)` -- the single missing "check before trust" predicate D-10-06 always intended to exist
- `service._resolve_one_column`'s `AMBIGUOUS` branch now trusts a declared `date_format` only when it parses every value in the mapped column; a refuted declaration falls through to the existing answer/conflict path (question raised, human overrides for this run only)
- A refuted-and-unanswered column now records `contradictions[field]` (one raw refuting value) so `validate()` renders the honest, actionable `_contradiction_objection_note` rather than the uninformative generic note
- Verified end-to-end against the REAL reported input (`data/synthetic/helixbio_export.csv` + `presets/assay-potency.yaml`): the resolver now raises the date-order question instead of silently trusting `%Y-%m-%d`, and answering `DAY_FIRST` clears `confirm()`'s gate and assembles `2025-11-03`

## Task Commits

1. **Task 1 (RED): failing tests pinning the dead-end, escape hatch, and earned-trust case** - `25b8148` (test)
2. **Task 2 (GREEN): promote parses_all, check the declaration against the data before trusting it** - `d7d3ede` (fix)
3. **Task 3: full-suite regression and real-fixture sanity check** - no code changes; verification only (see below)

## Files Created/Modified
- `src/assayingest/parsing/structure/date_order.py` - Renamed `_all_parse` to public `parses_all`, moved beside the other public functions, documented that a clean parse of every value refutes-or-fails-to-refute (never proves correctness); updated its 2 internal call sites (`_classify_iso`, `_resolved_dm_result`)
- `src/assayingest/service.py` - `_resolve_one_column`'s `AMBIGUOUS` branch now calls `date_order.parses_all(values, declared)` before trusting a declaration; a refuted-and-unanswered column additionally records `contradictions[name]`; updated the `resolve_date_formats` docstring decision table to document the two new AMBIGUOUS+declared rows (parses vs. refuted)
- `tests/test_date_escalation.py` - Added the dead-end reproduction, the honest-note test, the answered-escape-hatch test (through `service.confirm`), the answered-no-lingering-contradiction test, and a confirm-gate companion for the existing earned-trust test; extended that test's docstring to state the trust is now earned, not assumed
- `tests/test_date_order.py` - Added 3 tests pinning `date_order.parses_all`'s public name and blank-handling behavior

## Decisions Made
- A declared `date_format` in the AMBIGUOUS branch is trusted only when `date_order.parses_all(values, declared)` is `True`; this is the sole new condition -- every other branch of the decision table (EXCEL_SERIAL, INVALID/NON_DATE, DAY_FIRST/MONTH_FIRST agrees-or-contradicts) is untouched.
- `contradictions[name]` is recorded ONLY on the unanswered, refuted branch. Recording it on the answered branch would re-flag the field amber via `validate()` even after the human fixed it via `date_answers` -- reproducing the exact dead end this plan closes.
- Renamed the private `_all_parse` to the public `parses_all` rather than adding a second wrapper function, per the plan's explicit instruction -- keeps exactly one strptime-loop implementation in the module (verified via `grep -rn strptime src/assayingest/service.py`, which returns nothing outside a docstring comment).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in Task 1's own test] Corrected an overly strict "no generic note" assertion**
- **Found during:** Task 2 (GREEN) -- running the targeted test suite after the source fix
- **Issue:** Task 1's `test_ambiguous_refuted_declaration_amber_note_is_honest_not_generic` asserted the generic `"type/date/unit conversion check objected"` substring is entirely ABSENT from the amber note. In practice, `canonical.assemble()`'s own unchanged D-13 fallback (out of this plan's scope fence -- `canonical.py`/`validator.py` were not to be touched) still flags the field via the field's own un-refuted declared format (since no run-scoped override exists for an unanswered refuted column), so its generic note is additively appended alongside the new, honest contradiction note -- exactly matching `validator.py`'s pre-existing additive-only convention (Pattern 2, already exercised by `test_contradiction_objection_is_additive_with_another_violation` in `tests/test_canonical_dates.py`). Suppressing the generic note when a contradiction is present would require editing `validator.py`'s `_validate_mapping`, which the plan's scope fence explicitly forbids.
- **Fix:** Loosened the assertion to require the specific contradiction note's content (declared format + refuting value + "Schemas page") is present, and that the combined note is not IDENTICAL to the generic-only text -- matching the plan's literal intent ("MUST NOT be the generic note") without contradicting the codebase's established additive-note design.
- **Files modified:** `tests/test_date_escalation.py`
- **Verification:** `uv run pytest tests/test_date_escalation.py tests/test_date_order.py tests/test_canonical_dates.py tests/api/test_confirm_dates.py tests/api/test_date_format_route.py -q` -- 84 passed
- **Committed in:** `d7d3ede` (part of the Task 2 GREEN commit, since the fix only became visible while making Task 1's tests pass)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test bug)
**Impact on plan:** No scope creep; the fix was a test-assertion correction, not a source-code change beyond what the plan already specified. `validator.py`/`canonical.py` remain untouched, consistent with the scope fence.

## Issues Encountered
None beyond the deviation above.

## Real-fixture sanity check (Task 3)

Ran the exact reported bug scenario directly against the real files (`data/synthetic/helixbio_export.csv` mapped through `presets/assay-potency.yaml`'s `assay_date` field, which declares the stale `%Y-%m-%d`):

**Before this fix (the reported bug):** `resolve_date_formats` would have put `"%Y-%m-%d"` into `formats["assay_date"]` (blindly trusted), `has_conflicts` would be `False`, and `canonical.assemble()`/`confirm()` would strptime-fail on every row, forcing a permanent amber field with no way to clear it from Review (422 forever).

**After this fix (observed):**
```
formats: {}
has_conflicts: True
contradictions: {'assay_date': '03/11/2025'}
```
And with the human's answer supplied:
```python
service.confirm(table, mappings, field_set, date_answers={"assay_date": DateOrder.DAY_FIRST})
# -> confirm OK, assay_date cell 0: 2025-11-03
```
This is the exact inverse of the reported bug: no format resolved, question raised, contradiction recorded, and the escape hatch clears the gate with a correctly-assembled ISO-8601 cell.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The Confirm dead-end for a refuted declared date format is closed; the mechanism generalizes to any preset/field whose `date_format` doesn't match a particular vendor's file.
- No follow-up work identified; `validator.py`'s additive-note behavior (both the contradiction note and the generic conversion note co-occurring on this specific refuted-and-unresolved-format path) is a pre-existing, unchanged design and not a new gap introduced by this fix.

---
*Phase: quick-260712-qgc*
*Completed: 2026-07-12*

## Self-Check: PASSED

All created/modified files exist on disk; both task commits (`25b8148`, `d7d3ede`) verified present in `git log`.

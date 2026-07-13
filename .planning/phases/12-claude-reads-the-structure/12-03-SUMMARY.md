---
phase: 12-claude-reads-the-structure
plan: 03
subsystem: parsing
tags: [layout-verdict, dispatch, key-value, unpivot, locale-gate, fail-closed, tdd]

# Dependency graph
requires:
  - phase: 12-claude-reads-the-structure
    provides: "12-01's SheetLayout/LayoutKind/KeyValueBlock verdict types, unpivot_key_value, and StructuralHint.layout — the inputs this wave wires into the parse path"
provides:
  - "table.py _table_from_layout(path, rows, layout, sheet_tag, hint, *, origin_sheet) — the parse-path dispatch on layout.kind, entered from _parse_excel_structurally BEFORE header detection whenever hint.layout is not None"
  - "table.py _raw_table_from_key_value — a confirmed key-value verdict un-pivots into a real RawTable through the IDENTICAL _resolve_locales_or_ask gate as the header-row sibling (SHAPE-02)"
  - "table.py _raw_table_from_row_verdict — a row_per_record verdict re-parameterises _raw_table_from_header_row: header from the verdict (never re-detected), first/last_data_row trims trailing prose (the Quality Control case)"
  - "table.py _shape_unknown_question — every non-readable verdict kind asks with answerable_by_hint=True and the layout in the proposal (D-12-15); T-12-08 out-of-grid indices land here too, never IndexError"
affects: [12-04, 12-05, 12-06, 12-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verdict indices are untrusted at parse time: _blocks_within_grid and the row-verdict range guard check every index against the real grid BEFORE any indexing — out-of-grid fails closed to the answerable question (T-12-08's inner closure; the wire-boundary 422 lands in 12-05)"
    - "Verdict-read tables reuse the sibling assembly: _raw_table_from_row_verdict feeds a trimmed grid into _raw_table_from_header_row itself, so both verdict paths and the auto path share one assembly and one locale gate"

key-files:
  created: []
  modified:
    - src/assayingest/parsing/table.py
    - tests/test_parse_entry_shape.py

key-decisions:
  - "The shape gate never moved: the classify_shape dispatch at table.py's single choke point is byte-for-byte untouched; the layout branch is ADDED immediately before it and returns, so a verdict-less parse is exactly yesterday's parse (all 7 pre-existing tests in test_parse_entry_shape.py verbatim — only the import line widened)"
  - "The one-row locale bounce is NOT suppressed: a lone text-stored '150,000' in an un-pivoted table raises the locale StructureQuestion, and the same hint.decimal_separator that resolves the header-row sibling resolves it — asserted in both directions"
  - "layout.confidence is not consulted in parse(): a verdict arriving on a hint IS the confirmation (D-12-15's 'the hint path is the confirmation'); deciding when to ask about a low-confidence verdict is service's call (plan 12-05)"
  - "A row_per_record verdict with header_row_index=None, or any out-of-grid index, fails closed to _shape_unknown_question — never a guess, never an IndexError, never a billion-row loop"

patterns-established:
  - "_table_from_layout dispatch signature (for 12-04/12-05 routing): _table_from_layout(path: Path, rows: list[tuple], layout: SheetLayout, sheet_tag: str | None, hint: StructuralHint | None, *, origin_sheet: str) -> RawTable | StructureQuestion; reached via parse(path, sheet=..., hint=StructuralHint(layout=...))"

requirements-completed: [SHAPE-02]

coverage:
  - id: D1
    description: "A row_per_record verdict steers parse(): header from the verdict (not re-detected), first/last_data_row excludes trailing prose, low-confidence verdict passed as a hint still parses"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_a_row_per_record_verdict_takes_the_header_from_the_verdict_not_redetection, #test_a_row_per_record_verdict_row_range_excludes_trailing_prose, #test_a_low_confidence_row_per_record_verdict_passed_as_a_hint_still_parses"
        status: pass
    human_judgment: false
  - id: D2
    description: "A key-value verdict is READ, not refused: the real cascade Patient Info with the D-12-13 blocks parses through parse() to a 17-header, 1-row RawTable; the un-pivoted table goes through the identical locale gate (bounce not suppressed, hint resolution shared)"
    requirement: SHAPE-02
    verification:
      - kind: integration
        ref: "tests/test_parse_entry_shape.py#test_golden_patient_info_key_value_verdict_parses_to_a_real_raw_table, #test_key_value_one_row_locale_bounce_is_not_suppressed, #test_key_value_goes_through_the_identical_locale_gate_resolution"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every non-readable verdict kind asks answerably with the layout in the proposal (D-12-15); out-of-grid verdict indices fail closed to the same question (T-12-08); the verdict-less path is byte-for-byte unchanged"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_a_non_readable_verdict_returns_an_answerable_question (x4 kinds), #test_an_out_of_grid_row_verdict_fails_closed_to_the_answerable_question, #test_an_out_of_grid_key_value_block_fails_closed_not_index_error, #test_a_hint_without_a_layout_still_runs_the_shape_classifier"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 03: The Parse-Path Layout Dispatch Summary

**parse() now dispatches on a hint's layout verdict before the heuristic flow — key_value un-pivots into a real locale-gated RawTable (Patient Info golden: 17 headers/1 row through parse()), row_per_record reads via the verdict's indices trimming trailing prose, everything else asks answerably — with the shape gate byte-for-byte unmoved and the verdict-less path exactly yesterday's**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-13T13:44:26Z
- **Completed:** 2026-07-13T14:09:50Z
- **Tasks:** 2 (both TDD, red-first)
- **Files modified:** 2

## Accomplishments

- `_parse_excel_structurally` gained exactly one branch: when `hint.layout is not None`, delegate to `_table_from_layout` — a named helper, not a fourth inline branch. The existing `classify_shape` gate and `_shape_unsupported_question` are byte-for-byte untouched (they die in Wave C, plan 12-07); `git diff` over this plan's commits shows only additions to `table.py` and only additions (plus one widened import line) to the test file.
- **SHAPE-02 is now real at the parse path:** the real cascade `Patient Info` sheet with the D-12-13 blocks (`[(0,(1,),1,10),(3,(4,),1,10)]`) parses through `parse()` into a 17-header, 1-row `RawTable` with 17 column locales, `origin_sheet="Patient Info"` and the multi-sheet tag set — a key-value sheet is read, not refused.
- **The Quality Control case is ingestible per a verdict:** a `row_per_record` verdict's `first_data_row`/`last_data_row` trims rows outside the range — the QC-shaped tmp workbook (3-row table, blank row, Westgard prose) parses with the prose provably absent. The trimmed grid feeds `_raw_table_from_header_row` itself, so the verdict path shares the auto path's assembly and gate literally, not by imitation.
- **The shape question is finally answerable:** every non-readable kind (`wide_matrix`, `multiple_tables`, `not_a_table`, `unknown`) returns `_shape_unknown_question` — `answerable_by_hint=True`, `confidence=0.0`, evidence from the first 8 rows, and the judge's layout carried in `proposal` for the human to correct (or `None`, honestly, when no verdict exists) (D-12-15).
- **T-12-08 closed at the parse side:** `_blocks_within_grid` and the row-verdict range guard validate every verdict index against the real grid *before* indexing — a hallucinated `header_row_index=99`, a `last_row=999`, an out-of-width column, or a block-less key-value verdict all fail closed to the answerable question; a `first_row=10**9` can neither raise nor spin.
- **The locale gate is the product, and it stayed:** the un-pivoted one-row table with a text-stored `150,000` bounces into the locale question (no one-row special case), and the same `hint.decimal_separator` that resolves the header-row sibling resolves it — the gate is shared, asserted in both directions (T-12-09).
- Full suite green with credentials unset: **1216 passed, 4 skipped** (1163 Wave-1 baseline + this plan's 15 + parallel plan 12-02's judge tests), zero network calls. The structural guard `test_no_raw_table_construction_path_attaches_a_shape_field` holds verbatim over the new construction path (T-12-10), and `test_parse_source_never_returns_a_raw_table_for_a_non_row_per_record_shape` still exercises the real classifier (not vacuous — the verdict-less fixtures still route through `classify_shape`).

## Task Commits

Each task was committed RED then GREEN:

1. **Task 1: the layout dispatch — _table_from_layout, gate unmoved** — `01e7f03` (test, RED), `0c79139` (feat, GREEN)
2. **Task 2: _raw_table_from_key_value + _shape_unknown_question** — `f03607d` (test, RED), `f5ee6cc` (feat, GREEN)

## Files Created/Modified

- `src/assayingest/parsing/table.py` — `_table_from_layout` dispatch, `_raw_table_from_row_verdict`, `_raw_table_from_key_value`, `_blocks_within_grid`, `_shape_unknown_question`; one added branch in `_parse_excel_structurally` + a docstring paragraph naming the verdict branch under the unchanged choke-point rule
- `tests/test_parse_entry_shape.py` — 15 new tests (dispatch, QC trim, low-confidence-hint-still-parses, verdict-less invariant, Patient Info golden, locale bounce + shared resolution, 4-kind answerable question, out-of-grid guards); all 7 pre-existing tests verbatim

## The dispatch signature (recorded for plans 12-04/12-05)

```python
def _table_from_layout(
    path: Path,
    rows: list[tuple],
    layout: SheetLayout,
    sheet_tag: str | None,
    hint: StructuralHint | None,
    *,
    origin_sheet: str,
) -> RawTable | StructureQuestion
```

Route a verdict into it via the hint: `parse(path, sheet=..., hint=StructuralHint(layout=SheetLayout(...)))`. The branch fires in `_parse_excel_structurally` after sheet resolution, the drawing-only check and the grid read, and BEFORE header detection — so a verdict skips detection entirely. `layout.confidence` is deliberately not consulted in `parse()`: a layout arriving on a hint IS the confirmation; asking about low-confidence verdicts is service's job (12-05).

## Decisions Made

- **Verdict indices are untrusted even from the hint path:** the T-12-08 guard runs on every verdict regardless of source, because the same layout arrives from the judge (12-04) or from a client POST (12-05) — the parse-side guard is the inner closure; the wire-boundary 422 is 12-05's outer one.
- **`_raw_table_from_row_verdict` reuses `_raw_table_from_header_row` on a trimmed grid** rather than duplicating the assembly — one assembly, one gate, zero drift risk between the auto and verdict paths.
- **`_blocks_within_grid` checks columns against the widest row** (`max(len(row))`) — ragged rows inside a block remain the un-pivot's graceful-blank concern; only genuinely out-of-grid columns fail closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1's behavior tests split by helper dependency**
- **Found during:** Task 1 (RED planning)
- **Issue:** Task 1's behavior block lists the KEY_VALUE golden and non-readable-kind tests, but both need Task 2's helpers (`_raw_table_from_key_value`, `_shape_unknown_question`) — Task 1's GREEN could not pass them without swallowing Task 2, the same internal ordering conflict 12-01 hit.
- **Fix:** Tests were split by dependency: Task 1 RED covers the `row_per_record` arm + the verdict-less invariant; Task 2 RED covers the key-value golden, locale bounce, answerable question and T-12-08 guards. Task 1's GREEN dispatch references the two Task-2 helper names (Python resolves names at call time; no Task-1 test reaches those arms), which is exactly what made Task 2's RED fail honestly with `NameError`.
- **Files modified:** tests/test_parse_entry_shape.py, src/assayingest/parsing/table.py
- **Verification:** Task 1 GREEN full-suite green at `0c79139`; Task 2 RED 9 honest failures at `f03607d`
- **Committed in:** `0c79139` / `f03607d`

**2. [TDD fail-fast] A vacuously-green RED test was strengthened before implementing**
- **Found during:** Task 1 (RED run)
- **Issue:** `test_a_low_confidence_row_per_record_verdict_passed_as_a_hint_still_parses` passed before any implementation — its clean 2-row workbook parses via the old auto path, so it proved nothing about the verdict path.
- **Fix:** The grid was changed to one the heuristic classifier refuses today (blank separator + trailing prose ⇒ `multiple_tables`), so only the verdict path can produce its `RawTable`; observed RED, then GREEN.
- **Files modified:** tests/test_parse_entry_shape.py
- **Verification:** 3 honest failures observed at RED before `01e7f03`
- **Committed in:** `01e7f03`

---

**Total deviations:** 2 (one Rule-3 ordering conflict internal to the plan, one TDD-hygiene test strengthening)
**Impact on plan:** None on scope or behavior — every must_have truth holds as specified.

## TDD Gate Compliance

RED and GREEN commits exist for both tasks (`test(...)` before `feat(...)` in each pair). Task 1's RED was observed with 3 assertion failures (after strengthening the vacuous test per the fail-fast rule); Task 2's RED was observed with 9 `NameError` failures on the missing helpers. The verdict-less invariant test (`test_a_hint_without_a_layout_still_runs_the_shape_classifier`) passes by design at RED — it pins today's behavior, which is its stated purpose.

## Issues Encountered

- Plan 12-02 executed in parallel in the same working tree; its in-flight RED file (`tests/test_structure_judge.py`) transiently broke full-suite collection mid-run. Handled by excluding only that file for interim runs and staging only this plan's files per commit; the final full-suite run includes 12-02's completed work and is green (1216 passed, 4 skipped).

## Known Stubs

None — both verdict arms are fully wired to real transforms and real gates; no hardcoded empties, placeholders, or unwired paths in this plan's files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 12-04/12-05 can route judge verdicts and client-posted layouts into `parse()` via `StructuralHint(layout=...)` — the dispatch signature above is the contract, and the T-12-08 inner guard is already in place beneath whatever wire validation 12-05 adds.
- Wave C (12-07) deletes `classify_shape` by replacing the `hint.layout is None` branch's fallback with `_shape_unknown_question(path, sheet, rows, None)` — the question builder already handles the no-verdict case honestly (`proposal=None`).
- `tests/test_hint_and_locale.py` passed unchanged; its `:153` inversion belongs to Wave C.

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

Both modified files and the SUMMARY exist on disk; all 4 task commits (`01e7f03`, `0c79139`, `f03607d`, `f5ee6cc`) are in history; all three named artifacts (`_table_from_layout`, `_raw_table_from_key_value`, `_shape_unknown_question`) exist in `table.py`; zero file deletions across the plan's commits.

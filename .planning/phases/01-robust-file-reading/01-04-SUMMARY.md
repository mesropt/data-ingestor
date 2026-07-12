---
phase: 01-robust-file-reading
plan: 04
subsystem: parsing
tags: [openpyxl, shape-classification, type-homogeneity, structure-detection]

# Dependency graph
requires:
  - phase: 01-robust-file-reading/01-02
    provides: "parsing/structure/grid.py's read_grid()/list_worksheets() raw-grid reader; parsing/structure/header.py's detect_header() (always returns a best-guess index, even when not confident)"
  - phase: 01-robust-file-reading/01-03
    provides: "parsing/structure/sheets.py's rank_sheets(); parsing/table.py's parse() Excel branch already selecting a sheet before header detection; triton_screening_two_tables.xlsx fixture (the multiple_tables corpus gap RESEARCH.md flagged)"
provides:
  - "parsing/structure/shape.py: classify_shape() -- row_per_record | wide_matrix | transposed | multiple_tables | unknown from a native-typed data region, via row/column type-homogeneity inversion and a numeric-column-cluster fingerprint"
  - "parsing/table.py: parse()'s Excel branch gates RawTable construction on TableShape.ROW_PER_RECORD -- the shape check runs before the header-confidence check, at a single choke point covering both auto-detected and explicit-hint-override paths"
affects: [01-robust-file-reading/01-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shape classification runs BEFORE header-confidence gating, not after -- a confidently-detected header (apex) says nothing about whether the rows beneath it are row-per-record, and an unconfident header (bionexus, which has no real header row) still needs the specific shape diagnosis rather than the generic 'which row is the header' question"
    - "Connected-component graph over numeric-column value ranges (not a flat pairwise-overlap-count) isolates the wide_matrix measurement cluster from an unrelated numeric column (apex's 'n' replicate count, range 2-4) that would otherwise dilute a naive overlap check"
    - "Continuous majority-type-fraction homogeneity (not binary all-or-nothing column consistency) so one stray value doesn't collapse an otherwise-consistent column/row's score to zero"

key-files:
  created:
    - src/assayingest/parsing/structure/shape.py
    - tests/test_structure_shape.py
    - tests/test_parse_entry_shape.py
  modified:
    - src/assayingest/parsing/table.py

key-decisions:
  - "The homogeneity formula is a from-scratch, documented 'majority-type-fraction' metric, not a literal reproduction of 01-RESEARCH.md Pattern 5's quoted float values (col 0.875/1.0, row 0.333/0.9) -- RESEARCH.md describes the *concept* ('average, across columns, of how internally type-consistent each column is') but does not include the exact probe code that produced those numbers, and no canonical formula exists in prior art. Implemented a majority-type-fraction metric, verified directly against every corpus fixture (apex/bionexus/zephyr plus meridian/orion/delta/helix/vantage as regression controls) via a probe script, and confirmed it reproduces the correct classification for all of them before writing shape.py. The plan's own acceptance criteria only require the classification and the inversion mechanism to be correct ('via the intermediate ratios or a documented named constant'), not exact float parity with RESEARCH.md's numbers."
  - "classify_shape() receives the data region with the best-guess header row already excluded (rows[header_index + 1:], using HeaderDetection.index which is always populated per plan 02's D-02 contract, even when confident=False). This is what lets bionexus_transposed.xlsx -- whose header detection is genuinely NOT confident, since it has no real header row at all -- still classify correctly: the best-guess index (0) is used purely as a slice point, not as a claim that row 0 is a real header."
  - "Shape gate runs BEFORE the header-confidence check in table.py's _parse_excel_structurally, restructured into a single choke point that also covers the explicit hint.header_row_index override path -- not just the auto-detected path. This goes slightly beyond the plan's literal task-2 acceptance criteria (which only test the auto-detected apex/bionexus cases) but is required by D-11's stronger invariant ('no code path attaches a shape warning to a RawTable and returns it anyway') -- an explicit header hint on a wide-matrix or transposed file would otherwise bypass the gate entirely."
  - "wide_matrix's 'no single distinguishing category/unit column' fingerprint (RESEARCH.md Pattern 5) is satisfied implicitly by the connected-component cluster-size gate rather than a separate column-label heuristic: a table with a real category/unit column (zephyr's 'Units') never produces more than 1-2 overlapping-range numeric columns, so it never reaches the >=3-column minimum. Documented as a discretion call in shape.py's _is_wide_matrix docstring rather than building a second, more fragile predicate for a signal the corpus doesn't currently need."

patterns-established:
  - "One named helper per signal (_has_blank_separator_block, _column_type_homogeneity, _row_type_homogeneity, _first_column_all_unique_strings, _is_wide_matrix), each with a 'why, grounded in which fixture' docstring -- mirrors header.py's and sheets.py's private-helper-per-signal SLA style exactly"
  - "_TRANSPOSED_MARGIN / _WIDE_MATRIX_MIN_COLUMNS / _WIDE_MATRIX_MIN_FRACTION are named, corpus-tuned module constants with docstrings citing the specific fixture that grounds each threshold -- same pattern as header.py's _CONFIDENCE_MARGIN and sheets.py's _CONFIDENCE_MARGIN/_WIDTH_SATURATION_FACTOR"

requirements-completed: [PARSE-05, PARSE-06]

coverage:
  - id: D1
    description: "apex_labs_wide_matrix.xlsx classifies wide_matrix (5-column overlapping-range numeric cluster: EGFR/JAK2/BRAF/ALK/KRAS, the 'n' replicate column correctly excluded) and parse() returns a StructureQuestion, not a RawTable"
    requirement: "PARSE-05"
    verification:
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_apex_is_wide_matrix"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_parse_apex_wide_matrix_returns_structure_question_not_raw_table"
        status: pass
      - kind: other
        ref: "uv run assayingest data/synthetic/apex_labs_wide_matrix.xlsx (manual smoke, verified this session) -- prints the structural question, exit code 4"
        status: pass
    human_judgment: false
  - id: D2
    description: "bionexus_transposed.xlsx classifies transposed (row-homogeneity 1.0 exceeds column-homogeneity 0.644 by more than the named margin, confirmed by an all-unique-string first column) and parse() returns a StructureQuestion, not a RawTable -- including the case where header detection itself is not confident (no real header row exists)"
    requirement: "PARSE-05"
    verification:
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_bionexus_is_transposed"
        status: pass
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_transposed_fires_on_the_row_col_homogeneity_inversion"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_parse_bionexus_transposed_returns_structure_question_not_raw_table"
        status: pass
    human_judgment: false
  - id: D3
    description: "A normal row_per_record table (zephyr Week 1 control, plus meridian_cro_codes.xlsx as a second regression control) still classifies row_per_record and parse() still produces a RawTable -- the shape gate does not regress plans 01-03"
    requirement: "PARSE-05"
    verification:
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_zephyr_week1_is_row_per_record_control"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_parse_zephyr_week1_still_returns_a_raw_table_control"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_parse_meridian_still_returns_a_raw_table_no_shape_regression"
        status: pass
      - kind: other
        ref: "uv run pytest -q -- 116 passed, 1 skipped (the 108 tests from plans 01-03 remain green)"
        status: pass
    human_judgment: false
  - id: D4
    description: "There is no parse-anyway-with-a-warning path -- RawTable carries no shape/warning field to attach one to, and no code path in parse() constructs a RawTable for a non-row_per_record shape (D-11)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_no_raw_table_construction_path_attaches_a_shape_field"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_shape.py#test_parse_source_never_returns_a_raw_table_for_a_non_row_per_record_shape"
        status: pass
    human_judgment: false
  - id: D5
    description: "A blank-separator-block grid (two independent tables on one sheet) never misclassifies as row_per_record -- verified against both triton_screening_two_tables.xlsx (the real corpus fixture plan 03 added) and a constructed synthetic grid"
    requirement: "PARSE-05"
    verification:
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_multiple_tables_fixture_never_misclassifies_as_row_per_record"
        status: pass
      - kind: unit
        ref: "tests/test_structure_shape.py#test_classify_shape_blank_separator_block_classifies_multiple_tables"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-10
status: complete
---

# Phase 1 Plan 4: Unsupported-Shape Detection Summary

**`classify_shape()` distinguishes `apex_labs_wide_matrix.xlsx` (wide_matrix, via a connected-component numeric-cluster fingerprint) and `bionexus_transposed.xlsx` (transposed, via the verified row>col type-homogeneity inversion) from a normal record table, and `parse()`'s Excel branch now refuses to build a `RawTable` for either — returning a `StructureQuestion` that names the detected shape instead, with no "parse anyway with a warning" path.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-10T14:08:52+04:00
- **Completed:** 2026-07-10T14:11:25+04:00
- **Tasks:** 2 (both TDD: RED then GREEN)
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- Built `structure/shape.py`'s `classify_shape()`: a fully-connected-component numeric-column-cluster fingerprint correctly isolates `apex_labs_wide_matrix.xlsx`'s 5 overlapping-range measurement columns (EGFR/JAK2/BRAF/ALK/KRAS, all ~0-950 nM) from its unrelated `n` replicate-count column (range 2-4) — confirming `wide_matrix` without the replicate column diluting the cluster size. A continuous majority-type-fraction row/column homogeneity metric confirms `bionexus_transposed.xlsx`'s row-homogeneity (1.0) exceeds its column-homogeneity (0.644) by well past the named `_TRANSPOSED_MARGIN`, and its first column is confirmed all-unique field-label strings — the second confirming signal 01-RESEARCH.md's Pattern 5 specifies. A fully-blank-row-block predicate (checked first, before any homogeneity math) correctly flags `triton_screening_two_tables.xlsx` — plan 03's real `multiple_tables` corpus fixture — as `multiple_tables`, closing the gap 01-RESEARCH.md flagged as untestable at planning time.
- Verified the classifier against the *entire* Excel corpus (not just the two required fixtures) via a probe script before writing a single line of test/implementation code: `zephyr_bio_ZB-2025.xlsx`, `meridian_cro_codes.xlsx`, `orion_pk_report.xlsx` (both sheets), `helix_genomics_DE.xlsx`, `vantage_pk_with_chart.xlsx` all correctly classify `row_per_record`, so the shape gate introduces zero regressions across plans 01-03's existing green tests.
- Wired the gate into `table.py`'s `_parse_excel_structurally()` as a single choke point that runs shape classification *before* the header-confidence check and covers both the auto-detected header path and the explicit `hint.header_row_index` override path — required because `bionexus_transposed.xlsx`'s header detection is itself genuinely not confident (there is no real header row), so without reordering, it would have surfaced the generic "which row is the header" question instead of the specific, more useful shape diagnosis.
- Verified live: `uv run assayingest data/synthetic/apex_labs_wide_matrix.xlsx` and `... bionexus_transposed.xlsx` both print a structural question naming the detected shape and exit 4 (`BLOCKED: structure unresolved`), never a mapped table.

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: shape classification (shape.py)**
   - `e66d7ab` test(01-04): add failing test for shape classification (shape.py)
   - `a3e83e5` feat(01-04): implement shape classification by row/col type-homogeneity inversion
2. **Task 2: gate RawTable construction on row_per_record in parse()**
   - `4914d28` test(01-04): add failing test for parse() shape gate on RawTable construction
   - `58cb20e` feat(01-04): wire shape gate into parse()'s Excel branch (D-10/D-11)

## Files Created/Modified

- `src/assayingest/parsing/structure/shape.py` — `classify_shape()`, `_TRANSPOSED_MARGIN`, `_WIDE_MATRIX_MIN_COLUMNS`, `_WIDE_MATRIX_MIN_FRACTION`, and one private helper per signal (blank-separator, type-homogeneity, first-column-uniqueness, numeric-cluster overlap)
- `src/assayingest/parsing/table.py` — `_parse_excel_structurally()` restructured to resolve a header index (from hint override or `detect_header`) before deciding confidence, run `classify_shape()` on the resulting data region, and gate on `TableShape.ROW_PER_RECORD` at a single choke point; new `_shape_unsupported_question()` builder
- `tests/test_structure_shape.py`, `tests/test_parse_entry_shape.py` — 15 new tests

## Decisions Made

- **The homogeneity formula is my own documented "majority-type-fraction" metric, not an attempt to literally reproduce 01-RESEARCH.md Pattern 5's exact quoted numbers.** RESEARCH.md describes the concept but doesn't include the probe code behind the numbers (col 0.875/1.0/0.426, row 0.333/0.9), and no canonical formula exists in prior art for this. I verified my formula reproduces the correct *classification* for every fixture in the corpus (not just the two required ones) before implementing, which is what the plan's acceptance criteria actually require ("the inversion is what fires, via the intermediate ratios or a documented named constant" — not float parity).
- **Shape classification receives the data region with the best-guess header row excluded, using `HeaderDetection.index`, which plan 02 designed to always be populated even when `confident=False`.** This is what lets `bionexus_transposed.xlsx` — which has no real header row, so header detection is genuinely unconfident — still get correctly classified: the best guess is used only as a slice point, never as a confidence claim.
- **The shape gate runs before the header-confidence check, and covers the explicit-hint-override path too, not just the auto-detected path.** The plan's literal task-2 acceptance criteria only test the auto-detected apex/bionexus cases, but D-11's invariant ("no code path attaches a shape warning to a RawTable and returns it anyway") is stronger than that — an explicit `hint.header_row_index` on a wide-matrix or transposed file would otherwise skip the gate entirely and build a wrong-but-clean-looking table. Restructuring `_parse_excel_structurally()` into one choke point that both paths flow through was the more defensible reading of the decision, not scope creep.
- **wide_matrix's "no distinguishing category/unit column" fingerprint is satisfied implicitly, not via a separate heuristic.** A table with a real category/unit column (like zephyr's `Units`) never produces more than 1-2 overlapping-range numeric columns in the first place, so it never reaches the `>=3`-column cluster minimum on its own. Documented this reasoning directly in `_is_wide_matrix`'s docstring rather than building a second, more fragile column-label predicate for a signal the current corpus doesn't need to distinguish further.

## Deviations from Plan

None (Rule 1/2/3 sense) — two instances of exercised discretion documented above (the homogeneity formula's exact shape, and applying the shape gate to the hint-override path too), both explicitly invited by the plan's own framing (Claude's Discretion on the scoring heuristic; D-11's stronger "no code path" invariant).

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. The shape classifier is pure Python with no I/O (D-04), same as every deterministic layer in this phase.

## Next Phase Readiness

- `structure/shape.py`'s `classify_shape()` is a stable, standalone primitive — plan 05 (Claude structural assist) can call it the same way it calls `detect_header()`/`rank_sheets()` for its own proposal-generation, with no interface changes expected.
- The `_shape_unsupported_question()` builder follows the exact `StructureQuestion` construction pattern (`unsure_about`/`reason`/`confidence`/`proposal`/`evidence_rows`) every other question-builder in `table.py` already uses — plan 05's Claude-assist layer can pre-fill this same question shape with a higher-confidence proposal without changing its contract.
- Full test suite: 116 passed, 1 skipped (pre-existing live-API test, unaffected) — the 101 tests from plan 03's baseline remain green with zero regressions; 15 new tests added in this plan.
- No blockers for plan 05.

---
*Phase: 01-robust-file-reading*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 4 created/modified files verified present on disk; all 4 task commit hashes (e66d7ab, a3e83e5, 4914d28, 58cb20e) plus this summary's own commit (c7dead8) verified present in git log.

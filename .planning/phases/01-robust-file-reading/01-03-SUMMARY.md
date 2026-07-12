---
phase: 01-robust-file-reading
plan: 03
subsystem: parsing
tags: [openpyxl, excel, sheet-ranking, charts, chartsheets, images, xxe, defusedxml, pillow]

# Dependency graph
requires:
  - phase: 01-robust-file-reading/01-01
    provides: "parsing/hint.py's StructuralHint/StructureQuestion contract; parsing/table.py's parse() entry point shape"
  - phase: 01-robust-file-reading/01-02
    provides: "parsing/structure/grid.py's read_grid()/list_worksheets() raw-grid reader; parsing/structure/header.py's header-row detection wired into parse()'s Excel branch"
provides:
  - "parsing/structure/sheets.py: rank_sheets() -- structural sheet ranking that hesitates honestly (D-09) instead of silently picking a sheet"
  - "parsing/structure/grid.py: is_drawing_only_sheet() -- Pillow-independent image-only-sheet detection via ws._rels (D-18)"
  - "parsing/table.py: parse()'s Excel branch now selects the data sheet before header detection, and asks (StructureQuestion) on either a genuine sheet tie or a drawing-only sheet"
  - "cli.py: resolve_or_ask() routes Excel through the same parse() structural engine as CSV -- the wave-2 known limitation (CLI never surfacing header-detected Excel tables) is closed"
  - "4 new drawing/shape fixtures in data/synthetic/ (embedded chart, chartsheet, image-only, multiple-tables), and defusedxml closing the pre-existing XXE gap"
affects: [01-robust-file-reading/01-04, 01-robust-file-reading/01-05]

# Tech tracking
tech-stack:
  added:
    - "defusedxml (runtime) -- openpyxl auto-detects it; openpyxl.DEFUSEDXML now True"
    - "pillow (dev-only, dependency-groups.dev) -- used only by scripts/gen_synthetic_pk.py to construct a test fixture image; never imported from src/assayingest/"
  patterns:
    - "Structural signals normalized with saturating (min(x/threshold, 1.0)) rather than linear scoring, so two genuinely-comparable sheets can tie honestly instead of a raw magnitude difference silently deciding the winner"
    - "Drawing/chartsheet detection reuses grid.list_worksheets (already chartsheet-safe from plan 02) rather than re-deriving sheet iteration"

key-files:
  created:
    - src/assayingest/parsing/structure/sheets.py
    - tests/test_structure_sheets.py
    - tests/test_structure_drawings.py
    - tests/test_parse_entry_sheets.py
    - data/synthetic/vantage_pk_with_chart.xlsx
    - data/synthetic/nimbus_labs_chartsheet.xlsx
    - data/synthetic/quantex_scanned_report.xlsx
    - data/synthetic/triton_screening_two_tables.xlsx
  modified:
    - scripts/gen_synthetic_pk.py
    - pyproject.toml
    - src/assayingest/parsing/structure/grid.py
    - src/assayingest/parsing/structure/header.py
    - src/assayingest/parsing/table.py
    - src/assayingest/cli.py
    - data/synthetic/README.md

key-decisions:
  - "Sheet-ranking score weights fill density (0.3) + width saturation relative to the workbook's widest candidate (0.4) + row-count saturation (0.2) + first-column uniqueness (0.1, deliberately weak per RESEARCH.md's finding that it reveals record granularity, not correctness). _CONFIDENCE_MARGIN=0.1 corpus-tuned so orion's Summary/Raw timepoints tie (diff ~0.078) while meridian's DATA beats LEGEND confidently (diff ~0.171)"
  - "is_drawing_only_sheet implemented exactly per 01-RESEARCH.md Pattern 7e's verified predicate: has_content via iter_rows, has_drawing_rel via ws._rels' drawing relationship type -- never ws._images (silently empty without Pillow) or max_row==0 (a drawing-only sheet reports max_row=1)"
  - "resolve_or_ask() now calls parse() unconditionally for both CSV and Excel, always returning a single-element list or a StructureQuestion -- matches PROJECT.md's 'one chosen table per file' v1 scope (D-09) rather than the old per-sheet loop. resolve_tables()/parse_file() remain public and independently tested (test_excel_sheets.py) but are no longer wired into run()'s live path"
  - "[Rule 1 - Bug] header.py's _type_consistency treated int and float as distinct Python types; openpyxl reads a decimal-less numeric cell back as int while its neighbors read as float, so a genuinely-numeric column with one whole-number value looked type-inconsistent. This pushed meridian_cro_codes.xlsx's real header row below the 0.05 confidence margin, contradicting the plan's own acceptance criterion. Added _type_class() to normalize int/float into one numeric class before comparing"

patterns-established:
  - "SheetRanking (frozen dataclass: ranked list[tuple[str,float]], confident bool, winner property) mirrors HeaderDetection's shape from plan 02 -- 'always expose a best guess, gate on a named confidence margin' is now the consistent pattern across header, sheet, and (later) shape detection"

requirements-completed: [PARSE-04, PARSE-06]

coverage:
  - id: D1
    description: "orion_pk_report.xlsx (Summary and Raw timepoints both tidy tables, no distinguishing structural signal) makes the parser hesitate and return a StructureQuestion with both as ranked candidates, not a silently-picked winner"
    requirement: "PARSE-04"
    verification:
      - kind: unit
        ref: "tests/test_structure_sheets.py#test_rank_sheets_orion_reports_no_confident_winner_with_top_two_candidates"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_parse_orion_with_no_sheet_hesitates_with_summary_and_raw_as_alternatives"
        status: pass
    human_judgment: false
  - id: D2
    description: "meridian_cro_codes.xlsx picks DATA over the narrow LEGEND sheet confidently, and parse() proceeds through header detection to a RawTable"
    requirement: "PARSE-04"
    verification:
      - kind: unit
        ref: "tests/test_structure_sheets.py#test_rank_sheets_meridian_confident_with_data_as_winner"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_parse_meridian_with_no_sheet_auto_selects_data"
        status: pass
    human_judgment: false
  - id: D3
    description: "A chartsheet is dropped from ranking and never crashes the reader (D-17); an embedded chart on a data sheet does not disqualify that sheet from ranking or parsing (D-16)"
    requirement: "PARSE-04"
    verification:
      - kind: unit
        ref: "tests/test_structure_sheets.py#test_rank_sheets_chartsheet_fixture_never_raises_and_excludes_chartsheet"
        status: pass
      - kind: unit
        ref: "tests/test_structure_sheets.py#test_rank_sheets_embedded_chart_fixture_ranks_the_data_sheet_normally"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_parse_chart_embedded_sheet_resolves_normally"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_parse_chartsheet_workbook_single_data_sheet_resolves_without_asking"
        status: pass
    human_judgment: false
  - id: D4
    description: "An image-only sheet returns a StructureQuestion, not the old silent 'sheet has no data rows' skip; the CLI's run() reflects this end-to-end (exit code 4, no skip message printed)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_drawings.py#test_is_drawing_only_sheet_true_for_image_only_fixture"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_parse_image_only_sheet_returns_structure_question_not_empty_table"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_sheets.py#test_cli_run_on_image_only_sheet_asks_and_never_prints_the_old_skip_message"
        status: pass
    human_judgment: false
  - id: D5
    description: "defusedxml is installed so openpyxl.DEFUSEDXML is True, closing the pre-existing XXE/entity-expansion gap on untrusted .xlsx parsing"
    requirement: "PARSE-06"
    verification:
      - kind: other
        ref: "uv run python -c \"import openpyxl; print(openpyxl.DEFUSEDXML)\" prints True"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-10
status: complete
---

# Phase 1 Plan 3: Multi-Sheet Selection + Drawing Guards Summary

**`parse()`'s Excel branch now selects the data sheet structurally before header detection — `meridian_cro_codes.xlsx` auto-picks `DATA` over the narrow `LEGEND` sheet, `orion_pk_report.xlsx`'s genuinely tied `Summary`/`Raw timepoints` makes it hesitate and ask, a chartsheet is dropped without crashing, an embedded chart never disqualifies its data sheet, and an image-only sheet asks instead of the old silent "no data rows" skip — closing the wave-2 gap where the CLI never actually reached this code.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-10T09:47:37Z
- **Completed:** 2026-07-10T09:56:52Z
- **Tasks:** 3 (Task 1 auto; Tasks 2/3 TDD: RED then GREEN)
- **Files modified:** 14 (7 created, 7 modified)

## Accomplishments

- Extended `scripts/gen_synthetic_pk.py` with 4 deterministic fixtures the corpus previously had zero of: an embedded-chart workbook (D-16), a chartsheet-bearing workbook (D-17), an image-only-sheet workbook (D-18), and a two-independent-tables-on-one-sheet workbook (D-10's `multiple_tables` corpus gap). Added `defusedxml` as a runtime dependency — `openpyxl.DEFUSEDXML` flipped from `False` to `True` with no code change, closing a real pre-existing XXE gap. `pillow` added dev-only; `grep -rn "import PIL" src/` returns nothing.
- Built `structure/sheets.py`'s `rank_sheets()`: a saturating structural score (fill density + width-relative-to-widest-sheet + row-count + weak first-column-uniqueness) that empirically reproduces both required corpus behaviors — `orion_pk_report.xlsx`'s `Summary`/`Raw timepoints` tie (score diff ~0.078, below the 0.1 confidence margin) and `meridian_cro_codes.xlsx`'s `DATA` confidently beating `LEGEND` (diff ~0.171).
- Built `grid.is_drawing_only_sheet()` exactly per the RESEARCH.md-verified predicate: cell content via `iter_rows`, drawing presence via `ws._rels`' relationship type — never `ws._images` (silently empty without Pillow) or `max_row == 0` (a drawing-only sheet reports `max_row=1`).
- Wired both into `parse()`'s Excel branch (sheet selection ahead of header detection, drawing-only check before treating a sheet as empty) and into `cli.py`'s `resolve_or_ask()`, which now routes Excel through `parse()` exactly as CSV already did — closing the wave-2 "known limitation" where the CLI never surfaced header-detected or sheet-selected Excel tables end-to-end. Verified live: `uv run assayingest data/synthetic/orion_pk_report.xlsx` now prints a real `StructureQuestion` (exit 4); `uv run assayingest data/synthetic/quantex_scanned_report.xlsx` asks instead of printing "no data rows".

## Task Commits

1. **Task 1: generate drawing fixtures (Pillow dev-only) + close the XXE gap (defusedxml)** — `11fb578` (feat)
2. **Task 2: sheet ranking + drawing/chartsheet/image guards (sheets.py + grid.py)**
   - `a00dd76` test(01-03): add failing test for sheet ranking and drawing guards
   - `5b3aeb3` feat(01-03): implement sheet ranking and drawing/chartsheet/image guards
3. **Task 3: wire sheet selection into parse()/CLI end-to-end (fix the drawing-only skip)**
   - `9f47cf9` test(01-03): add failing test for parse()/CLI sheet-selection wiring
   - `7eb1a84` feat(01-03): wire sheet selection into parse()/CLI end-to-end

## Files Created/Modified

- `scripts/gen_synthetic_pk.py` — `gen_chart_embedded()`, `gen_chartsheet()`, `gen_image_only_sheet()`, `gen_multiple_tables()`, updated `main()`
- `pyproject.toml` — `defusedxml` (runtime dep), `pillow` (dev-only dep)
- `data/synthetic/README.md` — new "Drawing fixtures" table
- `data/synthetic/vantage_pk_with_chart.xlsx`, `nimbus_labs_chartsheet.xlsx`, `quantex_scanned_report.xlsx`, `triton_screening_two_tables.xlsx` — the 4 new fixtures
- `src/assayingest/parsing/structure/sheets.py` — `SheetRanking`, `rank_sheets()`, weighted-signal private helpers
- `src/assayingest/parsing/structure/grid.py` — `is_drawing_only_sheet()`
- `src/assayingest/parsing/structure/header.py` — `_type_class()` helper (deviation, see below)
- `src/assayingest/parsing/table.py` — `_parse_excel_structurally()` now selects a sheet via `_resolve_sheet()` before header detection; `_sheet_ambiguous_question()`, `_drawing_only_question()`
- `src/assayingest/cli.py` — `resolve_or_ask()` routes Excel through `parse()` unconditionally
- `tests/test_structure_sheets.py`, `tests/test_structure_drawings.py`, `tests/test_parse_entry_sheets.py` — 24 new tests

## Decisions Made

- Sheet-ranking score uses **saturating** signals (`min(x / threshold, 1.0)`), not linear ones, so two sheets that are both "wide enough" or "tall enough" to plausibly be data tables score equally on that dimension even when their raw counts differ a lot — this is what lets `Summary` (7 cols, 11 rows) and `Raw timepoints` (4 cols, 51 rows) tie honestly instead of the linearly-larger sheet always winning. First-column uniqueness stays a low-weight (0.1) tie-breaker per RESEARCH.md's explicit finding that it reveals record granularity, not "correctness."
- `resolve_or_ask()` now unconditionally calls `parse()` for every file type, always returning a single-element list or a `StructureQuestion` — the CLI no longer loops every sheet of a multi-sheet workbook. This matches PROJECT.md's stated v1 scope ("the tool targets one chosen table per file") and D-09 ("the human picks"), and is exactly what the plan's `resolve_or_ask` docstring rewrite specifies. `resolve_tables()`/`parse_file()` remain in the module, still exported and still covered by `tests/test_excel_sheets.py`, but are no longer reachable from `run()`'s live path — they are now legacy building blocks (used internally by `resolve_tables()` itself and as `parse()`'s fallback for unsupported extensions), not dead code, but their role changed. Flagging this explicitly per the plan's own instruction to say so rather than leave it silently orphaned.
- `is_drawing_only_sheet`'s `StructureQuestion` sets `confidence=0.0` (not the `0.5` used for the CSV-locale and header-uncertainty asks) — there is no plausible auto-fill answer for "this sheet is an unreadable image," unlike a locale or header-row guess where a best guess is always meaningful.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] header.py's `_type_consistency` treated int and float as distinct types, blocking meridian's confident resolution**
- **Found during:** Task 3 GREEN phase, while verifying `parse(meridian_cro_codes.xlsx)` against the plan's own acceptance criterion ("parse(meridian) returns a RawTable built from the DATA sheet")
- **Issue:** `meridian_cro_codes.xlsx`'s `VAL` column is genuinely numeric throughout, but one value (`193`) happens to be a whole number. openpyxl reads a decimal-less numeric cell back as Python `int` while its neighbors (`38.489`, `16.937`, ...) read as `float`. `header.py`'s `_type_consistency` compared exact `type(value)`, so this single whole-number value made an otherwise fully-consistent column look type-inconsistent for any candidate row whose 5-row lookahead window included it — dragging the real header row's score down to a 0.043 margin over the runner-up, below the existing 0.05 `_CONFIDENCE_MARGIN`. `detect_header` reported `confident=False`, so `parse(meridian)` returned a `StructureQuestion` instead of the required `RawTable`, contradicting the plan's stated acceptance criterion.
- **Fix:** Added `_type_class()`, which normalizes `int`/`float` into a single numeric class (`bool` stays distinct, since it's an `int` subclass) before the type-consistency comparison. This is a storage-artifact fix, not a threshold retune — the underlying signal ("is this column consistently one kind of value") now sees `193` and `38.489` as the same kind, which they semantically are.
- **Files modified:** `src/assayingest/parsing/structure/header.py` (not in this plan's original `files_modified` list — added because the bug directly blocked a stated acceptance criterion; Rule 3's "auto-fix blocking issues" applies alongside Rule 1)
- **Verification:** `uv run pytest tests/test_structure_header.py tests/test_parse_entry_excel_header.py tests/test_parse_entry_sheets.py -q` — all 22 tests pass, including the pre-existing zephyr and near-tie fixtures (unaffected — neither exercises a whole-number-among-decimals column)
- **Committed in:** `7eb1a84` (Task 3 GREEN commit, alongside the sheet-selection wiring)

---

**Total deviations:** 1 auto-fixed (1 pre-existing bug in a file outside this plan's stated scope, fixed because it directly blocked a stated acceptance criterion)
**Impact on plan:** No scope creep beyond the one file. The fix is a correctness fix (a genuinely numeric column should score as type-consistent regardless of whether one value happens to round to a whole number) with no behavior change for any other tested fixture.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None — no external service configuration required. `defusedxml`/`pillow` are ordinary `uv add`/`uv add --dev` installs, already completed and verified in Task 1.

## Next Phase Readiness

- `structure/sheets.py`'s `SheetRanking`/`rank_sheets()` and `grid.is_drawing_only_sheet()` are stable primitives — plan 04 (shape classification: `wide_matrix`/`transposed`/`multiple_tables`) can build on the same `grid.list_worksheets()`/`iter_rows()` foundation without re-deriving sheet iteration or drawing detection.
- The `triton_screening_two_tables.xlsx` fixture (two independent tables on one sheet, separated by 2 blank rows) closes RESEARCH.md's explicitly flagged corpus gap for `multiple_tables` — plan 04 now has a real fixture to test the previously-untestable shape-classification branch against, instead of only a defensive `unknown` fallback.
- The CLI's Excel path is now genuinely end-to-end through `parse()` — the wave-2 "Known Limitation" (CLI never surfacing header-detected Excel tables) is fully closed, verified live against `orion_pk_report.xlsx` (asks), `meridian_cro_codes.xlsx` (auto-selects, reaches the credentials gate), and `quantex_scanned_report.xlsx` (asks, no stale skip message).
- Full test suite: 101 passed, 1 skipped (pre-existing live-API test, unaffected) — the 85 tests from plan 02's baseline remain green with zero regressions; 16 new tests added in this plan.
- No blockers for plan 04 (shape classification) or plan 05.

---
*Phase: 01-robust-file-reading*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 14 created/modified files (plus this summary itself) verified present on disk; all 5 task commit hashes (11fb578, a00dd76, 5b3aeb3, 9f47cf9, 7eb1a84) verified present in git log.

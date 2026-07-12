---
phase: 01-robust-file-reading
plan: 02
subsystem: parsing
tags: [openpyxl, excel, structural-detection, header-row-scoring, json-contract]

# Dependency graph
requires:
  - phase: 01-robust-file-reading/01-01
    provides: "parsing/hint.py's StructuralHint/StructureQuestion contract; parsing/table.py's parse() entry point shape"
provides:
  - "parsing/structure/grid.py: read_grid()/list_worksheets() — the openpyxl NORMAL-mode raw-grid reader every later plan in this phase (03, 04, 05) reuses for chart/sheet/shape detection"
  - "parsing/structure/header.py: header_row_scores()/detect_header()/HeaderDetection — the width-consistency + type-mismatch header scoring heuristic, with a named, corpus-tuned confidence threshold"
  - "parsing/table.py: parse()'s Excel branch is now header-aware — detects the true header row beneath banner rows, honors hint.header_row_index, and returns a StructureQuestion (not an exception) when uncertain"
affects: [01-robust-file-reading/01-03, 01-robust-file-reading/01-04, 01-robust-file-reading/01-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw-grid detection reads via openpyxl.load_workbook() in NORMAL mode (never read_only=True) to keep native cell types and _charts/_images/_rels available for later plans"
    - "detect_header() always returns a best-guess index (even when not confident) so the caller can pre-fill a StructureQuestion's proposal — 'not confident' means 'don't auto-apply this', not 'no answer'"
    - "Detection runs on native openpyxl types; conversion to RawTable's strings-only shape happens only after the header row is resolved (never before)"

key-files:
  created:
    - src/assayingest/parsing/structure/grid.py
    - src/assayingest/parsing/structure/header.py
    - tests/test_structure_grid.py
    - tests/test_structure_header.py
    - tests/test_parse_entry_excel_header.py
  modified:
    - src/assayingest/parsing/table.py

key-decisions:
  - "_CONFIDENCE_MARGIN set to 0.05 (below zephyr's verified 0.086 margin), not RESEARCH.md's tentative 0.1 starting point — 0.1 would have flagged the plan's own reference case (zephyr_bio_ZB-2025.xlsx) as not-confident, contradicting the plan's explicit acceptance criterion that it must resolve confidently. Documented in header.py as corpus-tuned against exactly one real fixture, not a final constant (01-RESEARCH.md Open Question 1 explicitly asked for this to be validated/tuned during execution)."
  - "HeaderDetection.index is always the top-scoring row, even when confident=False — this lets parse()'s not-confident branch pre-fill StructureQuestion.proposal.header_row_index with a real best guess (D-02's 'propose, never auto-apply' pattern), rather than forcing the caller to re-derive a guess from raw scores."
  - "_parse_excel_structurally() reuses table.py's existing sheet_names()/target-resolution logic (not grid.py's own sheet-not-found path) to keep the unknown-sheet ValueError message identical to parse_file()'s existing contract; grid.read_grid() is called only after the sheet name is already validated."

patterns-established:
  - "structure/grid.py is the single raw-grid reader for the whole structure/ package — plans 03/04/05 read charts, chartsheets, images, and shape signals off the same list_worksheets()/read_grid() primitives rather than re-opening the workbook"
  - "header.py's private-helper-per-signal style (_str_ratio, _uniq_ratio, _fill_ratio, _type_consistency) mirrors locale.py's _scan_comma_decimals/_all_non_numeric/_resolve_locale split from plan 01 — single level of abstraction per function, one named helper per heuristic signal"

requirements-completed: [PARSE-01, PARSE-06]

coverage:
  - id: D1
    description: "zephyr_bio_ZB-2025.xlsx (3 banner rows + 1 blank above the real header) resolves to a RawTable whose header is the real column names at raw-grid row 4, not the banner text at row 0"
    requirement: "PARSE-01"
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_zephyr_detects_header_beneath_banner_rows"
        status: pass
      - kind: unit
        ref: "tests/test_structure_header.py#test_detect_header_finds_zephyr_row_beneath_banner_rows_confidently"
        status: pass
      - kind: unit
        ref: "tests/test_structure_grid.py#test_read_grid_zephyr_preserves_native_types"
        status: pass
    human_judgment: false
  - id: D2
    description: "Header-row detection reads native openpyxl types (float 32.051, not the string '32.051') so the type-mismatch signal can distinguish header from data; the final RawTable still holds every cell as a string (D-12 unchanged)"
    requirement: "PARSE-01"
    verification:
      - kind: unit
        ref: "tests/test_structure_grid.py#test_read_grid_zephyr_preserves_native_types"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_zephyr_all_cells_are_strings"
        status: pass
    human_judgment: false
  - id: D3
    description: "A constructed near-tie header case (two equally header-like rows) returns confident=False and a StructureQuestion pre-filled with a best-guess header_row_index and evidence rows — never a raised exception, never a silent pick of the marginally-higher score"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_header.py#test_near_tie_rows_report_not_confident"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_uncertain_header_returns_structure_question_not_raise"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_uncertain_header_proposal_prefills_best_guess"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_uncertain_header_evidence_rows_show_first_rows"
        status: pass
    human_judgment: false
  - id: D4
    description: "An explicit hint.header_row_index overrides detection and builds an equivalent RawTable directly from that row (PARSE-06's 'proceed using the human's hint' path)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_excel_header.py#test_parse_zephyr_hint_overrides_detection_with_equivalent_result"
        status: pass
    human_judgment: false
  - id: D5
    description: "A workbook containing a chartsheet never crashes grid access — list_worksheets() iterates wb.worksheets, which structurally excludes Chartsheet (D-17)"
    requirement: "PARSE-01"
    verification:
      - kind: unit
        ref: "tests/test_structure_grid.py#test_list_worksheets_excludes_chartsheet"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-07-10
status: complete
---

# Phase 1 Plan 2: Excel Header-Detection Vertical Slice Summary

**`zephyr_bio_ZB-2025.xlsx`'s real header — buried at raw-grid row 4 beneath 3 banner rows and 1 blank row — is now located structurally via width-consistency + type-mismatch scoring (openpyxl native types), and a genuinely uncertain header returns a pre-filled `StructureQuestion` instead of guessing.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-10T09:37:14Z
- **Completed:** 2026-07-10T09:41:00Z
- **Tasks:** 3 (all TDD: RED then GREEN)
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments

- Built `structure/grid.py`, the openpyxl NORMAL-mode raw-grid reader every later plan in this phase (chart/chartsheet/image detection in plan 03, sheet ranking in plan 04, shape classification in plan 05) will read through — `read_grid()` preserves native cell types (a numeric cell stays a `float`, never coerced to a string), and `list_worksheets()` iterates `wb.worksheets` so a chartsheet can never reach a caller as something that crashes on `.iter_rows()` (D-17).
- Built `structure/header.py`'s header-row scoring: `header_row_scores()` combines str-ratio, uniqueness, fill-ratio, and cross-row type-consistency (0.3/0.2/0.2/0.3 weighted, per 01-RESEARCH.md Pattern 1) to score every candidate row; `detect_header()` picks a winner only when its margin over the runner-up clears a named `_CONFIDENCE_MARGIN` constant, otherwise reporting `confident=False` — a first-class "I don't know" outcome (D-03), never a silent guess.
- Wired both into `parse()`'s Excel branch: the raw grid is read, the header is detected, and the grid is sliced at the resolved row before converting to the strings-only `RawTable` shape (D-12) — detection sees native types, the output never does. A not-confident detection returns a `StructureQuestion` with a pre-filled best-guess `header_row_index` and up to 8 evidence rows; an explicit `hint.header_row_index` skips detection entirely and builds the table from that row (PARSE-06's hint-override path).
- Verified end-to-end against the real `zephyr_bio_ZB-2025.xlsx` fixture: `parse(path, sheet="Week 1")` now returns real column names (`Compound ID`, `Assay`, `Result`, ...) and the first real record (`ZB-100`), not the banner text.

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: openpyxl normal-mode raw-grid reader (grid.py)**
   - `928055a` test(01-02): add failing test for openpyxl normal-mode raw-grid reader
   - `21f814c` feat(01-02): implement openpyxl normal-mode raw-grid reader
2. **Task 2: header-row scoring (header.py)**
   - `94f0f2b` test(01-02): add failing test for header-row scoring (header.py)
   - `8832bb7` feat(01-02): implement header-row scoring by width/type-consistency
3. **Task 3: wire header detection into parse() end-to-end**
   - `d6f5b1d` test(01-02): add failing test for parse() Excel header-detection branch
   - `09a92e6` feat(01-02): wire header detection into parse()'s Excel branch

## Files Created/Modified

- `src/assayingest/parsing/structure/grid.py` — `read_grid()`, `list_worksheets()`, `_select_worksheet()`
- `src/assayingest/parsing/structure/header.py` — `HeaderDetection`, `header_row_scores()`, `detect_header()`, `_CONFIDENCE_MARGIN`, and one private helper per scoring signal
- `src/assayingest/parsing/table.py` — `parse()`'s Excel branch now header-aware; `_parse_excel_structurally()`, `_raw_table_from_header_row()`, `_header_uncertain_question()`, `_row_to_strings()`
- `tests/test_structure_grid.py`, `tests/test_structure_header.py`, `tests/test_parse_entry_excel_header.py` — 21 new tests

## Decisions Made

- **`_CONFIDENCE_MARGIN = 0.05`, not RESEARCH.md's tentative 0.1.** RESEARCH.md's Pattern 1 proposed "~0.1" as a starting point, but zephyr's own verified margin (0.086) is *below* 0.1 — using 0.1 as written would have flagged the plan's own reference fixture as not-confident, directly contradicting the plan's acceptance criterion ("detect_header on zephyr Week 1's native-typed rows returns index == 4 with confident == True"). RESEARCH.md itself flagged this threshold as unvalidated at scale and explicitly asked for it to be tuned during execution (Open Question 1), so this is expected discretion, not a deviation from intent. **This constant is corpus-tuned against exactly one real fixture and should be revisited once more banner-row fixtures exist** (per RESEARCH.md's own caveat and the plan's critical_constraints instruction to document this honestly rather than pretend the threshold is settled).
- **`HeaderDetection.index` is always the top-scoring row, not `None` when unconfident.** The plan's Task 3 acceptance criteria require the not-confident path to pre-fill `StructureQuestion.proposal.header_row_index` with a best guess. Making `detect_header()` return that best guess directly (with `confident=False` as the "don't trust this" signal) avoids `table.py` having to re-derive a guess from raw scores, and matches D-02's "propose, never auto-apply" pattern — the proposal is always populated, only the trust decision differs.
- **The near-tie test fixture is a constructed synthetic grid, not a corpus file** (per RESEARCH.md's own note that no second banner-row fixture exists in the corpus to validate against). Two header-like rows, each followed by its own internally-consistent 5-row data block, produce an exact score tie (1.0 vs 1.0) — a genuine, deterministic not-confident case, reused identically across `tests/test_structure_header.py` and `tests/test_parse_entry_excel_header.py` (the latter round-trips it through an actual saved `.xlsx` file to prove the same tie survives openpyxl's save/reload).
- **`cli.py` was deliberately left untouched**, per this plan's explicit scope (`files_modified` in the frontmatter) and the plan's own constraint that "Sheet SELECTION is wave 3's job, not yours." `cli.py`'s `resolve_or_ask()` still routes every Excel file through the legacy `resolve_tables()`/`parse_file()` path (its own docstring already says so: "Excel structural detection lands in later plans of this phase"). See "Known Limitation" below.

## Deviations from Plan

None (Rule 1/2/3 sense) — one instance of exercised Claude's-Discretion documented above (`_CONFIDENCE_MARGIN` value), which the plan itself explicitly asked the planner/executor to ground rather than invent, and RESEARCH.md's Open Question 1 anticipated needing this exact adjustment.

One self-caught test bug during Task 1's GREEN phase, same class as plan 01's documented deviation:

**1. [Rule 1 - Bug] Over-broad "no read_only=True" assertion caught the module's own docstring prose**
- **Found during:** Task 1 GREEN phase (`grid.py` implementation)
- **Issue:** `test_grid_module_never_loads_in_read_only_mode` originally asserted `"read_only=True" not in text` against the entire file, which fails as soon as the module docstring explains *why* `read_only=True` is avoided (the docstring literally contains the string `read_only=True` in prose) — checking English words, not the actual `load_workbook(...)` call.
- **Fix:** Narrowed the assertion to only the lines containing a `load_workbook(` call, matching the exact concern the acceptance criterion cares about.
- **Files modified:** `tests/test_structure_grid.py`
- **Verification:** `uv run pytest tests/test_structure_grid.py -x -q` — 7 passed
- **Committed in:** `21f814c` (Task 1 GREEN commit, alongside `grid.py`'s implementation)

---

**Total deviations:** 1 auto-fixed (1 test bug, Rule 1); 1 documented discretion call (`_CONFIDENCE_MARGIN`, explicitly invited by the plan/research).
**Impact on plan:** No scope creep. Both are corrections that make the tests/threshold actually test what the plan requires.

## Issues Encountered

**Known limitation (not a bug, explicitly out of scope for this plan):** `uv run assayingest data/synthetic/zephyr_bio_ZB-2025.xlsx --sheet "Week 1"` still reaches the credentials gate without showing header-detected column names, because `cli.py`'s `resolve_or_ask()` routes every Excel file through the legacy `resolve_tables()`/`parse_file()` path, not the new `parse()` Excel branch. This is unchanged behavior from before this plan — `cli.py` is not in this plan's `files_modified`, and its own docstring already documents the deferral ("Excel structural detection lands in later plans of this phase"). The plan's `<verification>` section's manual-smoke bullet describes the eventual end state once a later plan (sheet ranking, per the plan's own "Sheet SELECTION is wave 3's job, not yours" constraint) wires `resolve_or_ask()`/`resolve_tables()` to call `parse()` for Excel too — `parse()` itself, called directly (as `tests/test_parse_entry_excel_header.py` does), already produces the correct header-detected output end-to-end.

## User Setup Required

None — no external service configuration required. The deterministic layer built here needs no API key (D-04), same as plan 01.

## Next Phase Readiness

- `structure/grid.py`'s `read_grid()`/`list_worksheets()` are the stable raw-grid primitives plans 03 (drawings), 04 (sheet ranking), and 05 (shape classification) will build on directly — no interface changes expected.
- `structure/header.py`'s `HeaderDetection`/`detect_header()` shape is stable; `_CONFIDENCE_MARGIN` is a named constant future plans (or a corpus-expansion task) can retune without touching call sites.
- `parse()`'s Excel branch establishes the same "detect on native types, convert to strings only after resolution" pattern the shape classifier (plan 05) will need to follow for its own row/column type-homogeneity signals.
- **Blocker for the CLI money-shot demo:** the CLI still does not surface header-detected Excel tables end-to-end (see "Issues Encountered" above) — a later plan in this phase must route `cli.py` through `parse()` for Excel, mirroring what plan 01 already did for CSV.
- Full test suite: 85 passed, 1 skipped (pre-existing live-API test, unaffected) — the original 64 tests (from plan 01's baseline) remain green with zero regressions.

---
*Phase: 01-robust-file-reading*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 7 created/modified files verified present on disk; all 6 task commit hashes (928055a, 21f814c, 94f0f2b, 8832bb7, d6f5b1d, 09a92e6) plus this summary's own commit (9c30154) verified present in git log.

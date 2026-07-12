---
phase: 01-robust-file-reading
plan: 01
subsystem: parsing
tags: [csv, pandas, regex, structural-detection, decimal-locale, json-contract]

# Dependency graph
requires: []
provides:
  - "parsing/hint.py: StructuralHint, StructureQuestion, TableShape, NumericLocale — the JSON-serialisable structural-question contract every later slice reuses"
  - "parsing/structure/delimiter.py: read_csv_grid() — CSV delimiter/comment sniffing immune to the csv.Sniffer comment-line trap"
  - "parsing/structure/locale.py: classify_column()/annotate_columns() — the D-14 decimal-locale ambiguity rule"
  - "parsing/table.py: parse() entry point returning RawTable | StructureQuestion; RawTable.column_locales field"
  - "cli.py: resolve_or_ask(), _ask_and_report(), _render_question() — the CLI ask-branch (exit code 4)"
affects: [01-robust-file-reading/01-02, 01-robust-file-reading/01-03, 01-robust-file-reading/01-04, 01-robust-file-reading/01-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "StructureQuestion mirrors domain/models.py's FieldMapping propose+confidence+gate shape one layer earlier, for structure instead of column meaning"
    - "Deterministic layer stays pure (no anthropic import, no network) — hint.py/structure/*.py import only dataclasses/enum/re/pandas"
    - "Structural uncertainty is a RETURNED value (StructureQuestion), never a raised exception — only broken files (missing path, bad extension) still raise"
    - "Local (function-scoped) import in structure/delimiter.py breaks a circular import with table.py, which imports structure/delimiter at module load time"

key-files:
  created:
    - src/assayingest/parsing/hint.py
    - src/assayingest/parsing/structure/__init__.py
    - src/assayingest/parsing/structure/delimiter.py
    - src/assayingest/parsing/structure/locale.py
    - tests/test_structure_hint.py
    - tests/test_structure_delimiter.py
    - tests/test_structure_locale.py
    - tests/test_parse_entry_csv.py
  modified:
    - src/assayingest/parsing/table.py
    - src/assayingest/cli.py

key-decisions:
  - "The D-14 ambiguity predicate (comma_digit_counts == {3} => ambiguous, variance => decimal_comma) implemented exactly as validated in 01-RESEARCH.md Pattern 3, including the single-value-column edge case (Pitfall 7)"
  - "parse() dispatches CSV through the new structural detector; Excel and parse_file() are left untouched — Excel structural detection (header row, sheet ranking, shape) is explicitly deferred to plans 02-04 of this phase"
  - "CLI's structural-question branch (_ask_and_report, exit code 4) fires before the credentials check — asking never requires an Anthropic API key, matching D-04/D-08"

patterns-established:
  - "Wire/domain-style boundary reuse: StructuralHint/StructureQuestion follow domain/models.py's frozen-value-object + to_dict() JSON-boundary convention exactly, so Phase 3 (LEARN-06 persistence) and Phase 4 (UI-02 HTTP) can consume them unchanged"
  - "Regex-predicate classification with named private helpers (_scan_comma_decimals, _all_non_numeric, _resolve_locale) for single-level-of-abstraction compliance"

requirements-completed: [PARSE-02, PARSE-03, PARSE-06]

coverage:
  - id: D1
    description: "pinnacle_labs_export.csv parses to 7 columns/14 rows end-to-end (not one junk column), immune to the csv.Sniffer '=' comment-line trap"
    requirement: "PARSE-02"
    verification:
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_pinnacle_csv_reads_seven_headers_not_one_junk_column"
        status: pass
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_pinnacle_csv_ignores_the_comment_lines_delimiter_hint"
        status: pass
    human_judgment: false
  - id: D2
    description: "The pinnacle 'Value' column resolves to decimal_comma with no StructureQuestion (digit-count variance proves the decimal); a uniform 3-digit-comma column is ambiguous and never guessed"
    requirement: "PARSE-03"
    verification:
      - kind: unit
        ref: "tests/test_structure_locale.py#test_pinnacle_value_sample_resolves_decimal_comma_without_ambiguity"
        status: pass
      - kind: unit
        ref: "tests/test_structure_locale.py#test_uniform_three_digit_comma_groups_are_ambiguous"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_pinnacle_returns_clean_table_with_decimal_comma_annotated"
        status: pass
    human_judgment: false
  - id: D3
    description: "parse() returns a StructureQuestion (never raises, never a RawTable) for a genuinely ambiguous decimal-locale CSV; the CLI prints the question via a dedicated ask-branch and exits without needing credentials"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_ambiguous_locale_returns_structure_question_not_raw_table"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_ambiguous_locale_does_not_raise"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_cli_ask_branch_prints_question_and_does_not_crash"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_cli_ask_branch_does_not_require_credentials"
        status: pass
      - kind: other
        ref: "uv run assayingest data/synthetic/pinnacle_labs_export.csv (manual smoke — reaches credentials gate, proving structural resolution succeeded without asking)"
        status: pass
    human_judgment: false
  - id: D4
    description: "StructuralHint/StructureQuestion are pure, JSON-round-trippable dataclasses with no anthropic/pandas import — the contract every later slice (headers, sheets, shape) and later phase (LEARN-06 persistence, UI-02 HTTP) reuses unchanged"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_hint.py#test_structural_hint_json_round_trips_when_fully_populated"
        status: pass
      - kind: unit
        ref: "tests/test_structure_hint.py#test_structure_question_to_dict_is_json_serialisable_with_proposal"
        status: pass
      - kind: unit
        ref: "tests/test_structure_hint.py#test_hint_module_imports_only_stdlib"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-10
status: complete
---

# Phase 1 Plan 1: CSV Vertical Slice + Structural-Question Contract Summary

**A semicolon-delimited, comment-laden, comma-decimal CSV (pinnacle_labs_export.csv) reads as a clean 7-column table via `pd.read_csv(sep=None, engine="python", comment="#")`, and a genuinely ambiguous decimal-locale column returns a JSON-serialisable `StructureQuestion` instead of a silent 1000x-corrupting guess.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-10T09:20:25Z
- **Completed:** 2026-07-10T09:28:09Z
- **Tasks:** 3 (all TDD: RED then GREEN)
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments

- Built the `StructuralHint`/`StructureQuestion` JSON-round-trippable contract (`parsing/hint.py`) that every later plan in this phase, plus Phase 3's LEARN-06 persistence and Phase 4's UI-02 HTTP surface, will reuse unchanged.
- Implemented CSV delimiter/comment sniffing (`structure/delimiter.py`) that survives the `csv.Sniffer` `'='`-delimiter trap documented in 01-RESEARCH.md Pitfall 1, verified against the real `pinnacle_labs_export.csv` fixture.
- Implemented the per-column decimal-locale ambiguity rule (`structure/locale.py`) — variance across a column's digit-counts-after-comma proves `decimal_comma`; uniform 3-digit groups (or mixed dot/comma notation) are flagged `ambiguous`, never guessed, matching D-14 exactly including the single-value-column edge case.
- Wired a new `parse()` entry point in `table.py` returning `RawTable | StructureQuestion` for CSV, and a CLI ask-branch (`_ask_and_report`, exit code 4) that renders a returned question without crashing and without requiring an API key — while leaving `parse_file()` and the Excel path untouched for the 32 pre-existing tests.

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: Define the structural-question contract (hint.py)**
   - `e4edb43` test(01-01): add failing test for StructuralHint/StructureQuestion contract
   - `cb334ae` feat(01-01): implement StructuralHint/StructureQuestion contract
2. **Task 2: CSV delimiter/comment sniffing + per-column decimal-locale annotation**
   - `ef753ae` test(01-01): add failing tests for CSV delimiter sniffing and decimal-locale classification
   - `3a68d6c` feat(01-01): implement CSV delimiter sniffing and decimal-locale classification
3. **Task 3: Wire the CSV slice end-to-end — parse() entry + RawTable locale annotation + CLI ask-branch**
   - `953cdf5` test(01-01): add failing test for parse() entry point and CLI ask-branch
   - `62fbf0c` feat(01-01): wire parse() entry point and CLI ask-branch for CSV

## Files Created/Modified

- `src/assayingest/parsing/hint.py` — `TableShape`, `NumericLocale` (str-Enums), `StructuralHint`, `StructureQuestion` (frozen dataclasses with `to_dict()`)
- `src/assayingest/parsing/structure/__init__.py` — empty package marker
- `src/assayingest/parsing/structure/delimiter.py` — `read_csv_grid()`
- `src/assayingest/parsing/structure/locale.py` — `classify_column()`, `annotate_columns()`
- `src/assayingest/parsing/table.py` — `RawTable.column_locales` field (defaulted, back-compat); `parse()`, `_parse_csv_structurally()`, `_ambiguous_locale_question()`
- `src/assayingest/cli.py` — `resolve_or_ask()`, `_ask_and_report()`, `_render_question()`; `run()` routes a `StructureQuestion` before the credentials gate
- `tests/test_structure_hint.py`, `tests/test_structure_delimiter.py`, `tests/test_structure_locale.py`, `tests/test_parse_entry_csv.py` — 32 new tests

## Decisions Made

- Followed 01-CONTEXT.md/01-RESEARCH.md exactly on the D-14 ambiguity predicate and the `pd.read_csv(sep=None, engine="python", comment="#", dtype=str)` sniffing approach — no deviation from the researched/verified pattern.
- `structure/delimiter.py` imports `table.py`'s `_clean_header` via a **local (function-scoped) import** rather than a module-level one, to avoid a circular import: `table.py` imports `structure/delimiter.py` at module load time (for the new `parse()` entry point), and `structure/delimiter.py` needs `_clean_header` from `table.py`. This is a mechanical necessity of the module layout chosen in 01-PATTERNS.md, not a deviation from the plan's intent ("reuse `_clean_header` behavior from table.py").
- Excel files and `parse_file()` are untouched in this plan, per the plan's explicit scope ("Keep `parse_file()` unchanged as the legacy simple path"). `parse()` falls back to `parse_file()` for any non-CSV extension; Excel structural detection is plans 02-04's job.
- CLI ask-branch exit code chosen as `4`, distinct from the existing 0 (success), 1 (mapping failed), 2 (bad file), 3 (missing credentials) codes — documented in `_ask_and_report`'s docstring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Over-broad import-purity test assertion caught docstring prose, not import statements**
- **Found during:** Task 1 GREEN phase (`hint.py` implementation)
- **Issue:** `test_hint_module_imports_only_stdlib` originally asserted `"pandas" not in text` / `"anthropic" not in text` against the *entire file text*, which fails as soon as the module docstring mentions "no dependency on pandas... or the Anthropic SDK" in prose — the test was checking the wrong thing (English words, not Python imports).
- **Fix:** Narrowed the assertion to only the collected `import_lines` (lines starting with `import `/`from `), which is what D-04 purity actually requires.
- **Files modified:** `tests/test_structure_hint.py`
- **Verification:** `uv run pytest tests/test_structure_hint.py -x -q` — 9 passed
- **Committed in:** `cb334ae` (Task 1 GREEN commit, alongside the `hint.py` implementation)

---

**Total deviations:** 1 auto-fixed (1 test bug, Rule 1)
**Impact on plan:** No scope creep. The fix corrected a test that would have permanently failed against any correctly-written module docstring explaining the D-04 purity invariant in prose.

## Issues Encountered

None beyond the test-assertion bug documented above.

## User Setup Required

None — no external service configuration required. (The `ANTHROPIC_API_KEY` gate already existed from Day 1 and is unrelated to this plan's deterministic layer, which is designed to work without it — see D-04.)

## Next Phase Readiness

- The `StructuralHint`/`StructureQuestion` contract is stable and JSON-round-trippable — plans 02 (header-row detection), 03 (sheet ranking), and 04 (shape classification) can construct `StructureQuestion` instances directly against it with no contract changes expected.
- `parse()`'s CSV branch is the reference implementation for how later plans should wire Excel structural detection into the same entry point (dispatch on suffix, return `RawTable | StructureQuestion`, never raise for uncertainty).
- The CLI's `_ask_and_report`/`_render_question` ask-branch is generic over any `StructureQuestion` — no CLI changes are anticipated when later plans start returning header-row or sheet-selection questions instead of only decimal-locale ones.
- No blockers. Full test suite: 64 passed, 1 skipped (pre-existing live-API test, unaffected) — the original 32 tests remain green with zero regressions.

---
*Phase: 01-robust-file-reading*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 10 created/modified files verified present on disk; all 6 task commit hashes (e4edb43, cb334ae, ef753ae, 3a68d6c, 953cdf5, 62fbf0c) plus this summary's own commit verified present in git log.

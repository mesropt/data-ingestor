---
phase: 11-multi-sheet-ingest
plan: 01
subsystem: parsing
tags: [parsing, structure, multi-sheet, tdd]
status: complete

requires: []
provides:
  - "describe_sheets(path) -> list[SheetDescription] — the per-sheet manifest above parse()"
  - "SheetDescription (name, headers, row_count, status) — frozen"
  - "SheetStatus (ok | drawing_only | unsupported_shape | header_uncertain)"
affects:
  - "src/assayingest/parsing/structure/sheets.py (additions only — rank_sheets untouched)"

tech-stack:
  added: []
  patterns:
    - "Sibling-not-successor: describe_sheets sits beside rank_sheets, reusing list_worksheets/detect_header/classify_shape/is_drawing_only_sheet verbatim rather than forking a second heuristic"
    - "Marked-never-dropped: a gate-failing sheet is described with a status, never omitted (SHEET-04)"
    - "Gate precedence mirrors table.py exactly: drawing-only, then shape, then header confidence"

key-files:
  created:
    - tests/test_structure_describe_sheets.py
  modified:
    - src/assayingest/parsing/structure/sheets.py

key-decisions:
  - "Header text is cleaned by a private _header_texts() in the structure layer rather than importing table._clean_header, which would invert the dependency direction (structure -> table). Divergence is pinned behaviourally instead: a test asserts describe_sheets' headers and row_count equal parse(path, sheet=X)'s for a real fixture."
  - "row_count for a sheet with no resolvable header is len(rows) (the whole grid), matching table.py's `data_region = rows if header_index is None else rows[header_index+1:]` — the same expression, so the manifest can never disagree with the later parse()."
  - "SheetStatus is a str Enum (project convention), so it serialises straight onto the wire in plan 11-02 with no adapter."

requirements-completed: [SHEET-01, SHEET-04]

coverage:
  - deliverable: "describe_sheets() describes every real worksheet of a workbook, in order, with resolved headers and true data-row counts"
    verification:
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_zephyr_describes_every_sheet_in_workbook_order"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_zephyr_reports_the_resolved_header_not_the_banner_row"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_zephyr_row_count_counts_data_rows_not_the_raw_grid"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_delta_keeps_each_panel_its_own_header_spelling"
        status: pass
    human_judgment: false
  - deliverable: "The description never disagrees with the verdict parse(path, sheet=X) reaches (one heuristic, one answer)"
    verification:
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_never_disagrees_with_what_parse_resolves_for_that_sheet"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_gate_precedence_shape_outranks_header_confidence"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_gate_precedence_drawing_only_outranks_header_confidence"
        status: pass
    human_judgment: false
  - deliverable: "A gate-failing sheet is surfaced and marked, never dropped, and no workbook can crash the description (SHEET-04)"
    verification:
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_meridian_surfaces_the_legend_sheet_rather_than_dropping_it"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_orion_notes_is_present_with_no_headers_and_marked"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_marks_a_drawing_only_sheet_and_claims_no_headers"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_marks_a_wide_matrix_sheet_as_an_unsupported_shape"
        status: pass
      - kind: test
        ref: "tests/test_structure_describe_sheets.py#test_describe_sheets_never_crashes_on_any_workbook_in_the_corpus"
        status: pass
    human_judgment: false
  - deliverable: "rank_sheets, SheetRanking, _score_sheet and _CONFIDENCE_MARGIN are byte-unchanged and every existing parsing test stays green unmodified (D-11-21's load-bearing assumption)"
    verification:
      - kind: command
        ref: "uv run pytest -q  (921 passed, 4 skipped)"
        status: pass
      - kind: command
        ref: "git diff 2191625 HEAD -- src/assayingest/parsing/structure/sheets.py | grep '^-'  (only the module docstring's opening line and the import line; the four protected symbols diff-clean)"
        status: pass
    human_judgment: false

metrics:
  duration: 21 min
  tasks: 2
  files: 2
  completed: 2026-07-13
---

# Phase 11 Plan 01: describe_sheets — the per-sheet manifest above parse() — Summary

Built the one genuinely new primitive of Phase 11: `describe_sheets(path)` reports every real worksheet of a workbook — name, RESOLVED headers, data-row count, structural status — and marks a broken sheet rather than dropping it.

## What was built

`src/assayingest/parsing/structure/sheets.py` gained three public artifacts as **siblings** of `rank_sheets`, plus two private helpers:

| Artifact | Contract |
|---|---|
| `SheetStatus(str, Enum)` | `ok` / `drawing_only` / `unsupported_shape` / `header_uncertain` — names the gate a sheet fails, so the manifest can SAY SO instead of hiding it |
| `SheetDescription` (frozen) | `name`, `headers`, `row_count`, `status` |
| `describe_sheets(path)` | One description per real worksheet, in workbook order. Orchestrates only |
| `_describe_one_sheet(worksheet, rows)` | The per-sheet gate chain |
| `_sheet_status(detection, data_region)` | Shape gate, then header-confidence gate |

The gate chain reuses `list_worksheets`, `is_drawing_only_sheet`, `detect_header` and `classify_shape` **verbatim** — the same heuristics `parse()` will later reach — in `table.py`'s exact precedence (drawing → shape → header confidence). Two heuristics would mean two answers; the manifest would tell the human one thing and `parse(path, sheet=X)` another.

## Why it sits above parse() (D-11-21)

`parse()` already short-circuits sheet ranking when handed an explicit `sheet=` (`table.py:359-367`). Building the manifest above it means `parse()`, `_resolve_sheet`, `rank_sheets` and `SheetRanking` are **not touched at all** — and SHEET-04 comes for free downstream: each per-sheet `parse(path, sheet=X)` already runs the full header/shape/locale/date chain on its own sheet.

Verified: the four protected symbols (`rank_sheets`, `SheetRanking`, `_score_sheet`, `_CONFIDENCE_MARGIN`) are byte-identical to their pre-plan state; the file's only two removed lines are the module docstring's opening line (extended) and the import line (widened).

## Behaviour on the real corpus

| Fixture | Result |
|---|---|
| `zephyr_bio_ZB-2025.xlsx` | 3 sheets, all `ok`. Headers resolved from **row 4**, not the `ZEPHYR BIOSCIENCES` banner on row 0. `row_count == 8`, not the grid's 13 |
| `delta_screening_per_target.xlsx` | 3 panels, all `ok`, each keeping its own header spelling (`Compound` / `Cmpd ID` / `compound_id`) — what the plan-02 Schema scorer needs |
| `meridian_cro_codes.xlsx` | `DATA` = `ok`; **`LEGEND` is present** and `header_uncertain`. Today `parse()` discards it silently — the manifest no longer does |
| `orion_pk_report.xlsx` | `Summary` (7 cols) and `Raw timepoints` (4 cols) both `ok`; **`Notes` survives** with `headers == []` and `header_uncertain`, where `detect_header` returns `index=None` |
| `quantex_scanned_report.xlsx` | `drawing_only`, `headers == []`, `row_count == 0` — drawing outranks header confidence |
| `bionexus_transposed.xlsx` | `unsupported_shape` although its header is *also* unconfident — shape outranks header confidence, as in `table.py` |
| `nimbus_labs_chartsheet.xlsx` | The chartsheet never appears (structural exclusion via `list_worksheets`, D-17) |

Every `.xlsx` in `data/synthetic/` is parametrized into a no-crash test: describing a workbook is not allowed to fail, because the sheet-selection screen cannot ask about a workbook it could not read.

## Deviations from Plan

None — plan executed exactly as written.

One judgment call inside the plan's stated discretion: the plan said headers should be "stringified the same way `table.py` does". Importing `table._clean_header` from the `structure/` package would invert the dependency direction (`structure` → `table`, a cycle within the parsing layer, against CLAUDE.md's Clean Architecture rule). A private `_header_texts()` mirrors its contract instead, and the risk that actually matters — divergence between the manifest's headers and the parser's — is pinned **behaviourally** by `test_describe_sheets_never_disagrees_with_what_parse_resolves_for_that_sheet`, which asserts `describe_sheets`' headers and row count equal `parse(path, sheet="Week 2")`'s. That is a stronger guarantee than sharing the function, since it also covers the `row_count` expression.

## TDD Gate Compliance

Both tasks ran RED → GREEN. Gate commits, in order:

1. `df401d7` `test(11-01)` — RED: `ImportError: cannot import name 'SheetDescription'`
2. `1bbc8bc` `feat(11-01)` — GREEN: 12 passed
3. `c56626b` `test(11-01)` — RED: 8 failed / 21 passed, including the `None` header-index `TypeError` crash on orion's `Notes`
4. `8e104d6` `feat(11-01)` — GREEN: 29 passed

No REFACTOR commit was needed — the GREEN implementations were already at a single level of abstraction. No live Anthropic API call is made by any test in this plan (the module has no `anthropic` import and no network access).

## Verification

- `uv run pytest -q` → **921 passed, 4 skipped** (the 4 skips are pre-existing live-API tests, unrelated to this plan)
- `uv run pytest tests/test_structure_describe_sheets.py -q` → 29 passed
- `uv run pytest tests/test_structure_sheets.py tests/test_structure_drawings.py tests/test_structure_shape.py tests/test_parse_entry_sheets.py tests/test_excel_sheets.py -q` → green, **with those files unmodified** (`git diff --name-only HEAD -- …` is empty)
- `grep -c 'from ..learning\|from assayingest.learning\|import learning' src/assayingest/parsing/structure/sheets.py` → 0 (no learning-layer import; the column signature belongs one layer up in `service.py`)
- `grep -c 'def describe_sheets' …/sheets.py` → 1
- `grep -c 'SheetStatus\.' tests/test_structure_describe_sheets.py` → 11 (every enum member asserted)

## Threat Model Check

- **T-11-01 (DoS, mitigate):** `describe_sheets` adds exactly one `load_workbook` pass on an already size-capped upload (≤20 MB, `upload.py:71`). No recursion, no per-cell allocation beyond the grid the parser already materializes. Honoured.
- **T-11-02 (XML entity expansion, transfer):** no new XML reader — goes through `grid.list_worksheets` like every other caller, inheriting the Phase 01-03 defusedxml hardening. Honoured.
- **T-11-03 (info disclosure, accept):** emits sheet names and header rows only; no cell value from the data region ever leaves the module. Honoured (`headers_only` is unaffected — a header is not a cell value, D-10-05).

No new security surface was introduced. No threat flags.

## Next

`describe_sheets` is the input plan 11-02's Schema scorer needs (`column_signature(description.headers)` is computed one layer up, in `service.py` — the parser stays free of any `learning/` import). Ready for 11-02.

## Self-Check: PASSED

- `src/assayingest/parsing/structure/sheets.py` — FOUND
- `tests/test_structure_describe_sheets.py` — FOUND
- Commits `df401d7`, `1bbc8bc`, `c56626b`, `8e104d6` — all FOUND in `git log`
- Full suite green; every task acceptance criterion re-run and passing

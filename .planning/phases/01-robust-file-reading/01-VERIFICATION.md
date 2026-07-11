---
phase: 01-robust-file-reading
verified: 2026-07-10T00:00:00Z
status: passed
score: 5/5 truths verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Excel files never receive decimal-locale annotation (Criterion 3 / PARSE-03) — closed by threading `_resolve_locales_or_ask()` through both the CSV and Excel branches (commit d030233)."
    - "The CSV branch drops the `hint` parameter, and the CLI has no way to supply one (Criterion 5 / PARSE-06) — closed by threading `hint` through `_parse_csv_structurally()`/`read_csv_grid()` and adding `--hint KEY=VALUE` to the CLI (commit d030233)."
  gaps_remaining: []
  regressions: []
deferred: []
human_verification: []
---

# Phase 1: Robust File Reading Verification Report

**Phase Goal:** The parser reads any messy Excel/CSV structurally — where the header row sits, what delimiter and decimal locale is used, which sheet holds the data, and whether the table shape is even supported — by detecting structure, not by hardcoding rules per vendor; when a file's structure is genuinely unfamiliar, the tool never crashes or emits garbage — it asks the human for a structural hint and proceeds.

**Verified:** 2026-07-10
**Status:** passed
**Re-verification:** Yes — after gap closure (commits `9c7e75a`, `d030233`), full phase re-checked from scratch, not just the two closed gaps.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Header row detected structurally beneath any number of banner rows (SC1, PARSE-01) | ✓ VERIFIED | Live: `parse("zephyr_bio_ZB-2025.xlsx", sheet="Week 1")` → RawTable, headers `['Compound ID', 'Assay', 'Result', 'Units', ...]`, 8 rows, banner text never leaks in. `--hint header-row=4` override also confirmed live via `parse(..., hint=StructuralHint(header_row_index=4))`. No regression: identical result to prior verification. |
| 2 | Non-comma CSV (delimiter + comment lines) reads as a proper multi-column table, not one junk column (SC2, PARSE-02) | ✓ VERIFIED | Live: `parse("pinnacle_labs_export.csv")` → 7 headers (`Compound, Endpoint, Value, Unit, Target, Replicates, Date`), 14 rows. `read_csv_grid` uses `pd.read_csv(sep=None/explicit, engine="python", comment="#")`. No regression. |
| 3 | Decimal-comma numbers annotated (not corrupted 1000x); genuine ambiguity flagged, for BOTH CSV and Excel (SC3, PARSE-03, D-13/D-14) | ✓ VERIFIED (gap closed) | **CSV:** `pinnacle`'s `Value` column → `decimal_comma`, no question (digit-count variance disambiguates). **Excel (the closed gap):** live `parse("helix_genomics_DE.xlsx")` — the phase's own canonical PARSE-03 fixture — now returns `column_locales = ['non_numeric', 'non_numeric', 'decimal_comma', 'non_numeric', 'decimal_point', 'non_numeric']`; the `Konz. (µM)` column is correctly `decimal_comma` and `table.rows[0][2] == "14,771"` — the string is annotated, **not** rewritten (correctly matching D-12/D-13/D-15's "detect in Phase 1, convert in Phase 2" scope, not the roadmap SC3 wording literally). A constructed uniform-3-digit column (`1,234` / `5,678`) still returns a `StructureQuestion`, never a silent guess, for both CSV and Excel paths. |
| 4 | Multi-sheet workbook auto-selects its data sheet or hesitates when genuinely tied; wide/transposed/multi-table shapes detected and refused rather than mapped wrong (SC4, PARSE-04/05, D-09/D-10/D-11) | ✓ VERIFIED | Live, all 13 Excel fixtures re-run against `parse()`: `meridian_cro_codes.xlsx` → `DATA` sheet auto-selected (LEGEND skipped). `orion_pk_report.xlsx` / `delta_screening_per_target.xlsx` → `StructureQuestion` (genuinely tied, per D-09's documented empirical finding — correct hesitation, not a bug). `apex_labs_wide_matrix.xlsx` → question naming `wide_matrix`. `bionexus_transposed.xlsx` → question naming `transposed`. `triton_screening_two_tables.xlsx` → question naming `multiple_tables`. `vantage_pk_with_chart.xlsx` (embedded chart) and `nimbus_labs_chartsheet.xlsx` (chartsheet) both resolve to a normal RawTable — no disqualification (D-16/D-17). `quantex_scanned_report.xlsx` (image-only) → `StructureQuestion`, never "no data rows" (D-18). **No regression from the new Excel locale gate:** every previously-clean Excel fixture still parses clean; no fixture newly asks a locale question it should not (checked all 13 `.xlsx` files across every sheet). |
| 5 | Unfamiliar structure triggers a structural-hint request instead of crashing/garbage; the tool proceeds using the hint for that run, INCLUDING via the actual shipped CLI (SC5, PARSE-06, D-05/D-06/D-08) | ✓ VERIFIED (gap closed) | "Never crash/garbage" fully verified across every hazard type (full suite: 143 passed, 1 skipped). **"Proceeds using the hint" (the closed gap), verified live end-to-end through the actual `assayingest` CLI, credentials unset:** `assayingest ambiguous.csv` → exit 4 ("structure unresolved") printing `To proceed, re-run with: --hint decimal=,`; `assayingest ambiguous.csv --hint decimal=,` → exit **3** ("structure resolved, no credentials") — the CSV decimal-separator hint now resolves. Same live transition confirmed for the Excel sheet-selection hint: `assayingest zephyr_bio_ZB-2025.xlsx` → exit 4; `assayingest zephyr_bio_ZB-2025.xlsx --hint "sheet=Week 1"` → exit 3. `--hint delimiter=\|` and `--hint header-row=N` also wired (`_hint_from_args`/`_HINT_KEYS`, unit-verified and code-reviewed). A malformed `--hint colour=blue` raises `ValueError` and exits 2, distinct from a structural question (D-05). |

**Score:** 5/5 truths verified. Both previously-partial criteria (3 and 5) are now fully verified for both the CSV and Excel paths, and for the real CLI, not only for direct Python `parse()` calls.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/parsing/hint.py` | `StructuralHint`/`StructureQuestion`/`TableShape`/`NumericLocale`, JSON round-trippable, stdlib-only | ✓ VERIFIED | No `anthropic`/`pandas` import (grep-confirmed). Live round-trip: `StructuralHint(**hint.to_dict()) == hint`. `answerable_by_hint` field added (D-11-adjacent) for the unsupported-shape question. |
| `src/assayingest/parsing/structure/delimiter.py` | `read_csv_grid()` immune to `csv.Sniffer` comment-line trap, now accepts an optional `delimiter` override | ✓ VERIFIED | pinnacle → 7 columns/14 rows unchanged; `--hint delimiter=\|` test (`test_csv_hint_forces_the_delimiter`) and live piped-CSV check both pass. |
| `src/assayingest/parsing/structure/locale.py` | `classify_column()`/`annotate_columns()`, D-14 ambiguity rule, plus `locale_from_separator()`/`resolve_ambiguity()` for hint resolution | ✓ VERIFIED and WIRED | Pure module (no pandas/anthropic import, grep-confirmed). Now called from **both** `parse()` branches via the shared `_resolve_locales_or_ask()` helper — verified live against `helix_genomics_DE.xlsx` (Excel) and `pinnacle_labs_export.csv` (CSV). |
| `src/assayingest/parsing/table.py` | Shared `_resolve_locales_or_ask()`; `_parse_csv_structurally(path, hint)` threading the hint; `_raw_table_from_header_row(...)` annotating locales | ✓ VERIFIED | Read in full; both branches call the same helper — no duplicated ambiguity-gate logic, no path that can build a `RawTable` skipping the locale annotation. |
| `src/assayingest/cli.py` | `--hint KEY=VALUE` (repeatable), `_hint_from_args()`, "To proceed, re-run with: …" affordance suppressed when unhelpful | ✓ VERIFIED and WIRED | Live CLI runs confirm exit 4 → exit 3 transition for both CSV (`decimal`) and Excel (`sheet`) hints; `apex_labs_wide_matrix.xlsx` (unsupported shape) correctly prints "no structural hint resolves it" and omits the "re-run with" line. |
| `data/synthetic/*` fixtures (14 total, incl. drawing/shape set) | Present, regenerable, documented | ✓ VERIFIED | All 14 corpus files present and exercised live in this verification pass, plus new synthetic files added to the repo since (`apex_labs_wide_matrix.xlsx`, `bionexus_transposed.xlsx`, etc. — same set as before). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `table.parse()` (CSV) | `structure/delimiter.py` + `structure/locale.py` | direct call, `hint` threaded through | ✓ WIRED | Live: `parse(csv, hint=StructuralHint(decimal_separator=","))` resolves the ambiguity question to a `RawTable`; `parse(csv, hint=StructuralHint(delimiter="\|"))` overrides sniffing. |
| `table.parse()` (Excel) | `structure/grid.py`, `structure/header.py`, `structure/sheets.py`, `structure/shape.py`, `structure/locale.py` | direct call | ✓ WIRED (previously gap 1: locale.py NOT wired — now closed) | Live: `helix_genomics_DE.xlsx`'s `column_locales` now populated (`decimal_comma` for `Konz. (µM)`) via the shared `_resolve_locales_or_ask()` call inside `_raw_table_from_header_row()`. |
| `table.parse()`'s `hint` param | `_parse_csv_structurally()` (`decimal_separator`, `delimiter`) | direct param | ✓ WIRED (previously gap 2 — now closed) | Live: parameter is no longer dropped; both dimensions verified end-to-end. |
| Human/CLI user | `parse()`'s `hint` param | `--hint` CLI flag | ✓ WIRED (previously not wired at all — now closed) | Live: `assayingest <file> --hint decimal=,` and `--hint "sheet=Week 1"` both drive exit 4 → 3. `_hint_from_args()` parses repeated `key=value` flags into a `StructuralHint`. |
| `cli.py::run()` | `_ask_and_report()` | `isinstance(outcome, StructureQuestion)` branch | ✓ WIRED | Unchanged from prior verification; still routes correctly through the now-hint-aware `resolve_or_ask()`. |
| `cli.py::_ask_and_report()` | `structure_assist.propose_structure()` (via `_enrich_question`) | injectable-client seam | ✓ WIRED, advisory-only | Re-confirmed: `_enrich_question` only ever does `dataclasses.replace(question, proposal=proposal)` — never resolves/applies (D-02 upheld); degrades gracefully with no client/credentials. |

### Data-Flow Trace (Level 4)

Not applicable in the strict "renders dynamic data to a UI" sense (this is a library + CLI, no frontend yet). The equivalent trace performed: `RawTable.column_locales` is populated by a real column-scan (`annotate_columns`) reading the actual parsed cell values, not a static/empty default, for both the CSV and Excel sources — confirmed live for `helix_genomics_DE.xlsx` (`decimal_comma` correctly assigned to the one column that has it, `non_numeric`/`decimal_point` correctly assigned elsewhere, not a blanket value).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite | `uv run pytest -q` | `143 passed, 1 skipped` | ✓ PASS (matches expected count exactly) |
| `openpyxl.DEFUSEDXML` closed (XXE) | `uv run python -c "import openpyxl; print(openpyxl.DEFUSEDXML)"` | `True` | ✓ PASS |
| Pillow stays dev-only | `grep -rn "import PIL\|from PIL" src/` | (no output) | ✓ PASS |
| `anthropic` isolated to `structure_assist.py` | `grep -rln "import anthropic" src/assayingest/parsing/` | only `structure_assist.py` | ✓ PASS (D-04 re-confirmed) |
| Excel decimal-comma annotation (the closed gap) | `parse("helix_genomics_DE.xlsx").column_locales` | `Konz. (µM)` → `decimal_comma`; row value stays `"14,771"` | ✓ PASS |
| CSV decimal-separator hint resolves (the closed gap) | `parse(ambiguous_csv, hint=StructuralHint(decimal_separator=","))` | `RawTable` returned, `column_locales[1] == "decimal_comma"` | ✓ PASS |
| CLI hint resolves structure end-to-end (the closed gap) | `assayingest ambiguous.csv` then `assayingest ambiguous.csv --hint decimal=,` (creds unset) | exit `4` then exit `3` | ✓ PASS |
| CLI Excel sheet-hint resolves end-to-end | `assayingest zephyr_bio_ZB-2025.xlsx` then `... --hint "sheet=Week 1"` (creds unset) | exit `4` then exit `3` | ✓ PASS |
| No new Excel regressions from the locale gate | `parse()` on all 13 `.xlsx` fixtures, every sheet | Same clean/question outcomes as before the fix — no fixture newly asks | ✓ PASS |
| `StructuralHint`/`StructureQuestion` JSON round-trip still holds | `StructuralHint(**hint.to_dict()) == hint` | Equal | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PARSE-01 | 01-02 | Header row detected structurally beneath banner rows | ✓ SATISFIED | zephyr resolves at row 4 confidently, both auto and hinted. |
| PARSE-02 | 01-01 | CSV delimiter/comment sniffing | ✓ SATISFIED | pinnacle → 7 columns, 14 rows. |
| PARSE-03 | 01-01, 01-06 fix | Decimal-comma recognized without 1000x corruption; ambiguity flagged | ✓ SATISFIED | CSV and Excel both annotate now; gap closed and live-confirmed. |
| PARSE-04 | 01-03 | Multi-sheet data-sheet selection, obvious non-data sheets skipped | ✓ SATISFIED | meridian auto-selects DATA over LEGEND; orion/delta correctly hesitate. |
| PARSE-05 | 01-04 | Non-row-per-record shapes detected and flagged, not silently mapped | ✓ SATISFIED | apex/bionexus/triton all correctly refused. |
| PARSE-06 | 01-01..05, 01-06 fix | Unfamiliar structure asks for a hint, then proceeds using it | ✓ SATISFIED | Asking fully satisfied; "proceeds using the hint" now fully satisfied for all `StructuralHint` fields exercised in this phase's scope, through the actual shipped CLI. |

No orphaned requirements — PARSE-01..06 are exactly the six requirements REQUIREMENTS.md maps to Phase 1, and all six appear across the five plans' frontmatter plus the 01-06 gap-closure commits.

### Anti-Patterns Found

None blocking. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any file touched by the gap-closure commits (`cli.py`, `hint.py`, `structure/delimiter.py`, `structure/locale.py`, `table.py`).

**One informational (non-blocking) observation:** `StructureQuestion.to_dict()` (the CLI's printed JSON output) does not include the `answerable_by_hint` field — the CLI's human-readable text rendering (`_render_answer_hint`) reads `answerable_by_hint` directly off the Python object and correctly suppresses the "re-run with" affordance for unsupported shapes, so today's CLI behavior is correct end-to-end. But the raw JSON blob a future API/browser client (Phase 4, D-06/D-07's "no CLI-only representation") would receive is missing this signal. This is forward-looking scope, not a Phase 1 success criterion, and was not one of the two closed gaps — noted for awareness, not a blocker.

### Human Verification Required

None. Every truth in this phase is programmatically verifiable (library/CLI behavior, no UI, no visual/real-time behavior); the fix was verified independently by direct execution (not merely by reading the test file), including live end-to-end CLI runs with credentials unset.

## Gaps Summary

Both gaps from the prior verification are closed, confirmed by independent live execution — not by re-reading the SUMMARY.md or trusting the test suite's self-report alone:

1. **Excel locale annotation (gap 1, Criterion 3/PARSE-03) — CLOSED.** `_resolve_locales_or_ask()` is now called from both `parse()` branches. Live: `parse("helix_genomics_DE.xlsx")` — the canonical fixture the original gap named — now returns `column_locales` with `Konz. (µM)` correctly `decimal_comma`, and the cell value is confirmed to remain the unconverted string `"14,771"` (correct per D-12/D-15's detect-only scope for Phase 1). Re-ran every Excel fixture in the corpus (13 files, all sheets) to confirm the new locale gate introduces no regression — no previously-clean fixture now asks a question it should not.

2. **CSV hint threading + CLI hint mechanism (gap 2, Criterion 5/PARSE-06) — CLOSED.** `_parse_csv_structurally()` now accepts and honors `hint.decimal_separator`/`hint.delimiter`; `parse()`'s CSV branch no longer drops the hint. The CLI gained a repeatable `--hint KEY=VALUE` flag (`header-row`, `sheet`, `delimiter`, `decimal`) wired through `run()`/`resolve_or_ask()`/`parse()`. Live-verified end-to-end through the actual `assayingest` command (not just direct `parse()` calls): `assayingest ambiguous.csv` exits 4 ("structure unresolved"), and `assayingest ambiguous.csv --hint decimal=,` exits 3 ("structure resolved, no credentials") — the same transition independently confirmed for the pre-existing Excel `sheet` hint, proving no regression there either.

No remaining gaps against the roadmap's 5 success criteria. All 6 requirements (PARSE-01..06) are satisfied. The three-layer structure-resolution pipeline (D-01: deterministic → Claude proposal → human confirmation) is intact and D-02 (Claude never auto-applies) is re-confirmed structurally — `_enrich_question` only ever does `dataclasses.replace(question, proposal=proposal)`. D-04 (parsing/`structure/*` never imports `anthropic`) and D-11 (no shape-warning field on `RawTable`, no "parse anyway" path) are both re-confirmed against current source, not assumed from the prior report.

---

*Verified: 2026-07-10*
*Verifier: Claude (gsd-verifier)*

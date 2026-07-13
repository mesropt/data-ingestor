---
phase: 11-multi-sheet-ingest
plan: 03
subsystem: export
tags: [provenance, canonical, writers, csv, xlsx, json, manifest, sheet-03]

# Dependency graph
requires:
  - phase: 02-canonical-export
    provides: "canonical.assemble() + the three writers + build_manifest — the export path this plan threads provenance through"
  - phase: 04-api
    provides: "UploadEntry.source_file_name (the client's real filename) + the /api/confirm route"
provides:
  - "RawTable.origin_sheet — the worksheet title, recorded on EVERY Excel parse (None for CSV)"
  - "canonical.SOURCE_SHEET_COLUMN ('__source_sheet') — the reserved export meta column"
  - "CanonicalTable.record_sources — per-row provenance, parallel to records, never a record key"
  - "assemble(*, source_sheet=None) — keyword-only, defaulted; CLI and validator call sites untouched"
  - "write_csv / write_xlsx / write_json / build_manifest all thread the reserved column deliberately"
  - "service.confirm(*, source_label=None) + the confirm route wiring — provenance on every ingest"
affects: [11-04-schema-scorer, 11-07-run-group, group-export]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reserved meta column: a __-prefixed export column that is NOT a Field, so FieldSet.signature never moves"
    - "Parallel-list provenance: record_sources beside records, so no writer sees an unexpected record key"
    - "Manifest reads provenance off the same CanonicalTable the writers wrote — audit trail cannot disagree with the data"

key-files:
  created:
    - tests/test_origin_sheet.py
    - tests/test_canonical_provenance.py
    - tests/api/test_provenance_export.py
  modified:
    - src/assayingest/parsing/table.py
    - src/assayingest/canonical.py
    - src/assayingest/export/writers.py
    - src/assayingest/service.py
    - src/assayingest/api/routes/confirm.py
    - src/assayingest/api/state.py
    - tests/test_export_writers.py
    - tests/api/test_state.py

key-decisions:
  - "source_sheet is a reserved export meta column (__source_sheet), never a Field in the FieldSet — a Field would change FieldSet.signature and silently invalidate every learned profile (D-11-13)"
  - "Provenance rides a parallel list (record_sources), never a key inside records — write_csv's DictWriter RAISES on an extra key, write_xlsx SILENTLY DROPS it, write_json keeps it (D-11-14)"
  - "The provenance VALUE is `table.origin_sheet or source_label`, never RawTable.source_name — on the API path source_name is a tempfile's generated name (T-11-09)"
  - "origin_sheet is a NEW field, not a widening of sheet_name: sheet_name composes into RawTable.label, the text the Claude prompt and CLI banner print, and must not change for single-sheet workbooks (rejected option P-B)"
  - "service.export reads source_sheet off the same CanonicalTable the writers wrote, rather than re-deriving it — so the manifest can never claim one source while the data files ship another"

patterns-established:
  - "Additive-defaulted evolution: every new contract (origin_sheet, record_sources, source_sheet, source_label) is keyword-only/defaulted, so untouched call sites are byte-identical"
  - "Persistence .get() idiom extended: a pending_uploads row written before origin_sheet existed still rehydrates"

requirements-completed: [SHEET-03]

coverage:
  - id: D1
    description: "Every parsed Excel table records its worksheet title (RawTable.origin_sheet), set unconditionally — a one-sheet workbook records its sheet too; a CSV records None"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/test_origin_sheet.py#test_one_sheet_workbook_records_origin_sheet_but_leaves_sheet_name_none"
        status: pass
      - kind: unit
        ref: "tests/test_origin_sheet.py#test_multi_sheet_explicit_sheet_records_that_sheets_title_as_origin"
        status: pass
      - kind: unit
        ref: "tests/test_origin_sheet.py#test_csv_leaves_origin_sheet_none"
        status: pass
    human_judgment: false
  - id: D2
    description: "RawTable.label — the text the Claude mapper prompt and the CLI banner print — is unchanged for a CSV and a one-sheet workbook"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/test_origin_sheet.py#test_label_unchanged_for_a_one_sheet_workbook"
        status: pass
      - kind: unit
        ref: "tests/test_origin_sheet.py#test_label_unchanged_for_a_csv"
        status: pass
      - kind: unit
        ref: "tests/test_excel_sheets.py#test_resolve_tables_single_csv"
        status: pass
    human_judgment: false
  - id: D3
    description: "The provenance never becomes a Field: FieldSet.signature is unchanged and no learned profile stops matching (T-11-10)"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/test_canonical_provenance.py#test_records_never_gain_a_source_sheet_key_in_either_case"
        status: pass
      - kind: unit
        ref: "tests/test_signature.py"
        status: pass
      - kind: unit
        ref: "tests/test_profile_store.py"
        status: pass
      - kind: integration
        ref: "tests/api/test_money_shot.py#test_upload_confirm_reupload_money_shot_zero_yellow_one_claude_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "All three writers + the manifest thread the reserved __source_sheet column: write_csv does not raise, write_xlsx does not drop, write_json does not diverge"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/test_export_writers.py#test_write_csv_appends_the_reserved_source_sheet_column_and_does_not_raise"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py#test_write_xlsx_carries_the_source_sheet_in_its_header_row_and_every_row"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py#test_write_json_emits_the_source_sheet_on_every_record_with_unicode_intact"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py#test_build_manifest_records_the_source_sheet_and_defaults_it_to_none"
        status: pass
    human_judgment: false
  - id: D5
    description: "With no provenance set, every writer's output is byte-identical to today (the CLI path and the validator are untouched)"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/test_export_writers.py#test_write_csv_without_record_sources_is_byte_identical_to_today"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py#test_write_xlsx_without_record_sources_is_byte_identical_to_today"
        status: pass
      - kind: unit
        ref: "tests/test_canonical_provenance.py#test_flagged_is_identical_with_and_without_a_source_sheet"
        status: pass
    human_judgment: false
  - id: D6
    description: "Provenance reaches the downloaded file on EVERY ingest, CSV included (D-11-15), valued with the client's real file name — never a tempfile name (T-11-09)"
    requirement: SHEET-03
    verification:
      - kind: integration
        ref: "tests/api/test_provenance_export.py#test_a_confirmed_csv_export_carries_source_sheet_in_all_three_formats"
        status: pass
      - kind: integration
        ref: "tests/api/test_provenance_export.py#test_the_exported_source_sheet_is_never_a_tempfile_name"
        status: pass
      - kind: integration
        ref: "tests/api/test_provenance_export.py#test_the_manifest_records_the_same_source_sheet_as_the_data"
        status: pass
      - kind: manual_procedural
        ref: "Confirmed a CSV through the real API (TestClient) and opened the exported CSV — last column is __source_sheet, valued novascreen_batch01.csv on every row"
        status: pass
    human_judgment: false
  - id: D7
    description: "origin_sheet survives a server restart: it round-trips through the pending_uploads persistence, and a row persisted BEFORE the key existed still rehydrates"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "tests/api/test_state.py#test_entry_json_round_trip_preserves_the_tables_origin_sheet"
        status: pass
      - kind: unit
        ref: "tests/api/test_state.py#test_a_row_persisted_before_origin_sheet_existed_still_rehydrates"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-07-13
status: complete
---

# Phase 11 Plan 03: Row Provenance (SHEET-03) Summary

**Every exported row now records the sheet it came from — as a reserved `__source_sheet` meta column threaded deliberately through all three writers and the manifest, never as a `Field` in the `FieldSet`, so `FieldSet.signature` never moves and no learned profile stops matching.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-13T06:50:09Z
- **Completed:** 2026-07-13T07:07:57Z
- **Tasks:** 3 (all TDD: RED → GREEN)
- **Files modified:** 11 (6 source, 5 test — 3 test files new)

## Accomplishments

- **`RawTable.origin_sheet`** — the worksheet title, recorded on *every* Excel parse (a one-sheet workbook records its sheet too; a CSV records `None`). Deliberately a **new** field rather than a widening of `sheet_name`: `sheet_name` composes into `RawTable.label`, the text the Claude prompt and the CLI banner print, and widening it would have silently rewritten the mapper's prompt for every single-sheet workbook (the rejected option P-B).
- **`CanonicalTable.record_sources` + `assemble(*, source_sheet=None)`** — per-row provenance carried as a list *parallel* to `records`, never as a key inside one. The keyword is defaulted precisely so the two other `assemble` call sites (`cli.py`, `validation/validator.py`) are behaviourally untouched — `validator.py` has a zero-line diff.
- **All three writers + `build_manifest`** thread the reserved column on purpose. This is the trap the plan existed to close: an extra key smuggled into `records` behaves *three different ways* — `write_csv`'s `DictWriter` **raises**, `write_xlsx` **silently drops** it, `write_json` **keeps** it. Each writer now opts in through one shared `_export_columns`/`_rows_with_sources` pair, and every writer's output is **byte-identical to today** when there is no provenance.
- **Provenance on EVERY ingest (D-11-15), CSV included.** The value is `table.origin_sheet or source_label` — the worksheet title when there is one, the client's real filename when there is not. Verified end to end by confirming a CSV through the real API and opening the downloaded file.

## Task Commits

Each task was committed atomically, RED then GREEN (TDD):

1. **Task 1: `RawTable.origin_sheet`** — `4dd3e69` (test, RED) → `5178b14` (feat, GREEN)
2. **Task 2: `CanonicalTable.record_sources` + `assemble(source_sheet=)`** — `bd7208a` (test, RED) → `1bf54cd` (feat, GREEN)
3. **Task 3: the three writers + the manifest + the service/route wiring** — `d837de7` (test, RED) → `71bb185` (feat, GREEN)

No REFACTOR commits were needed — each GREEN landed clean.

## Files Created/Modified

**Created:**
- `tests/test_origin_sheet.py` — `origin_sheet` set on every Excel parse; `label` pinned byte-identical (it feeds the Claude prompt)
- `tests/test_canonical_provenance.py` — the reserved column cannot collide; `records` never gains the key; `flagged` cannot shift
- `tests/api/test_provenance_export.py` — end to end: a CSV upload → confirm → export carries the real file name, never a tempfile name

**Modified:**
- `src/assayingest/parsing/table.py` — `RawTable.origin_sheet` (defaulted); set unconditionally in `_parse_excel_sheet` and `_raw_table_from_header_row`
- `src/assayingest/canonical.py` — `SOURCE_SHEET_COLUMN`, `CanonicalTable.record_sources`, `assemble(*, source_sheet=None)`
- `src/assayingest/export/writers.py` — `_export_columns` / `_rows_with_sources`; all three writers + `build_manifest(source_sheet=None)`
- `src/assayingest/service.py` — `confirm(*, source_label=None)`; `export` reads the manifest's source off the same `tidy` the writers wrote
- `src/assayingest/api/routes/confirm.py` — passes `source_label=entry.source_file_name`
- `src/assayingest/api/state.py` — `origin_sheet` persisted through `_entry_to_json` / `_entry_from_json` with the `.get()` idiom
- `tests/test_export_writers.py` — added the provenance section (every pre-existing assertion untouched; the only deletion in the diff is the import line)
- `tests/api/test_state.py` — `origin_sheet` persistence round-trip + the old-row rehydration guard

## Decisions Made

- **The manifest reads its `source_sheet` off the `CanonicalTable` the writers wrote, rather than re-deriving it from the `RawTable`.** The plan said "`export(...)` passes `source_sheet` through to `build_manifest`"; reading it off the `tidy` (which already carries exactly the value `confirm` resolved) is what *guarantees* the audit trail cannot claim one source while the data files ship another. This is the same discipline `value_source` already enforces between the manifest and the data, and it left all four existing `service.export` call sites unchanged. **Known limit:** a zero-row table has `record_sources == []`, so its manifest records `source_sheet: null` — vacuous (there are no rows to trace), but worth naming.
- **`_export_columns` / `_rows_with_sources` extracted as a shared pair** rather than inlining the opt-in three times. The three writers disagree about an unexpected key, so the *decision* about which columns exist belongs in one function that all three read.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules fired; no auto-fixes were needed.

## Issues Encountered

None. Every RED failed for the intended reason and every GREEN passed first time.

## Threat Model Notes

- **T-11-08 (formula injection via a worksheet title / filename in the provenance cell) — pre-existing, NOT widened.** The threat register asked me to check whether the existing writers apply formula escaping and, if not, to say so rather than silently widen the surface. **They do not:** `write_csv` uses a plain `csv.DictWriter` and `write_xlsx` a plain `openpyxl` `append` — neither escapes a leading `=`/`+`/`-`/`@`. This is a **pre-existing, phase-wide** property: *every* cell value from an uploaded file already reaches a downloaded export unescaped, and has since Phase 2. The provenance column adds **no new interpolation** — it goes through the identical writer path as every other cell, and no filename is ever built into a formula or a path. Flagging it here as a phase-wide concern for a dedicated hardening pass, not as a regression introduced by this plan.
- **T-11-09 (tempfile path leaking into an export) — mitigated and pinned.** The provenance value is `table.origin_sheet or entry.source_file_name`, never `RawTable.source_name` (a tempfile's generated name on the API path). Guarded by `test_the_exported_source_sheet_is_never_a_tempfile_name`.
- **T-11-10 (learned profiles silently invalidated) — mitigated by construction.** The provenance is never a `Field`; `FieldSet.signature` is not recomputed. `tests/test_signature.py`, `tests/test_profile_store.py` and `tests/api/test_money_shot.py` all pass **unmodified**.

## Verification

- `uv run pytest tests/ -q` → **965 passed, 4 skipped** (was 950 before this plan; +15 new tests, 0 regressions).
- Every "MUST keep passing UNCHANGED" file is green and has a **zero-line diff**: `src/assayingest/validation/validator.py`, `tests/test_canonical.py`, `tests/test_canonical_dates.py`, `tests/test_validator*.py`, `tests/test_signature.py`, `tests/test_profile_store.py`, `tests/api/test_money_shot.py`, `tests/api/test_upload.py`, `tests/api/test_confirm_*.py`.
- **Manual (the plan's own check):** confirmed `novascreen_batch01.csv` through the real API and opened the exported CSV. Last column is `__source_sheet`, valued `novascreen_batch01.csv` on all 12 rows; `manifest.json` agrees.
- No live Anthropic call was made from any test (`propose_mapping` is monkeypatched throughout).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **11-04 (the Schema scorer)** and **11-07 (the run group)** can build on this: `RawTable.origin_sheet` is populated for every sheet a future per-sheet `parse(path, sheet=X)` produces, so an N-member run group gets correct per-member provenance with no further work in the canonical/writer layer.
- **Scope boundary worth knowing (as the plan specified):** the **CLI** export path still writes no provenance — `cli.py`'s own direct `canonical.assemble(table, proposal, field_set)` call was deliberately left untouched (plan Task 3, item 4), so a CLI export's `record_sources` is empty and its writers emit nothing extra. D-11-15's "every ingest" is satisfied on the **API** path, which is the product surface. If the CLI should also carry provenance, that is a one-line change (`source_sheet=table.origin_sheet`) and a deliberate decision, not an oversight.

## Self-Check: PASSED

- Created files exist: `tests/test_origin_sheet.py`, `tests/test_canonical_provenance.py`, `tests/api/test_provenance_export.py` — all FOUND.
- Commits exist: `4dd3e69`, `5178b14`, `bd7208a`, `1bf54cd`, `d837de7`, `71bb185` — all FOUND in `git log`.
- Artifact greps: `record_sources` in `canonical.py` (5 ≥ 3); `SOURCE_SHEET_COLUMN` in `export/writers.py`; `origin_sheet` in `parsing/table.py`; `source_sheet=` in `service.py`; `source_file_name` in `api/routes/confirm.py` — all present.
- Full suite green: 965 passed, 4 skipped.

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

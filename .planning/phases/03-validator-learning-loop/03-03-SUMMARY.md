---
phase: 03-validator-learning-loop
plan: 03
subsystem: export
tags: [csv, openpyxl, json, provenance-manifest, privacy, cli]

# Dependency graph
requires:
  - phase: 03-validator-learning-loop
    provides: "03-01's _resolve_proposal(table, field_set, store) returning (proposal, provenance) -- the value threaded verbatim into the export manifest, never re-derived"
  - phase: 03-validator-learning-loop
    provides: "03-02's validate()/is_ready gate wired into _map_one before any print -- the same gate --export reuses"
  - phase: 02-user-defined-fields-dynamic-mapper
    provides: "canonical.assemble()'s CanonicalTable (D-15), the single source every writer serialises"
provides:
  - "export/writers.py: write_csv/write_xlsx/write_json (CanonicalTable -> file) + build_manifest (EXPORT-02/03/04)"
  - "--export/-o DIR CLI flags: writes CSV+.xlsx+JSON+manifest.json only when proposal.is_ready, default dir beside the source file (D-09/P1)"
  - "--headers-only CLI flag + mapper.propose_mapping(..., headers_only=)/_render_table(..., headers_only=): the sample-rows block is skipped entirely, zero data values sent to Anthropic (D-10/P2)"
affects: [04-fastapi-react-review-ui, 05-demo-assets]

# Tech tracking
tech-stack:
  added: []  # stdlib only (csv/json/pathlib/datetime) + openpyxl's WRITE API (already a dependency, first write use)
  patterns:
    - "Every writer takes only a canonical.CanonicalTable, never re-derives records from a RawTable/MappingProposal (D-15 reuse, no duplication)"
    - "build_manifest reuses learning.reconstruct.stored_mapping_from + learning.signature.column_signature -- the identical save-time functions the learning loop already established -- as its per-field base, rather than inventing a second notion of 'this field's resolved column'"
    - "_export_if_ready mirrors _save_profile_if_ready's shape exactly (a guard on is_ready, a status line with _GREEN/_YELLOW) -- the same 'explicit human command, gated, transparent' idiom used twice now"
    - "headers_only is one branch inside _render_table (the single 6-row send site) -- privacy is a data-shape decision at the send site, not a separate code path duplicated elsewhere"

key-files:
  created:
    - src/assayingest/export/__init__.py
    - src/assayingest/export/writers.py
    - tests/test_export_writers.py
    - tests/test_export_cli.py
    - tests/test_headers_only.py
  modified:
    - src/assayingest/cli.py
    - src/assayingest/mapping/mapper.py
    - tests/test_canonical.py
    - tests/test_cli_run.py
    - tests/test_learning_loop_cli.py
    - tests/test_validator_cli.py

key-decisions:
  - "build_manifest(field_set, headers, proposal, *, provenance, strictness) takes headers: list[str] rather than a RawTable or a LearnedProfile -- mirrors learning.reconstruct.stored_mapping_from's own signature exactly, keeping export/writers.py decoupled from parsing.table.RawTable"
  - "Export filenames are fixed (export.csv/export.xlsx/export.json/manifest.json) inside the resolved DIR -- CONTEXT.md/RESEARCH.md left naming to discretion; a multi-sheet workbook exporting more than one table into the same DIR would overwrite these (out of scope: v1's export path is single-table per invocation, matching the money-shot demo)"
  - "--export is a store_true flag; -o/--output-dir is a separate optional path flag (default: beside the source file) -- chosen over a single --export [DIR] nargs='?' flag to avoid argparse's ambiguity when a bare --export is immediately followed by another flag like --headers-only"
  - "headers_only reaches propose_mapping only on _resolve_proposal's fresh-Claude miss branch, never the auto-apply hit branch -- not a separate check, a structural consequence of Pattern 5 (the auto-apply path never calls propose_mapping at all)"

patterns-established:
  - "export/ package: one infra module (writers.py, first file-WRITE code + first openpyxl write use in the project), mirroring the learning/validation package layout"
  - "Fixed manifest field-entry shape: StoredFieldMapping.to_dict() as the base dict, confidence/confirmed appended -- the same 'base dict + extra keys' idiom cli.py::_field_to_dict already uses"

requirements-completed: [EXPORT-02, EXPORT-03, EXPORT-04]

coverage:
  - id: D1
    description: "write_csv/write_xlsx/write_json serialise a CanonicalTable to CSV/.xlsx/JSON; None becomes an empty CSV cell automatically; xlsx is openpyxl-reopenable; JSON is exactly tidy.records; Unicode unit symbols (µM) survive every format unescaped (EXPORT-02/03)"
    requirement: "EXPORT-02"
    verification:
      - kind: unit
        ref: "tests/test_export_writers.py::test_write_csv_header_row_is_field_names_and_none_becomes_empty_string"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py::test_write_xlsx_is_reopenable_with_field_names_header_and_record_values"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py::test_write_json_is_exactly_the_records_array_with_unicode_preserved"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_manifest reuses LearnedProfile.to_dict()'s field-mapping shape (via StoredFieldMapping) as its base, plus per-field confidence/confirmed, provenance, strictness, and exported_at -- the manifest is fully JSON-serialisable with ensure_ascii=False (EXPORT-04, D-09)"
    requirement: "EXPORT-04"
    verification:
      - kind: unit
        ref: "tests/test_export_writers.py::test_build_manifest_shares_the_saved_profile_shape_plus_provenance_strictness_and_exported_at"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py::test_build_manifest_records_auto_applied_provenance_given_an_auto_applied_proposal"
        status: pass
      - kind: unit
        ref: "tests/test_export_writers.py::test_build_manifest_is_json_serialisable_with_unicode_preserved"
        status: pass
    human_judgment: false
  - id: D3
    description: "--export writes CSV/.xlsx/JSON/manifest.json only when proposal.is_ready; a blocked (yellow) mapping writes nothing and stays exit 5; default output dir is beside the source file when -o is omitted; a normal run with no --export flag writes no export files at all (D-09/P1)"
    requirement: "EXPORT-02"
    verification:
      - kind: unit
        ref: "tests/test_export_cli.py::test_export_blocked_on_a_not_ready_mapping_writes_nothing_and_stays_exit_5"
        status: pass
      - kind: unit
        ref: "tests/test_export_cli.py::test_export_writes_exactly_csv_xlsx_json_and_manifest_when_ready"
        status: pass
      - kind: unit
        ref: "tests/test_export_cli.py::test_export_default_output_dir_is_beside_the_source_file"
        status: pass
      - kind: unit
        ref: "tests/test_export_cli.py::test_no_export_flag_writes_no_export_files_at_all"
        status: pass
    human_judgment: false
  - id: D4
    description: "The manifest records the run's actual provenance -- fresh-claude vs auto-applied-from-profile (the value _resolve_proposal already returns, never re-derived) -- and the run's strictness (D-08/D-11)"
    requirement: "EXPORT-04"
    verification:
      - kind: unit
        ref: "tests/test_export_cli.py::test_manifest_records_fresh_claude_provenance_and_strictness"
        status: pass
      - kind: unit
        ref: "tests/test_export_cli.py::test_manifest_records_auto_applied_provenance_on_a_profile_hit"
        status: pass
    human_judgment: false
  - id: D5
    description: "--headers-only renders the column list and locale evidence but skips the entire sample-rows block -- a distinctive cell value is provably absent from the Claude request; the default path is byte-for-byte unchanged (existing mapper tests unaffected); the CLI thread only reaches propose_mapping's fresh-Claude branch (D-10/P2)"
    requirement: "EXPORT-02"
    verification:
      - kind: unit
        ref: "tests/test_headers_only.py::test_headers_only_renders_headers_but_no_sample_rows_or_values"
        status: pass
      - kind: unit
        ref: "tests/test_headers_only.py::test_headers_only_keeps_locale_evidence_lines"
        status: pass
      - kind: unit
        ref: "tests/test_headers_only.py::test_propose_mapping_headers_only_kwarg_reaches_render_request"
        status: pass
      - kind: unit
        ref: "tests/test_headers_only.py::test_cli_headers_only_flag_threads_into_propose_mapping"
        status: pass
      - kind: unit
        ref: "tests/test_mapper_boundary.py -- full file, regression guard"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-07-10
status: complete
---

# Phase 3 Plan 3: Export + Privacy Mode Summary

**CSV/`.xlsx`/JSON export from the one Phase 2 canonical table, each run gated on `proposal.is_ready` and accompanied by a JSON manifest (field set, column signature, field→source mapping, per-field confidence/confirmed, provenance, strictness), plus a `--headers-only` privacy flag that skips the mapper's entire sample-rows block so zero data values reach Anthropic.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-10T20:48:52+04:00
- **Completed:** 2026-07-10T20:59:29+04:00
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- `export/writers.py::write_csv`/`write_xlsx`/`write_json` turn a `canonical.CanonicalTable` into three files -- `write_xlsx` is this project's first use of `openpyxl`'s WRITE API (it has only ever read Excel until now); `write_csv`'s `csv.DictWriter` writes a missing/`None` cell as `""` automatically; every writer is `ensure_ascii=False` so a unit symbol like µM survives unescaped in every format.
- `build_manifest` shares its field-entry shape with `LearnedProfile.to_dict()` by reusing `learning.reconstruct.stored_mapping_from`/`learning.signature.column_signature` directly -- the exact save-time functions the learning loop (03-01) already established -- then appends `confidence`/`confirmed` per field plus `provenance`/`strictness`/`exported_at`.
- `--export`/`-o DIR` wired into `cli.py::run()`/`_map_and_report`/`_map_one`: `_export_if_ready` mirrors `_save_profile_if_ready`'s exact shape (guard on `is_ready`, a `_GREEN`/`_YELLOW` status line) -- a blocked (yellow) mapping writes nothing and stays exit 5; a ready mapping writes exactly `export.csv`/`export.xlsx`/`export.json`/`manifest.json` into the resolved directory (default: beside the source file); a normal run with no `--export` flag writes no files at all, verified with an explicit file-absence assertion, not just "the test didn't check".
- `--headers-only` (D-10, P2, the privacy feature the builder wants highlighted for judges): `_render_table`'s `headers_only=True` branch stops after the `Columns (...)` line and locale-evidence lines, skipping the "First N of M rows" block and every value in it entirely -- proven with a `_FakeClient` capturing the exact request `content` string and asserting a distinctive cell value is absent. The CLI thread reaches `propose_mapping` only on `_resolve_proposal`'s fresh-Claude miss branch; the auto-apply hit branch already sends nothing to Claude at all (Pattern 5), so the flag is a no-op there by construction.
- Manual end-to-end smoke test (`--export` + `--headers-only` together, novascreen_batch01.csv, a monkeypatched Claude call): exit 0, `manifest.json`/`export.csv`/`export.xlsx`/`export.json` all present, `provenance: "fresh-claude"`, `strictness: "strict"` -- the money-shot the CLI now supports end to end.

## Task Commits

Each task followed the TDD RED -> GREEN cycle (MVP+TDD mode: `test(...)` then `feat(...)`):

1. **Task 1: Export writers + manifest builder** -- `44a76e2` (test), `a914c65` (feat)
2. **Task 2: `--export`/`-o` CLI wiring with the is_ready gate** -- `efef6e5` (test), `c35415e` (feat)
3. **Task 3: `--headers-only` privacy branch** -- `634f4ba` (test), `23251d7` (feat)

_No refactor commits were needed -- each GREEN implementation passed on the first pass (Task 3's GREEN commit also carries a scoped, foreseen test-fixture fix -- see Deviations)._

## Files Created/Modified
- `src/assayingest/export/__init__.py` - empty package marker
- `src/assayingest/export/writers.py` - `write_csv`/`write_xlsx`/`write_json`/`build_manifest`
- `src/assayingest/cli.py` - `_export_if_ready`, `_resolve_export_dir`; `run()`/`_map_and_report`/`_map_one`/`_resolve_proposal` threaded with `export`/`output_dir`/`headers_only`; `--export`/`-o`/`--headers-only` argparse flags
- `src/assayingest/mapping/mapper.py` - `propose_mapping`/`_render_request`/`_render_table` accept `headers_only`; the sample-rows block is now a conditional branch, not unconditional
- `tests/test_export_writers.py` - new, 6 tests (writers + manifest)
- `tests/test_export_cli.py` - new, 7 tests (gate, default dir, provenance/strictness, no-implicit-write, argparse)
- `tests/test_headers_only.py` - new, 8 tests (render branch, propose_mapping threading, CLI wiring, argparse)
- `tests/test_canonical.py`, `tests/test_cli_run.py`, `tests/test_learning_loop_cli.py`, `tests/test_validator_cli.py` - existing `propose_mapping` test fakes widened to accept `**kwargs` (see Deviations)

## Decisions Made
- **`build_manifest` takes `headers: list[str]`, not a `RawTable`** -- mirrors `learning.reconstruct.stored_mapping_from`'s own signature exactly (it already takes `headers: list[str]`), keeping `export/writers.py` decoupled from `parsing.table.RawTable` and consistent with the one existing precedent for "resolve a field mapping against a file's headers".
- **`--export` is a `store_true` flag; `-o`/`--output-dir` is a separate optional path flag**, rather than a single `--export [DIR]` flag with `nargs='?'`. CONTEXT.md's Claude's Discretion note explicitly leaves CLI flag shape open; the two-flag design avoids argparse's ambiguity when a bare `--export` is immediately followed by another flag (e.g. `--export --headers-only` could otherwise be misparsed as `--export=--headers-only`).
- **Export filenames are fixed** (`export.csv`/`export.xlsx`/`export.json`/`manifest.json`) inside the resolved directory. The plan's own `<verification>` wording ("produces exactly CSV + .xlsx + JSON + manifest.json") only constrains the file *types*, not their names; fixed names keep the writer call sites simple. A multi-sheet workbook exporting more than one table into the same `DIR` would overwrite these files across sheets -- out of scope for this plan (the money-shot demo and every test fixture are single-table), noted here for Phase 4/5 awareness rather than silently left undocumented.
- **`headers_only` only ever reaches `propose_mapping` on `_resolve_proposal`'s fresh-Claude miss branch** -- not a separate `if headers_only` check gating the auto-apply branch, but a structural consequence of Pattern 5 (the auto-apply branch never calls `propose_mapping` at all, so there is nothing to gate).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Adding a `headers_only` kwarg to `propose_mapping`'s call site broke four existing test files' fake fixtures**
- **Found during:** Task 3 (`--headers-only`) GREEN run, full-suite verification
- **Issue:** `cli.py::_resolve_proposal` now unconditionally calls `propose_mapping(table, field_set, headers_only=headers_only)` on the fresh-Claude branch. Several pre-existing tests across `tests/test_canonical.py`, `tests/test_cli_run.py`, `tests/test_learning_loop_cli.py`, and `tests/test_validator_cli.py` monkeypatch `cli.propose_mapping` with fake functions declared as `lambda t, fs, client=None: ...` or `def _ready(table, field_set, client=None): ...` -- none of them accept the new keyword, so each raised `TypeError: got an unexpected keyword argument 'headers_only'`. This mirrors 03-01's own precedent (its Task 3 deviation #2, relocating the credential check broke four direct `_map_one` tests the same way).
- **Fix:** Widened each fake's signature to accept `**kwargs` (e.g. `lambda t, fs, client=None, **kwargs: proposal`) -- no fake needed to inspect `headers_only`'s value, only to tolerate its presence.
- **Files modified:** `tests/test_canonical.py`, `tests/test_cli_run.py`, `tests/test_learning_loop_cli.py`, `tests/test_validator_cli.py`
- **Verification:** `python -m pytest -q` -- 383 passed, 4 skipped (up from 375 passed pre-Task-3, no regressions)
- **Committed in:** `23251d7` (Task 3 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** A direct, foreseen consequence of threading a new kwarg through an existing call site already exercised by four other test files' hand-rolled fakes -- no scope creep, no production behavior changed beyond what Task 3 itself specifies.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. `openpyxl`'s write API, `csv`, `json`, `pathlib`, and `datetime` are all already-available stdlib/existing-dependency surface; no new packages were added to `pyproject.toml`.

## Next Phase Readiness
- The full Phase 3 loop is now demonstrable end-to-end from the CLI: parse -> (auto-apply | fresh-Claude, optionally `--headers-only`) -> validate -> confirm (`is_ready`) -> `--export` (CSV/`.xlsx`/JSON/manifest.json). Manually smoke-tested with a monkeypatched Claude call against `novascreen_batch01.csv` and the `assay-potency` preset: exit 0, all four files present, correct provenance/strictness in the manifest.
- `--headers-only` is ready to be the highlighted privacy feature in the Phase 5 video/README per the builder's explicit instruction (memory: highlight-privacy-mode-for-judges) -- the mechanism is a single, legible branch in `_render_table`, easy to show live ("this run sent zero data values to Claude").
- Multi-sheet `--export` (multiple tables into one `DIR`) is an accepted, documented scope boundary (Decisions Made) -- not a blocker for the v1 CLI demo, but worth a one-line README caveat in Phase 5 if a multi-sheet file is used in the recorded demo.
- Phase 4 (FastAPI + React review UI) can reuse `export/writers.py` and `build_manifest` directly behind an HTTP endpoint -- both are pure functions over already-domain objects (`CanonicalTable`, `MappingProposal`, `FieldSet`), with no CLI-specific coupling.
- The two deferred items from CONTEXT.md (formal medical certification / regulatory path; data-confidentiality legal/contractual angle re: Anthropic API terms and zero-data-retention) remain **not yet raised** -- per the builder's explicit instruction, these must be surfaced at project close, not before. `--headers-only` (this plan) is a *technical* mitigation for the confidentiality concern, not a substitute for the legal/contractual answer still owed.

---
*Phase: 03-validator-learning-loop*
*Completed: 2026-07-10*

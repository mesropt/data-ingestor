---
phase: 02-user-defined-fields-dynamic-mapper
plan: 02
subsystem: export
tags: [canonical-form, decimal-locale, iso-8601, tidy-table, pure-python]

requires:
  - phase: 02-user-defined-fields-dynamic-mapper
    provides: "Plan 01's FieldSet/Field model, MappingProposal with plain-str target_field, RawTable.column_locales"
provides:
  - "canonical.py: convert_decimal_comma, convert_date, CanonicalTable, assemble(table, proposal, field_set) — the EXPORT-01 tidy assembly"
  - "CLI prints the canonical tidy table (JSON, converted decimal-comma floats) alongside the proposal draft"
affects: [export, validation, learning-loop, ui]

tech-stack:
  added: []
  patterns:
    - "Classify-then-convert pure function shape mirrored from structure/locale.py: assemble() never raises, every conversion failure or unit mismatch is a flag on the field name, not an exception"
    - "Per-field, per-cell independence: decimal-comma conversion and unit-mismatch detection are checked separately per field, on the raw string before any type conversion, so a unit is never touched by the numeric/date converters"

key-files:
  created:
    - src/assayingest/canonical.py
    - tests/test_canonical.py
  modified:
    - src/assayingest/cli.py

key-decisions:
  - "D-12 unit-mismatch detection is best-effort and field-scoped: only fires when a field explicitly declares Field.unit and its own mapped source cell differs from that declared string — no cross-field unit-column lookup, no prefix arithmetic, per CONTEXT.md's explicit instruction not to attempt one"
  - "Per the plan's literal action text, decimal-point-locale and ambiguous-locale columns mapped to a number/integer field pass the raw string through unconverted (only decimal_comma converts, non_numeric force-flags) — conservative by design, not a gap: D-14 only authorises the decimal_comma conversion"
  - "A malformed date value's canonical cell falls back to the raw string (not None) when strptime fails, so the record always carries the human-readable original alongside the flag rather than a bare null"

requirements-completed: [EXPORT-01]

coverage:
  - id: D1
    description: "assemble() converts a decimal_comma-annotated numeric column to a real float (11,076 -> 11.076); a unit is recorded exactly as written and never converted, and a declared-vs-source unit mismatch only flags the field (D-12/D-14)"
    requirement: "EXPORT-01"
    verification:
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_converts_a_decimal_comma_number_column"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_records_the_unit_verbatim_and_flags_a_declared_mismatch"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_does_not_flag_a_unit_that_matches_the_declared_unit"
        status: pass
    human_judgment: false
  - id: D2
    description: "A date converts to ISO-8601 only when the field declares a date_format; without one it passes through verbatim and the field is flagged (D-13)"
    requirement: "EXPORT-01"
    verification:
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_converts_a_date_field_with_a_declared_format"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_passes_a_date_through_verbatim_and_flags_when_no_format_declared"
        status: pass
    human_judgment: false
  - id: D3
    description: "A single unparseable value (malformed date, non_numeric column mapped to a number field) flags its field rather than crashing assemble()"
    requirement: "EXPORT-01"
    verification:
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_never_raises_on_a_malformed_date_and_a_non_numeric_row"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_assemble_forces_a_flag_on_a_non_numeric_column_mapped_to_a_number_field"
        status: pass
    human_judgment: false
  - id: D4
    description: "convert_decimal_comma/convert_date match the real corpus values plus the two synthetic gaps RESEARCH.md flagged (European thousands+decimal, negative) and the Excel-native-datetime-string shape, without ever raising out of assemble"
    verification:
      - kind: unit
        ref: "tests/test_canonical.py::test_convert_decimal_comma_matches_the_real_corpus_and_the_missing_synthetic_cases"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_convert_date_flags_an_excel_native_datetime_string_rather_than_raising"
        status: pass
    human_judgment: false
  - id: D5
    description: "The CLI prints the canonical tidy table (one record per row, columns = field names, decimal-comma values actually converted) alongside the proposal draft, with no change to exit-code logic"
    requirement: "EXPORT-01"
    verification:
      - kind: unit
        ref: "tests/test_canonical.py::test_map_one_prints_the_canonical_tidy_table_when_a_field_set_is_given"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py::test_map_one_skips_the_canonical_table_when_no_field_set_is_given"
        status: pass
    human_judgment: false
  - id: D6
    description: "A live `assayingest --fields presets/assay-potency.yaml data/synthetic/pinnacle_labs_export.csv` run shows converted value floats (e.g. 11.076, not 11,076) in the printed tidy output"
    verification: []
    human_judgment: true
    rationale: "ANTHROPIC_API_KEY is unset in this execution environment (documented constraint, same as Plan 01's live-call items) — the pure assembly path is fully proven offline (D1/D2/D5 above use the real pinnacle_labs_export.csv decimal-comma values as fixtures); only the end-to-end live-Claude demo run is blocked purely on credential availability, not a known defect."

duration: 6min
completed: 2026-07-10
status: complete
---

# Phase 2 Plan 2: Canonical Tidy-Table Assembly (EXPORT-01) Summary

**New `canonical.py` turns an applied mapping into one tidy record per source row — decimal-comma columns convert to real floats, dates convert to ISO-8601 only when a `date_format` was declared, units are recorded exactly as written and never converted — and the CLI now prints it alongside the proposal draft, completing the messy-in / clean-out money shot.**

## Performance

- **Duration:** 6 min (16:58 – 17:00 UTC+4, 2026-07-10; commit span, execution including context reading was longer)
- **Started:** 2026-07-10T12:58:40Z
- **Completed:** 2026-07-10T13:00:40Z
- **Tasks:** 2 (both TDD-shaped: RED-then-GREEN pairs)
- **Files modified:** 3 (1 created source, 1 created test, 1 modified source)

## Accomplishments

- `src/assayingest/canonical.py`: `convert_decimal_comma`/`convert_date` copied verbatim from 02-RESEARCH.md's verified code examples; `CanonicalTable` (frozen dataclass: `field_names`, `records`, `flagged`) and `assemble(table, proposal, field_set)` build one record per source row, applying only the conversion each field's declared `type`/`date_format` authorises.
- D-14 implemented exactly: a `decimal_comma`-annotated column mapped to a `number`/`integer` field converts to a real float (`11,076` → `11.076`); a `non_numeric` column force-flags the field rather than calling `float()` on garbage (Pitfall 4); every other locale (`decimal_point`, `ambiguous`, or no locale info) passes the raw string through unconverted, per the plan's literal instruction.
- D-13 implemented exactly: a `date` field with a declared `date_format` converts via `datetime.strptime` to ISO-8601; without a declared format the value passes through verbatim and the field is flagged; a malformed value under a declared format (`"32/01/2025"`) never raises — it flags the field and keeps the original string, proven against both a synthetic bad-day case and a real Excel-native `str(datetime)` shape (`"2025-01-01 00:00:00"`).
- D-12 implemented exactly: a field's `unit` cell is never converted by any code path; when a field declares `Field.unit` and the mapped source cell differs from it, the field is flagged but the cell is recorded byte-for-byte unchanged — verified with a µM-recorded-under-an-nM-declaring-field fixture that asserts both the verbatim value and the flag.
- `cli.py`'s `_map_one` now calls `canonical.assemble` and prints its `to_dict()` between the proposal draft and the human review report, whenever a `field_set` is available — verified end-to-end with a monkeypatched `propose_mapping` and a real decimal-comma fixture (3 rows, all three converted floats appear in stdout). The `field_set is None` path (used by the existing offline D-23 exit-code tests) is unchanged and explicitly tested to stay that way.

## Task Commits

Each task was committed atomically (TDD tasks show RED-then-GREEN pairs):

1. **Task 1: Canonical converters + assembly (canonical.py)** - `ce01544` (test, RED) → `c430d12` (feat, GREEN)
2. **Task 2: Show the tidy table in the CLI** - `b87f439` (test, RED) → `6b8cb50` (feat, GREEN)

**Plan metadata:** commit to follow (this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md)

## Files Created/Modified

- `src/assayingest/canonical.py` - `convert_decimal_comma`, `convert_date`, `CanonicalTable`, `assemble()` and its private helpers (`_column_index`, `_normalise_cell`, `_convert_by_type`, `_convert_numeric`, `_convert_field_date`, `_unit_mismatch`)
- `tests/test_canonical.py` - 14 tests: pure-function converter cases, per-conversion `assemble()` cases (decimal-comma, unit verbatim/mismatch, non_numeric force-flag, date-format-required, never-raises), and two CLI-wiring integration tests
- `src/assayingest/cli.py` - `_map_one` calls `canonical.assemble` and prints the tidy JSON when `field_set` is not `None`; import of the new `canonical` module

## Decisions Made

- Decimal-point-locale and ambiguous-locale numeric columns are passed through as raw strings, not force-converted to float — the plan's action text is explicit that only `decimal_comma` triggers `convert_decimal_comma`, and D-14 only authorises that one conversion. Extending conversion to `decimal_point` columns was considered but rejected as out of this plan's literal scope; the raw string is already a normal-looking number for downstream consumers in that case.
- The D-12 unit-mismatch check compares a field's own mapped source cell directly against `Field.unit`, with no cross-field lookup to a separate "unit column" for a "value" field — CONTEXT.md's "best-effort... do not attempt any prefix arithmetic" instruction was read as scoping the check to the field's own declared `unit` attribute, matching the test fixture shape the plan's own behavior list describes (a `unit`-typed field whose cell is the unit string itself).
- A malformed date's canonical value falls back to the original raw string (not `None`) when `strptime` fails inside `assemble` — keeps the human-readable original visible next to the flag rather than silently nulling data the human still needs to see to correct it.

## Deviations from Plan

None - plan executed exactly as written. The only adjustment was a self-correction to my own test assertion (`out.count('"compound_id"') == 3` was miscounting occurrences across both the proposal draft and the canonical JSON) — fixed before the GREEN commit, not a deviation from the plan itself.

## Issues Encountered

None.

## User Setup Required

None for offline development. **For a live demo run**, with `ANTHROPIC_API_KEY` set:
```
assayingest --fields presets/assay-potency.yaml data/synthetic/pinnacle_labs_export.csv
```
should show the tidy canonical JSON block printing `"value": 11.076` (not `"11,076"`) for PIN-010 — the D6 coverage item above, blocked only on credential availability in this environment.

## Next Phase Readiness

- `canonical.assemble` is the one representation Phase 3's CSV/Excel/JSON exports, the no-LLM validator, and the learning-loop profile store can all build directly on (D-15) — no further normalisation logic should be duplicated in Phase 3.
- The threat register's three items (T-02-04 per-value DoS, T-02-05 silent-corruption, T-02-06 strptime-injection) are all mitigated by this plan's implementation: every conversion is per-value try/except-guarded, units/decimal-comma follow the locked never-guess rules, and `date_format` reaches only `datetime.strptime`.
- One `human_judgment: true` coverage item (D6, the live end-to-end demo run) is blocked purely on `ANTHROPIC_API_KEY` availability, not on any known defect — ready to run as soon as credentials exist, alongside Plan 01's two still-open live-credential items.

---
*Phase: 02-user-defined-fields-dynamic-mapper*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 3 files confirmed present on disk (`src/assayingest/canonical.py`, `tests/test_canonical.py`, this SUMMARY.md). All 4 task commit hashes confirmed present in `git log` (`ce01544`, `c430d12`, `b87f439`, `6b8cb50`). Full suite: 176 passed, 3 skipped (same 3 credential-gated skips as Plan 01's baseline; no new skips or failures introduced).

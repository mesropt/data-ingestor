---
phase: 10-frictionless-correct-ingest
plan: 01
subsystem: parsing
tags: [date-order, ambiguity-detection, openpyxl, strptime, domain-model, tdd]

# Dependency graph
requires: []
provides:
  - "src/assayingest/parsing/structure/date_order.py — pure classify_column/implied_order/iso_from_excel_serial/format_for_order surface"
  - "DateOrder enum + DateColumnFormat frozen dataclass"
  - "EXCEL_SERIAL_MARKER sentinel constant"
  - "DateFormatConflict/DateFormatQuestion frozen dataclasses in domain/models.py"
affects: [10-frictionless-correct-ingest plan 03 (service.py wiring), canonical.py, validation/validator.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Evidence-based ambiguity predicate (mirrors structure/locale.py): a component >12 proves order; uniformity across a column fails closed to AMBIGUOUS, never a heuristic guess."
    - "Single-value-is-sufficient-evidence for date order — deliberately the OPPOSITE of locale.py's Pitfall-7 single-value-is-ambiguous rule for decimal commas, documented inline and in a dedicated test."
    - "Separator/year-width/time-suffix parameterised template generation instead of a hardcoded format list."

key-files:
  created:
    - src/assayingest/parsing/structure/date_order.py
    - tests/test_date_order.py
  modified:
    - src/assayingest/domain/models.py
    - tests/test_domain.py

key-decisions:
  - "DateFormatConflict/DateFormatQuestion live in domain/models.py beside ReconcileConflict/ReconcileQuestion, NOT in parsing/hint.py beside StructureQuestion — the date question needs post-mapping field context a pre-mapping structural question was never designed to carry (10-RESEARCH.md Pitfall 4)."
  - "Excel-serial sane range fixed at [25569, 73050] (1970-01-01..2099-12-31 under the standard 1900 epoch), computed via openpyxl.utils.datetime.to_excel rather than guessed; a 1904-epoch workbook is a documented, accepted limitation since RawTable carries no epoch flag."
  - "Mixed-column policy: a non-date-shaped cell (e.g. \"not a date\") in an otherwise date-shaped column is ignored by classify_column — order is derived only from date-shaped values; the validator flags the individual bad cell independently (a future plan's concern, not this one's)."
  - "A proven order's resolved date_format is validated by re-running strptime against every date-shaped value before being trusted; if any value fails, the column degrades to INVALID rather than returning a format that will fail at conversion time later."

requirements-completed: [INGEST-04]

coverage:
  - id: D1
    description: "classify_column() proves DAY_FIRST/MONTH_FIRST from a single component >12 anywhere in the column, and fails closed to AMBIGUOUS (naming both candidate formats) when no component ever exceeds 12"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_date_order.py#test_helixbio_experiment_date_is_ambiguous_and_names_both_formats"
        status: pass
      - kind: unit
        ref: "tests/test_date_order.py#test_pinnacle_date_is_unambiguous_day_first"
        status: pass
      - kind: unit
        ref: "tests/test_date_order.py#test_single_asymmetric_value_is_unambiguous_unlike_locale_pitfall_7"
        status: pass
    human_judgment: false
  - id: D2
    description: "implied_order() lets a declared date_format be compared against a column's independently-proven order, even when every row parses cleanly under the wrong declared format (the D-10-06 danger case)"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_date_order.py#test_a_declared_format_can_be_contradicted_by_evidence_even_when_every_row_parses"
        status: pass
    human_judgment: false
  - id: D3
    description: "Excel-native datetime strings, bare ISO dates, and compact 8-digit dates all classify ISO; bare Excel serials classify EXCEL_SERIAL and convert via openpyxl.utils.datetime.from_excel with a defensive 1970-2100 sanity range"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_date_order.py#test_castlebio_native_datetime_string_is_iso"
        status: pass
      - kind: unit
        ref: "tests/test_date_order.py#test_iso_from_excel_serial_converts_a_real_serial"
        status: pass
      - kind: unit
        ref: "tests/test_date_order.py#test_iso_from_excel_serial_rejects_a_value_far_above_the_sane_range"
        status: pass
    human_judgment: false
  - id: D4
    description: "DateFormatConflict/DateFormatQuestion domain types exist beside the Phase 08 reconcile pair, frozen, with to_dict() round-tripping and has_conflicts gating"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_domain.py#test_date_format_conflict_round_trips_through_to_dict"
        status: pass
      - kind: unit
        ref: "tests/test_domain.py#test_date_format_question_has_conflicts_only_when_non_empty"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 01: Date-Order Classifier + Domain Types Summary

**Pure, dependency-free `date_order.py` classifier (evidence-only day/month-first proof, Excel-serial + ISO handling) plus `DateFormatConflict`/`DateFormatQuestion` domain types — zero wiring, zero LLM, zero new dependencies.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-12T10:58:00Z (approx, first commit 2026-07-12T15:00:40+04:00)
- **Completed:** 2026-07-12T15:05:26+04:00
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- Built `src/assayingest/parsing/structure/date_order.py`: a pure classifier mirroring `structure/locale.py`'s shape exactly — `classify_column(values) -> DateColumnFormat`, `implied_order(date_format) -> DateOrder | None`, `iso_from_excel_serial(raw) -> str | None`, `format_for_order(column, order) -> str`, plus `DateOrder` enum and `EXCEL_SERIAL_MARKER` constant.
- The classifier proves order ONLY from a component >12 (never a heuristic); a genuinely ambiguous column (`helixbio_export.csv`'s `Experiment Date`, `summit_discovery_mixed.xlsx`'s unpadded `date`) fails closed to `AMBIGUOUS`, naming both candidate formats.
- Pinned the single-value asymmetry rule as the deliberate opposite of `locale.py`'s Pitfall 7: a lone `13/07/2026` value is sufficient evidence for `DAY_FIRST` on its own (a single 3-digit comma group can never disambiguate a decimal, but a single day/month value >12 can and does disambiguate a date).
- Pinned the "danger" `implied_order` comparison test: a column whose evidence proves `DAY_FIRST` (via a `21` in `pinnacle_labs_export.csv`-shaped data) parses cleanly under its own correct format while `implied_order` of a wrongly-declared `%m/%d/%Y` provably disagrees — the mechanism D-10-06 needs, independent of whether any individual `strptime` call happens to raise.
- Excel-native datetime strings (`str(datetime)` shape, `castlebio_native_dates.xlsx`), bare ISO dates, and compact 8-digit dates (`cascade_assays_nounit.xlsx`) all classify `ISO` with zero order ambiguity. Bare Excel serials (`46092`, from the genelab-disaster fixture's in-scope mechanism) classify `EXCEL_SERIAL` and convert through `openpyxl.utils.datetime.from_excel`, never a hand-rolled epoch formula; a serial outside a defensive `[25569, 73050]` (~1970-2100) sanity range returns `None` from `iso_from_excel_serial` rather than emitting an implausible date.
- Added `DateFormatConflict`/`DateFormatQuestion` frozen dataclasses to `domain/models.py`, mirroring `ReconcileConflict`/`ReconcileQuestion`'s exact shape (`to_dict()`, `has_conflicts`), placed beside the Phase 08 pair rather than beside `parsing/hint.py`'s pre-mapping `StructureQuestion` — documented in the class docstring so a future reader does not "tidy" it into the wrong module.
- 31 new tests in `tests/test_date_order.py` and 5 new tests in `tests/test_domain.py`, all using real fixture values quoted verbatim from `10-RESEARCH.md`'s verified corpus reads (independently re-verified against the actual files in this plan's own execution, not merely trusted from the research doc).

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing tests for the date-order ambiguity predicate** - `dcd27e3` (test)
2. **Task 2: Implement date_order.py until GREEN** - `77a01bc` (feat)
3. **Task 3: DateFormatConflict/DateFormatQuestion domain types** - `96a9a86` (feat — RED→GREEN internal to this task, single commit per the plan's own acceptance criteria)

_TDD Gate Compliance: `test(10-01)` commit precedes both `feat(10-01)` commits — RED then GREEN, verified in git log order._

## Files Created/Modified

- `src/assayingest/parsing/structure/date_order.py` - The pure date-order classifier: `DateOrder`, `DateColumnFormat`, `classify_column`, `implied_order`, `iso_from_excel_serial`, `format_for_order`, `EXCEL_SERIAL_MARKER`
- `tests/test_date_order.py` - 31 tests covering AMBIGUOUS/DAY_FIRST/MONTH_FIRST/ISO/EXCEL_SERIAL/INVALID/NON_DATE against real fixture values
- `src/assayingest/domain/models.py` - Added `DateFormatConflict`/`DateFormatQuestion` in a new `# --- Phase 10 ---` section below the Phase 08 reconcile types
- `tests/test_domain.py` - 5 tests for the two new domain types (to_dict round-trip, has_conflicts, frozen)

## Decisions Made

- Excel-serial sane range fixed at `[25569, 73050]`, computed directly via `openpyxl.utils.datetime.to_excel(datetime(1970,1,1))`/`to_excel(datetime(2100,1,1))` rather than an arbitrary guess — documented in the module docstring alongside the accepted 1900-vs-1904-epoch limitation.
- Mixed-column values (a date-shaped cell alongside a clearly non-date cell like `"not a date"`) are classified from the date-shaped values only, ignoring the rest — stated as an explicit design choice in both the test and the module docstring, matching the plan's "recommended" option.
- `classify_column` of an out-of-range bare integer (`"5"`, `"900000"`) resolves to `NON_DATE`, not `EXCEL_SERIAL` — matches the plan's literal action text ("all bare integers in the Excel-serial range → EXCEL_SERIAL... otherwise → NON_DATE"), while `iso_from_excel_serial` is separately tested to return `None` for the same out-of-range inputs when called directly.
- `DateFormatQuestion`/`DateFormatConflict` placed in `domain/models.py`, never `parsing/hint.py`, per D-10-07/10-RESEARCH.md Pitfall 4 — documented inline as a hard constraint for future readers.

## Deviations from Plan

None — plan executed exactly as written. All fixture values used in `tests/test_date_order.py` were independently re-verified against the actual files in `data/synthetic/` during this plan's execution (via direct `openpyxl`/`pandas` reads), not merely copied from `10-RESEARCH.md`'s claims.

One implementation bug was found and fixed during Task 2's own RED→GREEN cycle before the GREEN commit (not a deviation from the plan — this is exactly what the TDD loop is for): the day-first/month-first format template construction initially omitted the separator between `%m`/`%d` and the year component (`%d/%m%Y` instead of `%d/%m/%Y`), which `_all_parse`'s post-hoc strptime validation correctly caught as a validation failure (degrading proven-order columns to `INVALID`). Fixed inline before the Task 2 commit; no separate commit was needed since Task 2's tests were still RED at that point.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `date_order.py`'s full public surface (`DateOrder`, `DateColumnFormat`, `classify_column`, `implied_order`, `iso_from_excel_serial`, `format_for_order`, `EXCEL_SERIAL_MARKER`) is ready for Plan 03 to wire into `service.py`'s orchestration step between mapping resolution and `validate()`.
- `DateFormatConflict`/`DateFormatQuestion` are ready for Plan 03's `kind="date_question"` response arm and the corresponding `/api/date-format/resolve` route.
- No blockers. This plan touched exactly the 4 files declared in `files_modified` — `service.py`, `canonical.py`, `validation/validator.py`, and `api/` remain completely untouched, confirmed via `git diff --stat`.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 3 task commit hashes (dcd27e3, 77a01bc, 96a9a86) confirmed present in git log. Full suite re-verified green: 670 passed, 4 skipped.

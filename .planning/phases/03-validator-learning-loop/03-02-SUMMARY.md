---
phase: 03-validator-learning-loop
plan: 02
subsystem: validation
tags: [pure-python, dataclasses, no-llm, cli]

# Dependency graph
requires:
  - phase: 03-validator-learning-loop
    provides: "03-01's learning-loop: SqliteProfileStore, reconstruct_proposal, _resolve_proposal(table, field_set, store) returning (proposal, provenance) on both the auto-apply and fresh-Claude branches -- the single point 03-02 validates"
  - phase: 02-user-defined-fields-dynamic-mapper
    provides: "Field constraints (type, allowed_values, unit, min, max), canonical.assemble()'s flagged-but-unwired type/date/unit checking, FieldMapping/MappingProposal's non-frozen additive-evolution shape"
provides:
  - "validation/validator.py::validate(table, proposal, field_set, *, strictness) -- the no-LLM safety net (VAL-01/02/03)"
  - "FieldMapping.validator_note -- the tool's deterministic verdict, kept textually distinct from Claude's own reasoning"
  - "Validator wired into cli.py::_map_one on BOTH the fresh-Claude and auto-apply branches (D-03), plus a --strictness CLI flag (D-11)"
affects: [03-03-export-manifest]

# Tech tracking
tech-stack:
  added: []  # stdlib only -- dataclasses.replace, reuses canonical.py/mapper.py idioms
  patterns:
    - "Pattern 1 reuse: validate() calls canonical.assemble(table, proposal, field_set) first and reads .flagged -- zero duplication of decimal-comma/date/text-unit logic; the only NEW checks are allowed_values (case-insensitive) and min/max"
    - "Additive-only mutation (_apply_objection): needs_confirmation=mapping.needs_confirmation OR objects, never AND/overwrite -- the validator's silence can never clear a flag someone else raised"
    - "VAL-02 alternatives loop: every ColumnCandidate the mapper ranked is checked against the same field constraints, not only the chosen source_column"

key-files:
  created:
    - src/assayingest/validation/__init__.py
    - src/assayingest/validation/validator.py
    - tests/test_validator.py
    - tests/test_validator_strictness.py
    - tests/test_validator_cli.py
  modified:
    - src/assayingest/domain/models.py
    - src/assayingest/cli.py
    - presets/assay-potency.yaml

key-decisions:
  - "validate() is called in _map_one immediately after the proposal resolves (both branches) and BEFORE any output is printed -- so the JSON draft, the tidy canonical table, and the review all reflect the validated (possibly re-flagged) mapping, not the pre-validation one"
  - "VAL-01's unit check stays scoped to text-field unit-equality only (reused for free via canonical's _unit_mismatch) -- numeric-field-to-separate-unit-column cross-checking is explicitly out of scope for v1 per RESEARCH Pitfall 5/Assumption A2, recorded verbatim in Task 1's action text"
  - "Lenient strictness relaxes row COVERAGE only (samples the first 6 rows, mirroring mapper._SAMPLE_ROWS) -- an in-scope violation the sample DOES see is still a full, unsoftened objection; strict (default) always scans every row"
  - "presets/assay-potency.yaml's assay_date field was missing date_format -- fixed to \"%Y-%m-%d\" (matching the corpus's actual ISO dates), since canonical._convert_field_date always flags a date field with no declared format (D-13), which would have permanently blocked the novascreen money-shot once Pattern 1 wired .flagged into the gate"

patterns-established:
  - "validation/ package: one pure module (validator.py), zero I/O, zero LLM calls, mirrors canonical.py's own 'flag instead of raise' convention"
  - "CLI render precedent: a validator_note line is shown for BOTH yellow and clear fields (VAL-03/D-04) -- the validator's silence must never look like it never ran"

requirements-completed: [VAL-01, VAL-02, VAL-03]

coverage:
  - id: D1
    description: "allowed_values (case-insensitive) and min/max bounds are new checks the validator adds on top of Field's existing declared constraints, with no LLM call (VAL-01)"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "tests/test_validator.py::test_allowed_values_flags_a_value_not_in_the_declared_set"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_allowed_values_matches_case_insensitively"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_min_flags_a_value_below_the_declared_minimum"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_max_flags_a_value_above_the_declared_maximum"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_value_inside_bounds_is_not_flagged"
        status: pass
    human_judgment: false
  - id: D2
    description: "canonical.assemble().flagged (decimal-comma/date-format/text-unit) is reused as the validator's type/date/unit engine, forcing needs_confirmation with zero duplicated conversion logic (VAL-01, Pattern 1)"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "tests/test_validator.py::test_a_decimal_comma_conversion_failure_flagged_by_canonical_forces_confirmation"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_a_date_format_mismatch_flagged_by_canonical_forces_confirmation"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_a_text_unit_mismatch_flagged_by_canonical_forces_confirmation"
        status: pass
    human_judgment: false
  - id: D3
    description: "A validator objection overrides Claude's own confidence 1.0/needs_confirmation=False, and is additive-only -- never clears an existing True on a no-constraint field (VAL-02, Pattern 2/P1)"
    requirement: "VAL-02"
    verification:
      - kind: unit
        ref: "tests/test_validator.py::test_validator_overrides_a_confidence_1_0_clear_field"
        status: pass
      - kind: unit
        ref: "tests/test_validator.py::test_validator_never_clears_an_existing_confirmation_on_a_no_constraint_field"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every one of Claude's ranked alternatives is validated against the same field's constraints, not only the top-pick source_column (VAL-02)"
    requirement: "VAL-02"
    verification:
      - kind: unit
        ref: "tests/test_validator.py::test_every_alternative_is_validated_not_only_the_chosen_column"
        status: pass
    human_judgment: false
  - id: D5
    description: "A field with no declared constraints is never silently trusted -- validator_note records the explicit absence of an objection, and needs_confirmation is left to Claude's own gate (VAL-03/D-04); the note also renders in the CLI review for both yellow and clear fields"
    requirement: "VAL-03"
    verification:
      - kind: unit
        ref: "tests/test_validator.py::test_no_constraints_field_gets_an_explicit_absence_note_and_keeps_claudes_gate"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_render_field_shows_validator_note_for_a_yellow_field"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_render_field_shows_validator_note_for_a_clear_field_too"
        status: pass
    human_judgment: false
  - id: D6
    description: "Strictness defaults to strict (every row); lenient relaxes row coverage only, never an in-scope objection's severity; signature matching is never imported/touched by the validator module (D-11)"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_strict_default_scans_every_row_including_a_late_violation"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_lenient_only_samples_early_rows_and_misses_a_late_violation"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_lenient_still_fully_objects_to_a_violation_within_its_sample"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_invalid_strictness_raises_a_consequence_describing_value_error"
        status: pass
      - kind: unit
        ref: "tests/test_validator_strictness.py::test_validator_module_never_imports_the_learning_signature_package"
        status: pass
    human_judgment: false
  - id: D7
    description: "The validator runs on BOTH the fresh-Claude path and an auto-applied confidence-1.0 profile path (D-03) -- a violation forces exit 5 on either path; a genuinely clean auto-applied file still exits 0 (validation never spuriously flags clean data); --strictness threads from main() through run()/_map_and_report/_map_one into validate()"
    requirement: "VAL-02"
    verification:
      - kind: unit
        ref: "tests/test_validator_cli.py::test_fresh_claude_path_validator_forces_exit_5_despite_a_green_proposal"
        status: pass
      - kind: unit
        ref: "tests/test_validator_cli.py::test_auto_apply_path_validator_still_runs_under_a_saved_profile"
        status: pass
      - kind: unit
        ref: "tests/test_validator_cli.py::test_clean_auto_apply_still_exits_0_after_the_validator_is_wired_in"
        status: pass
      - kind: unit
        ref: "tests/test_validator_cli.py::test_run_defaults_to_strict_and_threads_a_lenient_choice_through_to_validate"
        status: pass
      - kind: unit
        ref: "tests/test_validator_cli.py::test_main_accepts_a_strictness_flag_and_threads_it_into_run"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-10
status: complete
---

# Phase 3 Plan 2: Validator Summary

**Pure-Python, no-LLM constraint validator that reuses `canonical.assemble().flagged` as its type/date/unit engine, adds `allowed_values`/`min`/`max` checks plus every ranked alternative, and is additive-only + wired into both the fresh-Claude and auto-applied-profile CLI paths with a fail-closed-by-default `--strictness` flag.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-10T16:26:00Z
- **Completed:** 2026-07-10T16:41:09Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- `validation/validator.py::validate()` seeds every field's objection from `canonical.assemble(table, proposal, field_set).flagged` (Pattern 1) -- decimal-comma/date-format/text-unit checks Phase 2 already wrote are now actually wired to `needs_confirmation`, closing a real pre-existing gap (a `MappingProposal` could be `is_ready` while `.flagged` silently named a broken conversion).
- The two genuinely new checks -- `allowed_values` (case-insensitive, D-07) and `min`/`max` numeric bounds -- are checked against the chosen `source_column` AND every ranked `ColumnCandidate` alternative (VAL-02), and the objection-application function (`_apply_objection`) is additive-only: it can only OR a `True` into `needs_confirmation`, never clear one (Pattern 2/P1), verified directly against a no-constraint field that started `needs_confirmation=True`.
- `FieldMapping.validator_note` is a new, separate optional field (not concatenated into `reasoning`) so the tool's deterministic verdict -- including the explicit "no declared constraints to check" absence note (VAL-03/D-04) -- stays visibly distinct from Claude's own reasoning; it renders in the CLI review for both yellow and clear fields.
- `--strictness` (`strict`|`lenient`, default `strict`, D-11) threads from `main()`'s argparse through `run()`/`_map_and_report`/`_map_one` into `validate()`; lenient relaxes row coverage only (samples the first 6 rows) and never softens an in-scope objection's severity, and the validator module imports nothing from `learning/` -- signature matching is untouched by strictness at any level.
- `validate()` is called in `_map_one` immediately after the proposal resolves and before any print, on BOTH the fresh-Claude branch and the auto-apply branch built in 03-01 (D-03): proven with a saved profile whose stored mapping is fully clear but whose actual file values violate a declared constraint -- the auto-applied confidence-1.0 proposal still comes out yellow (exit 5), with `propose_mapping` monkeypatched to raise if called and no credentials configured. The clean novascreen money-shot (assay-potency preset) still exits 0 after this wiring.

## Task Commits

Each task followed the TDD RED -> GREEN cycle (MVP+TDD mode: `test(...)` then `feat(...)`):

1. **Task 1: Validator core** -- `53b9cb9` (test), `a311e2c` (feat)
2. **Task 2: Configurable strictness + validator_note rendering** -- `7623d3b` (test), `df17f00` (feat)
3. **Task 3: Wire the validator into run() on both paths + --strictness flag** -- `1fc8524` (test), `2854279` (feat)

_No refactor commits were needed -- each GREEN implementation passed on the first pass (Task 3 required one test-fixture fix, see Deviations)._

## Files Created/Modified
- `src/assayingest/validation/__init__.py` - empty package marker
- `src/assayingest/validation/validator.py` - `validate()`, `_apply_objection` (additive-only), `_check_candidates`/`_check_column`/`_check_value` (allowed_values/min/max), `_rows_for_strictness`
- `src/assayingest/domain/models.py` - `FieldMapping.validator_note: str | None = None` (additive optional field)
- `src/assayingest/cli.py` - `_render_field`/`_with_validator_note` render the note; `run()`/`_map_and_report`/`_map_one` thread `strictness`; `validate()` called on both paths before any print; `--strictness` argparse flag
- `presets/assay-potency.yaml` - `assay_date.date_format: "%Y-%m-%d"` added (see Deviations)
- `tests/test_validator.py` - new, 10 tests (validator core)
- `tests/test_validator_strictness.py` - new, 8 tests (strictness + CLI render)
- `tests/test_validator_cli.py` - new, 5 tests (both-paths wiring + strictness threading)

## Decisions Made
- **`validate()` runs before any output is printed in `_map_one`**, not just before the gate check -- so the printed JSON draft, the tidy canonical table, and the review report all reflect the validated (possibly re-flagged) proposal consistently, rather than the human seeing a stale pre-validation draft followed by a post-validation gate summary that disagrees with it.
- **The validator's own header-index lookup (`_column_index`) is a small local helper, not a reuse of `canonical._column_index`.** Both do the identical trivial `headers.index(source_column)` with a `try/except`, but importing a private symbol across modules was avoided in favour of mirroring the shape locally (consistent with the project's existing convention of small private per-module helpers) -- this is not the kind of logic Pattern 1/Don't-Hand-Roll warns against duplicating (that's specifically decimal-comma/date conversion).
- **`_numeric_value` reuses `canonical.convert_decimal_comma` for a `decimal_comma`-locale column** rather than re-implementing locale coercion, per the plan's explicit instruction; a value that still doesn't parse is silently skipped by the min/max check (not flagged) because Pattern 1's canonical-flagged reuse already covers a numeric-field/non-numeric-cell mismatch -- duplicating that flag here would be redundant, not additive.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `presets/assay-potency.yaml`'s `assay_date` field was missing `date_format`**
- **Found during:** Task 3 (wiring the validator into both CLI paths), while verifying the "clean auto-apply stays green" behavior against the real novascreen/assay-potency money-shot fixture
- **Issue:** `canonical._convert_field_date` always sets `needs_confirmation=True` for a date field with no declared `date_format` (D-13's own field-set-level ambiguity rule) -- but `assay-potency.yaml` never declared one for `assay_date`, unlike `pk-parameters.yaml` and `reagent-inventory.yaml`, which both do. Before Phase 3, `canonical.flagged` was purely informational and never wired to the export gate, so this never surfaced. Once Task 3 wired `.flagged` into `needs_confirmation` (Pattern 1), `assay_date` became permanently unconfirmable for this preset, which would have broken the money-shot ("clean auto-apply stays green") requirement even for a perfectly clean ISO-formatted date column.
- **Fix:** Declared `date_format: "%Y-%m-%d"` on `assay_date`, matching the actual ISO date format used throughout the synthetic corpus (`data/synthetic/novascreen_batch0*.csv`).
- **Files modified:** `presets/assay-potency.yaml`
- **Verification:** `python -m pytest tests/test_presets.py tests/test_learning_loop_cli.py tests/test_cli_run.py tests/test_canonical.py -q` -- all pass unchanged; `tests/test_validator_cli.py::test_clean_auto_apply_still_exits_0_after_the_validator_is_wired_in` passes with exit code 0.
- **Committed in:** `1fc8524` (Task 3 RED commit, alongside the test that exercises this)

**2. [Rule 1 - Bug] Minimal single-column CSV test fixtures tripped the structural delimiter sniffer**
- **Found during:** Task 3 GREEN run, `test_fresh_claude_path_validator_forces_exit_5_despite_a_green_proposal`
- **Issue:** `run()` routes through `parsing.table.parse()`'s structural delimiter detection (Phase 1), not the legacy `parse_file()`. A minimal fixture (`"Flag\nX\n"` -- one column, one data row) is genuinely ambiguous evidence for that detector, which mis-split the single header `"Flag"` into two bogus columns (`"F"`, `"ag"`). This is a pre-existing parser-hardening edge case, not a validator bug -- out of this plan's scope (parser hardening is a separate, deferred phase).
- **Fix:** Added a second, unconstrained `"Compound"` column to every minimal CSV fixture in `tests/test_validator_cli.py`, giving the delimiter sniffer enough real structure to resolve correctly, matching how every other CSV fixture in the test suite is already at least two columns wide.
- **Files modified:** `tests/test_validator_cli.py`
- **Verification:** `python -m pytest tests/test_validator_cli.py -q` -- 5/5 pass.
- **Committed in:** `2854279` (Task 3 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both fixes were direct, foreseen consequences of correctly wiring Pattern 1's `.flagged` reuse and the structural parser Task 3 routes through -- no scope creep, no production behavior changed beyond what VAL-01/VAL-02/VAL-03/D-03/D-11 require.

## Issues Encountered
None beyond the two deviations above. One process note: `validate()`'s full `strictness` behavior (sampling + invalid-value rejection) was implemented in Task 1's GREEN commit ahead of Task 2's own TDD cycle, since Task 1's action text already specified the `strictness="strict"` keyword in `validate()`'s signature. As a result, Task 2's RED test run for the strictness-coverage assertions already passed before any Task-2-specific code was written; the genuinely new RED-to-GREEN behavior for Task 2 was the CLI's `validator_note` rendering, which failed cleanly and was then implemented. No behavior gap resulted -- Task 2's strictness tests remain in the suite as full regression coverage for behavior that happened to land one commit early.

## User Setup Required
None - no external service configuration required. Pure Python, stdlib only; no new dependencies.

## Next Phase Readiness
- `validate()` is a drop-in step between proposal resolution and review/export in `_map_one` -- 03-03 (export manifest) can call `proposal.is_ready`/`unclear_fields` after validation exactly as it already does today, with the extra guarantee that `is_ready` now also reflects every declared constraint, not just the mapper's own confidence.
- The `strictness` value accepted and validated here (`strict`/`lenient`) is ready for 03-03 to record in the export manifest per D-11 ("relaxation is explicit and recorded") -- this plan intentionally stopped short of writing it anywhere persistent, per Task 2's own action text ("do not record it here beyond accepting/validating it").
- `FieldMapping.validator_note` is populated on every field after `validate()` runs (including a `None` value never occurring for a validated proposal) -- ready for 03-03's manifest or a future UI to surface directly.
- No blockers. The Open Question flagged in CONTEXT.md ("revisit whether always-validate-under-profile is exactly right") remains open per the builder's own note and is unaffected by this plan's implementation -- D-03 was implemented literally as specified.

---
*Phase: 03-validator-learning-loop*
*Completed: 2026-07-10*

## Self-Check: PASSED

- All 9 created/referenced files verified present on disk.
- All 6 task commit hashes (`53b9cb9`, `a311e2c`, `7623d3b`, `df17f00`, `1fc8524`, `2854279`) verified present in `git log`.

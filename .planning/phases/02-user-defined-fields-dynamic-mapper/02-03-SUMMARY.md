---
phase: 02-user-defined-fields-dynamic-mapper
plan: 03
subsystem: presets
tags: [yaml-data, hatch-wheel-packaging, synthetic-corpus, no-biology-proof]

requires:
  - phase: 02-user-defined-fields-dynamic-mapper
    plan: "01"
    provides: "fields.loader.load(path), mapping.schema.build_wire_models(field_names), mapping.mapper._render_system_prompt(field_set), presets/assay-potency.yaml as the preset-YAML shape to mirror"
provides:
  - "presets/pk-parameters.yaml and presets/reagent-inventory.yaml: two more domain-spanning field-set presets, loaded by the identical load(path) call as assay-potency.yaml — zero per-preset code"
  - "SC5 proof: reagent-inventory's runtime schema enum and rendered system prompt contain no assay vocabulary (IC50/EC50/Ki/Kd/%inhibition/nM/µM)"
  - "Wheel packaging: [tool.hatch.build.targets.wheel.force-include] ships presets/*.yaml at assayingest/presets/ so a pip/uv install can load them"
  - "Two synthetic fixtures closing 02-RESEARCH.md's corpus gaps: European thousands+decimal (vertex_pk_eu_format.xlsx) and an Excel-native datetime-typed cell (castlebio_native_dates.xlsx)"
affects: [validation, learning-loop, export, ui, demo]

tech-stack:
  added: []
  patterns:
    - "Presets are provably data: adding a third and fourth preset touched zero .py files under src/ — verified with git diff --stat across both task commits"
    - "hatch force-include maps a top-level non-package directory (presets/) into the wheel under a namespaced path (assayingest/presets/), verified by building the wheel and listing its exact contents"

key-files:
  created:
    - presets/pk-parameters.yaml
    - presets/reagent-inventory.yaml
    - tests/test_presets.py
    - data/synthetic/vertex_pk_eu_format.xlsx
    - data/synthetic/castlebio_native_dates.xlsx
    - .planning/phases/02-user-defined-fields-dynamic-mapper/deferred-items.md
  modified:
    - pyproject.toml
    - scripts/gen_synthetic_pk.py
    - data/synthetic/README.md

key-decisions:
  - "pk-parameters' study_date date_format (%Y/%m/%d) matches orion_pk_report.xlsx's real Study Day column format, honoring the plan's framing of orion as this preset's natural target"
  - "European thousands+decimal fixture (vertex_pk_eu_format.xlsx) is a new file, not an edit to an existing tracked fixture (e.g. helix_genomics_DE.xlsx) — avoids any risk of invalidating structure/locale/parse-entry tests that already assert against the existing fixtures' exact shapes"
  - "Excel-native-date fixture (castlebio_native_dates.xlsx) is likewise a new file for the same reason, built cell-by-cell with ws.cell(...).value = date(...) rather than ws.append([...]), the only way to force a genuine datetime-typed cell instead of a formatted string"
  - "european_thousands_decimal() uses Python's own ',' thousands-grouping format spec plus a two-step character swap through a NUL placeholder, rather than a locale library — mirrors 02-RESEARCH.md's Don't-Hand-Roll guidance against pulling in a general locale-parsing dependency for one formatting need"

requirements-completed: [FIELD-05]

coverage:
  - id: D20-D21
    description: "Three presets across three domains (assay-potency, pk-parameters, reagent-inventory) load by path with zero registry, import, or per-preset code branch"
    requirement: "FIELD-05"
    verification:
      - kind: unit
        ref: "tests/test_presets.py::test_all_three_presets_load_through_the_identical_load_call"
        status: pass
      - kind: other
        ref: "git diff --stat 4c9ec5a~1..a434df3 -- src/  (no output — zero .py files touched across both task commits)"
        status: pass
    human_judgment: false
  - id: SC5
    description: "reagent-inventory's runtime schema enum and rendered system prompt contain none of IC50/EC50/Ki/Kd/%inhibition/nM/µM, proving no biology is compiled into the mapper"
    requirement: "FIELD-05"
    verification:
      - kind: unit
        ref: "tests/test_presets.py::test_reagent_inventory_schema_enum_matches_its_own_field_names"
        status: pass
      - kind: unit
        ref: "tests/test_presets.py::test_reagent_inventory_prompt_carries_no_biology"
        status: pass
    human_judgment: false
  - id: D20-wheel
    description: "Presets ship inside the built wheel (pip/uv install can load them, not just a checkout)"
    verification:
      - kind: other
        ref: "uv build && python3 -c \"...\" — dist wheel namelist contains exactly assayingest/presets/{assay-potency,pk-parameters,reagent-inventory}.yaml, no stray files"
        status: pass
    human_judgment: false
  - id: corpus-gaps
    description: "European thousands+decimal (1.234,56-style) and an Excel-native datetime-typed date cell both now exist in the corpus"
    verification:
      - kind: other
        ref: "uv run python -c \"...\" — re-read both fixtures with openpyxl: vertex_pk_eu_format.xlsx's Wert column reads '3.698,10'; castlebio_native_dates.xlsx's Tested On cell reads as datetime.datetime, not a string"
        status: pass
      - kind: unit
        ref: "uv run pytest -q — 182 passed, 3 skipped (176 baseline + 6 new test_presets.py tests, no regressions)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-10
status: complete
---

# Phase 2 Plan 3: Preset Library + Wheel Packaging + Corpus Gaps Summary

**Two more domain-spanning field-set presets (pk-parameters, reagent-inventory) shipped as plain YAML — the reagent-inventory preset's schema and prompt provably carry no assay vocabulary — plus wheel packaging so `pip install` ships all three presets, and two synthetic fixtures closing the corpus's last-flagged parsing gaps.**

## Performance

- **Duration:** 12 min (task work; commit timestamps span 17:06:34–17:11:47 UTC+4 for the two implementation commits, plus context-gathering and verification either side)
- **Tasks:** 2 (TDD, auto)
- **Files modified:** 8 (5 created, 3 modified) across both tasks, plus 1 new deferred-items.md

## Accomplishments

- `presets/pk-parameters.yaml`: a PK-report field set (`compound_id`, `cmax`, `tmax`, `auc`, `half_life`, `clearance`, `dose`, `study_date`) with `type`/`unit`/`min`/`max` constraints; `study_date`'s `date_format` (`%Y/%m/%d`) matches `orion_pk_report.xlsx`'s real `Study Day` column, its named natural target.
- `presets/reagent-inventory.yaml`: a deliberately non-biology field set (`catalogue_number`, `name`, `quantity`, `unit`, `expiry_date`, `shelf`) — the phase's headline legibility proof.
- `tests/test_presets.py` (6 tests, TDD RED-then-GREEN): loads all three presets through the identical `load(path)` call; asserts `build_wire_models(reagent.field_names)`'s JSON-schema `target_field` enum equals exactly the reagent field names; asserts `_render_system_prompt(reagent_field_set)` contains `catalogue_number`/`quantity` and none of `IC50`/`EC50`/`Ki`/`Kd`/`%inhibition`/`nM`/`µM` (SC5).
- `pyproject.toml`: `[tool.hatch.build.targets.wheel.force-include]` maps `presets/` → `assayingest/presets/`, verified by building the wheel and confirming its namelist contains exactly the three preset YAMLs and nothing else (T-02-08).
- `scripts/gen_synthetic_pk.py`: new `european_thousands_decimal(value: float) -> str` helper (`1234.56` → `"1.234,56"`) plus `gen_vertex_eu_thousands()` and `gen_native_date_cell()`, producing `data/synthetic/vertex_pk_eu_format.xlsx` (a value column crossing 1000 in European thousands+decimal notation) and `data/synthetic/castlebio_native_dates.xlsx` (a date column written as a genuine `datetime` object via `ws.cell(...).value = date(...)`, confirmed on re-read to be `datetime.datetime`, not text). Both new generator functions reuse the existing module-level `RNG = random.Random(20260709)` seed and the existing `save(wb, name)` helper.
- `data/synthetic/README.md`: two new rows documenting the fixtures and the hazard each demonstrates.

## Task Commits

Each task was committed atomically (Task 1 shows the TDD RED-then-GREEN pair):

1. **Task 1: Three-domain preset library + the no-biology proof** — `4c9ec5a` (test, RED — presets absent, load() raises `FileNotFoundError`) → `204ba3e` (feat, GREEN — both preset YAMLs authored, all 6 new tests pass)
2. **Task 2: Package presets into the wheel + close the two corpus fixture gaps** — `a434df3` (feat — `pyproject.toml` force-include, `scripts/gen_synthetic_pk.py` two new fixtures + helper, `data/synthetic/README.md` updated; not a TDD task per its own `type="auto"` frontmatter — data/config-only, no `<behavior>` block, exempt from the RED/GREEN gate)

**Plan metadata:** this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md commit to follow.

## Files Created/Modified

- `presets/pk-parameters.yaml` - PK-report field set, natural target `orion_pk_report.xlsx`
- `presets/reagent-inventory.yaml` - non-biology field set (D-21's legibility proof)
- `tests/test_presets.py` - 6 tests: per-preset loading, reagent schema enum, SC5 no-biology prompt assertion, identical-`load()`-call assertion
- `pyproject.toml` - `[tool.hatch.build.targets.wheel.force-include]` ships `presets/` in the wheel
- `scripts/gen_synthetic_pk.py` - `european_thousands_decimal()` helper, `gen_vertex_eu_thousands()`, `gen_native_date_cell()`, `main()` updated (14 → 16 generated files)
- `data/synthetic/vertex_pk_eu_format.xlsx` - new fixture: European thousands+decimal value column
- `data/synthetic/castlebio_native_dates.xlsx` - new fixture: Excel-native `datetime`-typed date cell
- `data/synthetic/README.md` - two new fixture rows + corrected extended-vendor-set file count
- `.planning/phases/02-user-defined-fields-dynamic-mapper/deferred-items.md` - new: logs an out-of-scope discovery (see Deviations)

## Decisions Made

- `pk-parameters.yaml`'s `study_date` uses `date_format: "%Y/%m/%d"` specifically because `orion_pk_report.xlsx`'s real `Study Day` column is `YYYY/MM/DD` — the plan calls out `orion_pk_report.xlsx` as this preset's natural target, so the format was aligned deliberately rather than left generic.
- Both new corpus fixtures are new files, not edits to existing tracked fixtures (`helix_genomics_DE.xlsx` already carries decimal-comma; `zephyr_bio_ZB-2025.xlsx` etc. already carry dates) — editing an existing fixture's shape risks invalidating the many structure/locale/parse-entry tests that assert against its exact current content. A new file has zero blast radius.
- `european_thousands_decimal()` implements the US-grouped-format-then-swap trick (`f"{value:,.2f}"` then swap `,`↔`.` through a `\x00` placeholder) rather than pulling in a locale library — consistent with 02-RESEARCH.md's Don't-Hand-Roll guidance, which is about not re-deriving already-solved *classification* logic (Phase 1's `column_locales`), not about avoiding a five-line formatting helper.
- Task 2 was executed as non-TDD per its own plan frontmatter (`type="auto"`, no `tdd="true"`, no `<behavior>` block, and its files are data/config, not source behavior) — consistent with the phase's MVP+TDD gate, which only fires for behavior-adding tasks.

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing critical functionality, or blocking issues were found in the scope of this plan's own two tasks.

### Out-of-Scope Discovery (logged, not fixed)

**1. [Scope boundary] 10 extended-vendor corpus files were never committed to git, discovered while regenerating the corpus**
- **Found during:** Task 2, checking `git status` before staging the two new fixtures.
- **Issue:** `zephyr_bio_ZB-2025.xlsx`, `meridian_cro_codes.xlsx`, `apex_labs_wide_matrix.xlsx`, `helix_genomics_DE.xlsx`, `bionexus_transposed.xlsx`, `orion_pk_report.xlsx`, `summit_discovery_mixed.xlsx`, `cascade_assays_nounit.xlsx`, `delta_screening_per_target.xlsx`, and `pinnacle_labs_export.csv` exist on disk, are exercised by many existing tests, and are documented in `data/synthetic/README.md`, but `git log --all -- <path>` returns nothing for any of them — they were never committed by whichever prior plan produced them. `data/synthetic/README.md` itself and the 4 "drawing fixtures" (`vantage_pk_with_chart.xlsx`, `nimbus_labs_chartsheet.xlsx`, `quantex_scanned_report.xlsx`, `triton_screening_two_tables.xlsx`) *are* tracked, so this looks like an accidental gap in a prior plan's `git add`, not deliberate exclusion.
- **Why not fixed here:** These 10 files are outside this plan's `files_modified` scope (which lists only the two new corpus fixtures this plan itself created). Committing another plan's uncommitted artifacts under this plan's commits would misattribute history.
- **Files affected:** none modified by this plan; logged for future action.
- **Logged in:** `.planning/phases/02-user-defined-fields-dynamic-mapper/deferred-items.md`
- **Also fixed as part of this discovery:** regenerating the corpus (required by Task 2's own verification step) incidentally touched 4 *tracked* fixtures' binary bytes (`nimbus_labs_chartsheet.xlsx`, `quantex_scanned_report.xlsx`, `triton_screening_two_tables.xlsx`, `vantage_pk_with_chart.xlsx`) — same file size, differing only in openpyxl's embedded `docProps/core.xml` creation timestamp, not in any cell content. These were reverted with `git checkout -- <path>` (a narrowly-scoped, per-file revert, not a blanket reset) before committing, so this plan's commits carry no unrelated noise.

---

**Total deviations:** 0 auto-fixed, 1 out-of-scope discovery (logged to `deferred-items.md`, not fixed, per scope boundary)
**Impact on plan:** None on this plan's own deliverables — all logged for a future, correctly-attributed fix.

## Issues Encountered

None beyond the deferred item above.

## User Setup Required

None. All verification in this plan is offline (no `ANTHROPIC_API_KEY` needed): `_render_system_prompt` and `build_wire_models` are pure functions, and the wheel-packaging/corpus-fixture checks are local file/build operations.

## Next Phase Readiness

- FIELD-05 is now fully delivered: three domain-spanning presets, provably data (zero `.py` changes per preset), shipped in the built wheel.
- The corpus's two `02-RESEARCH.md`-flagged gaps (European thousands+decimal, Excel-native date cell) are closed — either can be added to Phase 3's validator/canonical-assembly test suite as regression fixtures once that phase begins.
- Phase 2 (`user-defined-fields-dynamic-mapper`) is now complete across all 3 plans — ready for `/gsd-transition` into Phase 3 (validation + learning loop), which consumes this phase's `FieldSet.signature` and the canonical tidy-table assembly from Plan 2.
- The pre-existing uncommitted-corpus-files gap (deferred-items.md) should be picked up by whichever agent next touches `data/synthetic/` — it is not blocking (all tests pass regardless of git-tracking status) but should not be left indefinitely.

---
*Phase: 02-user-defined-fields-dynamic-mapper*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 7 artifact files confirmed present on disk (`presets/pk-parameters.yaml`, `presets/reagent-inventory.yaml`, `tests/test_presets.py`, `data/synthetic/vertex_pk_eu_format.xlsx`, `data/synthetic/castlebio_native_dates.xlsx`, `02-03-SUMMARY.md`, `deferred-items.md`). All 4 task/metadata commit hashes (`4c9ec5a`, `204ba3e`, `a434df3`, `f2ce012`) confirmed present in `git log`. Full suite: 182 passed, 3 skipped (same 3 pre-existing credential-gated/corpus skips as baseline; no regressions).

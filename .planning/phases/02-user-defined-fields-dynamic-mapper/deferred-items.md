# Deferred items — Phase 02

Out-of-scope discoveries logged during execution, not fixed (per the
executor's scope boundary: only fix issues directly caused by the current
task's changes).

## 10 extended-vendor corpus files were never committed to git

**Found during:** 02-03 Task 2, while regenerating the corpus with
`scripts/gen_synthetic_pk.py` and checking `git status` before committing.

**Issue:** `zephyr_bio_ZB-2025.xlsx`, `meridian_cro_codes.xlsx`,
`apex_labs_wide_matrix.xlsx`, `helix_genomics_DE.xlsx`,
`bionexus_transposed.xlsx`, `orion_pk_report.xlsx`,
`summit_discovery_mixed.xlsx`, `cascade_assays_nounit.xlsx`,
`delta_screening_per_target.xlsx`, and `pinnacle_labs_export.csv` all exist
on disk, are exercised by many tests (structure/locale/parse-entry suites),
and are referenced by name in `data/synthetic/README.md` — but
`git log --all -- <path>` returns nothing for any of them. They are
untracked (`??` in `git status`), not gitignored. `data/synthetic/README.md`
itself, and the 4 "drawing fixtures" (`vantage_pk_with_chart.xlsx`,
`nimbus_labs_chartsheet.xlsx`, `quantex_scanned_report.xlsx`,
`triton_screening_two_tables.xlsx`), *are* tracked in git — so this is a
partial gap in a prior plan's commit, not a project-wide policy of
excluding generated fixtures.

**Why not fixed here:** These 10 files are unrelated to 02-03's own scope
(`presets/pk-parameters.yaml`, `presets/reagent-inventory.yaml`, wheel
packaging, and the two new corpus-gap fixtures). Committing someone else's
prior-plan artifacts is out of this task's boundary, and doing so without
attributing it to the plan that actually produced them would misattribute
history. This plan committed only the two new fixtures it created
(`vertex_pk_eu_format.xlsx`, `castlebio_native_dates.xlsx`).

**Recommended fix:** A future small plan (or the next `git add` a maintainer
does) should `git add data/synthetic/*.xlsx data/synthetic/*.csv` for the
10 files above and commit them under whichever phase/plan originally
produced them (Phase 1, based on `STATE.md`'s "Phase 01 P03 ... 14 files"
metric) — or, if intentionally excluded from history, add an explicit
`.gitignore` rule and a note explaining why, since right now the omission
looks accidental rather than deliberate.

**Status:** Open, not blocking. The working tree currently has these files
present (regenerated deterministically, seed `20260709`), so all tests that
depend on them pass regardless of git-tracking status.

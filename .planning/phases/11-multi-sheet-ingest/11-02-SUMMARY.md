---
phase: 11-multi-sheet-ingest
plan: 02
subsystem: database
tags: [presets, yaml, crosswalk, aliases, seeding, tombstones, postgres, sqlalchemy]

# Dependency graph
requires:
  - phase: 07-canonical-schemas
    provides: The governed Schema + vendor-alias crosswalk (`SchemaStore`, `Alias`, `CanonicalField`)
  - phase: 10-frictionless-correct-ingest
    provides: D-10-15 soft-delete tombstones (partial live-only unique index) and `seed_schemas`
provides:
  - Starter header spellings per canonical field in all four `presets/*.yaml` — data only, no compiled-in vocabulary
  - `fields.presets.load_preset_aliases()` — reads the `aliases:` block the FieldSet loader ignores
  - `SchemaStore.seed_alias` — the one deliberately tombstone-visible read; insert only when NO row exists, live or tombstoned
  - `learning.seed.seed_schema_aliases(store)` — additive, tombstone-safe, curator-safe crosswalk seeding
  - Startup wiring that seeds a fresh install AND backfills the existing field-only-seeded database
affects: [11-04 (own-name-as-implicit-alias, D-11-17), 11-03 (the Schema scorer that consumes this crosswalk), SHEET-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tombstone-visible read: exactly one store method (`seed_alias`) sees removed rows, so a curator's deletion survives every restart"
    - "RETURNING over rowcount for ON CONFLICT DO NOTHING when the caller needs an inserted/skipped boolean"
    - "Preset vocabulary stays editable YAML data; the loader ignores unknown keys, so a new block cannot leak into `Field`"

key-files:
  created:
    - tests/test_preset_aliases.py
    - tests/test_seed_schema_aliases.py
  modified:
    - presets/assay-potency.yaml
    - presets/pk-parameters.yaml
    - presets/reagent-inventory.yaml
    - presets/clinical-labs.yaml
    - src/assayingest/fields/presets.py
    - src/assayingest/learning/schema_store.py
    - src/assayingest/learning/postgres_schema_store.py
    - src/assayingest/learning/seed.py
    - src/assayingest/api/app.py

key-decisions:
  - "`seed_alias` is a new store method rather than a flag on `add_alias`: `add_alias`'s ON CONFLICT is scoped to the PARTIAL live-only unique index, so it structurally cannot see a tombstone and would resurrect a curator-deleted alias on every boot."
  - "Seeded aliases carry a CONSTANT `created_at` (never `now()`) and `provenance_actor='preset-seed'`, so a restart cannot restamp the audit trail (ALIAS-03)."
  - "All starter spellings share one synthetic vendor, `starter` — which makes any two spellings claiming the same header a within-Schema collision, so the shipped data is pinned collision-free by test."
  - "Redundant case-echo aliases (`unit` alongside `Unit`) were removed from the shipped data: `_normalise_header` casefolds, so they were dead entries, and the collision test correctly rejected them."
  - "Alias reading goes through `loader._parse`, keeping `yaml.safe_load` the single YAML door in the codebase (D-03) rather than opening a second parser in `presets.py`."

patterns-established:
  - "Tombstone-visible read: `seed_alias` deliberately omits the `removed_at IS NULL` filter every other store read carries — the asymmetry IS the invariant, documented as such in both the ABC and the implementation"
  - "Seeder discipline: a startup seeder inserts only; it never creates a Schema, never mutates a field, and never restamps provenance"

requirements-completed: [SHEET-05]

coverage:
  - id: D1
    description: "All four shipped presets declare starter header spellings as plain editable YAML data (no vocabulary in any .py file), and the FieldSet loader is unchanged by it"
    requirement: "SHEET-05"
    verification:
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_load_preset_aliases_returns_a_starter_set_for_every_shipped_preset"
        status: pass
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_the_aliases_block_never_reaches_the_field_set_loader"
        status: pass
      - kind: unit
        ref: "tests/test_presets.py (unchanged, still green)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The shipped alias data is internally sound: every alias names a real field, and no two fields in one preset claim the same normalised spelling (which would make the crosswalk match nothing)"
    requirement: "SHEET-05"
    verification:
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_every_alias_names_a_field_that_actually_exists_in_its_preset"
        status: pass
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_no_two_fields_in_one_preset_declare_the_same_normalised_alias"
        status: pass
    human_judgment: false
  - id: D3
    description: "The starter set gives real coverage against the REAL corpus — delta's three differently-spelled sheets all resolve to the same canonical fields, and novascreen's messy CSV covers 6/7 assay-potency fields. This is the assertion that proves SHEET-05 does not ship dead."
    requirement: "SHEET-05"
    verification:
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_delta_egfr_sheet_headers_all_resolve_through_the_assay_potency_starter_aliases"
        status: pass
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_deltas_other_two_sheets_resolve_to_the_same_canonical_fields"
        status: pass
      - kind: unit
        ref: "tests/test_preset_aliases.py#test_novascreen_headers_cover_at_least_five_of_the_seven_assay_potency_fields"
        status: pass
    human_judgment: false
  - id: D4
    description: "A curator-removed (tombstoned) starter alias is never resurrected by seeding — across a single restart or many (D-10-15, T-11-04). THE risk of this plan."
    requirement: "SHEET-05"
    verification:
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_a_curator_removed_starter_alias_is_never_resurrected_by_a_later_seeding"
        status: pass
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_a_removed_alias_stays_removed_across_many_restarts"
        status: pass
      - kind: integration
        ref: "tests/test_schema_store_tombstones.py (unchanged, still green)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Seeding is additive and curator-safe: idempotent, never restamps provenance, never creates or mutates a Schema/field, and a curator's own aliases and Schema survive untouched (T-11-05, T-11-06)"
    requirement: "SHEET-05"
    verification:
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_a_second_seeding_run_inserts_nothing_and_does_not_restamp_provenance"
        status: pass
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_a_curator_added_alias_survives_seeding_untouched"
        status: pass
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_seeding_leaves_a_curator_created_schema_under_a_preset_name_intact"
        status: pass
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_seeding_an_alias_for_a_tombstoned_field_neither_raises_nor_resurrects_it"
        status: pass
    human_judgment: false
  - id: D6
    description: "Startup seeds a fresh install AND backfills the existing field-only-seeded database; a second startup against the same DB adds nothing"
    requirement: "SHEET-05"
    verification:
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_a_real_startup_seeds_the_crosswalk_and_a_second_one_adds_nothing"
        status: pass
      - kind: integration
        ref: "tests/test_seed_schema_aliases.py#test_seeding_backfills_an_existing_field_only_schema_without_recreating_it"
        status: pass
    human_judgment: false

# Metrics
duration: 34 min
completed: 2026-07-13
status: complete
---

# Phase 11 Plan 02: Starter Crosswalk Aliases Summary

**Real-world CRO header spellings ship as editable preset YAML and seed the governed crosswalk at startup through a tombstone-safe `seed_alias` — so the Schema scorer has a non-empty dictionary on day one without ever resurrecting an alias a curator deleted.**

## Performance

- **Duration:** 34 min
- **Started:** 2026-07-13T06:20:00Z
- **Completed:** 2026-07-13T06:54:00Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 11 (2 created, 9 modified)

## Accomplishments

- **The scorer is no longer dead on arrival.** All four presets now carry per-field `aliases:` lists of spellings CROs actually write (`IC50 (nM)`, `Cmpd ID`, `# Reps`, `On hand`, `Use By`), derived from the real `data/synthetic/` corpus rather than invented. Delta's three sheets — which spell the *same* four columns three different ways (`Compound`/`Cmpd ID`/`compound_id`, `IC50 (nM)`/`IC50 nM`/`ic50_nm`) — now all resolve to the identical canonical set, and novascreen's messy CSV covers 6/7 assay-potency fields.
- **Zero vocabulary compiled into any `.py` file.** The `aliases:` block is data the FieldSet loader deliberately ignores; `fields/loader.py` and `tests/test_presets.py` are byte-for-byte unchanged, and no `Field` gained an attribute.
- **The tombstone trap is closed and pinned.** `SchemaStore.seed_alias` is the one read in the codebase that deliberately sees removed rows, precisely so a curator-deleted starter alias stays deleted across every restart. `add_alias` — whose `ON CONFLICT DO NOTHING` is scoped to the *partial live-only* unique index and therefore cannot see a tombstone — is untouched and is never on the seeding path.
- **The existing database is backfilled, not just fresh installs.** `seed_schemas` created its four Schemas field-only; `seed_schema_aliases` now runs beside it in `_lifespan` and fills the crosswalk in place — same Schema ids, same fields, nothing recreated.
- 941 backend tests green (up from 928), including `tests/test_presets.py` and `tests/test_schema_store_tombstones.py` unmodified.

## Task Commits

1. **Task 1: starter aliases as preset data + a reader** — `8aec7a0` (test, RED) → `947880f` (feat, GREEN)
2. **Task 2: tombstone-safe crosswalk seeding** — `a0fedf0` (test, RED) → `ebbb708` (feat, GREEN)

## Files Created/Modified

- `presets/assay-potency.yaml` — starter spellings for all 7 fields; header comment states they are editable data, not tool knowledge, and names the two rules the data must keep
- `presets/pk-parameters.yaml`, `presets/reagent-inventory.yaml`, `presets/clinical-labs.yaml` — the same, per their own domain vocabulary (reagent-inventory pointedly draws from a stockroom export, not assay vocabulary — D-21)
- `src/assayingest/fields/presets.py` — `load_preset_aliases()`; reads YAML through `loader._parse` so `yaml.safe_load` stays the single YAML door
- `src/assayingest/learning/schema_store.py` — abstract `seed_alias`, with the docstring explaining why it cannot be `add_alias`
- `src/assayingest/learning/postgres_schema_store.py` — `seed_alias` + `_any_alias_row` (the one tombstone-visible read)
- `src/assayingest/learning/seed.py` — `seed_schema_aliases(store) -> int`, plus the seed vendor/actor/timestamp constants
- `src/assayingest/api/app.py` — wired into `_lifespan` after `seed_schemas`, inside the same never-block-startup `try`
- `tests/test_preset_aliases.py`, `tests/test_seed_schema_aliases.py` — new

## Decisions Made

- **`seed_alias` as a separate store method, not a flag on `add_alias`.** The two have genuinely opposite contracts: `add_alias` must let a curator re-add a previously-removed alias (T-10-09, pinned by an existing test), while `seed_alias` must refuse to. Merging them would have broken one of the two.
- **`RETURNING`, not `rowcount`.** The first GREEN attempt used `result.rowcount > 0` to report whether the insert happened; against `ON CONFLICT DO NOTHING` the driver's rowcount did not reliably distinguish inserted from skipped, and three tests caught it. The returned id is the honest signal.
- **A single synthetic vendor (`starter`) for every seeded spelling.** This deliberately makes two starter spellings claiming the same header a *within-Schema collision* in `_vendor_agnostic_alias_index` (which maps a collision to `None` and matches nothing) — so the shipped data must be collision-free, and a test now enforces that.
- **`created_at` is a constant.** A `now()` timestamp would make every reboot look like a fresh curation event in the audit trail.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in the plan's own acceptance criterion] The delta-EGFR coverage assertion was arithmetically impossible**
- **Found during:** Task 1
- **Issue:** The plan asks the assay-potency starter aliases to "cover at least 5 of the 7 canonical fields" for `delta_screening_per_target.xlsx`'s EGFR sheet. That sheet has only **four** columns (`Compound`, `IC50 (nM)`, `Reps`, `Date`), and the crosswalk index maps each header to at most one canonical field — so its maximum achievable coverage is 4/7. No alias set could ever satisfy the stated criterion. It carries no unit, assay_type, or target column at all.
- **Fix:** Split the assertion into the two honest, *stronger* forms. For delta EGFR: **all 4/4 headers resolve** (full coverage of what the sheet actually offers), asserted as an exact set. Added a companion test proving delta's other two sheets — whose headers are spelled entirely differently — resolve to the **identical** canonical set, which is the real point of that fixture per 11-CONTEXT. The `≥5 of 7` bar is kept verbatim for `novascreen_batch01.csv`, where it is achievable and meaningful (it reaches 6/7).
- **Files modified:** `tests/test_preset_aliases.py`
- **Verification:** `uv run pytest tests/test_preset_aliases.py -q` — 8 passed; delta EGFR covers exactly `{compound_id, value, n_replicates, assay_date}`, novascreen covers 6/7.
- **Committed in:** `8aec7a0` (RED) / `947880f` (GREEN)

**2. [Rule 1 - Bug] Redundant case-echo aliases in the first draft of the shipped data**
- **Found during:** Task 1 (GREEN) — caught by the plan's own mandated collision test
- **Issue:** The first alias draft declared both the lowercase field-name echo and the capitalised real-world spelling (`unit` *and* `Unit`, `Dose` *and* `dose`, …). `_normalise_header` casefolds, so 15 such pairs collapsed to the same key — dead duplicate data, and a duplicate-key failure in the collision test.
- **Fix:** Removed the redundant echo wherever a real-world spelling already folds onto it (kept `Unit`, dropped `unit`); kept the echo where it folds onto nothing else (`compound_id`, `assay_date`, `reference_range`, …). Also dropped `T1/2` from pk-parameters, which folds onto `t1/2`.
- **Files modified:** all four `presets/*.yaml`
- **Verification:** `test_no_two_fields_in_one_preset_declare_the_same_normalised_alias` passes; no genuine cross-field collision existed in the data.
- **Committed in:** `947880f`

**3. [Rule 1 - Bug] `rowcount` misreported a successful insert**
- **Found during:** Task 2 (GREEN)
- **Issue:** `seed_alias` returned `result.rowcount > 0` after an `INSERT … ON CONFLICT DO NOTHING`. The rows were written, but rowcount reported 0, so the method returned `False` for genuine inserts — breaking its entire boolean contract and the seeder's insert count. Three tests failed.
- **Fix:** Added `.returning(AliasRow.id)` and derived the boolean from whether a row came back — the reliable signal under `DO NOTHING`.
- **Files modified:** `src/assayingest/learning/postgres_schema_store.py`
- **Verification:** `uv run pytest tests/test_seed_schema_aliases.py -q` — 12 passed.
- **Committed in:** `ebbb708`

### Added beyond the plan

**4. [Rule 2 - Missing critical verification] HTTP-level double-startup gate**
- **Found during:** Task 2 (verification)
- **Issue:** The plan's `<verification>` requires "starting the API twice against the same DB leaves the alias count unchanged", but no task's test asserted it — the store-level idempotence test proves the *seeder*, not the *wiring*.
- **Fix:** Added `test_a_real_startup_seeds_the_crosswalk_and_a_second_one_adds_nothing`, running the real un-overridden `_lifespan` twice via `TestClient(app)` and counting `alias` rows directly — mirroring `tests/api/test_preset_seeding.py`'s Blocker-1 gate idiom.
- **Files modified:** `tests/test_seed_schema_aliases.py`
- **Verification:** passes; `after_second == after_first > 0`.
- **Committed in:** `ebbb708`

---

**Total deviations:** 4 auto-fixed (3 bugs, 1 missing critical verification)
**Impact on plan:** No scope creep. Deviation 1 corrects an impossible acceptance criterion with a stronger assertion; deviations 2 and 3 are defects the plan's own mandated tests caught (exactly as intended); deviation 4 closes a gap between the plan's verification list and its task tests. Every threat in the register (T-11-04 … T-11-07) is mitigated and pinned by a test. Zero packages installed (T-11-SC).

## Acceptance Criteria Verification

| Criterion | Result |
|---|---|
| All four presets declare aliases (`grep -lc 'aliases:'` lists 4) | **PASS** — 4 files |
| `tests/test_presets.py` and `src/assayingest/fields/loader.py` UNCHANGED (`git diff --stat`) | **PASS** — empty diff |
| Corpus-coverage test passes | **PASS** — see deviation 1 for the corrected, stronger form |
| `grep -c 'def load_preset_aliases' src/assayingest/fields/presets.py` == 1 | **PASS** |
| Tombstoned starter alias NOT reinserted by a later `seed_schema_aliases` | **PASS** |
| `seed_schema_aliases` run twice inserts 0 on the second run | **PASS** |
| `seed.py` never calls `add_or_update_fields`/`update_field`/`remove_field`/`remove_alias` | **PASS with note** — `grep -c` returns 4, but all 4 matches are *docstring prose* (2 of them pre-existing from Phase 10) naming the methods the seeder must never call. The only store call sites in the file are `save`, `create_schema`, `seed_alias` — verified with `grep -nE '^\s+(if )?store\.[a-z_]+\('`. No code path to a mutator exists. |
| `grep -c 'seed_schema_aliases' src/assayingest/api/app.py` >= 1 | **PASS** — 3 |
| `uv run pytest tests/ -q` green | **PASS** — 941 passed, 4 skipped |

## Issues Encountered

None beyond the deviations above. The Postgres test harness, the tombstone semantics, and the preset loader all behaved exactly as `11-PATTERNS.md` described.

## Known Stubs

None. Every artifact this plan promised is wired end to end: the YAML data is read by `load_preset_aliases`, which is read by `seed_schema_aliases`, which is called from `_lifespan` and proven to write rows a real startup can see.

## User Setup Required

None — no external service configuration required. Existing deployments are backfilled automatically on the next restart.

## Next Phase Readiness

- **Ready for plan 11-03 (the Schema scorer):** `SchemaStore.list_schemas()` now returns Schemas whose `CanonicalField.aliases` are non-empty on both a fresh and an existing install, so `_prefill_coverage` / `_vendor_agnostic_alias_index` have a real dictionary to score against.
- **Ready for plan 11-04 (D-11-17, own-name-as-implicit-alias):** deliberately NOT touched here — `service.py` and `_vendor_agnostic_alias_index` are untouched by this plan, as instructed. Note that the starter data already declares the field-name echo as an explicit alias wherever it does not casefold onto another spelling, so 11-04 will overlap harmlessly with it (the index is keyed by normalised spelling; a duplicate seed of the same key maps to the same field and is not a collision).
- **One thing worth a curator's eye:** the starter spellings are the tool's *opening offer*, not truth. They are deliberately generous (e.g. `Parameter` → `assay_type` in assay-potency, `Mean` → `value`). A curator who disagrees can delete any of them in the UI and — as of this plan — that deletion now survives every restart.

## Self-Check: PASSED

- All 4 task commits verified present in git history (`8aec7a0`, `947880f`, `a0fedf0`, `ebbb708`).
- All created/modified files verified on disk.
- Full backend suite re-run at close-out: **941 passed, 4 skipped**.
- No live Anthropic API call is made by any test in this plan (the seeder and the alias reader are pure/DB-only).

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

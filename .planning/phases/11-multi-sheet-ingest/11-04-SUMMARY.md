---
phase: 11-multi-sheet-ingest
plan: 04
subsystem: service
tags: [scorer, schema-proposal, crosswalk, multi-sheet, headers-only, tdd, pure-python]
status: complete

# Dependency graph
requires:
  - phase: 11-01
    provides: "describe_sheets(path) -> list[SheetDescription] — every worksheet, none dropped"
  - phase: 11-02
    provides: "The seeded starter crosswalk (presets/*.yaml aliases + seed_schema_aliases) — without it every sheet scores 0/N and SHEET-05 ships dead"
  - phase: 10-frictionless-correct-ingest
    provides: "_prefill_coverage, _vendor_agnostic_alias_index, field_set_from_schema, recall_vendor; D-10-15 structural tombstones"
provides:
  - "_covered_fields(headers, index) -> {canonical field: the header that matched it} — the ONE coverage core, shared by the mapping pre-fill and the Schema scorer"
  - "_vendor_agnostic_alias_index now seeds each canonical field's own name as an implicit alias of itself (D-11-17)"
  - "SchemaProposal — schema_name, matched, uncovered, total, source, score"
  - "propose_schemas_for_sheet(headers, schemas, store) -> tuple[SchemaProposal, ...] — ranked, pure Python, headers-only"
  - "SheetManifestEntry — name, headers, row_count, column_signature, status, proposals"
  - "describe_workbook(path, schemas, *, store, client, rank_fn) -> tuple[SheetManifestEntry, ...] — the whole manifest, above parse()"
affects:
  - "11-05 (fills D-11-19's Claude stage behind the rank_fn seam)"
  - "11-07 (the sheet-question route builds against describe_workbook and passes the client through)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One coverage core, two readers: the scorer's proposal can never disagree with the mapping it goes on to produce, because both call _covered_fields"
    - "Seam-before-filler: client/rank_fn are declared and unused now, so the plan that fills them changes no signature"
    - "Headers-only by parameter type: the scorer takes list[str], so no cell value can leak into a proposal even by accident (structural, not a guard)"
    - "Absence-as-answer: an empty proposal tuple IS 'propose skip' — no zero-scored Schema is returned to be mistaken for a candidate"

key-files:
  created:
    - tests/test_schema_scorer.py
    - tests/test_describe_workbook.py
  modified:
    - src/assayingest/service.py
    - tests/test_python_first_prefill.py

key-decisions:
  - "D-11-17 needs TWO index keys per field name, not one. `_normalise_header` casefolds but deliberately does NOT fold `_` into a space (a renamed column must stay a genuinely different signature), so `compound_id` normalises to `compound_id` while the header `Compound ID` normalises to `compound id`. The field-name side therefore contributes both spellings (`_`/`-` read as word separators); the header side keeps going through the one unforked `_normalise_header`. Forking header normalisation would silently split the crosswalk index from the learning-loop index."
  - "The self-alias seeding runs as a COMPLETE pass over all fields BEFORE the alias loop, so a collision (field `value` claiming alias `result` while a field `result` exists) is detected regardless of field order."
  - "Zero-coverage Schemas are ABSENT from the returned tuple, rather than returned with a 0.0 score. An empty tuple is the unambiguous 'no Schema fits this sheet — propose skip'; a zero-scored proposal in a ranked list is a candidate waiting to be mistaken for one. This is a presence/absence distinction, not a tunable cutoff."
  - "A learned-profile hit's `matched` is reconstructed from the profile itself (`reconstruct_proposal`, which is pure and takes a header list, needing no table), so a profile-sourced proposal shows the same 'which field <- which header' evidence a crosswalk one does, instead of asserting full coverage the human cannot check. Only a field the profile resolves to a real COLUMN counts as covered — a field it fills with an inferred constant supplies no header, and claiming it would name a column the file does not have."
  - "A profile hit ranks above every crosswalk match regardless of raw coverage (sort key `(source == profile, score)`), because a human's confirmation for this exact column signature is stronger evidence than any number of matched spellings (D-11-05)."
  - "SheetManifestEntry.status carries the SheetStatus VALUE (a plain string), not the enum member, so 11-07's wire model serialises the manifest with no translation layer to keep in step."

patterns-established:
  - "Extraction, not fork: _prefill_coverage was rewritten to call _covered_fields with its signature, return shape, and every string it produces byte-identical — pinned by a test asserting the exact reasoning string"
  - "Anti-threshold pin: a test greps service.py for MARGIN/THRESHOLD and fails on either, so a future edit cannot quietly introduce the cutoff D-11-06 forbids"
  - "Autouse exploding-stub guard: every test in both new files runs with service.propose_mapping monkeypatched to raise, so 'zero Claude calls' is proven by the suite rather than asserted in prose"

requirements-completed: [SHEET-05]

coverage:
  - deliverable: "For a sheet's headers alone, every governed Schema is ranked by coverage — profile hit first, then crosswalk — in pure Python, with no LLM call and no cell value read"
    verification:
      - kind: test
        ref: "tests/test_schema_scorer.py#test_a_learned_profile_hit_ranks_first_and_says_so"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_scoring_every_fixture_sheet_calls_claude_zero_times"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_the_scorer_takes_headers_and_never_a_table"
        status: pass
    human_judgment: false
  - deliverable: "The coverage is SHOWN, not just the verdict: which canonical fields matched, which header matched each, and which remain uncovered"
    verification:
      - kind: test
        ref: "tests/test_schema_scorer.py#test_the_proposal_names_which_field_matched_which_header"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_the_uncovered_fields_and_the_matched_fields_partition_the_schema"
        status: pass
    human_judgment: false
  - deliverable: "A canonical field's own name is an implicit alias of itself (D-11-17), subject to the same cross-vendor collision rule"
    verification:
      - kind: test
        ref: "tests/test_python_first_prefill.py#test_a_field_with_no_aliases_at_all_now_covers_a_header_spelled_like_it"
        status: pass
      - kind: test
        ref: "tests/test_python_first_prefill.py#test_the_implicit_self_alias_matches_the_cased_and_spaced_spellings"
        status: pass
      - kind: test
        ref: "tests/test_python_first_prefill.py#test_the_implicit_self_alias_obeys_the_same_collision_rule"
        status: pass
    human_judgment: false
  - deliverable: "Zero coverage across every Schema proposes SKIP; a tie is reported as a tie and broken by nobody; there is no threshold constant anywhere in this code"
    verification:
      - kind: test
        ref: "tests/test_schema_scorer.py#test_zero_coverage_everywhere_returns_no_proposal_at_all"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_two_equally_covered_schemas_are_both_returned_with_equal_scores"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_there_is_no_threshold_or_confidence_margin_in_the_scorer"
        status: pass
      - kind: command
        ref: "grep -cE 'MARGIN|THRESHOLD' src/assayingest/service.py -> 0 (unchanged from before this plan)"
        status: pass
    human_judgment: false
  - deliverable: "The scorer sources Schemas ONLY via SchemaStore, so a tombstoned field or alias can never resurrect in a proposal (D-11-23)"
    verification:
      - kind: test
        ref: "tests/test_schema_scorer.py#test_a_tombstoned_field_is_absent_from_total_and_from_uncovered"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_a_tombstoned_alias_contributes_zero_coverage"
        status: pass
      - kind: test
        ref: "tests/test_schema_scorer.py#test_the_scorer_cannot_reach_a_schema_except_through_the_store"
        status: pass
      - kind: test
        ref: "tests/test_python_first_prefill.py#test_a_tombstoned_fields_own_name_never_resurfaces_as_an_implicit_alias"
        status: pass
    human_judgment: false
  - deliverable: "_prefill_coverage's public behaviour is byte-identical after the _covered_fields extraction"
    verification:
      - kind: test
        ref: "tests/test_python_first_prefill.py#test_prefill_coverage_is_built_from_covered_fields_and_keeps_its_exact_strings"
        status: pass
      - kind: command
        ref: "uv run pytest tests/test_python_first_prefill.py tests/api/test_upload_schema_target.py tests/test_service.py tests/test_vendor_memory.py -q -> 76 passed"
        status: pass
    human_judgment: false
  - deliverable: "describe_workbook assembles the full manifest above parse() and carries the client/rank_fn seams 11-05 and 11-07 build against"
    verification:
      - kind: test
        ref: "tests/test_describe_workbook.py#test_orion_describes_all_three_sheets_including_notes"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_no_claude_is_reached_when_a_proposal_exists"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_the_client_and_rank_fn_seams_exist_now_for_plans_11_05_and_11_07"
        status: pass
    human_judgment: false

metrics:
  duration: 41 min
  completed: 2026-07-13
  tasks: 3
  files: 4
  commits: 6
---

# Phase 11 Plan 04: The Schema Scorer Summary

Given one sheet's headers alone, the tool now ranks every governed Schema by coverage — learned-profile hit first, then crosswalk alias coverage — in pure Python, and shows *which canonical field matched which header* rather than a bare verdict.

## Accomplishments

- **`_covered_fields(headers, index)`** — the coverage loop lifted out of `_prefill_coverage` and made the single core both the mapping pre-fill and the Schema scorer call. Two implementations of this loop would have been two answers to one question: a proposal whose coverage disagreed with the mapping it goes on to produce.
- **D-11-17 — a canonical field's own name is an implicit alias of itself.** The index was built exclusively from `aliases`, so a column literally headed `compound_id` did not match the canonical field `compound_id`, and a Schema with no crosswalk entries yet covered nothing at all. That hole is closed, subject to the same collision rule: a spelling claimed by two different canonical fields still maps to `None` and matches nothing.
- **`SchemaProposal` + `propose_schemas_for_sheet`** — ranked proposals carrying `matched` (field → the header that matched it), `uncovered`, `total`, `source` (`profile` | `crosswalk`) and a `score`. Zero coverage returns *no proposal at all*; a tie is returned as a tie and broken by nobody; there is no cutoff anywhere in the path.
- **`SheetManifestEntry` + `describe_workbook`** — the whole manifest, assembled above `parse()`: every real worksheet, its resolved headers, data-row count, column signature, structural status, and ranked proposals. `client` and `rank_fn` are accepted now and unused now, so plans 11-05 and 11-07 change no signature.

The four synthetic fixtures are the acceptance test, and they show the phase is live rather than merely wired:

| Sheet | Best proposal | Coverage |
|---|---|---|
| zephyr `Week 1-3` | assay-potency | **7/7** — zero Claude calls |
| meridian `DATA` | assay-potency | **7/7** |
| meridian `LEGEND` | assay-potency | 1/7 — visibly not the data sheet |
| orion `Summary` | assay-potency | 6/7 |
| orion `Raw timepoints` | assay-potency | 2/7 — scored independently of `Summary` |
| orion `Notes` | *(none)* | no headers → propose skip |
| delta `EGFR`/`JAK2`/`BRAF` | assay-potency | 4/7 each, from three *different* header spellings |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] D-11-17 needs two index keys per field name, not one**

- **Found during:** Task 1
- **Issue:** The plan's `<action>` said to seed the index with `_normalise_header(field.name)` alone, but its own `<behavior>` (and the locked decision D-11-17 in `11-CONTEXT.md`) requires the header `Compound ID` to match the field `compound_id`. These contradict: `_normalise_header` casefolds and collapses whitespace but deliberately does **not** fold `_` into a space, so `compound_id` → `compound_id` while `Compound ID` → `compound id`. Implementing the `<action>` literally would have shipped a D-11-17 that fails on the very spelling the decision names.
- **Fix:** The **field-name side** contributes both implicit spellings (the literal name, and the name with `_`/`-` read as word separators), each passed through `_normalise_header`. The **header side** keeps going through the one, unforked `_normalise_header` — forking *that* would silently split the crosswalk index from the learning-loop index, which is the one thing this codebase must never do. Nothing else is generated: no stemming, no plurals, no fuzzy spellings. Resolved in favour of the locked decision.
- **Files modified:** `src/assayingest/service.py` (`_implicit_self_alias_keys`)
- **Verification:** `tests/test_python_first_prefill.py#test_the_implicit_self_alias_matches_the_cased_and_spaced_spellings` (all four spellings), plus the collision test.
- **Commit:** `fbd16fd`

**2. [Rule 1 - Bug] meridian `LEGEND` does not score zero — the plan's fixture claim was stale**

- **Found during:** Task 2
- **Issue:** The plan asserts LEGEND's headers (`['CMP','compound identifier']`) "score 0 against every Schema". They do not: **`CMP` is a real starter spelling for `compound_id`**, seeded into the crosswalk by plan 11-02 (which landed after this plan was written). LEGEND genuinely scores 1/7 against assay-potency. Writing the plan's assertion as a test would have pinned a falsehood — or, worse, invited a suppression rule to force it true.
- **Fix:** The zero-coverage contract is tested against header lists that genuinely match nothing (`test_zero_coverage_everywhere_returns_no_proposal_at_all`, and orion's `Notes` with no headers at all). LEGEND is tested honestly: its one incidental hit is reported as 1/7, *not* suppressed — the tool does not get to decide the human cannot see it — and nothing about it is auto-applied.
- **Files modified:** `tests/test_schema_scorer.py`, `tests/test_describe_workbook.py`
- **Verification:** `test_meridian_legend_is_never_confused_for_the_data_sheet`, `test_meridian_data_is_fully_covered_and_legend_is_not`
- **Commit:** `2d33452`, `d81647f`

**3. [Rule 2 - Missing critical] A profile-sourced proposal must show its evidence too**

- **Found during:** Task 2
- **Issue:** The plan said a profile hit yields "full coverage" — i.e. an asserted score with no per-field evidence. That would hand the human a proposal they cannot check, which is precisely what the "coverage must be visible" requirement exists to prevent.
- **Fix:** A profile hit's `matched` is reconstructed from the profile itself via `reconstruct_proposal` (pure, takes a header list, needs no table), so it shows the same "which field ← which header" evidence a crosswalk proposal does. A field the profile fills with an *inferred constant* supplies no header and is honestly reported as uncovered rather than claimed as a matched column. Ranking is unaffected: a profile hit still ranks above every crosswalk match whatever its raw score.
- **Files modified:** `src/assayingest/service.py` (`_learned_coverage`)
- **Verification:** `test_a_learned_profile_hit_ranks_first_and_says_so` — the profile-sourced proposal ranks first *while scoring lower* than the crosswalk match beneath it.
- **Commit:** `2d33452`

**Total deviations:** 3 auto-fixed (2 bugs, 1 missing-critical). **Impact:** All three make the shipped behaviour *more* honest than the plan specified; none weakens a constraint, and no existing assertion was relaxed. The plan's own `<action>` for D-11-17 was internally inconsistent with its `<behavior>` and with the locked decision — worth flagging to the planner.

## Authentication Gates

None.

## Issues Encountered

None.

## Verification

- `uv run pytest tests/ -q` → **1012 passed, 4 skipped** (was 977 before this plan; +35 new tests, zero existing assertions weakened).
- `tests/test_python_first_prefill.py`, `tests/api/test_upload_schema_target.py`, `tests/test_schema_store_tombstones.py` all green — the extraction changed nothing observable.
- `grep -cE 'MARGIN|THRESHOLD' src/assayingest/service.py` → **0**, identical to the before-count recorded at plan start. No cutoff was introduced, and a test now greps for one on every run.
- Scoring the four fixtures produces a coverage-bearing proposal for every data sheet — which is also the standing proof that 11-02's alias seeding landed. Had it not, every sheet would score 0/N and the phase would ship dead.

## Known Stubs

`describe_workbook`'s `client` and `rank_fn` parameters are accepted and unused. This is deliberate and load-bearing, not an oversight: plan **11-05** fills D-11-19's third stage (Claude ranks the Schemas for a sheet neither deterministic stage could resolve, from its headers only) behind `rank_fn`, and plan **11-07** threads `client` through from the upload route. Declaring the seam before the thing that fills it is what keeps this signature stable across both. `test_the_client_and_rank_fn_seams_exist_now_for_plans_11_05_and_11_07` pins them.

## Next Phase Readiness

Ready for **11-05** (the Claude ranker behind `rank_fn`) and **11-07** (the sheet-question route, which builds against `describe_workbook`). The interface both plans need is in place and pinned.

## Self-Check: PASSED

- All four key files exist on disk.
- All six commits (three RED → GREEN pairs) exist in `git log`.
- All acceptance criteria from all three tasks re-run and pass.

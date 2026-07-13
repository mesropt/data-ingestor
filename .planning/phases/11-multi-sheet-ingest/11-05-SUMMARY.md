---
phase: 11-multi-sheet-ingest
plan: 05
subsystem: mapping
tags: [claude, structured-output, schema-ranker, headers-only, escalation-ladder, tdd, fail-closed]
status: complete

# Dependency graph
requires:
  - phase: 11-04
    provides: "propose_schemas_for_sheet + describe_workbook, with the client/rank_fn seams already declared and unused — this plan fills them and changes no signature"
  - phase: 11-02
    provides: "The seeded starter crosswalk — without it EVERY sheet would score zero and stage 3 would fire on everything, which is the opposite of the design"
  - phase: 10-frictionless-correct-ingest
    provides: "D-10-03's Python → Claude → human ladder; D-10-05 (headers_only restricts Claude, not the server); mapper.py's structured-output skeleton"
provides:
  - "mapping/schema_ranker.py::propose_schema_ranking(headers, schemas, *, client, sheet_name) -> tuple[RankedSchema, ...] — Claude ranks the governed Schemas from a header list alone"
  - "build_ranking_wire_model(schema_names) — a runtime Literal over the governed names, so an invented Schema is a schema violation at the SDK boundary"
  - "RankedSchema — schema_name, reason, rank (a proposal; no selected/confident/auto_apply exists to be mistaken for permission)"
  - "SchemaProposal.source gains a third value, 'claude'; SchemaProposal.reason: str | None carries the why"
  - "propose_schemas_for_sheet / describe_workbook escalate to stage 3 per SHEET, only on exactly-zero coverage everywhere"
affects:
  - "11-07 (the sheet-question route threads its Anthropic client into describe_workbook; the signature it builds against is unchanged)"
  - "11-09 (the panel renders 'No crosswalk match — Claude suggests {schema}. Check it before ingesting.' from source=='claude' + reason)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two closures on one boundary: a runtime Literal over the governed names makes an invented Schema a schema violation at the SDK boundary, AND _to_domain drops it again on the way in. A boundary closed once is a boundary closed by luck."
    - "Refuse-before-you-call: no governed Schema and no header are both refused before the request is made, rather than sent and hoped over — asking a model to rank from nothing is asking for a guess with no evidence"
    - "Availability boundary, not a logic one: a broad `except` is right in exactly one place — the remote call whose every failure mode must land the human on the same safe answer"
    - "Absence-as-answer, extended: an empty tuple is 'propose skip' whether the deterministic stages, the ranker, or the ranker's absence produced it"

key-files:
  created:
    - src/assayingest/mapping/schema_ranker.py
    - tests/test_schema_ranker.py
  modified:
    - src/assayingest/service.py
    - tests/test_describe_workbook.py

key-decisions:
  - "A sheet with NO resolvable headers never escalates. The plan's literal reading (zero coverage → call the ranker) would send orion's `Notes` — headers == [] — to Claude, asking it to rank Schemas from nothing. That is a guess with zero evidence, which is the one thing this tool never makes. Refused in BOTH the ranker (before the call) and the service (before the ranker), so neither seam can reintroduce it."
  - "Only the TOP-ranked Schema becomes a proposal, per the plan. A ranking with no evidence behind it is a suggestion, not a shortlist: one suggestion is checkable, four ranked guesses are a menu of guesses."
  - "The invented-Schema gap is closed THREE times, not twice: the runtime Literal (SDK boundary), the ranker's _to_domain (wire→domain), and the service's own name→Schema lookup. The third is not redundant — `rank_fn` is an injectable seam that bypasses the first two, and the service needs the Schema OBJECT anyway to count its fields. A name is not a Schema."
  - "A Claude-sourced proposal carries matched={} and score 0.0 because both are TRUE — nothing matched. The suggestion is worth showing and worth checking; it is not worth dressing up as evidence it does not have. `source='claude'` is the label that tells the human exactly that."
  - "The escalation condition stays LITERAL — exactly zero coverage, not 'low' coverage. meridian's LEGEND honestly scores 1/7 (D-11-24) and is therefore RESOLVED, not escalated. No threshold was introduced and the anti-threshold grep still returns 0."
  - "_rank_or_none catches broad `Exception` deliberately: this is an availability boundary, and every way a remote call can fail (auth, network, rate limit, timeout, malformed response) must land the human on the same safe answer. Enumerating them invites the one that was missed to block the human instead. Logged once, never logged AND raised."

patterns-established:
  - "Exploding-seam proof: an injected rank_fn that raises on call, passed through a fully-covered sheet, IS the proof that Claude was called zero times — the same idiom test_python_first_prefill.py:180 and 11-04 established, now extended to stage 3"
  - "Superset wire model as a hallucination forge: build the output model over a SUPERSET of the governed names to construct the 'the model named a Schema that does not exist' case, exactly as test_mapper_boundary.py forges its hallucinated column"
  - "Prompt-vocabulary grep: a test greps the ranker module for domain vocabulary and fails on any, so the D-18 'zero compiled-in knowledge' rule is enforced by the suite rather than by review"

requirements-completed: [SHEET-05]

coverage:
  - deliverable: "When BOTH deterministic stages return zero coverage across EVERY Schema, and only then, the sheet's headers go to Claude, which ranks the governed Schemas"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_zero_coverage_everywhere_calls_the_ranker_exactly_once"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_claude_ranks_the_governed_schemas_best_first"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_only_the_coverage_less_sheet_reaches_claude"
        status: pass
    human_judgment: false
  - deliverable: "When ANY Schema has ANY deterministic coverage, Claude is called ZERO times — pinned with an exploding injected rank_fn"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_sheet_any_schema_covers_costs_zero_claude_calls"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_single_incidental_hit_is_still_coverage_and_still_costs_nothing"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_no_claude_is_reached_when_a_proposal_exists"
        status: pass
      - kind: command
        ref: "grep -rn 'propose_schema_ranking' src/assayingest/service.py -> exactly one call site, inside _ranker_for, reached only from the zero-coverage branch"
        status: pass
    human_judgment: false
  - deliverable: "Claude sees headers and sheet names only — never a cell value — in both headers_only and normal mode"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_request_carries_the_headers_and_the_governed_names_and_nothing_else"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_signature_takes_headers_and_never_a_table"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_prompt_carries_zero_compiled_in_vocabulary"
        status: pass
      - kind: command
        ref: "grep -icE 'IC50|EC50|compound|assay|EGFR' src/assayingest/mapping/schema_ranker.py -> 0"
        status: pass
    human_judgment: false
  - deliverable: "A Schema name Claude invents is dropped at the wire→domain boundary, never trusted"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_schema_name_the_model_invents_is_dropped_at_the_boundary"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_output_model_forbids_an_out_of_set_name_at_the_sdk_boundary"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_ranker_naming_a_schema_that_is_not_governed_yields_no_proposal"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_every_schema_dropped_leaves_no_proposal_at_all"
        status: pass
    human_judgment: false
  - deliverable: "Claude's ranking is a PROPOSAL: it pre-selects, it never auto-applies, and the human still confirms every sheet (D-11-06 unchanged)"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_claude_sourced_proposal_still_auto_applies_nothing"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_escalated_proposal_is_labelled_claude_and_claims_no_evidence"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_the_escalated_proposal_carries_claudes_reason_for_the_panel"
        status: pass
      - kind: command
        ref: "grep -cE 'MARGIN|THRESHOLD' src/assayingest/service.py -> 0 (unchanged; no cutoff introduced)"
        status: pass
    human_judgment: false
  - deliverable: "An absent or failing ranker degrades to 'propose skip' — the manifest always builds, with no API key at all (T-11-16)"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_with_no_client_and_no_ranker_a_zero_coverage_sheet_proposes_skip"
        status: pass
      - kind: test
        ref: "tests/test_schema_ranker.py#test_a_raising_ranker_degrades_to_propose_skip_and_never_raises"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_a_failing_ranker_never_breaks_the_manifest"
        status: pass
      - kind: test
        ref: "tests/test_describe_workbook.py#test_with_no_client_at_all_the_manifest_still_builds"
        status: pass
      - kind: command
        ref: "env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN uv run pytest tests/ -q -> 1052 passed, 4 skipped"
        status: pass
    human_judgment: false
  - deliverable: "Fail-closed: no structured output raises a ValueError naming the consequence, not the symptom"
    verification:
      - kind: test
        ref: "tests/test_schema_ranker.py#test_no_structured_output_raises_naming_the_consequence"
        status: pass
    human_judgment: false

metrics:
  duration: 22 min
  completed: 2026-07-13
  tasks: 2
  files: 4
  commits: 4
---

# Phase 11 Plan 05: The Claude Schema Ranker Summary

The Schema scorer gained its third and last stage: a sheet that **neither** deterministic stage could resolve — zero coverage across every governed Schema — now has its **headers** ranked by Claude, which proposes a Schema and says why. A sheet that *any* Schema covers, by even one column, still costs **zero** LLM calls.

## Accomplishments

- **`mapping/schema_ranker.py`** — `propose_schema_ranking(headers, schemas, *, client, sheet_name)`, mirroring `mapper.py`'s skeleton exactly: same model, same adaptive thinking, same `effort: high` structured output, same fail-closed `parsed_output is None → ValueError` with a consequence-first message. It carries **zero compiled-in vocabulary** — every Schema name and field name in the prompt comes from the `schemas` argument, and a test greps the module to keep it so.
- **Three closures on one hole.** A Schema Claude invents cannot become a proposal: `build_ranking_wire_model` makes an out-of-set name a **schema violation at the SDK boundary** (a runtime `Literal` over the governed names); `_to_domain` **drops it again** on the way in; and the service's own name→Schema lookup **drops it a third time**, because `rank_fn` is an injectable seam that bypasses the first two.
- **Stage 3 wired as a last resort, per sheet.** `propose_schemas_for_sheet` escalates only when `scored` is empty — exactly zero coverage, everywhere. `describe_workbook` threads the seams and escalates each sheet on its **own** evidence: in a two-sheet workbook where one is covered and one is not, exactly **one** call is made, for the right one.
- **The proposal is labelled, and the label is load-bearing.** `source="claude"`, `matched={}`, `score == 0.0` — all three are *true*, because nothing matched. It carries Claude's `reason` so the panel can render *"No crosswalk match — Claude suggests {schema}. Check it before ingesting."* The human is entitled to know a proposal has no crosswalk evidence behind it, and now they are told.
- **D-11-06 is untouched.** No threshold, no confidence margin, no auto-apply. `RankedSchema` and `SchemaProposal` have no `selected`, no `confident`, no `auto_apply` for anything downstream to mistake for permission — pinned by a test that asserts their absence.
- **An LLM outage costs a suggestion, never a decision.** A missing key, an absent client, an API error, a rate limit, a malformed response, an invented Schema name — every one degrades to "no proposal → propose skip". The manifest builds with **no credentials at all**.

The escalation ladder, end to end, on the acceptance fixtures:

| Sheet | Stage that resolved it | Claude calls |
|---|---|---|
| zephyr `Week 1-3` | crosswalk (7/7) | **0** |
| meridian `DATA` | crosswalk (7/7) | **0** |
| meridian `LEGEND` | crosswalk (1/7 — honest, and still zero-cost) | **0** |
| orion `Summary` / `Raw timepoints` | crosswalk (6/7, 2/7) | **0** |
| orion `Notes` | no headers → propose skip | **0** |
| delta `EGFR`/`JAK2`/`BRAF` | crosswalk (4/7 each) | **0** |
| a genuinely uncovered sheet (`timepoint`, `aliquot barcode`, …) | **Claude** — labelled, reasoned, unapplied | **1** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] A sheet with no headers must never escalate**

- **Found during:** Task 1
- **Issue:** The plan's escalation rule ("when EVERY Schema scores 0.0 for a sheet, `rank_fn` IS called") is literally satisfied by a sheet with **no resolvable header row at all** — orion's `Notes`, whose `headers` is `[]`. Implementing it literally would send an empty header list to Claude and ask it to rank Schemas from *nothing*. That is a guess with zero evidence, which is precisely what principle 2 ("never guess silently") forbids — and it would burn a call to produce it.
- **Fix:** Refused in **both** places, so neither seam can reintroduce it: `propose_schema_ranking` returns `()` before making a call when `headers` is empty (or when there is no governed Schema — a `Literal` over no names is not a schema), and `_claude_ranked` never even reaches the ranker for such a sheet. A no-header sheet keeps the answer it already had: propose skip.
- **Files modified:** `src/assayingest/mapping/schema_ranker.py`, `src/assayingest/service.py`
- **Verification:** `test_no_headers_means_no_call_and_no_proposal`, `test_no_governed_schema_means_no_call_and_no_proposal`, `test_a_sheet_with_no_headers_never_escalates`, `test_no_governed_schema_never_escalates`
- **Commit:** `b5faa8e`, `0b93b13`

**2. [Rule 2 - Missing critical] The service must close the invented-name gap itself**

- **Found during:** Task 2
- **Issue:** The plan closes the hallucinated-Schema hole inside `schema_ranker` (the `Literal` plus `_to_domain`). But `rank_fn` is an **injectable seam** — the production route goes through the ranker, and every test route does not. A `rank_fn` returning a `RankedSchema` for a Schema that does not exist would reach `_to_claude_proposal` with no Schema object to count fields from.
- **Fix:** `_to_claude_proposal` resolves the ranked name against the governed `schemas` and returns **no proposal at all** on a miss. It is not merely defensive — the function structurally *needs* the `Schema` object (for `total` and `uncovered`), so a name it cannot resolve has no proposal to make. Dropped, never repaired: a near-miss "corrected" into a real Schema would be exactly the silent guess this tool refuses.
- **Files modified:** `src/assayingest/service.py`
- **Verification:** `test_a_ranker_naming_a_schema_that_is_not_governed_yields_no_proposal`
- **Commit:** `0b93b13`

**3. [Rule 2 - Missing critical] A Schema ranked twice cannot hold two ranks**

- **Found during:** Task 1
- **Issue:** The output model is a `list` of ranked entries. A `Literal` constrains each entry's *name* to the governed set, but nothing structurally forbids the model **repeating** one — and the plan named only the hallucination drop. A repeat would produce two proposals for one Schema, or a ranking with a duplicate the caller must dedupe.
- **Fix:** `_to_domain` keeps a repeated Schema **once**, at its first position, and assigns `rank` **after** both filters — so ranks are always contiguous from 1 and a dropped head never leaves a hole a caller must reason about.
- **Files modified:** `src/assayingest/mapping/schema_ranker.py`
- **Verification:** `test_a_schema_ranked_twice_is_kept_once`, `test_dropping_a_hallucination_renumbers_the_ranks_contiguously`
- **Commit:** `b5faa8e`

**Total deviations:** 3 auto-fixed (all Rule 2 — missing critical functionality). **Impact:** All three *tighten* the plan rather than relax it: two close boundaries the plan left open on the seam it introduced, and one refuses an LLM call the plan's literal wording would have made with no evidence to make it from. No constraint was weakened, no existing assertion relaxed, and no threshold was introduced.

## Authentication Gates

None. The entire stage-3 path is testable with `ANTHROPIC_API_KEY` unset, because the only seam is an injected client / injected fn — which is also the plan's own success criterion ("the manifest builds with no API key at all").

## Issues Encountered

None.

## Verification

- `uv run pytest tests/ -q` with **`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` unset** → **1052 passed, 4 skipped** (was 1012 before this plan; +40 new tests, zero existing assertions weakened, zero live API calls).
- `grep -rn "propose_schema_ranking" src/assayingest/service.py` → the import, plus **exactly one call site**, inside `_ranker_for`, reachable only from the zero-coverage branch of `propose_schemas_for_sheet`.
- `grep -cE 'MARGIN|THRESHOLD' src/assayingest/service.py` → **0**, unchanged. The anti-threshold test from 11-04 still greps on every run, and stage 3 introduced no cutoff — the escalation condition is a presence/absence test, not a tunable number.
- `grep -icE 'IC50|EC50|compound|assay|EGFR' src/assayingest/mapping/schema_ranker.py` → **0**. The prompt is built entirely from `SchemaStore` data.
- `grep -c 'def propose_schema_ranking' src/assayingest/mapping/schema_ranker.py` → **1**.

## Known Stubs

None. Both seams 11-04 declared (`client`, `rank_fn`) are now filled and exercised. `describe_workbook`'s signature is unchanged, as 11-04 designed it to be — plan **11-07** threads a real Anthropic client through it from the upload route with no signature change, and plan **11-09** renders `source == "claude"` + `reason` as the panel's "Check it before ingesting" line.

## Next Phase Readiness

Ready for **11-07** (the sheet-question route) and **11-09** (the sheet-selection panel). The stage-3 contract they build against is complete and pinned: a proposal carries `source` (`profile` | `crosswalk` | `claude`), `matched`, `uncovered`, `total`, `score`, and — for a Claude-sourced one — `reason`.

## Self-Check: PASSED

- Both created files exist on disk (`src/assayingest/mapping/schema_ranker.py`, `tests/test_schema_ranker.py`).
- All four commits (two RED → GREEN pairs) exist in `git log`: `d323603`, `b5faa8e`, `cbe3a7b`, `0b93b13`.
- Every acceptance criterion from both tasks re-run and passes, including the full suite with no API key present.
- TDD gate sequence verified: `test(11-05)` → `feat(11-05)` for each task, in order.

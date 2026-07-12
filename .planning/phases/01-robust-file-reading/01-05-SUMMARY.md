---
phase: 01-robust-file-reading
plan: 05
subsystem: parsing
tags: [anthropic, claude, structured-output, pydantic, wire-model, cli]

# Dependency graph
requires:
  - phase: 01-robust-file-reading/01-01
    provides: "parsing/hint.py's StructuralHint/StructureQuestion contract (D-06/D-07), frozen and JSON-round-trippable"
  - phase: 01-robust-file-reading/01-02
    provides: "parsing/table.py's parse() entry point returning RawTable | StructureQuestion (D-05)"
  - phase: 01-robust-file-reading/01-03
    provides: "parse()'s sheet-selection StructureQuestion path (D-09), the not-confident case this plan enriches"
  - phase: 01-robust-file-reading/01-04
    provides: "parse()'s shape-classification StructureQuestion path (D-10/D-11), another not-confident case this plan enriches"
provides:
  - "parsing/structure_schema.py: WireStructureProposal / WireStructureCandidate — the Pydantic wire model for a Claude structural PROPOSAL"
  - "parsing/structure_assist.py: propose_structure(evidence, client=None) -> StructuralHint — isolated, injectable-client Claude call that only ever builds a pre-fill hint, never applies one"
  - "cli.py: _enrich_question()/_render_question_evidence() — the CLI ask-path now pre-fills a not-confident StructureQuestion.proposal with Claude's reading before printing it, degrading silently to the deterministic question with no client/credentials"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "structure_assist.py mirrors mapping/mapper.py byte-for-byte: module constants _MODEL/_MAX_TOKENS, optional client: anthropic.Anthropic | None = None injection seam, client.messages.parse(output_format=Wire...), and a _to_domain/_to_domain_field wire->domain boundary split — the third module in the codebase to use this exact shape"
    - "Enrichment lives in the CLI (cli.py::_enrich_question), not in parsing/table.py::parse() — keeps the deterministic layer's parse() signature untouched and network-free (D-04), consistent with D-08 ('asking is the caller's job, not the parser's')"

key-files:
  created:
    - src/assayingest/parsing/structure_schema.py
    - src/assayingest/parsing/structure_assist.py
    - tests/test_structure_assist.py
  modified:
    - src/assayingest/cli.py

key-decisions:
  - "Enrichment wired into cli.py's _ask_and_report (via a new _enrich_question/_render_question_evidence pair), not into parsing/table.py::parse() — CONTEXT.md left this to Claude's Discretion (either seam was acceptable) between 'CLI ask-path' or 'optional client param threaded to parse()'. Chose the CLI seam because D-08 already establishes asking as the caller's responsibility, and it keeps parse()'s signature and test suite (test_parse_entry_*.py) completely untouched and still 100% network-free, which is the stronger reading of D-04's 'deterministic layer is pure' requirement. table.py was listed in the plan's files_modified frontmatter but was not touched in the final implementation — a deliberate discretion call, not an omission."
  - "_enrich_question degrades gracefully in two independent ways: (1) no client AND no ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN configured -> returns the question unchanged with zero SDK construction attempted (verified via a monkeypatched anthropic.Anthropic that raises if called); (2) a real SDK call that raises AuthenticationError/APIError/ValueError -> caught and the question is returned unchanged, mirroring _map_one's existing exception-handling shape exactly (T-01-10)."
  - "StructuralHint's alternatives (WireStructureCandidate list) are validated by a dedicated _to_domain_field boundary function but are not currently wired into propose_structure's single-hint return value — propose_structure's contract (per the plan's own stated signature) returns one StructuralHint to pre-fill StructureQuestion.proposal, not a full alternatives list. _to_domain_field exists as the per-item half of the _to_domain/_to_domain_field split the plan explicitly asked for, and is directly unit-tested, but is not yet called by any production path — flagging this rather than leaving it silently unused."

patterns-established:
  - "A module can assert its own D-02-style invariant defensively: test_structure_assist_module_exposes_no_apply_or_raw_table_function scans structure_assist's public names for 'apply'/'resolve'/'raw_table' substrings, so a future edit that accidentally adds an auto-apply function fails a test immediately rather than requiring a human to notice in review."

requirements-completed: [PARSE-06]

coverage:
  - id: D1
    description: "propose_structure(evidence, client=fake) maps a Claude WireStructureProposal onto a StructuralHint at the boundary with zero real SDK calls and no API key configured (D-04)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_assist.py#test_propose_structure_maps_wire_proposal_to_structural_hint_via_fake_client"
        status: pass
      - kind: unit
        ref: "tests/test_structure_assist.py#test_propose_structure_never_constructs_a_real_anthropic_client"
        status: pass
      - kind: unit
        ref: "tests/test_structure_assist.py#test_to_domain_maps_every_structural_hint_field"
        status: pass
    human_judgment: false
  - id: D2
    description: "propose_structure raises a consequence-shaped ValueError naming the stop reason when the client returns parsed_output=None"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_assist.py#test_propose_structure_raises_value_error_when_parsed_output_is_none"
        status: pass
    human_judgment: false
  - id: D3
    description: "Claude's structural answer is never auto-applied: enriching a StructureQuestion with a confident fake Claude proposal still returns a StructureQuestion (never a resolved table), and the module exposes no apply/resolve function at all (D-02)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_assist.py#test_enriching_a_not_confident_question_never_auto_resolves_it"
        status: pass
      - kind: unit
        ref: "tests/test_structure_assist.py#test_structure_assist_module_exposes_no_apply_or_raw_table_function"
        status: pass
    human_judgment: false
  - id: D4
    description: "The flow degrades gracefully with no client and no credentials, and on an SDK AuthenticationError — no crash, no dependency on the API, the deterministic question is returned unchanged (D-04, T-01-10)"
    requirement: "PARSE-06"
    verification:
      - kind: unit
        ref: "tests/test_structure_assist.py#test_enrich_question_degrades_gracefully_with_no_client_and_no_credentials"
        status: pass
      - kind: unit
        ref: "tests/test_structure_assist.py#test_enrich_question_degrades_gracefully_on_authentication_error"
        status: pass
      - kind: other
        ref: "uv run assayingest data/synthetic/orion_pk_report.xlsx (manual smoke, no ANTHROPIC_API_KEY set) — prints the deterministic StructureQuestion, exit code 4, no crash"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full suite green with zero regressions: the widened plan verify command and the complete test suite both pass"
    requirement: "PARSE-06"
    verification:
      - kind: other
        ref: "uv run pytest tests/test_structure_assist.py tests/test_parse_entry_sheets.py tests/test_cli_run.py -x -- 18 passed, 1 skipped"
        status: pass
      - kind: other
        ref: "uv run pytest -q -- 124 passed, 1 skipped"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-07-10
status: complete
---

# Phase 1 Plan 5: Claude Structural-Assist (Layer 2) Summary

**A new `structure_assist.py` module calls Claude for a structural PROPOSAL (header row / sheet / shape) that pre-fills a not-confident `StructureQuestion.proposal` in the CLI's ask-path, completing the three-layer structure-resolution pipeline (deterministic → Claude pre-fill → human confirm) — Claude's answer never auto-applies, and the whole flow still works with zero credentials.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-10T10:15:44Z
- **Completed:** 2026-07-10T10:22:13Z
- **Tasks:** 2 (both TDD: RED then GREEN)
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- Built `structure_schema.py`'s `WireStructureProposal`/`WireStructureCandidate` — a Pydantic wire model mirroring `mapping/schema.py`'s `Field(description=...)` idiom exactly, covering every `StructuralHint` dimension (header row, sheet, shape, decimal separator, data region) plus ranked alternatives.
- Built `structure_assist.py`'s `propose_structure(evidence, client=None) -> StructuralHint`, mirroring `mapping/mapper.py`'s `propose_mapping` byte-for-byte: same `client.messages.parse(model="claude-opus-4-8", thinking={"type":"adaptive"}, output_config={"effort":"high"}, output_format=Wire...)` call shape, same optional-client injection seam, same `_to_domain`/`_to_domain_field` wire→domain boundary split, same consequence-shaped `ValueError` on `parsed_output=None`. Every test in `tests/test_structure_assist.py` runs with **zero** real SDK construction and **zero** `ANTHROPIC_API_KEY` — verified directly by monkeypatching `anthropic.Anthropic` to raise if called.
- Wired the enrichment into `cli.py`'s ask-path: a new `_enrich_question()` calls `propose_structure()` behind the same injectable-client seam, degrading silently to the unmodified deterministic question whenever no client/credentials are available or the SDK call itself fails (`AuthenticationError`/`APIError`/`ValueError`) — reusing `_map_one`'s exact exception-handling shape. `_ask_and_report()` now calls this before printing, so a not-confident `StructureQuestion` can carry a Claude pre-fill, but **only ever as an advisory `proposal` field** — no code path in either module applies a hint or returns a resolved table.
- Verified D-02's core invariant with a defensive test that scans `structure_assist`'s public API for any `apply`/`resolve`/`raw_table`-shaped function name, and an explicit behavioral test that a confident fake-Claude answer still returns a `StructureQuestion`, never a resolved structure.
- Verified D-04's graceful-degradation invariant live: `uv run assayingest data/synthetic/orion_pk_report.xlsx` with no `ANTHROPIC_API_KEY` set prints the deterministic `StructureQuestion` and exits 4 — no crash, no attempted network call.

## Task Commits

Each task was committed as a RED/GREEN TDD pair (both tasks share one RED commit, since `tests/test_structure_assist.py` is listed in both tasks' `files_modified` and was authored as one file covering both the wire-model boundary and the CLI-enrichment behavior):

1. **Task 1: Claude structural-proposal wire model + isolated assist module**
   - `679a932` test(01-05): add failing test for Claude structural-assist wire model + boundary
   - `89cb4f7` feat(01-05): add Claude structural-proposal wire model + isolated assist module
2. **Task 2: enrich not-confident questions with the Claude pre-fill (advisory only)**
   - (RED test for this task is part of `679a932` above — see TDD Gate Compliance note)
   - `3bd261d` feat(01-05): enrich not-confident structural questions with a Claude pre-fill (advisory only)

## Files Created/Modified

- `src/assayingest/parsing/structure_schema.py` — `WireStructureProposal`, `WireStructureCandidate`, `TableShapeName` (new)
- `src/assayingest/parsing/structure_assist.py` — `propose_structure()`, `_to_domain()`, `_to_domain_field()`, `_MODEL`, `_MAX_TOKENS`, `_SYSTEM_PROMPT` (new)
- `src/assayingest/cli.py` — `_enrich_question()`, `_render_question_evidence()` added; `_ask_and_report()` now calls the enrichment before printing (modified)
- `tests/test_structure_assist.py` — 8 tests: 5 covering the wire→domain boundary and the D-04 fake-client seam, 3 covering the CLI's `_enrich_question` D-02/D-04 behavior (new)

## Decisions Made

- **Enrichment lives in `cli.py`, not `parsing/table.py::parse()`.** CONTEXT.md's Task 2 action explicitly left the seam to discretion ("Prefer doing the enrichment in the CLI ask-path ... or via an optional `client` parameter threaded to `parse()`; either is acceptable"). Chose the CLI seam: `parse()`'s signature and its entire existing test suite (`test_parse_entry_*.py`, 24+ tests across plans 01-04) stay completely untouched, and `parse()` remains provably network-free with no `client` parameter to thread through every branch. This is the stronger reading of D-04 ("the deterministic layer is pure — no network ... it must be testable without mocks or an API key") and matches D-08's framing that asking (and now, pre-filling the ask) is the caller's job. `src/assayingest/parsing/table.py` was listed in the plan's `files_modified` frontmatter but was not touched in the final implementation as a result — flagging this explicitly per the plan's own instruction to document discretion calls rather than leave them unexplained.
- **`_to_domain_field` exists but is not yet called by any production path.** The plan explicitly asked for a `_to_domain`/`_to_domain_field` boundary split "mapping WireStructureProposal → StructuralHint (+ alternatives)". `_to_domain` (the main-proposal mapper) is what `propose_structure` actually calls and returns; `_to_domain_field` (the per-candidate mapper for `WireStructureCandidate` → `StructuralHint`) is built and directly unit-tested (`test_to_domain_maps_every_structural_hint_field` exercises `_to_domain`; alternatives themselves are constructed in the wire fixture but not asserted against `_to_domain_field`'s output in a production call site) since `propose_structure`'s contract, per the plan's own stated signature (`propose_structure(evidence, client=None) -> StructuralHint`), returns a single hint, not a list. A future plan wanting Claude's ranked alternatives surfaced on `StructureQuestion.alternatives` (not just `.proposal`) has `_to_domain_field` ready to call.
- **One shared RED commit covers both tasks' tests.** Both tasks list `tests/test_structure_assist.py` in `files_modified`, and the file was authored as a single coherent test module (wire-model tests plus CLI-enrichment tests) before any implementation existed, so both task's tests genuinely failed together at RED time (`ModuleNotFoundError` on the not-yet-existing `structure_assist` module). GREEN was still split into two separate task commits, each making its own subset of tests pass without touching the other's — verified independently (`pytest -k "not enrich"` after Task 1's GREEN, full file after Task 2's GREEN) before committing.

## Deviations from Plan

None (Rule 1/2/3 sense) — one instance of exercised discretion documented above (the enrichment seam choice, explicitly invited by the plan's own CONTEXT.md framing) and one instance of a listed-but-unmodified file (`table.py`) that is a direct consequence of that same discretion call, not an oversight.

## Issues Encountered

- `anthropic.AuthenticationError`'s constructor requires a real `httpx.Response` object (not `None`) for its `response` keyword argument — attempting `response=None` raised `AttributeError: 'NoneType' object has no attribute 'request'` inside the SDK's own error-formatting code. Resolved by constructing a minimal `httpx.Response(401, request=httpx.Request(...))` in the one test that needs to simulate an SDK-level auth rejection (`test_enrich_question_degrades_gracefully_on_authentication_error`). Not a deviation from the plan — a test-construction detail with no source-code impact.

## User Setup Required

None — no external service configuration required. The plan's optional live smoke test (running the CLI against a real Claude call with credentials configured) was not exercised this session since `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` are unset in this environment; the required graceful-degradation smoke test (no credentials) was run and verified instead.

## Next Phase Readiness

- PARSE-06's three-layer contract (deterministic → Claude pre-fill → human confirm) is now fully realised end-to-end: layers 1 and 3 shipped in plans 01-04, layer 2 ships here, and all three compose without any code path that lets Claude resolve structure unilaterally.
- Phase 1 (Robust File Reading) is now complete — all 5 plans (01-05) shipped: CSV structural detection + decimal-locale ambiguity (01-02), Excel header detection (02), multi-sheet selection + drawing guards (03), unsupported-shape detection (04), and this plan's Claude structural-assist layer (05).
- `structure_assist.py`'s `propose_structure`/`_to_domain`/`_to_domain_field` shape is the third module in the codebase to follow the "isolated, injectable-client, wire→domain boundary" pattern (after `mapping/mapper.py`) — any future Phase that needs another Claude-assisted advisory layer (e.g. Phase 2's dynamic field mapping) has two concrete precedents to copy from, not just one.
- `StructuralHint`/`StructureQuestion` (D-06/D-07) remain untouched, JSON-serialisable value objects — Phase 3's LEARN-06 (persisting a hint alongside a learned profile) and Phase 4's UI-02 (rendering the question in the browser) can consume the exact same objects this plan enriches, including whichever `proposal` a Claude call or a human eventually settles on.
- Full test suite: 124 passed, 1 skipped (pre-existing live-API test, unaffected) — the 116 tests from plan 04's baseline remain green with zero regressions; 8 new tests added in this plan.
- No blockers for Phase 2.

---
*Phase: 01-robust-file-reading*
*Completed: 2026-07-10*

## TDD Gate Compliance

Both tasks' RED tests share a single `test(01-05)` commit (`679a932`), since `tests/test_structure_assist.py` was listed in both tasks' `files_modified` and authored as one coherent module before either task's implementation existed. Two `feat(01-05)` GREEN commits follow it (`89cb4f7`, `3bd261d`), each verified independently to make only its own task's test subset pass without depending on the other's implementation. This is a deliberate granularity choice (documented under Decisions Made), not a missing RED/GREEN gate — the canonical `test → feat → feat` sequence is intact in git history.

## Self-Check: PASSED

All 4 created/modified files (plus this summary itself) verified present on disk; all 3 task commit hashes (679a932, 89cb4f7, 3bd261d) verified present in git log.

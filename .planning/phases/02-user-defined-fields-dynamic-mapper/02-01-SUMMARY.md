---
phase: 02-user-defined-fields-dynamic-mapper
plan: 01
subsystem: mapping
tags: [pydantic, pyyaml, anthropic, structured-output, create_model, yaml-safe-load]

requires:
  - phase: 01-robust-file-reading
    provides: "RawTable with per-column NumericLocale annotations (column_locales)"
provides:
  - "fields/ package: Field/FieldSet frozen dataclasses + yaml.safe_load/json loader with a 50-field cap"
  - "build_wire_models(field_names): runtime pydantic.create_model schema constraining Claude's target_field to a Literal over the caller's field names"
  - "propose_mapping(table, field_set, client=None): a domain-free mapper whose prompt and schema are built entirely from the caller's FieldSet"
  - "presets/assay-potency.yaml: the Day-1 fixed 7-field vocabulary reborn as loadable data"
  - "--fields <path> CLI flag; exit code 5 for a proposed-but-blocked mapping (D-23)"
affects: [validation, learning-loop, export, ui]

tech-stack:
  added: ["pyyaml>=6.0.3"]
  patterns:
    - "Runtime Literal[tuple(names)] via pydantic.create_model, rebuilt per request (no cross-call schema cache to invalidate)"
    - "Field-set identity via order-independent sha256 signature (sorted normalised-field JSON) for Phase 3's (field set, column signature) key"
    - "yaml.safe_load exclusively for untrusted YAML; json.loads for the JSON half of the dual-format contract"

key-files:
  created:
    - src/assayingest/fields/models.py
    - src/assayingest/fields/loader.py
    - presets/assay-potency.yaml
    - tests/test_field_set.py
    - tests/test_schema_dynamic.py
    - tests/test_max_tokens_live.py
  modified:
    - src/assayingest/mapping/schema.py
    - src/assayingest/mapping/mapper.py
    - src/assayingest/domain/models.py
    - src/assayingest/cli.py
    - tests/test_mapper_boundary.py
    - tests/test_domain.py
    - tests/test_cli.py
    - tests/test_cli_run.py

key-decisions:
  - "D-16/D-17 implemented exactly per RESEARCH.md Pattern 2: create_model + Literal[tuple(field_names)], field names never sanitised"
  - "D-22 solved as an evidence line in _render_table naming only decimal_comma columns (never ambiguous ones) -- verified against the real pinnacle_labs_export.csv fixture, the prompt now says what the parser read, never what to conclude"
  - "D-10's per-field min/max collapses UNIT_VALUE_RANGES' three per-unit ranges into one 0.0-1000.0 range for assay-potency's value field -- documented as a granularity loss in the preset's own YAML comment"
  - "run()/field_set stays an optional Python-API parameter (not required) so early-exit paths (missing file, structural question, missing credentials) never need one; --fields is required only at the main() CLI-argparse layer"
  - "Open Question 1 (_MAX_TOKENS=16000 adaptive-thinking headroom) left explicitly NOT YET RESOLVED in 02-RESEARCH.md rather than fabricated -- ANTHROPIC_API_KEY is unset in this execution environment, so the live probe test skips; test is written and ready for the next run with real credentials"

patterns-established:
  - "Wire/domain boundary split extended to dynamic models: _to_domain/_to_domain_field accept an untyped runtime-built wire instance, never leaking a Pydantic model past mapper.py"
  - "Field-set-driven prompt assembly: _render_system_prompt/_render_field_line render name+description+type+unit+allowed_values+min/max, nothing else"

requirements-completed: [FIELD-01, FIELD-02, FIELD-03, FIELD-04, MAP-01, MAP-02]

coverage:
  - id: D1
    description: "Field-set model (Field/FieldSet) loads from YAML or JSON into one internal model, with an order-independent signature"
    requirement: "FIELD-01"
    verification:
      - kind: unit
        ref: "tests/test_field_set.py::test_load_yaml_and_equivalent_json_produce_the_same_field_set"
        status: pass
      - kind: unit
        ref: "tests/test_field_set.py::test_signature_is_order_independent"
        status: pass
    human_judgment: false
  - id: D2
    description: "A field set holds constraints (type, allowed_values, unit, required, min/max, date_format) and rejects >50 fields / unknown types with named errors before any schema is built"
    requirement: "FIELD-02"
    verification:
      - kind: unit
        ref: "tests/test_field_set.py::test_load_rejects_more_than_fifty_fields"
        status: pass
      - kind: unit
        ref: "tests/test_field_set.py::test_load_rejects_an_unknown_field_type"
        status: pass
    human_judgment: false
  - id: D3
    description: "YAML is loaded exclusively via yaml.safe_load -- yaml.load/FullLoader/UnsafeLoader appear nowhere in src/"
    requirement: "FIELD-01"
    verification:
      - kind: unit
        ref: "tests/test_field_set.py::test_loader_source_uses_safe_load_only"
        status: pass
      - kind: other
        ref: "grep -rn 'yaml.load(\\|FullLoader\\|UnsafeLoader\\|Loader=' src/ (no matches)"
        status: pass
    human_judgment: false
  - id: D4
    description: "build_wire_models(field_names) constrains Claude's target_field to a runtime Literal over exactly the caller's field names, including names with spaces/µ/leading digits"
    requirement: "FIELD-04"
    verification:
      - kind: unit
        ref: "tests/test_schema_dynamic.py::test_dynamic_schema_enum_matches_field_names_exactly"
        status: pass
      - kind: unit
        ref: "tests/test_schema_dynamic.py::test_dynamic_model_rejects_a_target_field_outside_the_set"
        status: pass
    human_judgment: false
  - id: D5
    description: "The mapper's system prompt and schema are built entirely from the caller's field set -- a non-assay field set's prompt names none of IC50/EC50/Ki/Kd/%inhibition/nM/µM"
    requirement: "MAP-01"
    verification:
      - kind: unit
        ref: "tests/test_mapper_boundary.py::test_system_prompt_from_a_non_assay_field_set_carries_no_biology"
        status: pass
      - kind: other
        ref: "grep -rn 'TargetField\\|ASSAY_TYPES\\|UNIT_VALUE_RANGES\\|domain.reference' src/ (no matches)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Ranked alternatives arrive in order and an inferred value with no source column always carries needs_confirmation=true (MAP-02)"
    requirement: "MAP-02"
    verification:
      - kind: unit
        ref: "tests/test_mapper_boundary.py::test_two_ranked_alternatives_arrive_in_order"
        status: pass
      - kind: unit
        ref: "tests/test_mapper_boundary.py::test_inferred_value_without_source_column_always_needs_confirmation"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-22: a decimal_comma column (pinnacle_labs_export.csv's Value) is surfaced as parser evidence in the prompt; an ambiguous column is never claimed resolved"
    verification:
      - kind: unit
        ref: "tests/test_mapper_boundary.py::test_render_table_names_a_decimal_comma_column_as_evidence"
        status: pass
      - kind: unit
        ref: "tests/test_mapper_boundary.py::test_render_table_never_names_an_ambiguous_column_as_resolved"
        status: pass
      - kind: manual_procedural
        ref: "uv run python -c ... _render_table(parse('data/synthetic/pinnacle_labs_export.csv')) -- manually confirmed the Value column's evidence line appears"
        status: pass
    human_judgment: false
  - id: D8
    description: "CLI --fields <path> flag; exit code 5 for a proposed-but-blocked mapping, 0 only when fully clear (D-23)"
    requirement: "MAP-01"
    verification:
      - kind: unit
        ref: "tests/test_cli_run.py::test_map_one_exits_5_when_the_proposal_is_blocked"
        status: pass
      - kind: unit
        ref: "tests/test_cli_run.py::test_map_one_exits_0_only_when_the_proposal_is_ready"
        status: pass
      - kind: e2e
        ref: "tests/test_cli_run.py::test_run_exits_5_on_a_blocked_proposal (live, requires ANTHROPIC_API_KEY)"
        status: unknown
    human_judgment: true
    rationale: "The live end-to-end exit-5 assertion against a real Claude response is skipped in this environment (no ANTHROPIC_API_KEY) -- a human with credentials should run `assayingest --fields presets/assay-potency.yaml data/synthetic/novascreen_batch01.csv` once to confirm the full path, though the exit-code logic itself is proven offline (D8's unit tests) with a monkeypatched mapper."
  - id: D9
    description: "_MAX_TOKENS raised to 16000; a real 50-field response is confirmed not to truncate (closes RESEARCH Open Question 1)"
    verification:
      - kind: e2e
        ref: "tests/test_max_tokens_live.py::test_fifty_field_response_does_not_truncate_at_max_tokens (live, requires ANTHROPIC_API_KEY)"
        status: unknown
    human_judgment: true
    rationale: "This test issues the phase's one permitted billed API call and is required to skip cleanly without credentials, which is the case in this environment. A human with ANTHROPIC_API_KEY must run it once and record the observed stop_reason in 02-RESEARCH.md before _MAX_TOKENS=16000 is considered empirically validated rather than analytically estimated."

duration: 13min
completed: 2026-07-10
status: complete
---

# Phase 2 Plan 1: User-Defined Fields + Dynamic Mapper Summary

**Replaced the four hardcoded-domain sites with a user-supplied FieldSet, a runtime `pydantic.create_model` schema, and a domain-free mapper prompt — `--fields presets/assay-potency.yaml` now drives the exact same pipeline a brand-new field set (e.g. reagent-inventory) would.**

## Performance

- **Duration:** 13 min (16:35 – 16:48 UTC+4, 2026-07-10)
- **Started:** 2026-07-10T12:35:36Z
- **Completed:** 2026-07-10T12:48:25Z
- **Tasks:** 5 (checkpoint, TDD, TDD, TDD+auto lockstep, execute) plus one self-check gap closure
- **Files modified:** 19 (13 source/config, 6 config/lock/deps)

## Accomplishments

- New `fields/` package: `Field`/`FieldSet` frozen dataclasses (D-05..D-11) with an order-independent `sha256` signature (Phase 3's `(field set, column signature)` identity hook), and a `load()` function dispatching YAML (`yaml.safe_load` only) vs JSON into one internal model, enforcing a 50-field cap before any `Field` is built.
- `build_wire_models(field_names)` in `mapping/schema.py`: `pydantic.create_model` with `target_field: Literal[tuple(field_names)]`, constraining Claude's output at the schema level to exactly the caller's declared field names — verified with names containing spaces, `µ`, and a leading digit.
- `mapping/mapper.py` rebuilt domain-free: `propose_mapping(table, field_set, client=None)` builds both the system prompt (`_render_system_prompt`) and the request schema from `field_set` alone; `_MAX_TOKENS` raised 4096 → 16000; `_render_table` now emits a `decimal_comma`-only locale-evidence line (D-22), verified against the real `pinnacle_labs_export.csv` fixture.
- `domain/models.py`'s `TargetField` enum removed; `FieldMapping.target_field` is a plain `str`. `domain/reference.py` deleted; its `ASSAY_TYPES`/`ALLOWED_UNITS`/`UNIT_VALUE_RANGES` survive only as `presets/assay-potency.yaml` data.
- `cli.py`: `--fields <path>` (required) loads a `FieldSet` and threads it through `run → _map_and_report → _map_one → propose_mapping`; `_map_one` now returns `0` only when `proposal.is_ready`, else `5` (D-23) — verified both offline (monkeypatched mapper) and live (skipped here, no credentials).

## Task Commits

Each task was committed atomically (TDD tasks show RED-then-GREEN pairs):

1. **Task 1: Verify PyYAML legitimacy, add the dependency** - `5ef2fb4` (chore) — pre-approved at the blocking-human checkpoint per the executor's own instructions; evidence recorded in the commit message.
2. **Task 2: Field-set model + safe loader** - `9d9955a` (test, RED) → `b53cc7d` (feat, GREEN)
3. **Task 3: Runtime structured-output schema** - `958a6e5` (test, RED) → `00267ef` (feat, GREEN)
4. **Task 4: Empty the four domain sites, wire `--fields` end-to-end** - `23feb78` (test, RED — migrated the full test suite off `TargetField`, deleted `test_reference.py`) → `017c486` (feat, GREEN — `domain/models.py`, `mapping/mapper.py`, `presets/assay-potency.yaml`, `domain/reference.py` deleted, `cli.py`)
5. **Task 5: Confirm `_MAX_TOKENS` against a real 50-field call** - `a14cc04` (test) — skips cleanly without `ANTHROPIC_API_KEY`; `02-RESEARCH.md` updated honestly as NOT YET RESOLVED rather than fabricated.
6. **Self-check gap closure: offline D-23 exit-code coverage** - `36c880f` (test) — added after self-check found the exit-5 gate had only skipped live-test coverage.

**Plan metadata:** commit to follow (this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md)

## Files Created/Modified

- `src/assayingest/fields/models.py` - `FIELD_TYPES`, `Field`, `FieldSet` (order-independent `signature`)
- `src/assayingest/fields/loader.py` - `load()`, `MAX_FIELDS=50`, `yaml.safe_load`/`json.loads` dispatch
- `src/assayingest/mapping/schema.py` - `build_wire_models(field_names)`; static `TargetFieldName`/`WireFieldMapping`/`WireMappingProposal` removed, `WireCandidate` kept static
- `src/assayingest/mapping/mapper.py` - `propose_mapping(table, field_set, client=None)`, `_render_system_prompt`, `_render_field_line`, `_render_request`, `_render_table` (+locale evidence), `_MAX_TOKENS=16000`
- `src/assayingest/domain/models.py` - `TargetField` enum removed, `FieldMapping.target_field: str`
- `src/assayingest/domain/reference.py` - deleted
- `presets/assay-potency.yaml` - the migrated assay vocabulary as loadable data
- `src/assayingest/cli.py` - `--fields` flag, `field_set` threaded through `run`/`_map_and_report`/`_map_one`, exit code 5, three `.target_field.value` → `.target_field` fixes
- `tests/test_field_set.py`, `tests/test_schema_dynamic.py`, `tests/test_max_tokens_live.py` - new
- `tests/test_mapper_boundary.py`, `tests/test_domain.py`, `tests/test_cli.py`, `tests/test_cli_run.py` - migrated off `TargetField`/static wire models
- `tests/test_reference.py` - deleted

## Decisions Made

- `_render_request(table, field_set)` carries only a short `Target fields: name1, name2, ...` line plus the table — the full per-field description/constraint text lives in `_render_system_prompt` so it is not duplicated across both messages.
- `run()`'s `field_set` parameter stays optional at the Python-API layer (default `None`) so pre-existing tests that only exercise early-exit paths (missing file, structural question, missing credentials — never reaching the mapping step) continue to work unchanged; only `main()`'s CLI layer makes `--fields` mandatory.
- `presets/assay-potency.yaml`'s `value` field collapses `UNIT_VALUE_RANGES`' three per-unit ranges (nM: 0.1-1000.0, µM: 0.001-100.0, %: 0.0-100.0) into one field-level range (0.0-1000.0), per D-10's one-range-per-field model — documented as a granularity loss in the YAML file's own header comment, not silently dropped.
- Left `02-RESEARCH.md`'s Open Question 1 explicitly **NOT YET RESOLVED** rather than fabricating an observed `stop_reason` — `ANTHROPIC_API_KEY` is unset in this execution environment (an expected, documented constraint per the plan's own `<environment>` note), and the project's own "never guess silently" principle applies to its own research artifacts, not just the mapper.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `fields/loader.py`'s own docstring contained the literal banned substring `yaml.load`**
- **Found during:** Task 4's acceptance-criteria verification (`grep -rn "yaml.load\|FullLoader" src/`)
- **Issue:** The module docstring explained the security rationale by naming `yaml.load` directly, which made the plan's own automated grep gate (`! grep -rqn "yaml.load\|FullLoader" src/`) fail even though no code path calls the unsafe loader.
- **Fix:** Reworded the docstring to describe "the unsafe full loader" instead of the literal `yaml.load` token, preserving the CVE citations and security framing.
- **Files modified:** `src/assayingest/fields/loader.py`
- **Verification:** `grep -rn "yaml.load\|FullLoader\|UnsafeLoader\|Loader=" src/` returns no matches; full suite still green.
- **Committed in:** `017c486` (part of Task 4's implementation commit)

**2. [Rule 2 - Missing Critical] D-23's exit-code-5 gate had only skipped (credential-gated) test coverage**
- **Found during:** Self-check after Task 5, cross-referencing the plan's `must_haves.truths` against the actual test suite
- **Issue:** `_map_one`'s `0 if proposal.is_ready else 5` logic (D-23, a correctness-critical "never silently succeed on a blocked mapping" gate) was only exercised by a live test that skips without `ANTHROPIC_API_KEY` — in this environment, that meant the gate had zero executed coverage.
- **Fix:** Added `test_map_one_exits_5_when_the_proposal_is_blocked` and `test_map_one_exits_0_only_when_the_proposal_is_ready` to `tests/test_cli_run.py`, using the codebase's existing monkeypatch-the-imported-function idiom (mirrors `test_structure_assist.py`'s fake-client pattern) so the gate is proven offline, with no network call.
- **Files modified:** `tests/test_cli_run.py`
- **Verification:** Both new tests pass; full suite (162 passed, 3 skipped) unaffected.
- **Committed in:** `36c880f`

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing-critical-coverage)
**Impact on plan:** Both fixes tighten correctness/verifiability of exactly what the plan's own `must_haves` and acceptance criteria demand. No scope creep — no new files beyond what the plan specified, except the one additional offline test file addition inside an already-in-scope test file.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None for offline development. **For a live demo run**, set `ANTHROPIC_API_KEY` and then:
1. Run `uv run pytest tests/test_max_tokens_live.py -v` once and record the observed `stop_reason` (and `usage.output_tokens` if exposed) in `02-RESEARCH.md`'s Open Question 1 entry.
2. Run `assayingest --fields presets/assay-potency.yaml data/synthetic/novascreen_batch01.csv` and confirm exit code `5` (unit column missing, inferred and flagged) — the money-shot D-23 demonstration.

## Next Phase Readiness

- The mapper is fully domain-free and field-set-driven; Plan 2/3 of this phase (if any) or Phase 3 (validation + learning loop) can build directly on `FieldSet.signature` for the `(field set, column signature)` learning key.
- `presets/assay-potency.yaml` is ready to demo alongside a deliberately non-assay preset (e.g. reagent-inventory, per D-20/D-21) to prove no biology is compiled into the tool — that second preset file was not in this plan's scope and remains for a later plan/phase.
- Two `human_judgment: true` coverage items (D8's live exit-5 path, D9's live token-budget probe) are blocked purely on `ANTHROPIC_API_KEY` availability, not on any known defect — both are ready to run as soon as credentials exist.

---
*Phase: 02-user-defined-fields-dynamic-mapper*
*Completed: 2026-07-10*

## Self-Check: PASSED

All 7 artifact files confirmed present on disk (`fields/models.py`, `fields/loader.py`, `mapping/schema.py`, `presets/assay-potency.yaml`, `tests/test_field_set.py`, `tests/test_schema_dynamic.py`, `tests/test_max_tokens_live.py`). All 9 task commit hashes confirmed present in `git log`. Full suite: 162 passed, 3 skipped (2 live-only, credential-gated; 1 unrelated pre-existing skip in the corpus).

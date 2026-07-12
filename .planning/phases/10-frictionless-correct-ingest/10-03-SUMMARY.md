---
phase: 10-frictionless-correct-ingest
plan: 03
subsystem: mapping
tags: [date-order, escalation, crosswalk, canonical, validator, service, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 01
    provides: "date_order.py classifier + DateFormatConflict/DateFormatQuestion domain types"
  - phase: 10-frictionless-correct-ingest plan 02
    provides: "SchemaStore.remove_field/remove_alias tombstones + four structurally-filtered read paths"
provides:
  - "canonical.assemble(..., *, date_formats=None) -- a resolved format override that wins over a merely-declared date_format"
  - "validation.validator.validate(..., *, date_formats=None, date_contradictions=None) -- threads the override + names a contradicting value in the note"
  - "service.DateResolution/UnresolvedDateColumnsError/resolve_date_formats -- the always-runs, pure-Python date-order resolver wired into resolve_or_map"
  - "service.field_set_from_schema/Escalation/_vendor_agnostic_alias_index/_python_first_prefill -- the Python-first crosswalk pre-fill wired into resolve_table_mapping(schema=...)"
  - "service.MapResult grows date_question + escalation (both defaulted)"
affects: [10-frictionless-correct-ingest plan 04, 10-frictionless-correct-ingest plan 05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Resolved-format override wins over a declared one, threaded as a keyword-only, defaulted Mapping[str, str] param through assemble()/validate() -- every existing call site preserves today's exact behavior untouched."
    - "Decision-table dispatch (one branch per row, not a nest of ifs) for resolve_date_formats' 8-row classification x declaration x human-answer matrix."
    - "answers=None never raises (first-pass question); answers={} or any non-None dict asserts 'resolve everything now' and fails closed via UnresolvedDateColumnsError on any still-ambiguous column -- the asymmetry is deliberate, not a bug."
    - "Escalation counts derived via a pure, no-LLM _prefill_coverage helper shared by _python_first_prefill (the real resolution) and resolve_or_map (reporting), so counting the Python/Claude split never triggers a second mapper call."
    - "resolve_table_mapping's return arity (3-tuple) is a hard invariant -- cli.py unpacks it positionally and is out of this plan's scope, so Escalation is never threaded through that return; it is recomputed cheaply where needed instead."

key-files:
  created:
    - tests/test_canonical_dates.py
    - tests/test_date_escalation.py
    - tests/test_python_first_prefill.py
  modified:
    - src/assayingest/canonical.py
    - src/assayingest/validation/validator.py
    - src/assayingest/service.py

key-decisions:
  - "canonical.py/validator.py's new date_formats/date_contradictions kwargs default to None and change ZERO behavior when omitted -- verified by re-running tests/test_canonical.py and tests/test_validator.py completely unmodified (52 tests green)."
  - "date_contradictions[field] carries ONE raw contradicting example value (a string), not a pre-formatted sentence -- the validator's own _contradiction_objection_note composes the UI-SPEC copy shape from that value plus the field's own declared date_format, keeping the wire-shape decision in one place."
  - "resolve_date_formats' answers=None vs answers={} asymmetry is deliberate: None means 'first pass, just tell me what's ambiguous' (returns a DateFormatQuestion, never raises); any non-None dict (even empty) asserts 'attempt to fully resolve now', so an ambiguous column left uncovered raises UnresolvedDateColumnsError fail-closed."
  - "resolve_table_mapping's return type stays a strict 3-tuple even with schema= added -- cli.py's `proposal, provenance, profile_id = service.resolve_table_mapping(...)` is out of this plan's file scope and would break on any arity change. Escalation is instead recomputed via the pure _prefill_coverage helper inside resolve_or_map, never via a second Claude call (verified: propose_mapping call counts stay exact in every test)."
  - "_vendor_agnostic_alias_index is a NEW function, never a call to _alias_index with a narrower key -- a plain upload under the locked D-10-01 three-control UI has no vendor selector in the mapping path at all, so scoping by vendor would force a vendor prompt onto every plain upload."
  - "field_set_from_schema keeps FieldSet.signature stable across the field-set-to-Schema migration (verified explicitly: promoting a FieldSet, adding aliases, then deriving a FieldSet back from the Schema produces the identical signature) so profiles learned before Schemas existed keep auto-applying; a tombstoned field correctly CHANGES the signature (documented as intended, not a bug)."

requirements-completed: [INGEST-02, INGEST-04]

coverage:
  - id: D1
    description: "A resolved date format (detected from a column's own evidence, or chosen by a human) wins over a merely-declared one in both canonical.assemble() and validate(); every existing call site is unaffected when the new kwargs are omitted"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_canonical_dates.py#test_assemble_resolved_format_wins_over_a_wrongly_declared_format"
        status: pass
      - kind: unit
        ref: "tests/test_canonical_dates.py#test_assemble_with_no_date_formats_kwarg_is_byte_identical_to_todays_behavior"
        status: pass
      - kind: unit
        ref: "tests/test_canonical.py (52 pre-existing tests, unmodified, all green)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A declared date_format that parses every row cleanly is still flagged amber, with an actionable note naming the declared format and a contradicting value, when the column's own evidence contradicts it"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_canonical_dates.py#test_a_cleanly_parsing_but_wrong_order_declared_format_still_flags"
        status: pass
      - kind: unit
        ref: "tests/test_canonical_dates.py#test_validate_flags_a_contradicted_declared_format_with_an_actionable_note"
        status: pass
    human_judgment: false
  - id: D3
    description: "service.resolve_date_formats always runs between mapping and validate(), implementing the full 8-row decision table (unambiguous/ambiguous/excel-serial/invalid-non-date x declared x human-answer), fails closed on an incomplete answers dict, and needs no API key"
    requirement: "INGEST-04"
    verification:
      - kind: unit
        ref: "tests/test_date_escalation.py (21 tests covering every decision-table row + fail-closed answers)"
        status: pass
      - kind: unit
        ref: "tests/test_date_escalation.py#test_date_detection_is_identical_under_headers_only"
        status: pass
    human_judgment: false
  - id: D4
    description: "A fully-crosswalked file maps with zero Claude calls; a partially-crosswalked one sends Claude only the uncovered fields; the profile auto-apply still wins over both; a tombstoned field/alias is invisible to the whole pass"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "tests/test_python_first_prefill.py#test_full_crosswalk_coverage_calls_the_mapper_zero_times"
        status: pass
      - kind: unit
        ref: "tests/test_python_first_prefill.py#test_profile_auto_apply_still_wins_over_the_python_pass_and_claude"
        status: pass
      - kind: unit
        ref: "tests/test_python_first_prefill.py#test_field_set_from_schema_excludes_a_tombstoned_field_and_the_signature_changes"
        status: pass
      - kind: unit
        ref: "tests/test_python_first_prefill.py#test_vendor_agnostic_index_excludes_a_tombstoned_alias"
        status: pass
    human_judgment: false

duration: 21min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 03: Escalation Wiring — Python-First Pre-fill + Always-Run Date Resolution Summary

**Extended `canonical.assemble`/`validation.validator.validate` with a resolved-date-format override (D-10-06 supersedes D-13), a new `service.resolve_date_formats` that always classifies every date-typed mapped column before `validate()` runs, and a new `service.field_set_from_schema`/`_python_first_prefill` deterministic crosswalk pass that lets a fully-aliased file map with zero Claude calls — all three wired into `resolve_or_map`/`resolve_table_mapping` with every existing call site (including `cli.py`, untouched) preserving its exact prior behavior.**

## Performance

- **Duration:** ~21 min
- **Started:** 2026-07-12T15:24:09+04:00 (first commit)
- **Completed:** 2026-07-12T15:45:07+04:00
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- `canonical.py`: `assemble(..., *, date_formats=None)` threads a resolved-format override (a per-run dict, never written back to the stored `Field`) down through `_assemble_record` → `_normalise_cell` → `_convert_by_type` → `_convert_field_date`. An `EXCEL_SERIAL_MARKER` override converts via `date_order.iso_from_excel_serial`, falling back to the raw string (never `None`, never a crash) on a non-serial value. With no override at all, every existing call site — including `tests/test_canonical.py`'s 15 pre-existing tests — behaves byte-identically to before.
- `validation/validator.py`: `validate(..., *, date_formats=None, date_contradictions=None)` forwards `date_formats` into its internal `canonical.assemble()` reuse (Pattern 1) and appends a new `_contradiction_objection_note` (additive, through the existing `_apply_objection` mechanism) naming both the declared format and one contradicting raw value in the exact UI-SPEC copy shape. Pinned the load-bearing test the plan exists to prove: `test_a_cleanly_parsing_but_wrong_order_declared_format_still_flags` — `canonical.assemble()` alone converts every row cleanly (nothing to flag on its own), yet `validate()` with a supplied `date_contradictions` entry still forces `needs_confirmation=True`, proving the mechanism is independent of any individual `strptime` call happening to raise.
- `service.py` — date resolution: `resolve_date_formats(table, proposal, field_set, *, answers=None) -> DateResolution` implements the full decision table from the plan (unambiguous/ambiguous/Excel-serial/invalid-or-non-date, crossed with declared-format presence and human-answer presence) as one branch per row in `_resolve_one_column`, never a nest of ifs. `answers=None` (first pass) never raises — it returns unresolved conflicts in `DateResolution.question`; any non-`None` `answers` dict (even `{}`) asserts "resolve everything now," and a still-ambiguous column raises `UnresolvedDateColumnsError` (mirrors `UnresolvedConflictsError`'s fail-closed shape verbatim). Wired into `resolve_or_map` immediately before `validate()`, on every branch. `MapResult` grew `date_question` (defaulted). The privacy test (`test_date_detection_is_identical_under_headers_only`) proves detection is bit-identical under `headers_only` and that no cell value reaches the outbound Anthropic request when the flag is on.
- `service.py` — Python-first pre-fill: `field_set_from_schema(schema)` makes a Schema's canonical fields the mapper's target fields (D-10-02), with `FieldSet.signature` verified stable across a field-set→Schema→derived-field-set round-trip (an already-learned profile keeps matching) and verified to correctly CHANGE when a field is tombstoned (a different target set, intended). `_vendor_agnostic_alias_index(schema)` is a genuinely new, vendor-agnostic crosswalk lookup (not a narrower call to `_alias_index`, since a plain upload has no vendor selector at all under the locked D-10-01 UI) that resolves a normalized header colliding across two different vendors to `None` (never guesses). `_python_first_prefill` pre-fills every matched header at confidence 1.0, calls the mapper only on the uncovered remainder (or not at all, when everything is covered — the demo money shot), and returns an `Escalation(python_matched, claude_matched, total)`. `resolve_table_mapping` gained a keyword-only, defaulted `schema=` param implementing the exact order profile-auto-apply → Python pre-fill → Claude → human, confirmed the profile auto-apply still short-circuits both new mechanisms with zero `propose_mapping` calls. `resolve_table_mapping`'s return signature deliberately stayed a strict 3-tuple (see Deviations) so `cli.py` — out of this plan's file scope — needed zero changes; `resolve_or_map` instead recomputes the Escalation via a shared, pure, no-LLM `_prefill_coverage` helper, never a second Claude call.
- 45 new tests across the three new files, all API-key-free and Claude-call-free (verified explicitly by running `tests/test_date_escalation.py`/`tests/test_python_first_prefill.py` with `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` unset).

## Task Commits

Each task was committed atomically (TDD RED then GREEN per task):

1. **Task 1: Date resolution through canonical + validator (INGEST-04)** - test `9e1aaab`, feat `1f5a55f`
2. **Task 2: service.resolve_date_formats — the always-runs detector (INGEST-04)** - test `a8fb837`, feat `4ae50b5`
3. **Task 3: Python-first alias pre-fill + Schema→FieldSet adapter (INGEST-02)** - test `307fd18`, feat `5621972`

_TDD Gate Compliance: every task's `test(10-03)` commit precedes its `feat(10-03)` commit, verified in git log order for all three tasks._

## Files Created/Modified

- `src/assayingest/canonical.py` - `assemble`/`_convert_field_date` gain a resolved-format override (keyword-only, defaulted `None`); module docstring updated (D-10-06 supersedes D-13)
- `src/assayingest/validation/validator.py` - `validate` gains `date_formats`/`date_contradictions` (keyword-only, defaulted `None`); new `_contradiction_objection_note`
- `src/assayingest/service.py` - `DateResolution`, `UnresolvedDateColumnsError`, `resolve_date_formats`, `field_set_from_schema`, `Escalation`, `_vendor_agnostic_alias_index`, `_prefill_coverage`, `_python_first_prefill`; `resolve_table_mapping`/`resolve_or_map` extended with `schema=`; `MapResult` grows `date_question`/`escalation`
- `tests/test_canonical_dates.py` - 12 tests: resolved-format override, Excel-serial conversion, contradiction flagging, full backward-compatibility pins
- `tests/test_date_escalation.py` - 21 tests: the full decision table, fail-closed unanswered ambiguity, the headers_only privacy pin
- `tests/test_python_first_prefill.py` - 20 tests: `field_set_from_schema` signature stability + tombstone exclusion, `_vendor_agnostic_alias_index` collision handling + tombstone exclusion, zero/partial/full Claude-call scenarios, profile-auto-apply composition, escalation counts end-to-end

## Decisions Made

- `date_contradictions[field]` carries one raw contradicting value (a plain string), not a pre-formatted sentence — `_contradiction_objection_note` composes the exact UI-SPEC copy from that value plus `target_field.date_format`, keeping the one wire-shape decision in one function.
- `resolve_date_formats`' `answers=None` vs `answers={}` asymmetry is deliberate: `None` (the default, unasked-yet state) never raises; any explicit dict (even empty) asserts "resolve everything now" and fails closed on any still-ambiguous column via `UnresolvedDateColumnsError`.
- `resolve_table_mapping`'s return arity stays a strict 3-tuple even with `schema=` added, because `cli.py`'s existing `proposal, provenance, profile_id = service.resolve_table_mapping(...)` unpack is outside this plan's file scope (`files_modified` in the PLAN.md frontmatter) and would break on any arity change. `Escalation` is instead recomputed inside `resolve_or_map` via a pure, side-effect-free `_prefill_coverage` helper shared with `_python_first_prefill` — verified this never doubles a Claude call by asserting exact `propose_mapping` call counts in every relevant test.
- `_vendor_agnostic_alias_index` is a new function rather than a narrower call to the existing `_alias_index` (which is keyed `(vendor, header)`), because a plain upload under the locked D-10-01 three-control UI never has a vendor selector in its mapping path at all.

## Deviations from Plan

None — plan executed as written, including the one genuine design decision the plan left implicit (how `Escalation` reaches `MapResult` without changing `resolve_table_mapping`'s return arity): resolved via the shared pure `_prefill_coverage` helper described above, which avoids both a breaking signature change to `resolve_table_mapping` (protecting `cli.py`, outside this plan's scope) and a duplicated Claude call.

## Issues Encountered

- One test (`test_no_crosswalk_coverage_sends_claude_the_full_field_set`) was initially written with a flawed premise — an alias recorded under a DIFFERENT vendor for the SAME source column, expecting "no coverage." Since `_vendor_agnostic_alias_index` is deliberately vendor-agnostic (there is no vendor concept in a plain upload), that alias correctly DOES cover the column regardless of which vendor recorded it. Fixed by using a genuinely uncovered source column in the test fixture; this is expected, correct behavior of the new index, not a bug in the implementation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Final public surface for Plans 04/05 to build HTTP adapters on:

- `canonical.assemble(table, proposal, field_set, *, date_formats: Mapping[str, str] | None = None) -> CanonicalTable`
- `validation.validator.validate(table, proposal, field_set, *, strictness="strict", date_formats: Mapping[str, str] | None = None, date_contradictions: Mapping[str, str] | None = None) -> MappingProposal`
- `service.DateResolution` (frozen: `formats: dict[str, str]`, `question: DateFormatQuestion`, `contradictions: dict[str, str]`)
- `service.UnresolvedDateColumnsError` (carries `columns: tuple[DateFormatConflict, ...]`; a route maps this to 422)
- `service.resolve_date_formats(table, proposal, field_set, *, answers: Mapping[str, DateOrder] | None = None) -> DateResolution`
- `service.field_set_from_schema(schema: Schema) -> FieldSet`
- `service.Escalation` (frozen: `python_matched: int`, `claude_matched: int`, `total: int`)
- `service._vendor_agnostic_alias_index(schema: Schema) -> dict[str, str | None]` (private; Plan 05's route composes via `resolve_table_mapping`/`resolve_or_map`, not directly)
- `service.resolve_table_mapping(table, field_set, store, *, headers_only=False, client=None, propose_mapping_fn=None, schema: Schema | None = None) -> tuple[MappingProposal, str, str | None]` (unchanged 3-tuple return; `schema=` is the only new param)
- `service.resolve_or_map(path, field_set, *, store=None, hint=None, sheet=None, strictness="strict", headers_only=False, client=None, propose_mapping_fn=None, schema: Schema | None = None) -> MapResult | StructureQuestion`
- `service.MapResult` (frozen: `proposal`, `table`, `provenance`, `profile_id=None`, `date_question: DateFormatQuestion = DateFormatQuestion(())`, `escalation: Escalation | None = None`)

No blockers. `git diff --stat` for this plan's commits touches only `canonical.py`, `validation/validator.py`, `service.py`, and the three new test files — nothing under `api/` or `frontend/`, matching the plan's own verification gate. Full suite: 731 passed, 4 skipped (up from the 686-passed/4-skipped baseline: +45 new tests, zero regressions).

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 7 created/modified files confirmed present on disk; all 6 task commit hashes (9e1aaab, 1f5a55f, a8fb837, 4ae50b5, 307fd18, 5621972) confirmed present in git log. Full suite re-verified green: 731 passed, 4 skipped (686 baseline + 45 new tests, zero regressions).

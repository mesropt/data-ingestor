---
phase: 12-claude-reads-the-structure
plan: 02
subsystem: parsing
tags: [structure-judge, batched-call, runtime-literal, redaction, headers-only, tdd]

# Dependency graph
requires:
  - phase: 12-claude-reads-the-structure
    provides: "12-01's parsing/structure/layout.py — LayoutKind/KeyValueBlock/SheetLayout, the pure verdict contract the judge's _to_domain maps onto"
provides:
  - "parsing/structure_assist.judge_workbook_layout(grids, client=None, *, headers_only) -> dict[str, SheetLayout] — ONE Claude call per workbook, boundary closed twice (runtime Literal + clamp/UNKNOWN-fill)"
  - "parsing/structure_assist.render_evidence_grid(sheet_name, rows, *, max_rows=20, max_cols=10, headers_only) — the bounded evidence grid with the D-12-17 type-bucket redaction; headers_only is a REQUIRED keyword"
  - "parsing/structure_schema.build_workbook_layout_wire_model(sheet_names) — runtime-Literal wire model; reasoning is the only free-string field (introspection-pinned)"
affects: [12-04, 12-05, 12-06, 12-07, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Required-keyword privacy choke point: headers_only has NO default on the renderer and the judge, so a future call site that forgets it is a TypeError, never a leak (deliberately stricter than mapper._render_table's defaulted analog)"
    - "Boundary closed twice for integers: runtime Literal on names at the SDK boundary AND index clamp + omission fill in _to_domain_verdicts — out-of-grid ⇒ UNKNOWN, never IndexError, never a repaired-but-wrong verdict"
    - "Free-string introspection guard on a create_model product: _free_string_paths walks nested wire models and asserts ['sheets.reasoning'] exactly, so a future widening fails CI"

key-files:
  created:
    - tests/test_structure_judge.py
  modified:
    - src/assayingest/parsing/structure_assist.py
    - src/assayingest/parsing/structure_schema.py

key-decisions:
  - "The judge's private mapper is named _to_domain_verdicts, not _to_domain — the plan's name was already taken by propose_structure's WireStructureProposal->StructuralHint mapper in the same module"
  - "String length is bucketed AFTER whitespace collapse ('  Patient Demographics  ' measures 20, not 24) so padding cannot shift a cell's bucket"
  - "bool cells bucket as num under redaction (bool is an int subclass; an Excel TRUE/FALSE cell is a value, not a string)"
  - "Empty grids dict returns {} before constructing a client (a Literal over no names is not a schema — the propose_schema_ranking refuse-before-calling posture)"

patterns-established:
  - "Judge signature for 12-04/12-05: judge_workbook_layout(grids: dict[str, list[tuple]], client: anthropic.Anthropic | None = None, *, headers_only: bool) -> dict[str, SheetLayout]"
  - "_to_domain_verdicts(wire, sheet_names: list[str], grid_dims: dict[str, tuple[int, int]]) — grid_dims maps sheet_name -> (n_rows, n_cols) computed from the FULL grid (len(rows), max row width), not the rendered slice, so last_data_row=117 on a 118-row sheet is valid even though only 20 rows render"

requirements-completed: [SHAPE-01, SHAPE-03, SHAPE-04]

coverage:
  - id: D1
    description: "render_evidence_grid — bounded 20x10 grid, visible R/C indices, true-dimensions line, newline-collapsed cells, and the blank/num/date/str:short/str:med/str:long redaction under headers_only"
    requirement: SHAPE-04
    verification:
      - kind: unit
        ref: "tests/test_structure_judge.py#test_golden_patient_info_redaction_and_default_rendering (+9 more render/redact tests, golden on the REAL cascade grid, both directions)"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_workbook_layout_wire_model — sheet_name a runtime Literal over real sheet names, kind a Literal over LayoutKind values, reasoning the only free string; _to_domain_verdicts clamps every index and fills every omission with UNKNOWN"
    requirement: SHAPE-03
    verification:
      - kind: unit
        ref: "tests/test_structure_judge.py#test_wire_model_reasoning_is_the_only_free_string_field, #test_to_domain_turns_each_out_of_grid_index_into_unknown (9 parametrized clamp cases) (+6 more)"
        status: pass
    human_judgment: false
  - id: D3
    description: "judge_workbook_layout — exactly one messages.parse call per workbook, the three-rule prompt with the verbatim definitional line, fail-closed ValueError, the D-18 hygiene pair, zero network calls in the suite"
    requirement: SHAPE-01
    verification:
      - kind: unit
        ref: "tests/test_structure_judge.py#test_judge_makes_exactly_one_call_for_an_eight_sheet_workbook, #test_judge_headers_only_redacts_the_outbound_request (+11 more fake-client tests)"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 02: The Structure Judge Summary

**One batched Claude call per workbook returning a SheetLayout verdict per sheet — sheet names closed by a runtime Literal AND re-checked in _to_domain_verdicts, every index clamped against the real grid (out-of-grid ⇒ UNKNOWN, never IndexError), omissions UNKNOWN-filled, and the evidence grid redacted to type buckets under a REQUIRED headers_only keyword**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-13T13:44:39Z
- **Completed:** 2026-07-13T14:02:02Z
- **Tasks:** 3 (all TDD, red-first)
- **Files modified:** 3

## Accomplishments

- `render_evidence_grid(sheet_name, rows, *, max_rows=20, max_cols=10, headers_only: bool)` is the phase's fourth `headers_only` enforcement site, built as its own choke point: the kwarg is REQUIRED, so forgetting the privacy question is a `TypeError`, never a leak (T-12-04 mitigated at the renderer). Under `headers_only=True` every cell renders as `blank`/`num`/`date`/`str:short`(≤8)/`str:med`(9-24)/`str:long`(25+) — bucketed per D-12-17, never a raw length. The golden test on the REAL cascade `Patient Info` grid pins both directions: `R1: str:short | str:med | blank | str:med | str:med` with `"TAYLOR, James"`/`"3809217"`/`"CS-2026-698392"` absent under redaction and PRESENT by default (D-12-09 makes presence a requirement too). Every cell is newline-collapsed (`_one_line` contract) so an embedded newline cannot escape its bullet, and the true-dimensions line always renders.
- `build_workbook_layout_wire_model(sheet_names)` mirrors `build_ranking_wire_model`: `sheet_name` is `Literal[tuple(sheet_names)]`, `kind` is a Literal derived at import time from `LayoutKind` values (the vocabularies cannot drift), and an introspection test walks the nested models asserting `_free_string_paths(model) == ["sheets.reasoning"]` — SHAPE-03 is a type, and a future free-string field fails CI.
- `_to_domain_verdicts(wire, sheet_names, grid_dims)` closes the boundary a second time: out-of-set names dropped, duplicates keep-first, confidence clamped into [0,1], and — the two inventions — every integer index checked against the real grid (9 parametrized rejection cases: out-of-range label/value columns, negative rows, past-the-edge rows, inverted ranges, bad header/data-row indices — each ⇒ `SheetLayout(kind=UNKNOWN, confidence=0.0, reasoning naming the rejected index)`) and every omitted sheet UNKNOWN-filled, never defaulted to `row_per_record`. The returned dict has exactly one `SheetLayout` per real sheet, always (T-12-05 mitigated).
- `judge_workbook_layout` makes EXACTLY ONE `messages.parse` call for an 8-sheet workbook (counted by the fake), on the module's existing posture (`claude-opus-4-8`, 4096 max tokens, adaptive thinking, high effort — pinned by a posture test). The system prompt carries the three rules (propose-never-decide / never-guess-silently / indices-never-cell-contents), the verbatim definitional `row_per_record` vs `key_value` line from RESEARCH, and — only under `headers_only` — the replaced-by-types notice. `parsed_output=None` ⇒ `ValueError` naming the consequence and the stop reason; no retry, no logging (availability is 12-04's boundary). The D-18 hygiene pair passes: no domain vocabulary in the module source (outside comments) and none in the captured system+content from a neutral grid.
- `propose_structure` and its prompt are byte-for-byte untouched; all 8 tests in `tests/test_structure_assist.py` pass unmodified. Full suite green with credentials unset: **1207 passed, 4 skipped, zero network calls** (includes 12-03's parallel Wave-2 additions landing in the same tree).

## Task Commits

Each task was committed RED then GREEN:

1. **Task 1: render_evidence_grid — bounded grid + type-bucket redaction** — `404168b` (test, RED), `3ab4cb1` (feat, GREEN)
2. **Task 2: wire model + _to_domain_verdicts — boundary closed twice** — `58ca71c` (test, RED), `c4b6d50` (feat, GREEN)
3. **Task 3: judge_workbook_layout — one batched call, prompt, hygiene pair** — `669d0da` (test, RED), `e0f674a` (feat, GREEN)

## Files Created/Modified

- `src/assayingest/parsing/structure_assist.py` — `judge_workbook_layout`, `_render_judge_system_prompt` (+`_JUDGE_SYSTEM_PROMPT`/`_JUDGE_REDACTED_NOTICE`), `render_evidence_grid`, `_render_cell`, `_bucket_string_length`, `_one_line`, `_to_domain_verdicts`, `_one_verdict_to_domain`, `_rejected_index`; module docstring extended to name both call sites
- `src/assayingest/parsing/structure_schema.py` — `WireKeyValueBlock`, `build_workbook_layout_wire_model`, `_LAYOUT_KIND_NAMES` (derived from `LayoutKind`); `WireStructureProposal` untouched
- `tests/test_structure_judge.py` — 40 tests: 10 renderer (incl. the real-file golden and the required-kwarg TypeError), 17 wire/_to_domain (incl. the free-string introspection and 9 clamp cases), 13 judge (one-call count, both redaction directions, prompt rules, fail-closed, never-real-client, full-path clamp, empty-workbook refusal, hygiene pair, posture)

## The interface 12-04/12-05 wire against (recorded per the plan's output spec)

```python
judge_workbook_layout(
    grids: dict[str, list[tuple]],          # sheet name -> native-typed raw grid (grid.read_grid's shape)
    client: anthropic.Anthropic | None = None,
    *,
    headers_only: bool,                      # REQUIRED — no default
) -> dict[str, SheetLayout]                  # exactly one verdict per grids key, insertion order

_to_domain_verdicts(wire, sheet_names: list[str], grid_dims: dict[str, tuple[int, int]])
# grid_dims: sheet_name -> (n_rows, n_cols), computed by the judge from the FULL grid as
# (len(rows), max((len(row) for row in rows), default=0)) — NOT the rendered 20x10 slice,
# so a verdict may legally name rows beyond the rendered window (the dims line tells the
# model the true size).
```

Failure contract for 12-04's `_judge_or_unknown`: `judge_workbook_layout` raises (`anthropic.AuthenticationError` from the SDK, `ValueError` on a missing structured output) and never logs — the caller owns the broad-except availability boundary.

## Decisions Made

- **`_to_domain_verdicts`, not `_to_domain`:** the plan's private name was already taken in `structure_assist.py` by `propose_structure`'s existing `WireStructureProposal -> StructuralHint` mapper, which the plan forbids touching. A second same-name function is a redefinition in Python; the judge's mapper is named for what it maps.
- **Bucket after collapse:** string length is measured after `_one_line` whitespace collapse — `'  Patient Demographics'` is 20 chars, not 22 — so cell padding cannot shift a bucket (pinned by a test).
- **`bool` ⇒ `num`:** an Excel TRUE/FALSE cell redacts as `num` (bool is an int subclass); explicit isinstance ordering keeps dates from being caught by the numeric branch.
- **Empty workbook refuses before calling:** `judge_workbook_layout({})` returns `{}` without constructing a client — a `Literal` over no names is not a schema (`propose_schema_ranking`'s posture, pinned by a monkeypatched-boom test).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The judge's `_to_domain` renamed to `_to_domain_verdicts`**
- **Found during:** Task 2
- **Issue:** The plan says "Put _to_domain (private) in structure_assist.py", but `structure_assist._to_domain` already exists as `propose_structure`'s wire→hint mapper — which the plan simultaneously requires to stay byte-for-byte untouched. Defining a second `_to_domain` would silently shadow the first and break `propose_structure` and its 8 tests.
- **Fix:** The judge's mapper is `_to_domain_verdicts`; the existing `_to_domain` is untouched. Same contract, same tests, distinct name.
- **Files modified:** src/assayingest/parsing/structure_assist.py, tests/test_structure_judge.py
- **Verification:** `tests/test_structure_assist.py` 8/8 green untouched; all clamp/fill tests green
- **Committed in:** `c4b6d50`

---

**Total deviations:** 1 auto-fixed (a name collision internal to the plan's own constraints)
**Impact on plan:** None on scope or behaviour — every specified rule, test, and boundary exists as specified.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks (`test(...)` before `feat(...)` in each pair); every RED run was observed failing before implementation (ImportError collection failures on the missing `render_evidence_grid`, `_to_domain_verdicts`/`build_workbook_layout_wire_model`, and `judge_workbook_layout` respectively).

## Issues Encountered

None. The pre-RED probe of the real `Patient Info` grid confirmed the golden literals and bucket lengths (`Name`=4, `TAYLOR, James`=13, `Accession #`=11, `CS-2026-698392`=14) before the test was written — including the detail that `'3809217'` is a *string* cell in the file (it redacts as `str:short`, and the golden asserts its absence rather than a `num` bucket).

## Known Stubs

None — `judge_workbook_layout` is fully implemented and fully offline-tested; nothing in production calls it yet **by design** (the plan's own scope: wiring lands in 12-04/12-05).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 12-04 (`_judge_or_unknown` / service seam) has its exact signature and failure contract recorded above; the judge raises and never logs, so the broad-except availability boundary composes cleanly.
- 12-05's privacy tests can exercise `render_evidence_grid` directly (it is public for exactly that reason) and prove the HTTP-boundary redaction through the real judge with a captured fake client — both molds already exist in `tests/test_structure_judge.py`.
- The threat register's T-12-04/T-12-05/T-12-06 mitigations from this plan's scope are implemented and test-pinned; T-12-04's HTTP-boundary proof remains 12-05's, as planned.

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 3 source/test files and the SUMMARY exist on disk; all 6 task commits (`404168b`, `3ab4cb1`, `58ca71c`, `c4b6d50`, `669d0da`, `e0f674a`) are in history; zero file deletions across the plan's commits; `uv run pytest tests -q` green with credentials unset (1207 passed, 4 skipped, zero network calls).

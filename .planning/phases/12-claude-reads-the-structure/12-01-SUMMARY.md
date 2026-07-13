---
phase: 12-claude-reads-the-structure
plan: 01
subsystem: parsing
tags: [key-value, unpivot, layout-verdict, frozen-dataclass, json-round-trip, tdd]

# Dependency graph
requires:
  - phase: 11-multi-sheet
    provides: "structure/grid.py read_grid (native-typed row tuples), the sheet manifest the verdict will feed in Wave B"
provides:
  - "parsing/structure/layout.py — LayoutKind (6 members), KeyValueBlock, SheetLayout: the pure verdict contract (D-12-13), with needs_confirmation (0.9 bar) and record_count properties and SheetLayout.from_dict"
  - "parsing/structure/unpivot.py — unpivot_key_value(rows, layout) -> (headers, string_rows): the pure key-value/transposed transform, golden-verified against both driving sheets"
  - "StructuralHint.layout: SheetLayout | None — the hint field that makes the round trip load-bearing, lossless through to_dict()/JSON/from_dict and the Postgres profile store"
affects: [12-02, 12-03, 12-04, 12-05, 12-06, 12-07, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SHAPE-03 as a type: the only str-typed field on a verdict is `reasoning`; a type-shape guard test introspects dataclass fields so a future free-string field fails CI"
    - "Parametrized purity guard over layout.py AND unpivot.py (the Wave-C re-point of test_structure_shape.py:101, written fresh)"
    - "Duplicate-header disambiguation: 'Collected', 'Collected (2)', with a used-set walk so a genuine 'X (2)' label never collides"

key-files:
  created:
    - src/assayingest/parsing/structure/layout.py
    - src/assayingest/parsing/structure/unpivot.py
    - tests/test_structure_layout.py
    - tests/test_structure_unpivot.py
  modified:
    - src/assayingest/parsing/hint.py
    - src/assayingest/learning/postgres_store.py
    - tests/test_structure_hint.py
    - tests/test_profile_store.py

key-decisions:
  - "Blank-row skip rule inside a block: a row whose label AND every value cell are all blank is padding and is skipped — this is what produces the golden counts (Summary 10 of 12 candidate rows, Patient Info 17 of 20); a blank label over a real value is kept with header ''"
  - "one_record_per_value_column=True with multiple blocks: records are enumerated block-by-block, value-column-by-value-column; a record fills its own block's header segment and leaves other blocks' cells empty (degenerates exactly to the plan's single-block melt)"
  - "SheetLayout.from_dict lives in layout.py beside the type (still pure stdlib); StructuralHint.from_dict in hint.py delegates to it; the Postgres loader routes through from_dict instead of StructuralHint(**json)"
  - "table_shape kept and marked DEPRECATED in the StructuralHint docstring — persisted in saved profiles, removing it is a migration this phase refuses"

patterns-established:
  - "_jsonable tuple branch: isinstance(value, (list, tuple)) -> [_jsonable(v) for v in value] — tuples coerced to lists so to_dict() output is canonical JSON types and recursion reaches enums nested inside block tuples (plan 12-05's wire mapping reads this)"
  - "Pure-module cell contracts duplicated deliberately: unpivot._stringify mirrors table.py:524-526 (_row_to_strings), unpivot._clean_label mirrors table.py:206-215 (_clean_header) minus the pandas-only 'Unnamed:' branch — importing them would drag pandas into the pure module"

requirements-completed: [SHAPE-02, SHAPE-03]

coverage:
  - id: D1
    description: "LayoutKind/KeyValueBlock/SheetLayout — the pure frozen verdict contract with needs_confirmation and record_count, structurally unable to carry a cell value"
    requirement: SHAPE-03
    verification:
      - kind: unit
        ref: "tests/test_structure_layout.py#test_the_only_str_typed_field_on_the_verdict_is_reasoning (+12 more)"
        status: pass
    human_judgment: false
  - id: D2
    description: "unpivot_key_value turns key-value/transposed grids into (headers, string_rows) — golden-verified on both driving sheets, duplicate labels deterministically disambiguated"
    requirement: SHAPE-02
    verification:
      - kind: integration
        ref: "tests/test_structure_unpivot.py#test_golden_cascade_summary_yields_ten_headers_and_one_row (+12 more, incl. Patient Info 17/1 and the transposed melt)"
        status: pass
    human_judgment: false
  - id: D3
    description: "StructuralHint.layout round-trips losslessly through to_dict()/JSON/from_dict and the Postgres profile store; old stored profiles without a layout key load as layout=None"
    requirement: SHAPE-03
    verification:
      - kind: integration
        ref: "tests/test_profile_store.py#test_layout_carrying_hint_round_trips, tests/test_profile_store.py#test_stored_profile_without_a_layout_key_loads_as_layout_none, tests/test_structure_hint.py (3 new)"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 01: The Verdict Types and the Un-Pivot Summary

**Pure verdict contract (LayoutKind/KeyValueBlock/SheetLayout) plus the pure key-value/transposed un-pivot, golden-verified against both cascade driving sheets (Summary 10 headers/1 row, Patient Info 17/1), with StructuralHint.layout round-tripping losslessly through the learning store**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-13T13:24:56Z
- **Completed:** 2026-07-13T13:40:01Z
- **Tasks:** 3 (all TDD, red-first)
- **Files modified:** 8

## Accomplishments

- The D-12-13 verdict contract exists verbatim as pure frozen types: `LayoutKind` (six members incl. `key_value`/`not_a_table`/`unknown`), `KeyValueBlock` (indices only), `SheetLayout` with `needs_confirmation` (the 0.9 confidently-wrong bar) and `record_count`. SHAPE-03 is now structural: a type-shape guard test asserts the only `str`-typed field on either type is `reasoning` — a future field that could carry a transcribed cell value fails CI (threat T-12-01 mitigated).
- `unpivot_key_value` reproduces 12-RESEARCH's measured golden outputs on the real driving workbook: Summary blocks `[(0,(1,),7,12),(4,(5,),7,12)]` → exactly 10 headers/1 row with first header "Patient Name" and first value "TAYLOR, James"; Patient Info blocks `[(0,(1,),1,10),(3,(4,),1,10)]` → exactly 17 headers/1 row. The transposed melt (one block, `value_columns=(1,2,3)`, `one_record_per_value_column=True` → 3 rows) falls out of the same transform for free.
- Duplicate labels never become duplicate headers: deterministic `Collected (2)` suffixing (with a used-set walk so a genuine `X (2)` label never collides), asserted within and across blocks — `canonical._column_index`'s first-occurrence lookup can never silently strand a column (threat T-12-02 mitigated).
- `StructuralHint` gained `layout: SheetLayout | None = None`; a layout-carrying hint survives `to_dict()` → `json.dumps`/`loads` → `from_dict` → the full Postgres profile-store save/load cycle byte-equal, and a stored profile with no `layout` key loads as `layout=None` (no migration).
- The full suite is green with credentials unset: **1163 passed** (1132 baseline + 31 new), 4 pre-existing live-test skips, zero network calls — the wave's additive-only invariant held; nothing existing was touched beyond the one optional hint field and its loaders.

## Task Commits

Each task was committed RED then GREEN:

1. **Task 1: layout.py — the verdict contract** — `1d50075` (test, RED), `7f6c04d` (feat, GREEN)
2. **Task 2: unpivot.py — the pure transform** — `7e949ab` (test, RED), `62bf211` (feat, GREEN)
3. **Task 3: StructuralHint.layout + round-trip** — `7a90097` (test, RED), `728c261` (feat, GREEN)

## Files Created/Modified

- `src/assayingest/parsing/structure/layout.py` — LayoutKind, KeyValueBlock, SheetLayout (+`from_dict`); pure stdlib, types only
- `src/assayingest/parsing/structure/unpivot.py` — `unpivot_key_value` + block reader, combined-record and per-value-column assembly, `_disambiguate`; pure stdlib + layout imports
- `src/assayingest/parsing/hint.py` — `layout` field, `from_dict`, `_jsonable` tuple branch, `table_shape` deprecation note
- `src/assayingest/learning/postgres_store.py` — loader routes through `StructuralHint.from_dict`
- `tests/test_structure_layout.py` — 13 tests: members, frozenness, properties, type-shape guard, parametrized purity guard over both new modules
- `tests/test_structure_unpivot.py` — 13 tests: unit grids, both real-file goldens, transposed melt, duplicates, stringification, blanks, bounds
- `tests/test_structure_hint.py` — 3 new round-trip/tolerance tests; purity-guard allowlist widened for `from .structure.layout`
- `tests/test_profile_store.py` — 2 new store-level tests (layout round-trip; missing-key tolerance via raw SQL row rewrite)

## The `_jsonable` fix shape (recorded for plan 12-05)

The latent bug was real: `asdict()` preserves `key_value_blocks` as a **tuple** of dicts, and `_jsonable` had branches for `Enum`/`dict`/`list` only, so the tuple fell through the final `return` unrecursed — `json.dumps` still serialised it (as an array), but `json.loads(json.dumps(d)) == d` failed (list ≠ tuple), and any enum nested inside the tuple would have leaked unserialised. The fix is one widened branch:

```python
if isinstance(value, (list, tuple)):
    return [_jsonable(v) for v in value]
```

— tuples coerced to lists with recursion, so `to_dict()` emits canonical JSON types end to end. The reconstruction inverse is `SheetLayout.from_dict` (layout.py — re-freezes `value_columns`/`key_value_blocks` to tuples, re-anchors `kind` to `LayoutKind`) called from `StructuralHint.from_dict` (hint.py), which the Postgres loader now uses in place of `StructuralHint(**json.loads(...))`.

## Decisions Made

- **Blank-row skip rule** (the semantics behind the golden counts, verified against the fixture before implementing): a row inside a block whose label AND every value cell are blank is skipped; a blank label over a real value keeps an `""` header (the `_clean_header` "unlabelled is signal" rationale).
- **Multi-block transposed semantics**: with `one_record_per_value_column=True`, records enumerate block-by-block then value-column-by-value-column (matching `record_count`'s "total across blocks"); each record fills its own block's header segment and leaves other blocks' cells `""`. Degenerates exactly to the plan's single-block melt.
- **`SheetLayout.from_dict` lives in layout.py** beside the type rather than in hint.py — reconstruction is part of the type's serialisation contract (mirroring `StructuralHint.to_dict` living on its type) and keeps hint.py's import to one name. layout.py remains pure stdlib and the type-shape guard is unaffected (it inspects fields, not methods).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] unpivot.py placeholder created in Task 1's GREEN commit**
- **Found during:** Task 1 (layout.py)
- **Issue:** The plan requires Task 1's purity guard to be parametrized over `layout.py` AND `unpivot.py`, but `unpivot.py` is Task 2's file — Task 1's acceptance criterion (guard passes) was unsatisfiable with the file absent.
- **Fix:** Task 1's GREEN commit created `unpivot.py` as a docstring-only pure placeholder (no functions), so the guard could read it; Task 2's RED still failed honestly on the missing `unpivot_key_value` import.
- **Files modified:** src/assayingest/parsing/structure/unpivot.py
- **Verification:** Task 1 guard green at `7f6c04d`; Task 2 RED collection error at `7e949ab`
- **Committed in:** `7f6c04d`

**2. [Rule 3 - Blocking] hint.py purity-guard allowlist widened**
- **Found during:** Task 3 (StructuralHint.layout)
- **Issue:** `tests/test_structure_hint.py::test_hint_module_imports_only_stdlib` allowlists import prefixes (`__future__`/dataclasses/enum only); the planned `from .structure.layout import SheetLayout` would have failed it.
- **Fix:** Added `"from .structure.layout"` to the allowed prefixes with a comment noting layout.py is itself pure stdlib (pinned by its own guard), preserving the guard's intent (no pandas/anthropic reachable from hint.py).
- **Files modified:** tests/test_structure_hint.py
- **Verification:** Guard still asserts no pandas/anthropic import line; full suite green
- **Committed in:** `7a90097`

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking ordering/guard conflicts internal to the plan)
**Impact on plan:** None on scope — both were the minimum needed to satisfy the plan's own acceptance criteria. No behaviour differs from the plan's specification.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks (`test(...)` before `feat(...)` in each pair); every RED run was observed failing before implementation (collection errors for Tasks 1-2, 5 assertion/attribute failures for Task 3).

## Issues Encountered

None. The fixture probe before Task 2's RED confirmed the blank-row skip semantics that reconcile the block spans (12 and 20 candidate rows) with the golden counts (10 and 17) — written into the tests up front rather than discovered mid-implementation.

## Known Stubs

None — the Task-1 `unpivot.py` placeholder was fully replaced by the Task-2 implementation; no hardcoded empties, placeholders, or unwired paths remain in this plan's files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The verdict contract and the transform exist for every later plan in the phase: 12-05's wire mapping has its `_jsonable`/`from_dict` shapes recorded above; Wave B can wire `hint.layout` into `table.py`/`sheets.py`; Wave C can delete `shape.py` knowing the purity guard already covers the successor modules.
- `classify_shape` still runs untouched; the 1132 pre-existing tests are all green — the additive-only invariant of Wave A held.

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 4 created source/test files and the SUMMARY exist on disk; all 6 task commits (`1d50075`, `7f6c04d`, `7e949ab`, `62bf211`, `7a90097`, `728c261`) are in history; zero file deletions across the plan's commits.

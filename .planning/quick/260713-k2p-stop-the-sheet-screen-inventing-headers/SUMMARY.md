---
task: 260713-k2p
slug: stop-the-sheet-screen-inventing-headers
type: tdd
status: complete
completed: 2026-07-13
subsystem: parsing/structure, api/wire, frontend/sheet-question
tags: [honesty-gate, fail-closed, sheet-manifest, presentation]
key-files:
  created:
    - .planning/quick/260713-k2p-stop-the-sheet-screen-inventing-headers/deferred-items.md
  modified:
    - src/assayingest/parsing/structure/sheets.py
    - src/assayingest/api/wire.py
    - frontend/src/state/sheets.ts
    - frontend/src/components/SheetQuestionPanel.tsx
    - tests/test_structure_describe_sheets.py
    - tests/api/test_sheets_route.py
    - frontend/src/state/sheets.test.ts
key-decisions:
  - "A sheet whose SHAPE cannot be read reports headers == [] — the same suppression DRAWING_ONLY already had. detect_header is a RANKING, not a gate: it always names its top-scoring row, so on a grid that is not a table it returns cells that are values."
  - "unsupported_shape and header_uncertain are NOT collapsed. The line between them is ANSWERABILITY — an uncertain header row the human can point at; an unreadable shape nobody can correct. Exactly what table.py encodes as answerable_by_hint=False."
  - "The default_schema fallback is DENIED to an unreadable sheet, not deleted. header_uncertain keeps it (D-11-16 intact)."
  - "The client needed its own gate as a second lock: _preSelectedSchema's `proposed_schema ?? defaultSchema` would have re-filled from the dropdown the very Schema the wire had just refused to send."
  - "DEFERRED — the real bug is upstream: classify_shape has NO key-value predicate. See deferred-items.md D-1 and the note below."
---

# Stop the sheet screen inventing headers

## What shipped

All three links of the root-cause chain, tests first at each:

1. **`parsing/structure/sheets.py`** — headers (and the `column_signature` derived from them) are now gated on the shape verdict, as `DRAWING_ONLY` already was. This also stops a signature computed over a **patient's name** reaching the learning store as a mapping key.
2. **`api/wire.py`** — `_pre_selection` no longer falls through to the Upload dropdown's `default_schema` for an unreadable sheet.
3. **`SheetQuestionPanel.tsx` / `state/sheets.ts`** — the headers list and the Schema `Select` are both gated, with one honest line in their place.

Commits: `8bb3835` (RED), `b233979`, `7f8d9c4`, `9981d41`, `3d1d2cc`.
Verification: `uv run pytest -q` → **1132 passed, 4 skipped**. `npm test -- --run` → **256 passed**. `npm run build` → clean.

## The finding that matters more than the fix

**The plan's central premise — "the shape classifier did its job" — is only ACCIDENTALLY true.**

Driving the real 8-sheet workbook end-to-end (which no unit test does) shows `classify_shape` has **no key-value predicate at all**:

| Sheet | Layout | transposed inversion (margin 0.1) | `classify_shape` |
|---|---|---|---|
| `Summary` | key-value | **+0.000** | `multiple_tables` |
| `Patient Info` | key-value (identical) | **+0.000** | **`row_per_record`** |

A key-value sheet is all-strings, so rows and columns are *equally* type-homogeneous and the `transposed` inversion is exactly **zero** — nowhere near the threshold. `Summary` was ruled `unsupported_shape` **only because it happens to contain a blank separator row**, tripping the unrelated `multiple_tables` test. `Patient Info` is the same layout *without* that row — so the classifier sees a perfectly good table, and only low header confidence saved it from status `ok`.

Live wire, after this fix:

```
Summary          unsupported_shape   None                (no headers)               <- fixed
Quality Control  unsupported_shape   None                (no headers)               <- fixed
Patient Info     header_uncertain    reagent-inventory   Name, TAYLOR, James, ...   <- STILL LYING
```

`Patient Info` correctly keeps its headers under this task's rule (suppressing `header_uncertain` would regress meridian's LEGEND) — but its "headers" are a patient's name, because **it isn't a table at all**. Presentation cannot reach this. The shape gate has to catch it first.

This was NOT fixed here: a key-value fingerprint is new *detection* capability in a corpus-tuned classifier whose every threshold was corpus-grounded in research. It would reclassify sheets across the corpus and every downstream gate. It deserves its own plan — not an unvalidated heuristic slipped into a presentation fix. See `deferred-items.md` D-1.

**Consequence to act on: a workbook whose cover sheet lacks a blank separator row will still show a patient's name as a column header.**

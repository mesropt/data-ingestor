---
task: 260713-k2p
slug: stop-the-sheet-screen-inventing-headers
created: 2026-07-13
type: tdd
files_modified:
  - src/assayingest/parsing/structure/sheets.py
  - src/assayingest/api/wire.py
  - frontend/src/components/SheetQuestionPanel.tsx
  - frontend/src/state/sheets.ts
  - tests/test_structure_describe_sheets.py
  - tests/api/test_sheets_route.py
  - frontend/src/state/sheets.test.ts
---

# Stop the sheet screen presenting confident nonsense for a sheet it cannot read

## The defect, as the builder found it

A workbook's `Summary` sheet is a **key-value layout** — labels down column A, values in column B. The shape classifier correctly ruled it `unsupported_shape` and the screen correctly left it unticked. But the screen *also* showed:

> **Detected headers:** `Patient Name` · `TAYLOR, James` · `(blank header)` · `(blank header)` · `Accession #` · `CS-2026-698392` · …
>
> **Schema for this sheet:** `assay-potency`

`TAYLOR, James` is a **patient's name — a value**, presented to the curator as a column header. And a Schema is pre-filled for a sheet the tool has just proposed to skip.

This is the exact failure the product exists to prevent: *never guess silently, never present a verdict the human cannot check.* A sheet the tool cannot read must say so — not invent an answer.

## Root cause (three links in one chain)

1. **`parsing/structure/sheets.py:217-227` (`_describe_one_sheet`)** runs `detect_header` **before and independently of** the shape gate, and ships whatever it found as `SheetDescription.headers` even after `_sheet_status` (`sheets.py:239`) has ruled the sheet `UNSUPPORTED_SHAPE`. `DRAWING_ONLY` already short-circuits with `headers=[]` (`sheets.py:209-215`) — **that is the precedent to follow.**

2. **`api/wire.py::_pre_selection` (`wire.py:687-708`)** falls back to the Upload dropdown's `default_schema` when a sheet has **no proposals at all** — so a zero-coverage, unsupported-shape sheet still arrives carrying `proposed_schema = "assay-potency"`.

3. **`frontend/src/components/SheetQuestionPanel.tsx:114-123`** renders the "Detected headers" badge list with **no status gate**; the Schema `Select` (`SheetQuestionPanel.tsx:162-180`, `state/sheets.ts:57-60`) renders pre-filled for **every** sheet regardless of status.

## What the fix must do

A sheet whose **shape** cannot be read shows **no headers** and **no pre-filled Schema**. In their place it states plainly what it is and what the tool cannot do.

The shape — not the location — is the problem, so there is nothing here for the human to correct. This is the same reasoning `table.py::_shape_unsupported_question` (`table.py:439-461`) already encodes when it sets `answerable_by_hint=False`.

The sheet **stays visible and stays tickable**. The human may still insist; it is never dropped and never disabled away. (Insisting is safe: the mapping would find nothing, every field goes amber, and the confirm gate blocks the export. Fail-closed already covers it.)

## Out of scope — deliberately

**Do NOT read or un-pivot the key-value layout.** That is `PARSE-V2-01` (`REQUIREMENTS.md:78`, Out of Scope: *"Automatic un-pivot of wide/transposed layouts — still detect-and-flag / ask-the-human only"*). It is a real capability the builder wants, and it gets its own phase. This task only stops the lying.

## Tasks

### Task 1 — the backend tells the truth (TDD)

**Behavior (RED first).** Extend `tests/test_structure_describe_sheets.py`:
- A key-value sheet (labels in col A, values in col B) is described with `status == UNSUPPORTED_SHAPE` **and `headers == []`** — no label/value strings leak out as headers.
- Its `column_signature` must likewise not be computed from fabricated headers.
- Regression: an `ok` sheet still reports its real headers; a `header_uncertain` sheet still reports what it found (that status means *the header row is uncertain*, which the human CAN correct — unlike shape).

**Action.** In `_describe_one_sheet` (`sheets.py:198-228`), gate the header/signature computation on the shape verdict the way `DRAWING_ONLY` already is (`sheets.py:209-215`). Keep the sheet in the manifest, keep `row_count`, keep the status.

### Task 2 — the wire stops answering where it has no answer (TDD)

**Behavior (RED first).** Extend `tests/api/test_sheets_route.py`:
- A sheet with **no proposals** arrives with `proposed_schema is None` — even when the Upload dropdown supplied a `default_schema`.
- Regression: a sheet **with** proposals still pre-selects its top proposal; the `default_schema` fallback still applies to a sheet that has coverage but no clear winner. The fallback is not being deleted — it is being denied to sheets with *nothing to go on*.

**Action.** `_pre_selection` (`wire.py:687-708`): the `default_schema` fallback applies only when the sheet has something to propose from.

### Task 3 — the screen says what it means

**Behavior (RED first)** in `frontend/src/state/sheets.test.ts`: the pure selectors report, for an `unsupported_shape` sheet, that neither headers nor a Schema control should render, and that no Schema is pre-selected.

**Action.** `SheetQuestionPanel.tsx`: for `unsupported_shape`, render neither the "Detected headers" list nor the Schema `Select`. In their place, one honest line naming the shape and the limit — e.g. *"This sheet isn't laid out as one row per record (it reads as label/value pairs). The tool can't read this shape yet, so it has nothing to map. Skipping it."* Keep the checkbox: the human may still tick it.

Follow the inherited design system; no new primitives.

## Verify

- `uv run pytest -q` — green.
- `cd frontend && npm test -- --run && npm run build` — green.
- Manual: upload the 8-sheet workbook; the `Summary` sheet shows **no** headers, **no** Schema dropdown, and an honest reason — while the real data sheets are unaffected.

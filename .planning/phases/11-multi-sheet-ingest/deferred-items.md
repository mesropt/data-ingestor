# Phase 11 — deferred items

Out-of-scope findings surfaced during execution. Not fixed here (scope boundary:
only issues DIRECTLY caused by the current plan's changes are auto-fixed).

---

## D-1: A validator-rejected value is a UI dead end — no control can resolve it

**Found during:** 11-10, Task 3 (the end-to-end walkthrough), step 3.
**Severity:** medium (blocks confirming a real fixture; fail-closed, so nothing
wrong ships — the curator is simply stuck).
**Pre-existing:** YES — proven by a control experiment, see below. Plan 11-10
introduced neither the behaviour nor the gap.

**What happens:** `data/synthetic/zephyr_bio_ZB-2025.xlsx` has a `Units` column
whose values are `uM` (ASCII `u`). The `assay-potency` Schema's `unit` field
allows `['µM', 'nM', '%']`. Claude maps `unit ← 'Units'` and the no-LLM
validator correctly refuses on confirm:

```
422 {"unclear_fields":["unit"],"unclear_details":[{"field":"unit",
     "reason":"column 'Units': 'uM' is not one of the allowed values (µM, nM, %)"}]}
```

That refusal is CORRECT and must not be weakened (fail-closed; the Phase 3
accuracy principle). The gap is what the curator can do next: `FieldRow`'s three
D-02 controls are **chip** (a ranked alternative column), **Accept** (keep
Claude's proposal as-is), and **dropdown** (pick a different column). All three
resolve a field to a *column*. None can express the resolution the codebase's own
tests treat as the curator's answer here — clear the column and supply the
inferred constant (`source_column: null, inferred_value: "µM"`, the MAP-02
null-column shape; see `tests/api/test_group_export.py::_resolved_unit`, which
performs exactly this edit programmatically). So in the browser the curator gets
the 422, the field re-flags amber with the reason shown (`applyGateRejection`,
working as designed), and there is no control that can clear it.

**Control experiment (proves it is not 11-10's):** the SINGLE-SHEET path, which
this plan does not touch, produces the identical 422 — upload the same workbook
with an explicit `sheet=Week 1` (never entering the group flow at all, D-11-16),
Accept every field, confirm:

```
POST /api/upload  (file=zephyr_bio_ZB-2025.xlsx, schema_name=assay-potency, sheet=Week 1)
  -> kind=mapping
POST /api/confirm (every field needs_confirmation=false)
  -> 422  unit: 'uM' is not one of the allowed values (µM, nM, %)
```

**Options for a future phase (not decided here):**
1. A "use this value for every row" affordance on an amber `FieldRow` — the UI
   expression of the `inferred_value` shape the wire and the domain already
   support end to end (`MAP-02`, `canonical._inferred_constants`). This is the
   smallest fix and the one the domain is already shaped for.
2. Let a curator add `uM` as an accepted spelling on the Schema's `unit` field
   (the Schemas page already edits `allowed_values`) — a data fix, available
   today, but it asks the curator to widen a governed Schema to work around a
   missing control, which is the wrong incentive.

Option 1 is the honest one: the tool already knows the right value (`µM`) and
already has a wire shape for "a constant, not a column" — the human just has no
button for it.

---

## D-2: The plan's stale LEGEND claim, 4th recurrence

**Found during:** 11-10, Task 3, step 5. **Not a defect — a stale PLAN claim.**

11-10's plan (like 11-04's and 11-07's before it, and flagged by 11-09's SUMMARY
as the third recurrence) states that meridian's `LEGEND` sheet appears "with
'No canonical fields matched any Schema — proposed: skip this sheet.'" It does
not, and per **D-11-24** it must not. Observed on the live wire:

```
LEGEND: rows=6  status=header_uncertain  proposals=[assay-potency 1/7, matched: compound_id <- 'CMP']
```

LEGEND arrives **unticked via the GATE rule** (`header_uncertain`), carrying its
honest 1/7 coverage — exactly as D-11-24 ordains. Rendering the zero-coverage
skip line for it would require inventing the suppression threshold D-11-24
forbids. The genuine skip line fires where it is genuinely true: orion's `Notes`
sheet, which has zero proposals.

**Ask:** planners should stop propagating this claim.

# Quick 260713-k2p — deferred items

Out-of-scope findings surfaced during execution. Not fixed here (scope boundary:
only issues DIRECTLY caused by the current plan's changes are auto-fixed).

---

## D-1: `classify_shape` has no key-value predicate — the shape gate catches the builder's `Summary` sheet BY ACCIDENT

**Found during:** Task 3's end-to-end verification against the real 8-sheet
workbook (`data/synthetic_second/cascade_allergy_CS-2026-698392.xlsx`).
**Severity:** HIGH — a patient's name is STILL rendered as a column header on
that workbook, on a different sheet, after this task's fix.
**Pre-existing:** YES. This task changed only presentation; it introduced neither
the classifier nor the gap.

**This qualifies the plan's central premise.** The plan states: *"The shape
classifier did its job (the sheet is correctly marked `unsupported_shape` and
unticked). The failure is purely one of PRESENTATION."* The first half is true of
`Summary` only **by coincidence**, and is false in general.

**The measurements** (data region, after header resolution):

| Sheet | Layout | col_homog | row_homog | inversion (margin 0.1) | `classify_shape` |
|---|---|---|---|---|---|
| `Summary` | key-value | 1.000 | 1.000 | **+0.000** | `multiple_tables` |
| `Patient Info` | key-value (identical) | 1.000 | 1.000 | **+0.000** | **`row_per_record`** |

Neither sheet trips the `transposed` test — a key-value sheet is all-strings, so
its rows and columns are *equally* type-homogeneous and the inversion is exactly
zero, nowhere near `_TRANSPOSED_MARGIN`. Nor does either trip `wide_matrix`
(no numeric cluster).

`Summary` is ruled `unsupported_shape` **only because it happens to contain a
blank separator row**, which trips the unrelated `multiple_tables` predicate.
`Patient Info` is the same layout without that blank row — so it classifies as
`row_per_record`, i.e. the classifier sees a perfectly good table. It was saved
from status `ok` only by low header confidence, landing on `header_uncertain`.

**The consequence, on the live wire, after this task's fix:**

```
Summary               unsupported_shape   None             (none)               <- fixed
Quality Control       unsupported_shape   None             (none)               <- fixed
Patient Info          header_uncertain    reagent-inventory  Name, TAYLOR, James, ...   <- STILL LYING
```

`Patient Info` correctly keeps its headers under this task's rule (an uncertain
header ROW is answerable by the human — meridian's LEGEND depends on that, and
the plan's hard constraint forbids regressing it). But its "headers" are a
patient's name, because it is not a table at all. **The presentation layer cannot
fix this. The shape gate has to catch it first.**

It also pre-fills a nonsense Schema (`reagent-inventory`) via the D-11-16
fallback, which is legitimate for a genuinely answerable sheet and absurd for
this one.

**Why not fixed here:** adding a key-value fingerprint to `classify_shape` is new
DETECTION capability in a corpus-tuned classifier (`_TRANSPOSED_MARGIN`,
`_WIDE_MATRIX_MIN_COLUMNS`, `_WIDE_MATRIX_MIN_FRACTION` were each corpus-grounded
in 01-RESEARCH.md Pattern 5). It would reclassify sheets across the whole corpus
and every downstream gate — deserving its own plan, its own corpus validation,
and its own named threshold, exactly as its siblings got. Doing it inline, under
a plan that declared the classifier correct and out of scope, is precisely the
kind of unvalidated heuristic change this project does not make.

**Proposed predicate for a future phase** (detect-and-flag ONLY — not un-pivot;
un-pivoting remains `PARSE-V2-01`, `REQUIREMENTS.md:78`): a data region that is
≤2-3 populated columns wide, whose first column is all-unique non-numeric labels,
and whose second column is a value column, is a key-value / property-sheet
layout, not one row per record. Candidate name: `TableShape.KEY_VALUE`, or fold
into `TRANSPOSED` (a key-value sheet IS a transposed single record). Fixtures
already in tree to validate against: `cascade_allergy_CS-2026-698392.xlsx`
(`Summary`, `Patient Info`, `Methodology & Notes`).

**Until then:** the sheet screen still presents cell values as column headers for
any key-value sheet that lacks a blank separator row. This is the builder's
original complaint, surviving in a narrower form.

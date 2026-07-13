---
phase: quick-260712-r8b
plan: 01
subsystem: parsing
tags: [pandas, csv, delimiter-sniffing, data-integrity]

requires: []
provides:
  - "read_csv_grid strips whole comment lines via an explicit quote-aware pre-filter instead of pandas' comment= kwarg"
  - "The live parse() path no longer truncates a header/data line at a mid-line '#' (helixbio's '# Reps' column and every row's HLX-100 compound ID survive)"
  - "D-01 fail-closed guard: a dropped '#'-prefixed line that is structurally a header/data row (same column count as the table) raises a named ValueError instead of being silently dropped or promoted"
affects: [parsing, csv-ingest, structural-detection]

tech-stack:
  added: []
  patterns:
    - "Whole-line, quote-aware comment stripping done in application code before handing text to pandas, rather than relying on a library kwarg whose semantics don't match the domain need"

key-files:
  created: []
  modified:
    - src/assayingest/parsing/structure/delimiter.py
    - tests/test_structure_delimiter.py
    - tests/test_parse_entry_csv.py
    - .planning/todos/completed/parser-hash-comment-truncation.md (moved from pending/)

key-decisions:
  - "D-01: a '#'-prefixed line that splits into exactly the table's own column count is refused with a named ValueError, not silently treated as a comment or promoted to header — the one genuinely ambiguous case fails closed per the project's stated principle"
  - "Comment-only files are detected explicitly (empty-after-filtering check) rather than relying on pandas' EmptyDataError, because pandas raises a different exception (csv.Error 'Could not determine delimiter') when sep=None and the filtered text is empty vs. EmptyDataError when an explicit delimiter is given — an inconsistency that would have made the named 'empty' failure unreliable"

patterns-established:
  - "Quote-aware line-state tracking: toggle an in-quoted-field boolean once per line for each ODD count of the quote character on that line; a doubled '\"\"' escape is an even count and self-cancels"

requirements-completed: [PARSE-02]

coverage:
  - id: D1
    description: "Live parse() path no longer destroys helixbio_export.csv's '# Reps' header column or the HLX-100 compound ID"
    requirement: "PARSE-02"
    verification:
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_helixbio_returns_raw_table_with_hash_header_intact"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_helixbio_first_row_has_compound_id_intact"
        status: pass
    human_judgment: false
  - id: D2
    description: "read_csv_grid strips whole comment lines only (quote-aware), never truncates mid-line"
    requirement: "PARSE-02"
    verification:
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_helixbio_hash_header_column_survives"
        status: pass
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_hash_mid_line_in_data_cell_survives_verbatim"
        status: pass
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_hash_inside_open_multiline_quoted_field_survives"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-01 fail-closed guard: hash-prefixed header row is refused with a named ValueError instead of guessed"
    requirement: "PARSE-02"
    verification:
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_hash_prefixed_header_row_is_refused"
        status: pass
    human_judgment: false
  - id: D4
    description: "pinnacle_labs_export.csv's leading metadata comment lines still strip before delimiter sniffing; ';' still sniffed correctly (no regression)"
    requirement: "PARSE-02"
    verification:
      - kind: unit
        ref: "tests/test_structure_delimiter.py#test_pinnacle_csv_reads_seven_headers_not_one_junk_column"
        status: pass
      - kind: unit
        ref: "tests/test_parse_entry_csv.py#test_parse_pinnacle_returns_clean_table_with_decimal_comma_annotated"
        status: pass
    human_judgment: false
  - id: D5
    description: "Full backend suite green with no regression: 843 passed (832 baseline + 11 new), 4 skipped, 0 failed"
    verification:
      - kind: unit
        ref: ".venv/bin/python -m pytest -q"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-12
status: complete
---

# Quick Task 260712-r8b: Fix Silent Data Loss in the CSV Parser Summary

**Replaced pandas' `comment="#"` kwarg (which truncates any line at the first mid-line `#`) with an explicit, quote-aware whole-line comment pre-filter, restoring `HLX-100` and the `# Reps` header column to the live `parse()` path.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files modified:** 4 (1 source, 2 test files, 1 todo moved)

## Accomplishments
- Fixed the live `/api/upload` parse path (`parse()` → `read_csv_grid`) so a `#` anywhere in a header or data cell survives verbatim instead of truncating the rest of the line and shifting every subsequent column
- Preserved the existing defense against `csv.Sniffer()` being poisoned by a `delimiter=';'` comment (pinnacle's leading metadata lines still strip before sniffing)
- Added a fail-closed D-01 guard: the one genuinely ambiguous case — a `#`-prefixed line that structurally matches the table's own column count — now raises a named `ValueError` instead of silently being dropped (which would promote the first real data row to header) or silently kept (which would re-introduce the original bug)
- Made the comment-stripping pre-filter quote-aware so a `#` inside an open multi-line quoted cell is treated as data, not a comment
- Closed the `parser-hash-comment-truncation` todo with a resolution note

## Task Commits

1. **Task 1 (RED): Write the failing regression tests** - `c3408c4` (test)
2. **Task 2 (GREEN): Strip whole comment lines only, never truncate mid-line** - `9a4ef34` (fix)
3. **Task 3: Full-suite regression gate and close the todo** - `b9bca1b` (chore)

## Files Created/Modified
- `src/assayingest/parsing/structure/delimiter.py` - `_read_or_name_the_failure` now decodes text, runs it through a new `_strip_comment_lines` pre-filter, feeds the filtered text to `pd.read_csv` via `io.StringIO` with no `comment=` kwarg, then applies the new `_refuse_if_dropped_line_matches_table_shape` D-01 guard; module docstring rewritten to describe the new approach
- `tests/test_structure_delimiter.py` - 9 new regression tests against `read_csv_grid`: helixbio header/compound-ID survival, mid-line hash in a data cell, quote-aware multi-line hash survival, prose-comment-still-dropped (no over-fire), hash-header refusal (D-01), and the three pre-existing named failures (empty, non-UTF-8, comments-only)
- `tests/test_parse_entry_csv.py` - 2 new regression tests against the live `parse()` entry point, proving the fix reaches the actual `/api/upload` code path, not just `read_csv_grid` in isolation
- `.planning/todos/completed/parser-hash-comment-truncation.md` - moved from `pending/`, resolution section appended

## Decisions Made

**Header row that legitimately starts with `#` (D-01):** Refused with a named `ValueError`, not silently treated as a comment and not silently promoted to a header. The rejected alternative — treating it as a comment and letting the first data row silently become the header — is the exact same class of silent corruption this whole task exists to fix (a clean-looking table with every field wrong). Detection rule: after the grid is parsed, split each dropped `#`-line on the resolved delimiter; if it yields the table's exact column count (and the table has more than one column), it's structured, not prose — refuse rather than guess. Verified safe against the real corpus: pinnacle's two genuine metadata comment lines split into 1 and 4 fields against pinnacle's 7-column table, so they never trigger the guard.

A `StructureQuestion` (this project's normal idiom for "ask the human instead of crashing," per D-05/D-08) would have been more consistent with the rest of the codebase than a raw `ValueError`. It was not used here because `read_csv_grid` returns a plain `tuple[list[str], list[list[str]]]`, and changing that return type would have required touching `table.py` to handle the new return shape — explicitly out of bounds per this task's scope fence. The `ValueError` is not a new pattern in this module, though: `_read_or_name_the_failure` already raises named `ValueError`s for the other "genuinely broken file" cases (empty file, non-UTF-8 encoding, inconsistent column counts), so the D-01 guard is consistent with the function's existing contract, just not with the newer `StructureQuestion` convention used elsewhere in the parsing package. This is a real trade-off, not a non-issue — a future phase that wants a human to *resolve* this case (rather than just be told to fix the file and re-upload) will need to either widen `read_csv_grid`'s return type or catch this specific `ValueError` at a higher layer and convert it into a `StructureQuestion` there.

**Quote-aware filtering:** Achieved, not a partial/compromise fix. Quote-open state is tracked across line boundaries by counting `"` characters per line: an odd count toggles the state (the field's opening or closing quote), an even count leaves it unchanged (a `""` escaped-quote pair inside an already-open field self-cancels, matching RFC 4180 double-quote escaping). A line whose first non-whitespace character is `#` while a quoted field is still open is treated as a continuation of that cell's text, not a comment, and kept verbatim — verified directly by `test_hash_inside_open_multiline_quoted_field_survives`, which embeds a `#`-starting line inside a multi-line quoted cell and confirms it survives with the correct column count.

**Comment-only file handling:** Explicitly checked (`if not kept_text.strip(): raise pd.errors.EmptyDataError(...)`) rather than left to pandas to raise naturally. This was a real deviation from the plan's literal expectation — the plan assumed `pd.errors.EmptyDataError` would fire naturally on the filtered-to-empty text, matching today's behavior. In practice, when `sep=None` (no delimiter hint given) and the text is empty, pandas' python engine raises `csv.Error: Could not determine delimiter` instead of `EmptyDataError` — a different exception than when an explicit delimiter is passed with empty text (which does raise `EmptyDataError`). Relying on pandas' inconsistent behavior here would have made the named "empty" failure unreliable depending on whether a structural hint's delimiter was supplied. Explicitly detecting "nothing left after filtering" and raising the same `EmptyDataError` ourselves keeps the existing named-failure contract honest and consistent regardless of whether a delimiter hint is present.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment-only file's "empty" ValueError did not fire when no delimiter hint was given**
- **Found during:** Task 2, running the Task 1 regression tests after the initial implementation
- **Issue:** `test_comments_only_file_raises_valueerror_matching_empty` failed: pandas raised `csv.Error: Could not determine delimiter` (caught by the "inconsistent columns" clause) instead of `EmptyDataError`, because `sep=None` behaves differently than an explicit delimiter on empty input
- **Fix:** Added an explicit `if not kept_text.strip(): raise pd.errors.EmptyDataError(...)` check right after the comment pre-filter, before handing the text to `pd.read_csv` — this makes the "file is empty" failure deterministic regardless of whether a delimiter hint is supplied
- **Files modified:** `src/assayingest/parsing/structure/delimiter.py`
- **Verification:** All 9 `test_structure_delimiter.py` regression tests pass; full suite unaffected
- **Committed in:** `9a4ef34` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug fix during implementation, before any commit)
**Impact on plan:** No scope creep; the fix stayed entirely within `delimiter.py` as planned. The plan's literal expectation about which pandas exception would fire was slightly wrong, corrected during implementation with no change to the intended behavior (a comment-only file still names its failure as "empty").

## Issues Encountered

**Observed RED failure output (Task 1, before any source change):**

```
FAILED tests/test_structure_delimiter.py::test_helixbio_hash_header_column_survives
  AssertionError: assert ['Compound Na...e Symbol', ''] == ['Compound Na...eriment Date']
  At index 4 diff: '' != '# Reps'
  Right contains one more item: 'Experiment Date'

FAILED tests/test_structure_delimiter.py::test_helixbio_compound_id_survives_in_first_row
  AssertionError: assert ['EC50', '0.0... '03/11/2025'] == ['HLX-100', '... '03/11/2025']
  At index 0 diff: 'EC50' != 'HLX-100'

FAILED tests/test_structure_delimiter.py::test_hash_mid_line_in_data_cell_survives_verbatim
  AssertionError: assert ['1', 'Lot ', ''] == ['1', 'Lot #42', '3']
  At index 1 diff: 'Lot ' != 'Lot #42'

FAILED tests/test_structure_delimiter.py::test_hash_prefixed_header_row_is_refused
  (no ValueError raised — line was silently dropped)

FAILED tests/test_structure_delimiter.py::test_hash_inside_open_multiline_quoted_field_survives
  AssertionError: assert [['1', 'line one\n', '']] == [['1', 'line ... three', '3']]

FAILED tests/test_structure_delimiter.py::test_comments_only_file_raises_valueerror_matching_empty
  (raised the "inconsistent columns" message instead of "empty" — pre-fix pandas comment= behavior)

FAILED tests/test_parse_entry_csv.py::test_parse_helixbio_returns_raw_table_with_hash_header_intact
  AssertionError: 5-header list ending in '' vs. the expected 6 real headers

FAILED tests/test_parse_entry_csv.py::test_parse_helixbio_first_row_has_compound_id_intact
  AssertionError: rows[0][0] == 'EC50', not 'HLX-100'

8 failed, 17 passed in 9.25s
```

Every failure reproduced the exact bug described in the todo and the plan's objective (truncated/shifted header, missing compound ID, silent drop) — none were import errors, missing fixtures, or typos. All 17 pre-existing tests in the two files passed unchanged, confirming the new tests were additive and correctly targeted.

## Next Phase Readiness
- The live CSV parse path is now honest: a `#` in a header or data cell no longer causes silent column loss, and the one ambiguous case (a hash-prefixed header row) fails closed with a named error rather than guessing.
- No blockers introduced. The `StructureQuestion`-vs-`ValueError` trade-off noted in D-01 is worth revisiting if a future phase wants this specific ambiguity to be human-resolvable via the existing ask-flow rather than requiring a manual file edit and re-upload.

---
*Phase: quick-260712-r8b*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 3 task commits (`c3408c4`, `9a4ef34`, `b9bca1b`) confirmed in git history.

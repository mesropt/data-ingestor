---
phase: 12-claude-reads-the-structure
plan: 04
subsystem: service
tags: [layout-verdict, manifest, judge-seam, fail-closed, pii-leak, regression-red-first, tdd]

# Dependency graph
requires:
  - phase: 12-claude-reads-the-structure
    provides: "12-01's LayoutKind/SheetLayout/KeyValueBlock + unpivot_key_value; 12-02's judge_workbook_layout (raises, never logs — the caller owns the availability boundary); 12-03's parse dispatch that will consume entry.layout via the hint"
provides:
  - "service._judge_for / service._judge_or_unknown — the judge seam mirroring _ranker_for/_rank_or_none, with the D-12-16 difference STATED in the docstring (a ranker failure costs a SUGGESTION; a judge failure costs a QUESTION)"
  - "service.describe_workbook(path, schemas, *, store, client, rank_fn, judge_fn=None, headers_only=False) — ONE judge call per workbook, BEFORE the per-sheet scoring loop; verdicts thread into describe_sheets(path, layouts=...)"
  - "service.SheetManifestEntry.layout: SheetLayout | None — the FULL verdict retained server-side, key_value_blocks and row indices included (12-05's resolve/un-pivot input)"
  - "parsing/structure/sheets.py describe_sheets(path, layouts=None) + SheetStatus.LAYOUT_UNKNOWN ('layout_unknown') — status/header suppression keyed off LayoutKind when verdicts exist; classifier fallback byte-for-byte for layouts=None (dies in 12-07)"
  - "tests/api/conftest.py judging_client — the shared duck-typed structured-output fake whose parsed_output is a REAL wire-model instance surviving the REAL _to_domain_verdicts"
affects: [12-05, 12-06, 12-07, 12-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Availability boundaries come in pairs and are NOT the same: _rank_or_none loses a suggestion, _judge_or_unknown loses a question — both broad-except, both logged-once-never-raised, difference stated in code (D-12-16)"
    - "Signature only when headers exist: _manifest_entry computes column_signature over non-empty headers only; a headerless sheet gets '' — the learning store is never keyed on a sheet whose columns are unknown"
    - "Schema-bound API fake: judging_client reads sheet names from the wire model's runtime Literal via typing.get_args, so the fake cannot drift from the schema it fakes"

key-files:
  created: []
  modified:
    - src/assayingest/service.py
    - src/assayingest/parsing/structure/sheets.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/routes/upload.py
    - tests/api/conftest.py
    - tests/api/test_sheets_route.py
    - tests/test_describe_workbook.py
    - tests/test_structure_describe_sheets.py

key-decisions:
  - "SheetOut.status wire Literal widened with 'layout_unknown' in THIS wave (Rule 3): without it every multi-sheet upload through a None-client test client 500s on response validation — ~40 API tests, including all resolve tests, would break"
  - "upload.py's _sheet_question forwards headers_only into describe_workbook (Rule 2): with a real client and the toggle on, the judge's evidence grid would otherwise render real cell values in private mode"
  - "Verdict-less fallback kept BYTE-FOR-BYTE: _sheet_status/_reportable_headers delegate to _status_per_verdict/_headers_per_verdict when a layout exists and run the untouched classifier path otherwise — the strongest form of the plan's 'layouts=None → today's behaviour' guarantee"
  - "The four fixture suppression tests (apex/bionexus) were KEPT as verdict-less fallback pins rather than rewritten — they ARE the 'suppressed before is still suppressed after' assertion for the fallback path, alive until Wave C deletes it; verdict-path suppression got its own parametrized tests"

patterns-established:
  - "describe_sheets(path, layouts: Mapping[str, SheetLayout] | None = None); a sheet missing from a supplied mapping is UNKNOWN-filled (fail closed), never classifier-fallback for one sheet of a judged workbook"
  - "SheetStatus.LAYOUT_UNKNOWN = 'layout_unknown' — a gate about the tool's EVIDENCE (answerable), never conflated with unsupported_shape (a fact about the sheet); the layout kind travels separately on entry.layout"

requirements-completed: [SHAPE-01]

coverage:
  - id: D1
    description: "_judge_for/_judge_or_unknown — injected-fn-wins seam; no judge / raising judge / omitted sheet all degrade to UNKNOWN, logged once with exc_info, never logged AND raised, warning names the consequence"
    requirement: SHAPE-01
    verification:
      - kind: unit
        ref: "tests/test_describe_workbook.py#test_judge_or_unknown_swallows_any_judge_failure_logged_once_never_raised (+5 more seam tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "describe_workbook judges ONCE per workbook before the scoring loop, forwards headers_only, retains the FULL SheetLayout (blocks + indices) on SheetManifestEntry.layout, and the row_per_record null hypothesis changes nothing"
    requirement: SHAPE-01
    verification:
      - kind: unit
        ref: "tests/test_describe_workbook.py#test_the_judge_is_called_exactly_once_per_workbook_with_every_grid, #test_a_key_value_verdicts_full_layout_rides_the_manifest_entry, #test_a_row_per_record_judge_changes_nothing_the_null_hypothesis (+3 more)"
        status: pass
    human_judgment: false
  - id: D3
    description: "THE D-12-12 regression (observed red first): no cell value as a manifest header, no signature for an unjudged sheet; suppression only widened (key_value reports LABELS; wide_matrix/multiple_tables/not_a_table suppressed; unknown → LAYOUT_UNKNOWN); judge failure → all-LAYOUT_UNKNOWN manifest still builds"
    requirement: SHAPE-01
    verification:
      - kind: integration
        ref: "tests/test_structure_describe_sheets.py#test_a_key_value_sheets_manifest_never_reports_a_cell_value_as_a_header, #test_a_failing_judge_degrades_every_sheet_to_layout_unknown_and_the_manifest_still_builds (+13 verdict-path tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "judging_client — the shared fake proven through the REAL /api/upload chain and the REAL _to_domain_verdicts; the paired no-judge contract pinned by name"
    requirement: SHAPE-01
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_the_judging_client_survives_the_real_to_domain_through_the_real_chain, #test_no_client_really_does_mean_no_judge"
        status: pass
    human_judgment: false

# Metrics
duration: 76min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 04: The Manifest onto the Verdict Summary

**describe_workbook now judges the workbook ONCE before the per-sheet scoring loop and every status/header/signature keys off the verdict — the live D-12-12 leak (a patient's name as a column header, hashed into the learning-store signature) is dead and pinned by a regression test that demonstrably failed first, with suppression only ever widened and every judge failure degrading to an answerable LAYOUT_UNKNOWN**

## Performance

- **Duration:** ~76 min
- **Started:** 2026-07-13T14:14:20Z
- **Completed:** 2026-07-13T15:30:45Z
- **Tasks:** 4 (all TDD, red-first; execution order re-sequenced — see Deviations)
- **Files modified:** 8

## THE observed red (D-12-12 — the plan's proof of work)

Run on pre-switch code (seams landed, `describe_workbook` not yet switched — the fallback path identical to `main`), 2026-07-13:

```
>       assert "TAYLOR, James" not in patient.headers
E       AssertionError: assert 'TAYLOR, James' not in ['Name', 'TAYLOR, James', '', 'Accession #', 'CS-2026-698392']
E        +  where ['Name', 'TAYLOR, James', '', 'Accession #', 'CS-2026-698392'] =
E           SheetManifestEntry(name='Patient Info',
E               headers=['Name', 'TAYLOR, James', '', 'Accession #', 'CS-2026-698392'],
E               ..._signature='8bb44f063ca99f643f5f1aed4190454cf96e942a1c1e3d7f320eb0881ffbdbd7',
E               status='header_uncertain', proposals=()).headers

FAILED tests/test_structure_describe_sheets.py::test_a_key_value_sheets_manifest_never_reports_a_cell_value_as_a_header
1 failed in 0.23s
```

The failure shows both halves of the leak live: the patient's name IS a column header (via the `header_uncertain` suppression exemption), and `column_signature` `8bb44f06…` is hashed over it — the learning-store key. The pre-implementation probe confirmed `Methodology & Notes` leaked the same way (`['Testing Laboratory', 'Cascade Allergy & Immunology, Portland, OR 97201']`). The observed-red date and output are quoted in the test's own docstring. After the switch: no client + no judge ⇒ all 8 sheets `layout_unknown`, `headers == []`, `column_signature == ""`.

## What 12-05 and 12-06 consume (the plan's output spec)

**`SheetManifestEntry.layout` stored shape:** the FULL `SheetLayout` dataclass, unchanged — `kind` (a `str`-valued `LayoutKind` member), `confidence`, `reasoning`, `header_row_index`, `first_data_row`, `last_data_row`, `key_value_blocks: tuple[KeyValueBlock, ...]` **with the real label/value column and row indices retained**, `one_record_per_value_column`; `None` only on hand-built pre-verdict test manifests (field is defaulted). "Server-side" in 12-UI-SPEC Discretion §1 means retained on the server and withheld from the BROWSER: only `SheetLayoutOut` (12-05) drops the indices down to `{kind, confidence, reasoning, record_count, needs_confirmation}`. The retained blocks are the un-pivot's only input — `entry.layout` rides onto the resolve hint (12-05), which the parse dispatch un-pivots from (12-03).

**`SheetStatus.LAYOUT_UNKNOWN` value:** `"layout_unknown"`. It is a GATE outcome ("the layout could not be judged — answerable, not unreadable"), never conflated with `unsupported_shape`; the layout kind travels separately on `entry.layout`. The backend wire `SheetOut.status` Literal already accepts it (widened this wave — see Deviations); the FRONTEND union (`lib/types.ts`, `sheets.ts#isUnreadableShape`, badge copy) does not know it yet — that is 12-06's, per the RESEARCH inventory.

## Accomplishments

- **The seams (Task 1):** `_judge_for` mirrors `_ranker_for` (injected fn wins → client binds `judge_workbook_layout` → else `None`, "a legitimate answer"); `_judge_or_unknown` owns the broad-except availability boundary (the judge raises and never logs — 12-02's recorded contract), degrades no-judge / raising-judge / omitted-sheet to `UNKNOWN` at confidence 0.0, logs exactly once with `exc_info`, and its warning names the consequence ("Every sheet will ask about its layout before anything is mapped"). The D-12-16 difference is stated verbatim in the docstring — `grep -i "costs a question"` finds it — AND the raising-judge test proves the behaviour it describes.
- **The switch (Task 2):** `describe_workbook` gains keyword-only, defaulted `judge_fn`/`headers_only` (every existing call site unchanged), reads every sheet's native grid once, judges ONCE before the per-sheet `_manifest_entry` loop (recorder test: 1 call, all 8 cascade grids, caller's `headers_only` forwarded), and threads the verdicts into `describe_sheets(path, layouts=...)`. The stale contract died in the same commit as the behaviour (RESEARCH Pitfall 3): the "There is still no `headers_only` parameter" docstring is rewritten (the manifest is now a pure function of the file PLUS one proposed — never auto-applied — verdict per sheet), the `:188` signature test is INVERTED, the `:214` seams test extended with `judge_fn`, and the autouse `_no_claude` guard stays (the MAPPER is still never called) with its "pure Python" prose dropped.
- **The re-key (Task 3):** with verdicts supplied, `KEY_VALUE`+blocks ⇒ `OK` with the un-pivot's LABEL headers (Python reads the grid per the verdict — never verdict text) and `record_count` as `row_count`; `ROW_PER_RECORD` ⇒ the existing header-confidence gate with the header row from the verdict when it names one in-grid (and its `first/last_data_row` trimming the count); `WIDE_MATRIX`/`MULTIPLE_TABLES`/`NOT_A_TABLE` ⇒ `UNSUPPORTED_SHAPE`, suppressed; `UNKNOWN` — or a block-less `key_value`, which names nothing readable — ⇒ the new `LAYOUT_UNKNOWN`, suppressed. `Result Visualization` (the chart sheet `ok` today) is no longer offered as ingestible under a `not_a_table` verdict. Suppression only ever WIDENED — pinned by a parametrized test over both previously-suppressed fixtures on BOTH paths, and the classifier fallback (`layouts=None`) is byte-for-byte untouched. `_manifest_entry` computes `column_signature` only over non-empty headers: a key-value sheet's signature is a signature over its LABELS; an unjudged sheet gets `""` — never a key.
- **The fixture (Task 4):** `judging_client` in `tests/api/conftest.py` — a duck-typed `messages.parse(**kwargs)` fake whose `parsed_output` is a REAL instance of the judge's per-request wire model, with sheet names read from the model's own runtime `Literal` (`typing.get_args`), so it cannot drift from the schema and every verdict still runs the REAL `_to_domain_verdicts`. Its docstring states the mechanical fact that forced it (the `client=None` short-circuit precedes every seam — an HTTP test cannot reach `judge_fn`) and the honesty rule (no client means no judge — production behaviour, not a test artifact). Self-test proven through the real `/api/upload` chain (statuses `ok`, real headers, `entry.layout.kind is ROW_PER_RECORD` in the retained manifest); the paired `test_no_client_really_does_mean_no_judge` pins all-`layout_unknown`. The 5 manifest-subject `test_sheets_route.py` tests migrated onto it; the resolve/ingestion tests stay on `lambda: None` (they never read the manifest's statuses) and move in 12-05.
- Full suite green with credentials unset: **1243 passed, 4 skipped, zero network calls** (Wave-2 baseline 1216 + this plan's net 27).

## Task Commits

Each task was committed RED then GREEN (execution order re-sequenced by dependency — see Deviations):

1. **Task 1: _judge_for + _judge_or_unknown** — `d9e5c6d` (test, RED: 6 AttributeError), `530e999` (feat, GREEN)
2. **Task 3 (sheets half): describe_sheets re-keyed on LayoutKind** — `c662252` (test, RED: 15 TypeError on the layouts kwarg), `7f69a82` (feat, GREEN — full suite green here)
3. **Task 2 + Task 3's regression: the switch** — `73976f4` (test, RED: 24 failures incl. THE observed-red D-12-12 assertion quoted above), `2838a48` (feat, GREEN — the 5 sanctioned API migrations interim-red, everything else green)
4. **Task 4: the judging fake client** — `e7f263b` (test, RED: fixture missing), `9040f3e` (feat, GREEN — full suite green)

## Files Created/Modified

- `src/assayingest/service.py` — `_judge_for`, `_judge_or_unknown`, `_unknown_layout`; `describe_workbook` switched (judge once, before the loop, verdicts into `describe_sheets`); `SheetManifestEntry.layout`; `_manifest_entry(layout=..., signature-only-when-headers)`; imports for `list_worksheets`/`LayoutKind`/`SheetLayout`/`judge_workbook_layout`
- `src/assayingest/parsing/structure/sheets.py` — `describe_sheets(path, layouts=None)`, `_layout_for` (UNKNOWN-fill), `SheetStatus.LAYOUT_UNKNOWN`, `_sheet_status`/`_reportable_headers` gain the layout arm (`_status_per_verdict`/`_headers_per_verdict`/`_verdict_header_index`/`_row_count`), classifier fallback byte-for-byte; `_reportable_headers`' docstring still names the screen → `_manifest_entry` → `column_signature` → learning-store chain
- `src/assayingest/api/wire.py` — `SheetOut.status` Literal + `"layout_unknown"` (deviation 1)
- `src/assayingest/api/routes/upload.py` — `_sheet_question` forwards `headers_only` into `describe_workbook` (deviation 2)
- `tests/api/conftest.py` — `judging_client` fixture + `_JudgingClient`/`_JudgingMessages`/`_judged_sheet_names`
- `tests/api/test_sheets_route.py` — fixture self-test + no-judge pair; `_client(..., anthropic_client=None)` seam; 5 manifest tests migrated; module docstring updated
- `tests/test_describe_workbook.py` — 6 seam tests, 5 switch tests, inverted `headers_only` pin, extended seams pin, `_row_per_record_judge` re-fit of every keep-test, autouse prose de-pure-Python'd
- `tests/test_structure_describe_sheets.py` — THE regression test, the all-LAYOUT_UNKNOWN degradation test, 13 verdict-path tests (labels, per-kind suppression, widened-never-narrowed, UNKNOWN-fill, chart-sheet, signature-over-labels)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `SheetOut.status` wire Literal widened with `"layout_unknown"`**
- **Found during:** Task 2 (planning the GREEN)
- **Issue:** `api/wire.py` is not in the plan's `files_modified`, but its `SheetOut.status` is a closed Literal. Once a None-client upload produces `layout_unknown` statuses, `SheetQuestionResponse.from_manifest` fails pydantic validation → every multi-sheet upload 500s — Task 4's no-judge contract and ~40 API tests (all resolve tests reach the manifest via `_ask`) would break, and the plan's own "Full suite green" criterion is unsatisfiable without it.
- **Fix:** One-line Literal widening. Semantic wire/frontend treatment of the new status (badges, `isUnreadableShape`, pre-selection nuance) remains 12-05/12-06's as planned; `_pre_selection` deliberately untouched (a `layout_unknown` sheet is answerable, so rung-2 default pre-fill — `header_uncertain`'s treatment — is the honest interim).
- **Files modified:** src/assayingest/api/wire.py
- **Verification:** `test_no_client_really_does_mean_no_judge` + 41 pre-existing sheet-route tests green
- **Committed in:** `2838a48`

**2. [Rule 2 - Missing critical] `upload.py` forwards `headers_only` to `describe_workbook`**
- **Found during:** Task 2
- **Issue:** The route already receives the curator's `headers_only` toggle but `_sheet_question` did not pass it; with a real client, a private-mode multi-sheet upload would have rendered REAL cell values into the judge's evidence grid — exactly the D-12-11 "the feature is a lie" failure, live between Wave B and 12-05.
- **Fix:** `headers_only=headers_only` at the call site, with a comment naming the consequence. Idempotent with whatever wiring 12-05 adds.
- **Files modified:** src/assayingest/api/routes/upload.py
- **Verification:** `test_the_callers_headers_only_reaches_the_judge` (service level) + `test_headers_still_cross_the_wire_under_headers_only` (route level, migrated)
- **Committed in:** `2838a48`

**3. [Rule 3 - Blocking] Task execution order re-sequenced; tests split by helper dependency**
- **Found during:** Task 2 (RED planning)
- **Issue:** Task 2's GREEN passes verdicts into "Task 3's parameter" (`describe_sheets(layouts=...)`) — unimplementable before Task 3's sheets.py work; conversely Task 3's regression test only goes green at Task 2's switch. The same internal ordering conflict 12-03 hit.
- **Fix:** Executed Task 1 → Task 3's sheets-level re-key (RED/GREEN, suite fully green after) → Task 2's switch WITH Task 3's regression + degradation tests in its RED batch (both exercise `describe_workbook`) → Task 4. THE regression test was observed red BEFORE the switch existed — the fallback path it ran on was identical to `main`, which is what D-12-12 demands.
- **Files modified:** (ordering only)
- **Verification:** All four RED commits observed failing before their GREEN; commit list above
- **Committed in:** `c662252`/`73976f4` (the split RED batches)

**4. [Rule 3 - Minor] Four of the "six inventory assertions" kept as fallback pins instead of rewritten**
- **Found during:** Task 3
- **Issue:** The plan says "rewrite the six inventory assertions", but four of them (apex wide-matrix ×2, bionexus ×2) exercise the VERDICT-LESS path, which this plan simultaneously requires to stay "byte-for-byte today's classifier behaviour" — rewriting them onto the verdict path would delete the only tests pinning that fallback before Wave C removes it.
- **Fix:** The two `_key_value_workbook` tmp_path tests rewritten onto the verdict path (now assert READABLE with label headers), the `:268` signature test widened (labels case + UNKNOWN case), and the four fixture tests kept as explicit fallback pins (docstrings updated to say so) with the verdict-path suppression covered by the new parametrized per-kind tests and the widened-never-narrowed test. Coverage strictly increased; nothing the plan wanted asserted is unasserted.
- **Files modified:** tests/test_structure_describe_sheets.py
- **Verification:** 48/48 in that file green; suppression pinned on both paths
- **Committed in:** `c662252`/`7f69a82`

---

**Total deviations:** 4 (two production one-liners forced by the plan's own green-suite criterion, one ordering split, one test-inventory judgment call)
**Impact on plan:** None on scope or behaviour — every must_have truth holds as specified; the wire/frontend semantics of `layout_unknown` remain 12-05/12-06's.

## TDD Gate Compliance

RED and GREEN commits exist for all four task pairs (`test(...)` before `feat(...)` in each). Every RED was observed failing before implementation: 6 AttributeError (Task 1), 15 TypeError (Task 3 sheets), 24 failures including THE quoted D-12-12 assertion (Task 2), 1 missing-fixture error (Task 4). `test_no_client_really_does_mean_no_judge` passes by design at its RED — it pins the behaviour the immediately preceding GREEN created, which is its stated purpose (the 12-03 "verdict-less invariant" precedent).

## Issues Encountered

None beyond the deviations above. The pre-RED probe of the real cascade workbook confirmed every literal the tests pin (the 8 sheet names, the leaked `Patient Info`/`Methodology & Notes` header lists, the 17-label un-pivot of the D-12-13 blocks) before any test was written.

## Known Stubs

None — both seams are fully wired to the real judge, the verdict path is fully implemented, and the fallback is deliberately intact (not a stub: Wave C's planned deletion target, exercised by its own tests).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **12-05 (wire):** `entry.layout` carries the full `SheetLayout` (blocks + indices) exactly as the resolve path needs; `SheetLayoutOut` should drop indices per 12-UI-SPEC Discretion §1. `SheetOut.status` already accepts `"layout_unknown"` on the backend. The ~18 resolve-subject API tests still ride `lambda: None` and are 12-05's to migrate onto `judging_client` (exported, schema-bound, one fake for everyone).
- **12-06 (frontend):** the `SheetOut["status"]` union in `lib/types.ts` and `sheets.ts#isUnreadableShape` do not know `layout_unknown` yet; badge copy for `key_value`/`layout_unknown` per the RESEARCH inventory.
- **12-07 (Wave C):** the classifier fallback to delete is fully fenced — `_sheet_status`/`_reportable_headers`' `layout is None` arms, `_layout_for`'s `None` branch, and the four fallback-pin tests named in deviation 4.

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 8 modified source/test files and the SUMMARY exist on disk; all 8 task commits (`d9e5c6d`, `530e999`, `c662252`, `7f69a82`, `73976f4`, `2838a48`, `e7f263b`, `9040f3e`) are in history; the named artifacts (`_judge_or_unknown`, `LayoutKind` in sheets.py, `cascade_allergy` in the regression tests, the `judging_client` fixture) all exist; zero file deletions across the plan's commits; full suite green with credentials unset (1243 passed, 4 skipped, zero network calls).

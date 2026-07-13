---
phase: 12-claude-reads-the-structure
plan: 05
subsystem: api
tags: [layout-verdict, null-hypothesis, round-trip, wire-boundary, headers-only, asvs-v5, tdd]

# Dependency graph
requires:
  - phase: 12-claude-reads-the-structure
    provides: "12-01's SheetLayout/LayoutKind/KeyValueBlock + the needs_confirmation/record_count properties; 12-02's judge_workbook_layout + render_evidence_grid (required headers_only kwarg); 12-03's _table_from_layout parse dispatch; 12-04's _judge_for/_judge_or_unknown seam, SheetManifestEntry.layout retaining the FULL verdict, SheetStatus.LAYOUT_UNKNOWN, and the shared judging_client fixture"
provides:
  - "service.resolve_or_map(judge_fn=None, layout_confirmed=True) — the single-sheet judge seam + D-12-15's null-hypothesis rule; layout_confirmed=False means BOTH 'this layout is a proposal' AND 'never seek another verdict' (the resolve path's zero-extra-calls posture)"
  - "service.layout_question_for(path, sheet_name, layout) — PUBLIC, because /api/sheets/resolve's ask_layout disagree path returns the IDENTICAL question (one answer surface, reached from both paths)"
  - "wire.SheetLayoutOut {kind, confidence, reasoning, record_count, needs_confirmation} — the browser's verdict model, carrying NO index; SheetOut.layout: SheetLayoutOut | None"
  - "wire.SheetLayoutIn + wire.KeyValueBlockIn — the human's CONFIRMED answer (indices included, the un-pivot's only input); StructuralHintIn.layout"
  - "wire.SheetSelectionIn.ask_layout: bool = False — the per-sheet disagree flag (12-UI-SPEC Discretion §2)"
  - "structural_hint._refuse_out_of_grid_indices — the OUTER T-12-15 closure: a 422 naming the consequence, bounded before any allocation"
affects: [12-06, 12-07, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two index closures, neither redundant: the wire model refuses what is impossible of ANY grid (a negative column, an inverted range — Pydantic ge=0 + model_validator); the route refuses what is merely false of THIS grid (bounded against the re-parsed file BEFORE any allocation). parse()'s own T-12-08 guard is the third, and it stays, because a verdict also arrives from the judge, which the route never sees."
    - "A single flag carrying two facts, stated out loud: layout_confirmed=False means 'proposal, not answer' AND 'a verdict was already sought — make no call'. Splitting it into two booleans would let a caller set an incoherent pair."
    - "Mutation as the proof of non-vacuity when a test passes on arrival: each half of the SHAPE-04 pair was shown to fail under exactly its own regression (ignore headers_only -> the redaction test alone fails; always redact -> the mirror alone fails)."

key-files:
  created: []
  modified:
    - src/assayingest/service.py
    - src/assayingest/api/wire.py
    - src/assayingest/api/routes/sheets.py
    - src/assayingest/api/routes/structural_hint.py
    - tests/test_service.py
    - tests/api/test_upload.py
    - tests/api/test_sheets_route.py
    - tests/api/test_group_export.py
    - tests/api/test_structural_hint_context.py

key-decisions:
  - "resolve_or_map judges only the ONE honest target sheet (an explicit sheet=, or a single-worksheet workbook) — a multi-sheet workbook with no explicit sheet is NEVER judged here: the sheet question owns that case (D-12-15 rejected forcing it), and picking a sheet just to judge it would be a second answer to a question parse() already owns"
  - "A CONFIDENT row_per_record naming NO header row DROPS the layout rather than attaching it: parse()'s T-12-08 guard fails a header-less row verdict closed to a question, which would turn the null hypothesis into friction. 'Read it the ordinary way' therefore means exactly that — today's header detection runs"
  - "layout_confirmed=False also SUPPRESSES the judge (not just marks the verdict a proposal): without it, a manifest entry whose retained verdict is None would trigger a brand-new Claude call at RESOLVE time — on the one path whose whole point is that it makes none (D-12-14)"
  - "Round trip B's bare-header_row_index form is pinned HERE and NOT pre-implemented: it terminates today via the shape classifier, which Wave C deletes. 12-09's promotion rule is what must keep it alive — and if 12-09 forgets, this test fails LOUDLY instead of the loop silently reopening. Implementing the promotion in this plan would have removed the very pin the plan asked for"

patterns-established:
  - "SheetLayoutOut drops indices; SheetManifestEntry.layout retains them. '12-UI-SPEC server-side' means RETAINED ON THE SERVER AND WITHHELD FROM THE BROWSER, never discarded — the blocks are the un-pivot's only input, and the smallest untrusted-input surface is the one that does not exist"
  - "Every API test that expects a DATASET now needs a verdict: a `lambda: None` client honestly means no judge, so the manifest is all-layout_unknown, and an unknown layout ASKS. The None override survives in exactly two families — the tests whose subject IS the no-judge path, and the validation-only refusals (422/404/401) that fail closed before any parse"

requirements-completed: [SHAPE-02, SHAPE-04]

coverage:
  - id: D1
    description: "D-12-15's null hypothesis in resolve_or_map: a confident row_per_record proceeds with NO question (its row range trimming trailing prose); EVERY other verdict — key_value however confident, wide_matrix, multiple_tables, not_a_table, unknown — and a low-confidence row_per_record returns the answerable question with the verdict (blocks and indices intact) riding its proposal"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "tests/test_service.py#test_a_confident_row_per_record_verdict_proceeds_with_no_question, #test_every_other_verdict_returns_the_answerable_layout_question (5 parametrized kinds), #test_a_low_confidence_row_per_record_verdict_asks_before_reading, #test_a_confident_verdict_naming_no_header_row_reads_the_ordinary_way"
        status: pass
    human_judgment: false
  - id: D2
    description: "The verdict rides the retained manifest to resolve time at ZERO extra Claude calls (D-12-02/D-12-14) — including for a layout-less entry; the judge is never reached on a CSV, on a multi-sheet workbook with no explicit sheet, or a second time for a layout already in hand; headers_only reaches the judge on this path too"
    requirement: SHAPE-04
    verification:
      - kind: unit
        ref: "tests/test_service.py#test_a_verdict_riding_the_hint_costs_zero_judge_calls, #test_a_layout_less_resolve_path_still_costs_zero_judge_calls, #test_a_csv_never_reaches_the_judge, #test_the_callers_headers_only_reaches_the_single_sheet_judge"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_resolving_ticked_sheets_makes_no_claude_call_at_all (a RECORDING client that refuses every call: `calls == []` is the proof)"
        status: pass
    human_judgment: false
  - id: D3
    description: "UNKNOWN ATTACHES — never dropped to a None that silently means 'ask': the member's question carries the verdict's reasoning, so the human is told WHY. And THE BLOCKS SURVIVE the manifest handoff: ticking the cascade Patient Info sheet yields a question whose proposal.layout carries the D-12-13 key_value_blocks with their real column indices"
    requirement: SHAPE-02
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_an_unknown_verdict_attaches_and_the_member_question_says_why, #test_the_key_value_blocks_survive_the_manifest_handoff"
        status: pass
    human_judgment: false
  - id: D4
    description: "BOTH human answers round-trip and END IN A MAPPED DATASET, and neither re-returns the question: the confirmed key-value answer un-pivots the cascade Patient Info sheet into a 17-column dataset (SHAPE-02, end to end); the 'one row per record' answer terminates in BOTH forms (explicit layout AND bare header_row_index)"
    requirement: SHAPE-02
    verification:
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_round_trip_a_a_confirmed_key_value_answer_yields_a_mapped_dataset, #test_round_trip_a_the_key_value_answer_does_not_re_return_the_question, #test_round_trip_b_one_row_per_record_terminates_in_a_mapped_dataset (2 parametrized forms)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The wire: SheetLayoutOut carries the verdict and NOT ONE index; needs_confirmation is the SERVER's gate, always beside the raw confidence; no verdict is an honest null; a client-posted layout with an impossible or out-of-grid index is a 422 naming the consequence, never an IndexError dressed as a 500 (T-12-15, ASVS V5)"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "tests/api/test_sheets_route.py#test_sheet_layout_out_carries_the_verdict_and_not_one_index, #test_needs_confirmation_is_the_servers_gate_never_a_client_threshold, #test_a_sheet_with_no_verdict_carries_a_null_layout_not_a_fabricated_one (+3 more)"
        status: pass
      - kind: integration
        ref: "tests/api/test_structural_hint_context.py#test_a_structurally_impossible_layout_is_422_at_the_wire_boundary (8 parametrized cases), #test_an_out_of_grid_index_is_422_naming_the_consequence_never_a_500, #test_a_huge_last_row_never_materialises_a_giant_list, #test_a_rejected_layout_leaves_no_temp_file_behind"
        status: pass
    human_judgment: false
  - id: D6
    description: "SHAPE-04 proven at the HTTP boundary in BOTH directions, through the REAL /api/upload -> describe_workbook -> judge_workbook_layout -> render_evidence_grid chain with only the SDK client faked: the real cascade cell values are ABSENT under headers_only and PRESENT by default (D-12-09 makes presence a requirement, not an accident)"
    requirement: SHAPE-04
    verification:
      - kind: integration
        ref: "tests/api/test_upload.py#test_upload_headers_only_judge_sends_no_cell_value, #test_upload_default_judge_sends_the_real_grid — non-vacuity established by mutation (see TDD Gate Compliance)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The sheet screen's disagree path exists on the wire: ask_layout routes that member to the layout question in Review (proposal = Claude's read) while its sibling maps normally — and the loop CLOSES there, in a mapped dataset"
    requirement: SHAPE-02
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_ask_layout_routes_the_member_to_the_one_answer_surface"
        status: pass
    human_judgment: false

# Metrics
duration: 68min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 05: The Verdict Reaches Parse Time Summary

**Every production path now gets its layout verdict from the right place — the single-sheet path judges once in `resolve_or_map` under D-12-15's null hypothesis (a confident `row_per_record` proceeds silently, everything else asks answerably), the multi-sheet path rides the retained manifest at ZERO extra Claude calls with UNKNOWN attached rather than dropped, and BOTH human answers round-trip to a mapped dataset — the cascade `Patient Info` sheet, refused before this phase, comes back as a real 17-column dataset — with SHAPE-04 proven at the HTTP boundary in both directions and every client-posted index a 422 rather than an IndexError**

## Performance

- **Duration:** ~68 min
- **Started:** 2026-07-13T15:35:43Z
- **Completed:** 2026-07-13T16:43:00Z
- **Tasks:** 3 (all TDD, red-first except Task 3 — see TDD Gate Compliance)
- **Files modified:** 9

## The wire field names 12-06's `types.ts` mirrors verbatim (the plan's output spec)

```ts
// SheetOut gains ONE field. Indices are NOT here, by design.
type SheetLayoutOut = {
  kind: "row_per_record" | "key_value" | "wide_matrix"
      | "multiple_tables" | "not_a_table" | "unknown";
  confidence: number;          // raw, ALWAYS beside the gate below
  reasoning: string;           // Claude's one sentence — the human's checking material
  record_count: number | null; // key_value only; null for every other kind
  needs_confirmation: boolean; // the SERVER's gate. The client renders it, never sets it.
};
type SheetOut = { /* ...unchanged... */ layout: SheetLayoutOut | null };

// SheetSelectionIn gains the disagree flag (12-UI-SPEC Discretion §2).
type SheetSelectionIn = { sheet_name: string; schema_name: string; ask_layout?: boolean };

// StructuralHintIn gains the human's CONFIRMED answer — indices INCLUDED here,
// because the blocks are the un-pivot's only input. `table_shape` is superseded.
type KeyValueBlockIn = {
  label_column: number; value_columns: number[]; first_row: number; last_row: number;
};
type SheetLayoutIn = {
  kind: LayoutKind; confidence: number; reasoning?: string;
  header_row_index?: number | null;
  first_data_row?: number | null;
  last_data_row?: number | null;
  key_value_blocks?: KeyValueBlockIn[];
  one_record_per_value_column?: boolean;
};
type StructuralHintIn = { /* ...unchanged... */ layout?: SheetLayoutIn | null };
```

`SheetOut.status` still carries the GATE (`"ok" | "drawing_only" | "unsupported_shape" | "header_uncertain" | "layout_unknown"`); the layout KIND travels on `layout.kind` (12-RESEARCH Pitfall 7, binding). A `key_value` sheet is `status: "ok"` **and** `layout.kind: "key_value"` — readable, tickable, labels as headers, Schema control intact.

**The two answer forms the panel posts** (both proven to terminate in a mapped dataset):
- "Labels down the side" → `hint.layout = {kind: "key_value", key_value_blocks: [...]}` — a **confirmation of Claude's blocks**, never indices the browser invented.
- "One row per record" → `hint.layout = {kind: "row_per_record", header_row_index: N}`. The bare `hint.header_row_index = N` form also terminates (see Deviations).

## Accomplishments

- **The null hypothesis, as a rule (Task 1).** `resolve_or_map` gained `judge_fn`/`layout_confirmed` (keyword-only, defaulted — every existing call site unchanged). With no layout in hand it judges the ONE honest target sheet and applies D-12-15: a **confident `row_per_record` proceeds with no question** — identical to today, where the classifier auto-applied its own `row_per_record` with no human in the loop — while **every other verdict**, `key_value` however confident (an unconfirmed un-pivot silently reshapes the data), returns the answerable question with the verdict riding its proposal. `_judge_target_sheet` owns the availability boundary (broad-except, logged once with the consequence named, never logged AND raised — 12-02's judge raises and never logs, so no failure is reported twice or zero times).
- **UNKNOWN ATTACHES (the decision with the largest blast radius).** `_resolve_one_sheet` threads the retained `SheetManifestEntry.layout` onto the hint even when its kind is `UNKNOWN` — never `None`. The member's question carries the verdict's own reasoning, so the human is told WHY they are being asked. The rationale is in the code, not just here: post-Wave-C a `None` and an `UNKNOWN` both end at the same question, but only one of them can say why, and a `None` that silently means "ask" is the write-only dead end this phase exists to kill.
- **THE BLOCKS SURVIVE THE HANDOFF, asserted rather than assumed.** Ticking the cascade `Patient Info` sheet yields a `StructureQuestion` whose `proposal.layout` carries the D-12-13 blocks (`[(0,(1,),1,10), (3,(4,),1,10)]`) with their real label/value column indices, intact through `entry.layout` → hint → dispatch. Those blocks are the un-pivot's ONLY input; had they been dropped anywhere along that chain, the panel could never offer "Labels down the side" and SHAPE-02 would have died silently on the multi-sheet path with every other test still green.
- **ZERO EXTRA CALLS, proven with a recorder rather than an exploder.** A recording client that *also* refuses every call proves `calls == []` on the resolve path — the stronger form, because both availability boundaries **swallow** a raising judge, so an exploder alone could have passed vacuously.
- **BOTH round trips END IN A MAPPED DATASET, and neither re-returns the question (Task 2).** Round trip A: the confirmed key-value answer posts Claude's blocks back and the cascade `Patient Info` sheet — a sheet the tool **refused** before this phase — returns as a real **17-column, 1-row mapped dataset** (`Name`, `Medical Record #`, `Date of Birth`, … `Fasting Status`). Python did the un-pivot; Claude never wrote a value. Round trip B (the REJECT path): "One row per record" terminates in **both** answer forms.
- **The wire boundary is closed twice, and neither closure is redundant.** `SheetLayoutIn`/`KeyValueBlockIn` refuse at the wire what could not be true of ANY grid (a negative column, an inverted range, an invented kind, a confidence above 1 — 8 named 422 cases); the route refuses what is merely false of THIS grid, bounded against the re-parsed file **before any allocation**, so a `last_row` of a billion is a 422 in a moment rather than a memory-exhausting slice. Both name the consequence ("Nothing was ingested: …"), never an `IndexError` dressed as a 500 — the WR-02 bug class, fixed once and not reintroduced.
- **SHAPE-04 is now a captured-outbound FACT at the outermost boundary, in both directions (Task 3).** Through the real `/api/upload` → `describe_workbook` → `judge_workbook_layout` → `render_evidence_grid` chain with **only the SDK client faked**, `"TAYLOR, James"` / `"CS-2026-698392"` / `"3809217"` are absent under `headers_only=true` — and **present** under `headers_only=false`, because D-12-09 makes default-path realness a requirement, not an accident.
- Full suite green with credentials unset: **1287 passed, 4 skipped, zero network calls** (Wave-3 baseline 1243 + this plan's net 44).

## Task Commits

1. **Task 1: the judge seam + the null hypothesis** — `42db09b` (test, RED: 15 `TypeError` on the `judge_fn` kwarg + 3 `AssertionError`), `e637a49` (feat, GREEN)
2. **Task 1 collateral: the enumerated migration** — `4a38cf3` (test — its own reviewable commit, as the plan directed)
3. **Task 2: the layout wire** — `13ceac6` (test, RED: 19 failures), `0c94bed` (feat, GREEN)
4. **Task 3: the SHAPE-04 captured-outbound pair** — `0ec32d7` (test; passes on arrival — non-vacuity proven by mutation)
5. **Post-review fix: no second verdict on the resolve path** — `dbe9bf4` (fix + its pin)

## Files Created/Modified

- `src/assayingest/service.py` — `resolve_or_map(judge_fn, layout_confirmed)`; `_judge_target_sheet` (the availability boundary), `_layout_target` (the ONE honest target), `_apply_null_hypothesis` (D-12-15's rule), `_hint_with_layout`, and the PUBLIC `layout_question_for` (shared with `ask_layout`)
- `src/assayingest/api/routes/sheets.py` — `_resolve_one_sheet` threads the retained verdict onto the hint (`layout_confirmed=False`) with UNKNOWN attached; the `ask_layout` disagree branch
- `src/assayingest/api/wire.py` — `SheetLayoutOut` (+ `SheetOut.layout`), `SheetLayoutIn`/`KeyValueBlockIn` (+ `StructuralHintIn.layout`), `SheetSelectionIn.ask_layout`
- `src/assayingest/api/routes/structural_hint.py` — `_to_domain_hint` maps the confirmed layout; `_refuse_out_of_grid_indices`/`_out_of_grid_error` (the outer T-12-15 closure, cleaning up its temp file like every other error branch)
- `tests/test_service.py` — 16 seam/rule tests (the 5-kind parametrized ask, both zero-call proofs, the raising judge, the CSV exclusion, headers_only, the multi-sheet refusal)
- `tests/api/test_sheets_route.py` — the verdict-at-resolve section (zero calls, UNKNOWN attaches, blocks survive, ask_layout) + 6 `SheetLayoutOut` wire tests + the key-value-keeps-its-Schema-control test; 16 resolve-subject tests migrated onto `judging_client`
- `tests/api/test_group_export.py` — the `anthropic_client` seam + 4 archive tests migrated onto `judging_client`
- `tests/api/test_structural_hint_context.py` — round trips A and B + 11 wire-boundary refusal tests
- `tests/api/test_upload.py` — the SHAPE-04 captured-outbound pair

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `layout_confirmed=False` had to suppress the judge, not merely mark the verdict a proposal**
- **Found during:** post-Task-3 self-review
- **Issue:** `/api/sheets/resolve` passes `hint=StructuralHint(layout=entry.layout)`, and `entry.layout` can legitimately be `None` (a pre-verdict manifest entry). My first cut keyed the judge on "no layout in hand" alone — so such an entry would have fallen through to a **brand-new Claude call at RESOLVE time**, on the one path whose whole point (D-12-14) is that it makes none. The plan's zero-calls test did not catch it, because `judging_client` always supplies a verdict.
- **Fix:** `layout_confirmed=False` now says two things at once, stated out loud in the docstring: *this layout is a proposal* AND *a verdict was already sought — make no call*. One flag, because splitting it would let a caller set an incoherent pair.
- **Files modified:** src/assayingest/service.py, tests/test_service.py
- **Verification:** `test_a_layout_less_resolve_path_still_costs_zero_judge_calls` (new)
- **Commit:** `dbe9bf4`

**2. [Rule 3 - Blocking] A confident `row_per_record` naming NO header row DROPS the layout rather than attaching it**
- **Found during:** Task 1 (GREEN)
- **Issue:** `judging_client` — and any real judge on a sheet whose header row it cannot pin — returns a confident `row_per_record` with `header_row_index=None`. Attaching that to the parse hint sends it into `_raw_table_from_row_verdict`, whose T-12-08 guard (correctly) fails a header-less row verdict **closed to a question** — turning the null hypothesis into friction on the 90% case it exists to keep friction-free.
- **Fix:** such a verdict drops the layout and lets today's header detection run, which is *literally* what "read it the ordinary way" means. Rationale is in `_apply_null_hypothesis`'s docstring.
- **Files modified:** src/assayingest/service.py
- **Verification:** `test_a_confident_verdict_naming_no_header_row_reads_the_ordinary_way`
- **Commit:** `e637a49`

**3. [Rule 3 - Scope] The enumerated collateral was larger than "~18 + 5" and is enumerated here exactly**
- **Found during:** Task 1 (GREEN)
- **Issue:** The plan predicted the resolve-subject tests would need a verdict. Run against the real suite, the set is **16** in `test_sheets_route.py` and **4** in `test_group_export.py` (the 5th, `test_group_membership_survives_a_still_ambiguous_hint_re_put`, is question-bearing on its own merits and needs no verdict). `test_group_export.py`'s `_client` had no `anthropic_client` seam at all and gained one, mirroring `test_sheets_route.py`'s.
- **Fix:** Migrated exactly those 20 onto `judging_client`, in their own reviewable commit; the honesty rule is stated in both module docstrings — the `lambda: None` override survives in exactly two families (the tests whose subject IS the no-judge path, and the validation-only 422/404/401 refusals that fail closed before any parse).
- **Files modified:** tests/api/test_sheets_route.py, tests/api/test_group_export.py
- **Verification:** `uv run pytest tests/api -q` green (326) between files, as the plan directed
- **Commit:** `4a38cf3`

### Judgment Calls

**4. Round trip B's bare-`header_row_index` form was PINNED, deliberately NOT pre-implemented**
- The plan notes that 12-09 supplies the parse-dispatch promotion rule (an explicit header row IS a `row_per_record` confirmation) and asks this plan to "pin it at the HTTP boundary from the plan that depends on it". Implementing the promotion **here** would have destroyed the very pin: the test would then pass for a reason 12-09 no longer had to supply.
- Instead the test asserts both answer forms terminate in a mapped dataset **today** — the explicit-layout form through the verdict path (which survives Wave C), the bare form through the shape classifier (which Wave C **deletes**). If 12-09 forgets its promotion rule, this test fails **loudly** at Wave C instead of the loop silently reopening. That is what a pin is for, and it is recorded in the test's own docstring.

---

**Total deviations:** 3 auto-fixed (one real bug caught in self-review, one 90%-case correctness fix, one enumeration correction) + 1 recorded judgment call
**Impact on plan:** None on scope. Every `must_have` truth holds as specified.

## TDD Gate Compliance

RED and GREEN commits exist for Tasks 1 and 2 (`test(...)` before `feat(...)` in each), and every RED was **observed failing**: 15 `TypeError` on the unknown `judge_fn` kwarg plus 3 `AssertionError` (Task 1); 19 failures across the wire models and the 422 boundary (Task 2).

**Task 3 passed on arrival, and this is disclosed rather than dressed up.** Its `files` list is *tests only*: 12-02's required-`headers_only` renderer and 12-04's forwarding had already made SHAPE-04 true, and this plan's job was to **prove it at the outermost boundary** (D-12-06: the guarantee is enforced per call site, and this phase added one). A test that is green on arrival proves nothing by itself — so non-vacuity was established by **mutation** instead, and each half of the pair was shown to catch exactly its own regression:

| Mutation in `render_evidence_grid` | Result |
|---|---|
| `headers_only` silently ignored (the leak) | `test_upload_headers_only_judge_sends_no_cell_value` FAILS (`TAYLOR, James` leaks); the mirror passes |
| always redact (over-zealous — the D-12-09 regression) | `test_upload_default_judge_sends_the_real_grid` FAILS; the redaction test passes |

`src/assayingest/parsing/structure_assist.py` was restored byte-for-byte after each (`git status` clean, verified).

Two tests in Task 1 also pass by design at RED and say so in their docstrings — `test_resolving_ticked_sheets_makes_no_claude_call_at_all` and the key-value-keeps-its-Schema-control wire test — because they pin invariants the seam must PRESERVE (the 12-03/12-04 "verdict-less invariant" precedent).

## Issues Encountered

None beyond the deviations. The cascade `Patient Info` un-pivot (17 headers, 1 row) and zephyr's real header row (index 4, under a 3-line banner) were both probed against the real files before the tests that pin them were written.

## Known Stubs

None. Every path in this plan is wired to a real transform, a real gate, or a real refusal.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information-disclosure (PRE-EXISTING, T-12-18, transferred) | `src/assayingest/api/wire.py` (`StructuralQuestionResponse.evidence_rows`) | The new layout question carries `evidence_rows` to the browser through the **existing, unchanged** wire path, which does not redact under `headers_only` (only the frontend hides them). This is the leak CONTEXT §deferred already records and the threat register explicitly **transfers** — neither fixed here nor worsened: `service.layout_question_for` builds its evidence exactly as `table.py::_shape_unknown_question` already does. It remains a live follow-up. |

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **12-06 (frontend):** every wire name is recorded verbatim above. `SheetOut.layout` and `SheetSelectionIn.ask_layout` are live; `SheetOut["status"]` already accepts `"layout_unknown"` on the backend but `lib/types.ts` / `sheets.ts#isUnreadableShape` still do not know it (12-04's handoff, unchanged). `needs_confirmation` is server-sent — the panel must never threshold `confidence` itself.
- **12-07 (Wave C):** the classifier fallback this plan leans on is fenced and named: `_judge_target_sheet` returning `None` (no judge, a CSV, an outage) falls through to `classify_shape`. That is deliberate THIS wave; flipping it fail-closed is 12-07's.
- **12-09 (the promotion rule):** `test_round_trip_b_one_row_per_record_terminates_in_a_mapped_dataset[bare-header_row_index]` is your pin, and it is deliberately load-bearing — it currently terminates via the classifier Wave C deletes. Implement the promotion (an explicit `header_row_index` IS a `row_per_record` confirmation) or this test will tell you, loudly.
- **CSVs (D-12-18):** still out of scope and now pinned as such (`test_a_csv_never_reaches_the_judge`). A key-value CSV parses into garbage today and will continue to.

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 9 modified source/test files and the SUMMARY exist on disk; all 7 task commits (`42db09b`, `e637a49`, `4a38cf3`, `13ceac6`, `0c94bed`, `0ec32d7`, `dbe9bf4`) are in history; every named artifact exists (`layout_question_for`, `_apply_null_hypothesis`, `SheetLayoutOut`, `SheetLayoutIn`, `ask_layout`, `_refuse_out_of_grid_indices`, `headers_only` in `test_upload.py`); ZERO file deletions across the plan's commits; full suite green with credentials unset (1287 passed, 4 skipped, zero network calls).

---
phase: 12-claude-reads-the-structure
plan: 06
subsystem: frontend
tags: [layout-verdict, sheet-panel, hint-panel, copywriting-contract, ask-layout, tdd]

# Dependency graph
requires:
  - phase: 12-claude-reads-the-structure
    provides: "12-05's wire: SheetLayoutOut {kind, confidence, reasoning, record_count, needs_confirmation} on SheetOut.layout; SheetSelectionIn.ask_layout; SheetLayoutIn/KeyValueBlockIn on StructuralHintIn.layout; service.layout_question_for attaching the verdict (UNKNOWN included) to proposal.layout. 12-04's SheetStatus.LAYOUT_UNKNOWN = 'layout_unknown'."
provides:
  - "lib/types.ts: LayoutKind, SheetLayoutOut, SheetLayoutIn, KeyValueBlockIn mirrored verbatim from api/wire.py; SheetOut.layout + the widened status union; SheetSelection.ask_layout; StructuralHintIn.layout"
  - "state/sheets.ts: isUnreadableShape re-keyed on layout.kind (never key_value, never unknown); layoutLine/refusalLine/sheetBadge/allUnknown/showsAskLayoutAction + every Copywriting Contract string; SheetChoice.askLayout riding ask_layout"
  - "state/sheets.ts hint-panel derivations: proposalLayout (layout-question detection off proposal.layout, the derive-from-non-null pattern), hintVerdictLine, hintLabels (label columns only, clamped), hintLayoutOptions (key-value option iff blocks), toLayoutAnswerPayload (both 12-05 round-trip forms verbatim)"
  - "SheetQuestionPanel: per-card layout line (kind strong, confidence mono, amber only off needs_confirmation), verdict badges, 'Detected labels' caption, disagree action on EVERY judged sheet, ONE workbook-level all-unknown notice"
  - "StructuralHintPanel: verdict block + 'Labels found' chips (shown under headers-only, Discretion §4), two-option 'How is this sheet laid out?', header-row control revealed by 'One row per record' pre-filled from the verdict, submit gated on an option"
affects: [12-07, 12-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Copy-in-parts: contract strings are built in the pure module as {lead, kindPhrase, rest, confidence, trailer} so the panel can render the kind phrase strong and the confidence mono WITHOUT composing any copy itself; the tests reassemble the parts and assert the contract string verbatim"
    - "A question's KIND is derived from which proposal fields are non-null, never from unsure_about's free text: proposal.layout non-null IS the layout question — possible only because 12-05 attaches even an UNKNOWN verdict rather than dropping it to None"
    - "Additive-optional payloads: ask_layout and the layout answer are OMITTED when unset/unanswered (never sent as false/null), so undisputed payloads stay byte-identical to Phase 11's — pinned by Object.keys tests"

key-files:
  created: []
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/state/sheets.ts
    - frontend/src/state/sheets.test.ts
    - frontend/src/components/SheetQuestionPanel.tsx
    - frontend/src/components/StructuralHintPanel.tsx
    - frontend/src/state/upload.test.ts

key-decisions:
  - "The sheet Select is suppressed on a LAYOUT question (the question is the member's own; changing the sheet mid-answer answers a different question) but the sheet name still rides the answer payload, mirroring the panel's existing include-when-proposed behaviour"
  - "The disagree action is absent from an unknown line — that sheet already routes to the layout question, and its line says so; every JUDGED kind gets the action, including a confident row_per_record (D-12-08)"
  - "hintLabels clamps block rows to the evidence actually sent (8 rows) — the chips are checking material, not an exhaustive listing, and a last_row beyond the preview is not an error"
  - "The confirmed answers post confidence 1.0 with reasoning 'confirmed by the curator' — the exact forms 12-05 pinned at the HTTP boundary in tests/api/test_structural_hint_context.py"

patterns-established:
  - "Badge tone carries meaning, decided in the pure module: secondary = readable positive fact (labels down the side), amber = a human must act (layout unknown, header unclear), muted = structural fact (not a table, can't read this layout yet)"
  - "The verdict's badge outranks the status's; a stale layout_unknown status with a null layout still flags amber — the gate is the server's either way"

requirements-completed: [SHAPE-01, SHAPE-02]

coverage:
  - id: D1
    description: "isUnreadableShape true iff layout.kind in {not_a_table, wide_matrix, multiple_tables} — NEVER key_value (readable now), never unknown (answerable, not unreadable), never a null layout; a key_value sheet renders labels-as-chips under 'Detected labels', keeps its Schema select, and arrives ticked"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "frontend/src/state/sheets.test.ts#'key_value is never unreadable — the phase's point', #'unknown is not unreadable — an unknown sheet is ANSWERABLE', #'a key_value sheet is a first-class readable citizen' (4 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every judged sheet's layout line renders Claude's reasoning and confidence in the Copywriting Contract's exact words (incl. the N-records variant and the no-theatre unknown line), carries the disagree action — including a confident row_per_record — and amber keys ONLY off the server-sent needs_confirmation flag"
    requirement: SHAPE-01
    verification:
      - kind: unit
        ref: "frontend/src/state/sheets.test.ts#'layoutLine — the Copywriting Contract, verbatim' (8 tests), #'shows on a CONFIDENT row_per_record', #'keys amber ONLY off the server-sent needs_confirmation flag (T-12-20)'"
        status: pass
    human_judgment: false
  - id: D3
    description: "The all-unknown state is first-class: ONE workbook-level amber notice (allUnknown true only when EVERY verdict is unknown; a null layout is not a judge failure), quiet cards, contract copy verbatim"
    requirement: SHAPE-01
    verification:
      - kind: unit
        ref: "frontend/src/state/sheets.test.ts#'allUnknown — the judge-was-unreachable workbook state' (4 tests), #'the all-unknown workbook notice'"
        status: pass
    human_judgment: false
  - id: D4
    description: "The hint panel is the ONE answer surface: verdict block + 'Labels found' chips read off Claude's block indices (label columns only — TAYLOR, James never chips), key-value option offered iff blocks exist and pre-selected when present, 'One row per record' always offered revealing the header-row control, both answers posting 12-05's exact wire forms with no invented index"
    requirement: SHAPE-02
    verification:
      - kind: unit
        ref: "frontend/src/state/sheets.test.ts#'offers the key-value option ONLY when the proposal carries blocks', #'pre-selects the key-value option when present', #'reads ONLY the label columns of Claude's blocks', #'toLayoutAnswerPayload — both answers, exactly as 12-05 pinned them' (4 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The two panels render per the binding UI-SPEC on the running app: cascade Summary/Patient Info show 'labels down the side' with label chips and no patient name as a header; ticking Patient Info and confirming via the hint panel maps a 17-column dataset; headers-only keeps the verdict + labels but no grid values"
    requirement: SHAPE-02
    verification:
      - kind: manual
        ref: "12-06-PLAN.md Task 3 human-check (end-of-phase UAT walkthrough)"
        status: pending
    human_judgment: true

# Metrics
duration: 27min
completed: 2026-07-13
status: complete
---

# Phase 12 Plan 06: The Verdict Reaches the Screen Summary

**Both curator-facing surfaces now render the layout verdict per the binding 12-UI-SPEC, verbatim — every sheet card gets a layout line (kind strong, reasoning checkable, confidence mono, amber only off the server-sent gate) with the "Not right? Answer the layout yourself" action on EVERY judged sheet including a confident `row_per_record`; a `key_value` sheet is a first-class readable citizen (labels as chips under "Detected labels", Schema select intact, ticked on arrival); the all-unknown judge-failure state is ONE amber notice over quiet cards; and the `StructuralHintPanel` is finally answerable — verdict block, "Labels found" chips as the checking material, and the two-option layout question posting exactly the answer forms 12-05 pinned at the HTTP boundary**

## Performance

- **Duration:** ~27 min
- **Started:** 2026-07-13T16:41:20Z
- **Completed:** 2026-07-13T17:08:31Z
- **Tasks:** 3 (all TDD, red-first, every RED observed failing)
- **Files modified:** 6

## Accomplishments

- **The pure module re-keyed on the verdict (Task 1).** `isUnreadableShape` is `layout.kind ∈ {not_a_table, wide_matrix, multiple_tables}` — by name, the tests pin that `key_value` is NEVER unreadable (the phase's point) and `unknown` is not unreadable (answerable — collapsing them would rebuild the dead end D-12-15 killed). `layoutLine` builds every Copywriting Contract string in parts (`lead + kindPhrase + rest + confidence + trailer` reassembles verbatim), the unknown line carries no reasoning and no confidence (no "0% confident" theatre), and amber keys ONLY off the server-sent `needs_confirmation` — pinned by a test where confidence 0.55 with the gate off stays muted (T-12-20: the client renders gates, it does not set them). Per-kind `refusalLine`s replace `UNREADABLE_SHAPE_LINE`; the "PARSE-V2-01, deliberately not v1" and TAYLOR-James doc stories are rewritten as history in place, not stranded. `SheetChoice.askLayout` rides `ask_layout: true` onto the resolve payload only when set — an undisputed payload stays byte-identical to Phase 11's (Object.keys pin).
- **The sheet card, per §Screens 1 (Task 2).** The layout line inserts as card item 2; the disagree action is a real `<button>` with visible text and a 32px hit area on every judged sheet — including a confident `row_per_record`, because under `headers_only` the judge is weakest exactly where a wrong `row_per_record` re-opens D-12-12, and the human is the only check (D-12-08). Engaged state swaps the line for "You'll be asked about this sheet's layout in Review. · Use Claude's read instead". Badges per contract with tone decided in the pure module: "labels down the side" secondary, "layout unknown" amber (the header-unclear classes exactly), "not a table" / "can't read this layout yet" muted outline. A `key_value` sheet's chips read "Detected labels". The all-unknown state renders ONE amber workbook-level notice; the cards stay quiet. Nothing new got accent.
- **The hint panel, upgraded once (Task 3).** `proposal.layout` non-null IS the layout question — the panel's existing derive-controls-from-non-null-proposal-fields pattern, never `unsure_about`'s free text, and possible only because 12-05 attaches even an UNKNOWN verdict rather than dropping it. The verdict block renders first with the "Labels found" mono chips read off Claude's block indices from the evidence grid — label columns only, block order, clamped to the evidence sent, and the tests pin that `TAYLOR, James` and `CS-2026-698392` never chip. "Labels down the side — {n} record(s)" appears ONLY when the proposal carries blocks (a kind without indices is un-actionable) and arrives pre-selected; "One row per record" is always offered and reveals the existing header-row number input and clickable grid rows, pre-filled from `layout.header_row_index` (the off-by-one fix path pre-selects it). No key-value proposal → the honest limit line. Submit is disabled until an option is chosen ("Choose how the sheet is laid out."). Both answers post exactly the forms round trips A and B pinned: key-value as CONFIRMATION of Claude's blocks (never invented indices — Object.keys pin), row-per-record as `{kind, confidence: 1.0, reasoning: "confirmed by the curator", header_row_index}`. The `!answerable_by_hint` dead-end branch is kept for stale responses with no new copy. Under headers-only the grid stays value-suppressed while the verdict and labels still show (Discretion §4's ruling, residual acknowledged there).
- **`keepMounted` throughout** — `grep -rn forceMount` over both panels returns nothing AND the full vitest suite exercising them passes (the Phase-11 lesson: the grep alone proves nothing; the running suite is the gate).
- Frontend suite green: **321 passed** (baseline 256 + this plan's net 65); `npx tsc --noEmit` clean; `npm run build` clean.

## Task Commits

Each task RED then GREEN, every RED observed failing:

1. **Task 1: types + the pure derivations** — `7a6e6b8` (test, RED: 28 failures — missing exports, missing `layout` field, `askLayout` expectations), `e3ea6d3` (feat, GREEN)
2. **Task 2: the sheet card** — `5ff94f7` (test, RED: 14 failures), `d9868e8` (feat, GREEN)
3. **Task 3: the hint panel** — `9f3dbc7` (test, RED: 20 failures), `261f724` (feat, GREEN)

(12-09's backend commits `8735d9b`/`864d616` interleave on the branch — the parallel wave-5 sibling; zero file overlap.)

## Files Created/Modified

- `frontend/src/lib/types.ts` — `LayoutKind`, `SheetLayoutOut`, `SheetLayoutIn`, `KeyValueBlockIn` mirrored verbatim from 12-05's recorded wire (doc comments cite the `wire.py` classes, the file's habit); `SheetOut.layout` + `"layout_unknown"` in the status union; `SheetSelection.ask_layout?`; `StructuralHintIn.layout?`
- `frontend/src/state/sheets.ts` — the re-keyed gates, the copy builders (`layoutLine`, `refusalLine`, `sheetBadge`, `hintVerdictLine`, `hintLayoutOptions`, `hintLabels`, `toLayoutAnswerPayload`, `proposalLayout`, `allUnknown`, `showsAskLayoutAction`), every contract constant; both closed doc stories rewritten
- `frontend/src/state/sheets.test.ts` — 88 tests (34 new-named this plan): every LayoutKind × derivation combination, contract strings verbatim, the T-12-20/T-12-21 pins by name
- `frontend/src/components/SheetQuestionPanel.tsx` — `LayoutLine`/`StatusBadge` render the pure module's parts/badges; card anatomy per §Screens 1; all-unknown notice; `onAskLayoutChange` plumbing
- `frontend/src/components/StructuralHintPanel.tsx` — verdict block + labels chips, the two-option layout question, header-row control conditional on the "one row per record" answer, `headerRowActive` grid affordance, legacy branches kept
- `frontend/src/state/upload.test.ts` — two `SheetOut` fixtures gain `layout: null` (deviation 1)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `upload.test.ts` fixtures needed `layout: null`**
- **Found during:** Task 3 (`npm run build`)
- **Issue:** `SheetOut.layout` is mirrored as REQUIRED (`layout: SheetLayoutOut | null`, exactly as the wire always sends it). `tsc -b` (the build's project mode, which includes test files `tsc --noEmit` alone did not surface) failed on two hand-built `SheetOut` literals in `upload.test.ts` — a file not in the plan's list. Making the field optional instead would have weakened the mirror the plan ordered verbatim.
- **Fix:** `layout: null` added to both fixtures — two lines, no behavioural change.
- **Files modified:** frontend/src/state/upload.test.ts
- **Verification:** `npm run build` clean; full suite green
- **Commit:** `261f724`

### Judgment Calls

**2. The sheet Select is hidden on a layout question, and the sheet name rides the payload**
- A layout question is the member's OWN question — `layout_question_for` sets `proposal.sheet_name`, and the panel's derive-from-non-null rule would have rendered a one-option sheet Select mid-answer. Suppressed for layout questions; the sheet name is still included in the answer payload (mirroring the panel's existing include-when-proposed behaviour), so the server re-parses the right sheet.

**3. No disagree action on the unknown line**
- The contract puts the action "on every judged sheet's layout line"; an `unknown` sheet is not judged, and its line already says it will be asked in Review — a disagree button there would offer to route to the place it is already going. Pinned by `showsAskLayoutAction`'s named test.

---

**Total deviations:** 1 auto-fixed (a two-line required-field collateral) + 2 recorded judgment calls
**Impact on plan:** None on scope. Every `must_have` truth holds as specified.

## TDD Gate Compliance

RED and GREEN commits exist for all three tasks (`test(...)` before `feat(...)` in each), and every RED was observed failing before its implementation: 28 failures (Task 1), 14 (Task 2), 20 (Task 3). No test passed unexpectedly at RED.

## Issues Encountered

None beyond the deviations above. The plan and the UI-SPEC matched the shipped wire exactly — every field name in `types.ts` was checked against `api/wire.py` (`SheetLayoutOut:681`, `SheetLayoutIn:410`, `KeyValueBlockIn:372`, `SheetSelectionIn.ask_layout:910`) and both answer forms against the round-trip tests before a line was written.

## Known Stubs

None. Every derivation is wired to the real wire shape and every rendering to a real derivation; no placeholder copy, no hardcoded-empty data paths (empty `hintLabels`/`keyValueOptionLabel` returns are honest absences the spec designs for, with the limit line covering them).

## Threat Flags

None new. T-12-19's acknowledged residual (labels are Claude's claim about which cells are names; a wrong verdict under the redacted grid would surface values as chips) is exactly the UI-SPEC Discretion §4 ruling this plan implements — mitigated by the reasoning/confidence rendering and the disagree affordance on every judged sheet, per the plan's own register. T-12-18 (evidence_rows not server-redacted under headers-only) remains the pre-existing transferred leak, neither fixed nor worsened.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **End-of-phase human check (pending):** the Task 3 walkthrough — upload `data/synthetic/lab_corpus/cascade_allergy_CS-2026-698392.xlsx`, see "labels down the side" with label chips on Summary/Patient Info (no patient name as a header), tick Patient Info, confirm via the hint panel, get the 17-column dataset; re-upload with headers-only ON and confirm verdict + labels show with no grid values.
- **12-07 (Wave C):** the frontend now renders every verdict state including `layout_unknown`; the classifier-fallback statuses (`drawing_only`/`unsupported_shape` with a null layout) still render through the kept legacy badge arms — those arms outlive the classifier only as stale-response defence.
- **12-08:** the ask-me-instead flow is live end to end on the client (flag → payload → the member's hint panel via the Phase 11 recursive arm, `keepMounted` untouched).

---
*Phase: 12-claude-reads-the-structure*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 6 modified files and the SUMMARY exist on disk; all 6 task commits (`7a6e6b8`, `e3ea6d3`, `5ff94f7`, `d9868e8`, `9f3dbc7`, `261f724`) are in history; every named artifact exists (`SheetLayoutOut` in types.ts, `proposalLayout`/`toLayoutAnswerPayload` in sheets.ts, `ALL_UNKNOWN_NOTICE` in SheetQuestionPanel, `HINT_LAYOUT_QUESTION_LABEL` in StructuralHintPanel); ZERO file deletions across the plan's commits; `grep forceMount` over both panels returns nothing; frontend suite 321 passed, `tsc --noEmit` and `npm run build` clean.

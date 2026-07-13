---
phase: 11-multi-sheet-ingest
plan: "09"
subsystem: ui
tags: [react, typescript, vitest, shadcn, checkbox, sheet-question, discriminated-union, tdd]
status: complete

# Dependency graph
requires:
  - phase: 11-07
    provides: "The exact wire contract rendered here: SheetOut (headers, row_count, status, ranked proposals with matched pairs), SheetSchemaProposalOut, SheetResolveRequest, SheetGroupResponse"
  - phase: 10-frictionless-correct-ingest
    provides: "The upload reducer's phase/action recipe, the DateFormatQuestionPanel multi-item/single-submit shape, the shadcn design system and type roles"
provides:
  - "lib/types.ts: SheetSchemaProposal, SheetOut, SheetQuestionResponse, SheetSelection, SheetResolveRequest, SheetMember(Response), SheetGroupResponse — UploadResponse union carries both new kinds"
  - "state/upload.ts: sheetQuestion / resolvingSheets / sheetGroup phases + SUBMIT_SHEETS / SHEETS_SUCCESS / SHEETS_ERROR triple; all three phases lock the dropzone"
  - "state/sheets.ts (NEW, pure): initialSelections, submitBlockedReason, toResolvePayload, coverageLine — every panel decision, zero React"
  - "components/SheetQuestionPanel.tsx (NEW): the sheet manifest — checkbox row, header chips, ALWAYS-visible coverage with matched pairs and the Not-matched remainder, per-sheet Schema Select, one submit"
  - "components/ui/checkbox.tsx: the one approved shadcn install (zero new npm packages)"
  - "lib/api.ts: resolveSheets(request) -> Promise<SheetGroupResponse>"
affects:
  - "11-10 (routes the sheetGroup phase from App.tsx into ReviewGroupTabs; the Upload screen's sheet_group arm is a deliberate no-op until then)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "resolvingSheets CARRIES the question response (unlike its resolving siblings) and SHEETS_ERROR returns to sheetQuestion with errorMessage — the panel never unmounts mid-flight or on failure, so the curator's ticks and Schema choices (component-local state) survive, per UI-SPEC's binding 'all selections preserved' error state"
    - "The panel is keyed by upload_token in Upload.tsx: a NEW workbook's question remounts with fresh pre-selections, while sheetQuestion <-> resolvingSheets transitions (same token) preserve state"
    - "Count-emphasis without a second copy source: coverageLine's profile/crosswalk strings always LEAD with the count, so the component slices the tested string after an emphasized `{m}/{t}` span — copy stays single-sourced in state/sheets.ts"

key-files:
  created:
    - frontend/src/state/sheets.ts
    - frontend/src/state/sheets.test.ts
    - frontend/src/components/SheetQuestionPanel.tsx
    - frontend/src/components/ui/checkbox.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/upload.ts
    - frontend/src/state/upload.test.ts
    - frontend/src/screens/Upload.tsx

key-decisions:
  - "SHEETS_ERROR lands back on sheetQuestion (with errorMessage), NEVER on the error phase: the sibling recipe's error path tears the panel down, which would destroy every tick and per-sheet Schema choice the curator just made — UI-SPEC §Screens 1 'all selections preserved' is binding and wins over touch-for-touch symmetry"
  - "The tick state reads sheet.status AND the proposal list: a gate-failed sheet (drawing_only/unsupported_shape/header_uncertain) arrives UNTICKED however well it scores, but stays present, scored, and tickable (SHEET-04). meridian's LEGEND (1/7, header_uncertain) therefore arrives unticked via the GATE rule, not via a coverage threshold that does not exist (D-11-24)"
  - "A tie pre-fills nothing and the Upload dropdown does not get to settle it (11-07's hard short-circuit, mirrored client-side): _preSelectedSchema returns null on tie BEFORE any fallback"
  - "The D-11-16 dropdown fallback is applied client-side too (proposed_schema ?? defaultSchema after the tie short-circuit) — belt-and-braces over the server's own _pre_selection, and it fills the Select WITHOUT ticking the sheet"

patterns-established:
  - "Question panels whose answers must survive a failed resolve: carry the response through the resolving phase and route the error back to the question phase with a message field — never through the dropzone's error surface"

requirements-completed: [SHEET-01, SHEET-05]

coverage:
  - id: D1
    description: "The 5th and 6th response kinds in the client union, handled exhaustively — assertNever still compiles, all three new phases lock the dropzone, and the SUBMIT/SUCCESS/ERROR triple drives sheetQuestion -> resolvingSheets -> sheetGroup"
    requirement: SHEET-01
    verification:
      - kind: unit
        ref: "frontend/src/state/upload.test.ts#transitions uploading -> sheetQuestion on a kind:'sheet_question' UPLOAD_SUCCESS"
        status: pass
      - kind: unit
        ref: "frontend/src/state/upload.test.ts#locks the dropzone for all three sheet phases"
        status: pass
      - kind: other
        ref: "npm run build (tsc -b) — fails with TS2345 at both assertNever sites when a case is removed; verified during RED, green after GREEN"
        status: pass
    human_judgment: false
  - id: D2
    description: "All panel logic as pure functions — pre-selection derivation for the four D-11-06 states (proposal ticked+Schema, zero-coverage skip, tie ticked+empty Select, gate-failed unticked-but-selectable), submit gating with UI-SPEC copy verbatim, resolve payload of only ticked sheets, and the three coverage-line copies"
    requirement: SHEET-05
    verification:
      - kind: unit
        ref: "frontend/src/state/sheets.test.ts (14 tests, all four pre-selection states, both blocked reasons, exact payload keys, all three coverage sources)"
        status: pass
      - kind: other
        ref: "grep -c 'useState' frontend/src/state/sheets.ts -> 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "SheetQuestionPanel renders every worksheet with headers, row count, status badge, and its coverage-bearing proposal — matched pairs and 'Not matched:' always visible, never behind a disclosure; Claude proposals visibly labelled evidence-free; submit blocked with the named reason; error keeps the panel up with selections preserved"
    requirement: SHEET-01
    verification:
      - kind: other
        ref: "grep -c 'Not matched' SheetQuestionPanel.tsx -> 1; grep -cE '#[0-9a-fA-F]{6}' -> 0; gating-function grep -> 0; npm run build && npm run lint && npm test -- --run all green (223 tests)"
        status: pass
    human_judgment: true
    rationale: "Rendering adequacy (coverage prominence per D-11-24, amber/muted color discipline, the 32px click target) is checker-validated, not test-asserted — the logic beneath it is D2's tested surface"
  - id: D4
    description: "resolveSheets posts SheetResolveRequest to /api/sheets/resolve with credentials and parses the sheet_group response; the shadcn checkbox install added zero npm packages"
    verification:
      - kind: unit
        ref: "frontend/src/state/upload.test.ts#resolveSheets POSTs the SheetResolveRequest to /api/sheets/resolve with credentials and parses the sheet_group response"
        status: pass
      - kind: other
        ref: "git diff frontend/package.json frontend/package-lock.json -> empty (T-11-34/T-11-SC)"
        status: pass
    human_judgment: false

# Metrics
duration: 13min
completed: 2026-07-13
---

# Phase 11 Plan 09: The Sheet-Selection Panel Summary

**A multi-sheet workbook now shows every worksheet below the dropzone — headers, row count, status, and its ranked Schema proposal WITH the coverage that produced it — and the human ticks, chooses, and confirms; the coverage number ("1/7" beside "6/7") is rendered as the control it is, ties arrive with an empty Select, and a failed resolve preserves every selection.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-13T09:19:22Z
- **Completed:** 2026-07-13T09:32:40Z
- **Tasks:** 2 (Task 1 TDD: RED then GREEN)
- **Files modified:** 9 (4 created, 5 modified)
- **Suite:** frontend 223 passed (was 208; +15 tests), `npm run build` (tsc -b) and `npm run lint` green

## Accomplishments

- **The coverage is on the screen, and it is the control.** Each sheet card renders its top proposal's coverage line with the count emphasized (600, tabular-nums, accent), then every matched pair (`{field} ← {header}`) and the `Not matched: {fields}` remainder — always visible, never behind a disclosure. Per D-11-24 there is no threshold and never will be: "1/7" beside "6/7" is the only thing that tells a curator LEGEND is a legend, so it is rendered impossible to miss.
- **The four pre-selection states of D-11-06, exactly, as tested pure functions.** A proposal pre-ticks and pre-selects; zero coverage (`proposals: []` — 11-07's ruling, never `proposed_schema`) arrives unticked with the skip line; a tie arrives ticked with an EMPTY Select and the amber tie notice — and neither the scorer nor the Upload dropdown gets to break it; a gate-failed sheet arrives unticked, marked (muted badges for structural facts, amber for `header unclear`), and still tickable — marked, never dropped, never disabled away (SHEET-04).
- **A Claude proposal is visibly labelled as evidence-free.** `source: "claude"` renders "No crosswalk match — Claude suggests {schema}. Check it before ingesting." — no fabricated count, no pairs, because there are none (D-11-19). A human is entitled to know a proposal has nothing behind it.
- **Submit fails closed with the reason named.** Disabled at 0 ticked ("Tick at least one sheet to ingest.") and while any ticked sheet lacks a Schema ("Choose a Schema for '{sheet}' — ties aren't broken automatically."), mirroring the server's own 422s. The payload carries ONLY ticked sheets with their chosen Schemas — exact `SheetResolveRequest` keys pinned by test.
- **A failed resolve destroys nothing.** `resolvingSheets` carries the question and `SHEETS_ERROR` returns to `sheetQuestion` with the consequence-first message rendered as a destructive Alert INSIDE the still-mounted panel — every tick and Schema choice survives, per UI-SPEC's binding error state.
- **The compile-time net held twice.** Extending `UploadResponse` broke `assertNever` in both `upload.ts` and `Upload.tsx` (verified failing during RED), and the build is green only because both switches now handle both kinds — no `default` was widened.
- **The one approved install, cleanly.** `npx shadcn@latest add checkbox` created exactly `components/ui/checkbox.tsx` and changed neither `package.json` nor the lockfile (T-11-34/T-11-SC satisfied; `@base-ui/react` was already a dependency).

## Task Commits

1. **Task 1: the two new kinds, the three new phases, and the pure panel logic** — RED: `a5bdd67` (test) · GREEN: `f93b877` (feat)
2. **Task 2: SheetQuestionPanel — the coverage is on the screen** — `37087a4` (feat)

## Files Created/Modified

- `frontend/src/lib/types.ts` — the seven sheet wire mirrors + both kinds in `UploadResponse`; `SheetMemberResponse` is the recursive arm (`Exclude<UploadResponse, the two group kinds>`)
- `frontend/src/lib/api.ts` — `resolveSheets(body) -> Promise<SheetGroupResponse>`
- `frontend/src/state/upload.ts` — the three phases, the action triple, two `fromResponse` cases, three `toDropzonePhase -> "locked"` mappings
- `frontend/src/state/sheets.ts` — `initialSelections` / `submitBlockedReason` / `toResolvePayload` / `coverageLine` (+ the `SheetChoice` answer shape); zero React imports
- `frontend/src/state/sheets.test.ts` — 14 pure-function tests
- `frontend/src/state/upload.test.ts` — +6 reducer/dropzone tests, +1 API-client test
- `frontend/src/components/SheetQuestionPanel.tsx` — the panel + its `SheetCard` per-sheet block
- `frontend/src/components/ui/checkbox.tsx` — official shadcn primitive
- `frontend/src/screens/Upload.tsx` — panel mounted in the inline-question slot; `SUBMIT_SHEETS -> resolveSheets -> SHEETS_SUCCESS/ERROR` wiring; both new kinds in its `assertNever` switch

## Decisions Made

- **`SHEETS_ERROR` deviates from the sibling error recipe on purpose** (see key-decisions): the UI-SPEC error state ("Your selections are kept") is unimplementable if the panel unmounts, and the panel is where the selections live.
- **The panel reads the question straight off reducer state** (both sheet phases carry `response`), so no `lastSheetQuestion` screen-local mirror was needed — one less state to drift.
- **`sheet_group` is terminal for the Upload screen**: the reducer lands on `sheetGroup`, the dropzone stays locked, and routing the group into Review's member tabs is 11-10's declared job (`App.tsx` routes the phase there).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1's verify (`npm run build`) cannot pass without Upload.tsx's case arms, a Task 2 file**

- **Found during:** Task 1 (GREEN step)
- **Issue:** Extending the `UploadResponse` union breaks `assertNever` in `screens/Upload.tsx` at compile time (the safety net working as designed) — but `Upload.tsx` is listed under Task 2, while Task 1's verify and acceptance criteria require a green build.
- **Fix:** Added the minimal `sheet_question` / `sheet_group` case arms to `Upload.tsx`'s `handleResponse` switch in Task 1 (no panel wiring, no widened `default`); Task 2 completed the real wiring.
- **Files modified:** `frontend/src/screens/Upload.tsx`
- **Verification:** `npm run build` green at the end of Task 1; the RED step captured the compile failure first.
- **Committed in:** `f93b877` (Task 1 GREEN)

**2. [Rule 2 - Design contract] SHEETS_ERROR routes back to the question, not to the `error` phase**

- **Found during:** Task 1 (behavior design)
- **Issue:** The plan orders the reducer triple copied "touch-for-touch" from the date recipe, whose ERROR arm lands on `phase: "error"` — which unmounts the panel and destroys the curator's ticks and per-sheet Schema choices. UI-SPEC §Screens 1 (approved, binding) requires the error state to preserve all selections.
- **Fix:** `resolvingSheets` carries the `SheetQuestionResponse`, and `SHEETS_ERROR` transitions back to `sheetQuestion` with an `errorMessage` field the panel renders as a destructive Alert. `SHEETS_ERROR` deliberately carries no `title` — it never reaches the dropzone's error surface.
- **Files modified:** `frontend/src/state/upload.ts`, `frontend/src/state/upload.test.ts`
- **Verification:** `transitions resolvingSheets -> sheetQuestion (NOT error) on SHEETS_ERROR` pins the contract.
- **Committed in:** `a5bdd67` (RED) / `f93b877` (GREEN)

**3. [Rule 1 - Bug] The plan's manual-verification claim about meridian's LEGEND is stale against D-11-24 — third recurrence of the same stale claim**

- **Found during:** Task 1 (test design)
- **Issue:** The plan's `<verification>` says LEGEND appears "with 'No canonical fields matched any Schema — proposed: skip this sheet.'" It does not and must not: per D-11-24 (and 11-07's shipped wire), LEGEND honestly carries a 1/7 proposal (`compound_id ← 'CMP'`) and `status: header_uncertain`. Rendering the zero-coverage skip line for it would require inventing the suppression threshold D-11-24 forbids. **11-04 and 11-07 both flagged the identical stale-LEGEND claim — planners should stop propagating it.**
- **Fix:** LEGEND's honest behavior is pinned instead: unticked via the GATE rule (`header_uncertain`), with its 1/7 coverage, its matched pair, and the "header unclear" badge + helper line all visible — the coverage number doing exactly the job D-11-24 assigned it. The genuine skip line is pinned where it is genuinely true (a zero-proposal sheet).
- **Files modified:** `frontend/src/state/sheets.test.ts`
- **Verification:** `pre-unticks a header-uncertain sheet even when it carries a real proposal (meridian's LEGEND at 1/7)` and `pre-unticks a zero-coverage sheet`.
- **Committed in:** `a5bdd67` (RED) / `f93b877` (GREEN)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 design-contract, 1 stale plan claim). **Impact:** correctness-only, no scope creep. Deviation 2 is the one behavioral divergence from the sibling recipe and exists to satisfy the binding UI-SPEC.

## Known Stubs

- **`Upload.tsx`'s `sheet_group` arm is a deliberate no-op** (`case "sheet_group": return;`): the reducer's `sheetGroup` phase locks the dropzone and holds the `SheetGroupResponse`, but nothing routes it to Review yet. This is not an accidental dead end — 11-10's plan explicitly claims "`App.tsx`: route the `sheetGroup` phase to `ReviewGroupTabs`" and reads this SUMMARY for the client types. No other stub: no placeholder values, no unwired data path, no TODO.

## Threat Flags

None new. Both `mitigate` dispositions applied:

| Threat | Applied |
|---|---|
| T-11-33 (XSS via worksheet title / header text) | Sheet names, headers, Schema names, and pair text render as text children only — no `dangerouslySetInnerHTML`, no `innerHTML` anywhere in the new component |
| T-11-34 / T-11-SC (supply chain via the shadcn add) | Official registry, one file created, `git diff frontend/package.json frontend/package-lock.json` empty — zero packages installed |
| T-11-35 (client re-sending server state) | `toResolvePayload` emits exactly `{upload_token, selections:[{sheet_name, schema_name}]}` — exact key set pinned by test; the manifest/workbook/Schemas stay server-retained |

## Issues Encountered

- The `key_links` pattern in the plan frontmatter expects `from "../state/sheets"`; the component imports `from "@/state/sheets"` — the project's established alias convention for the components layer (every sibling panel imports `@/state/*`). The link itself (panel renders, sheets.ts decides) holds exactly as specified.

## User Setup Required

None.

## Verification

- `cd frontend && npm run build && npm run lint && npm test -- --run` → all green (223 passed; lint's 3 warnings are pre-existing in shadcn `ui/` files).
- `git diff frontend/package.json frontend/package-lock.json` → empty.
- Task 1 ACs: build green; `sheets.test.ts` passes (all four pre-selection states + both blocked reasons); `grep -c 'sheet_question\|sheet_group' lib/types.ts` → 7 (≥2); `grep -c useState state/sheets.ts` → 0.
- Task 2 ACs: `ui/checkbox.tsx` exists with zero dependency delta; `grep -c 'Not matched' SheetQuestionPanel.tsx` → 1 and matched-pair rendering present; hex grep → 0; gating-function grep → 0.
- Manual meridian check: deferred to browser UAT — the expected render is LEGEND unticked with "header unclear" (amber) and its honest 1/7 coverage visible (per D-11-24), not the plan's stale skip-line claim (Deviation 3); the underlying derivations are unit-pinned.

## TDD Gate Compliance

- **RED gate:** `a5bdd67` — verified failing first: `sheets.test.ts` failed at collection (module absent), 6 behavioral failures in `upload.test.ts`; `tsc -b` additionally captured the `assertNever` compile breaks once the union widened.
- **GREEN gate:** `f93b877` — 64/64 in the two target files, build green.
- **REFACTOR:** not needed.

## Next Phase Readiness

- **11-10 has everything it declared it needs:** `SheetGroupResponse` / `SheetMember` / `SheetMemberResponse` (the recursive arm) in `lib/types.ts`, the `sheetGroup` phase carrying `response` + `groupId` on the reducer, and the Upload screen's deliberate no-op to replace with routing into `ReviewGroupTabs`.
- The dropzone stays locked through `sheetGroup`, so until 11-10 lands, resolving a multi-sheet workbook parks the Upload screen — expected, and exactly the seam 11-10 fills.

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

## Self-Check: PASSED

- All 4 created files exist on disk, plus this SUMMARY.
- All 3 task commits present in `git log`: `a5bdd67` (RED), `f93b877` (GREEN), `37087a4` (Task 2).
- No file deletions in any of this plan's commits.
- Every acceptance criterion from both tasks re-run and passes.
- Full frontend suite green: 223 passed; `npm run build` (typecheck included) and `npm run lint` green.

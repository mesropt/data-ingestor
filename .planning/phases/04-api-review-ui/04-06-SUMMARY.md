---
phase: 04-api-review-ui
plan: 06
subsystem: ui
tags: [react, vite, vitest, typescript, review-screen, confirm-gate, learning-loop]

# Dependency graph
requires:
  - phase: 04-api-review-ui
    provides: "04-04's scaffold (D-01 tokens, AppShell, lib/types.ts, lib/api.ts's typed confirm stub), 04-05's Upload screen + upload_token/field_mappings seam (App.tsx's onMapped), and 04-03's POST /api/confirm (the server-side P1 gate) + GET /api/export/{run_id}/{fmt} this screen calls"
provides:
  - "state/review.ts + review.test.ts -- a pure, vitest-covered module: isReady (mirrors domain MappingProposal.is_ready), resolutionProgress, the three D-02 resolution paths (resolveByChip/Accept/Dropdown, each immutable and single-field), toConfirmPayload (exact /api/confirm shape, never a trusted ready flag), and isAutoApplied (UI-06)"
  - "lib/api.ts -- real confirm(payload) POSTing to /api/confirm, mapping a 422 to a typed GateRejected(unclearFields) instead of a bare ApiError"
  - "screens/Review.tsx + components/ReviewTable.tsx + FieldRow.tsx + ConfidenceChip.tsx + ConfirmGate.tsx + ExportBar.tsx + ProfileAppliedBanner.tsx -- the full UI-03/04/05/06 Review screen: side-by-side source/target panes, amber-at-rest uncertain rows with reasoning/validator_note/chips/Accept/dropdown, a sticky confirm gate mirroring the server's is_ready, post-confirm export links, and the accent-toned auto-apply banner"
  - "App.tsx/Upload.tsx -- threaded the selected FieldSetPayload from Upload through onMapped into Review (needed for toConfirmPayload's field_set); replaced the Plan-05 ReviewPlaceholder with the real Review screen, keyed by upload_token so a fresh/re-upload always remounts with fresh local resolution state"
affects: [05-demo-and-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "state/review.ts stays a pure module with no React import (mirrors state/fieldSet.ts/state/upload.ts's own split) -- Review.tsx is the only caller, holding the editable field_mappings array in useState and dispatching every resolution through the tested resolveBy* functions rather than a hand-rolled inline mutation"
    - "isReady is the SAME function ConfirmGate's disabled prop and Review.tsx's own ready flag both read -- there is exactly one is_ready mirror in the client, never a second heuristic computed differently in two places (UI-05, T-04-19)"
    - "api.confirm maps a 422 ApiError to a typed GateRejected(unclearFields) at the api.ts boundary, not in the screen -- Review.tsx's catch block distinguishes GateRejected from any other ApiError by instanceof, never by re-parsing a status code or a message string a second time"
    - "Review.tsx is keyed by mapping.upload_token in App.tsx (not synchronized via useEffect) -- a fresh upload (including the UI-06 same-signature re-upload) always gets a brand-new component instance with fresh local resolution state, the same 'remount over reconcile' pattern already implicit in Upload.tsx's own reducer-per-mount design"
    - "ExportBar renders plain <a href download> links styled via the exported buttonVariants() function rather than routing through the base-ui Button component's render prop -- avoids depending on Button forwarding an anchor correctly for a plain-GET download link, the one place this plan diverges from the Button-everywhere convention 04-04/04-05 established"

key-files:
  created:
    - frontend/src/state/review.ts
    - frontend/src/state/review.test.ts
    - frontend/src/components/ReviewTable.tsx
    - frontend/src/components/FieldRow.tsx
    - frontend/src/components/ConfidenceChip.tsx
    - frontend/src/components/ConfirmGate.tsx
    - frontend/src/components/ExportBar.tsx
    - frontend/src/components/ProfileAppliedBanner.tsx
    - frontend/src/screens/Review.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/App.tsx
    - frontend/src/screens/Upload.tsx

key-decisions:
  - "The Source Columns pane renders column NAMES ONLY, with a short muted note explaining sample values aren't part of the response -- 04-UI-SPEC.md's literal description ('1-2 truncated sample values shown as small muted chips') cannot be implemented against the actual wire contract: MappingResponse.source_columns is `list[str]` (04-01/04-02's api/wire.py), never sample cell values, for either the headers-only or fresh-Claude path. Adding sample values would require a new backend wire field (a schema change, Rule 4 territory, and outside this plan's declared files_modified), so this plan renders what the contract actually carries and documents the gap explicitly rather than fabricating sample data or silently omitting the sub-bullet with no explanation."
  - "resolveByChip additionally adopts the selected candidate's own confidence (not just source_column), and resolveByDropdown sets confidence to 1.0 -- the plan's Task 1 behavior bullets only test source_column + needs_confirmation, but a resolved FieldRow's clear-state badge shows a confidence percentage, so leaving a stale pre-resolution confidence value in place would misrepresent what the human just chose. resolveByAccept deliberately leaves confidence untouched (it is explicitly accepting Claude's proposal as-is)."
  - "Accept is enabled even when source_column is null (the inferred_value-only MAP-02 case) -- accepting an inferred value (e.g. a unit inferred from value range with no matching column) is a legitimate D-02b resolution path per the domain model (FieldMapping.is_clear only checks needs_confirmation, not source_column), not a state Accept should refuse to act on."
  - "Review.tsx's own 'Loading state' and 'Error state' (04-UI-SPEC.md Screen 3) are intentionally NOT implemented -- Plan 05's own architecture (App.tsx's onMapped seam) already established that Review is only ever reached AFTER a mapping response resolves; the initial parse/map call's loading and error UI live entirely in Upload.tsx (04-05), so Review structurally never needs its own pre-mapping loading/error branch. This is a continuation of 04-05's own documented scope boundary, not a new gap."
  - "The vertical height budget for the two-pane region (`h-[calc(100vh-8rem)]` on Review.tsx's root, `h-full overflow-y-auto` on ReviewTable) is a reasoned approximation of AppShell's actual chrome (header h-16 = 4rem + main's py-8 = 4rem = 8rem), not a pixel-verified value -- consistent with the plan's own instruction that visual/layout conformance to 04-UI-SPEC.md is gsd-ui-checker's job, not a fabricated pixel unit test."
  - "App.tsx/Upload.tsx were modified even though this plan's frontmatter files_modified list only names lib/api.ts + the Review screen/components + state/review.ts -- Review needs the FieldSetPayload the upload was mapped against to build toConfirmPayload's field_set, and nothing else in the app retains it once Upload's own selectedTemplate state is gone. Mirrors 04-04's own documented App.tsx-wiring deviation (Rule 2: missing critical functionality) for the identical reason -- without it, the plan's own must-have ('the confirm request carries the upload_token + edited field_mappings the /api/confirm gate rebuilds') would be unreachable."

patterns-established:
  - "A single is_ready-mirroring function is read from exactly one place by both the gate component's disabled prop and the screen's own confirm-payload logic -- never two independently-computed readiness checks that could drift."
  - "A typed error subclass (GateRejected) is thrown from the api.ts boundary function itself (not the screen) when a specific HTTP status carries screen-actionable structure (unclear_fields) -- the screen's catch block does instanceof narrowing, never a second parse of the raw ApiError.detail."

requirements-completed: [UI-03, UI-04, UI-05, UI-06]

coverage:
  - id: D1
    description: "state/review.ts's isReady mirrors domain MappingProposal.is_ready exactly (empty mapping never ready, any needs_confirmation=true blocks ready); resolutionProgress counts clear/total; the three D-02 resolution paths (resolveByChip/Accept/Dropdown) each update exactly one field immutably; toConfirmPayload produces the exact /api/confirm request shape with no trusted ready flag; isAutoApplied gates UI-06's banner off the server's own provenance claim"
    requirement: "UI-05"
    verification:
      - kind: unit
        ref: "frontend/src/state/review.test.ts (15 tests: isReady x4, resolutionProgress x1, resolveByChip x1, resolveByAccept x2, resolveByDropdown x1, toConfirmPayload x2, isAutoApplied x2, api.confirm x2) -- npm run test -- --run"
        status: pass
    human_judgment: false
  - id: D2
    description: "api.confirm POSTs the exact ConfirmRequest JSON body to /api/confirm and returns the parsed ConfirmResponse on 200; a 422 is mapped to a typed GateRejected(unclearFields), never a generic ApiError, so the caller can distinguish a gate rejection from any other failure"
    requirement: "UI-05"
    verification:
      - kind: unit
        ref: "frontend/src/state/review.test.ts#'api.confirm -- /api/confirm' (2 tests, mocked fetch) -- npm run test -- --run"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Review screen renders the side-by-side source/target layout (UI-03) from a real MappingResponse; an amber FieldRow shows Claude's reasoning at rest (never hover), the validator_note on its own sub-line when present, ranked ConfidenceChips, an Accept button, and a manual full-column dropdown (UI-04, D-02); resolving any of the three ways clears that field's amber state locally; ConfirmGate is disabled while any field is yellow and shows the verbatim tooltip copy (UI-05); a server 422 (GateRejected) shows the rejection Alert and never renders ExportBar; a 200 renders ExportBar with the four export links"
    requirement: "UI-04"
    verification:
      - kind: other
        ref: "npm run build (tsc -b && vite build) -- frontend/, all three task commits"
        status: pass
    human_judgment: true
    rationale: "Visual conformance to 04-UI-SPEC.md (amber-at-rest not hover, validator_note visually distinct from reasoning, the exact D-02 control set, side-by-side layout with horizontal-scroll-not-body-scroll, color/spacing/typography tokens) requires the dedicated gsd-ui-checker pass this executor does not run itself, and no live browser round-trip against a running FastAPI backend + Vite dev server was exercised this session (the plan explicitly forbids running the dev server interactively during execution). The resolution/gate LOGIC is vitest-covered (D1/D2); the RENDERING is not pixel-unit-tested by design."
  - id: D4
    description: "ProfileAppliedBanner renders above the two-pane region only when the upload response's provenance is auto-applied-from-profile (UI-06); it is accent (teal/--primary) toned, distinct from the success-green FieldRow border and the amber uncertain wash; the confirm+save path (save_profile: true on every /api/confirm call) is what makes a subsequent same-signature upload return that provenance with zero amber rows -- the visible learning loop"
    requirement: "UI-06"
    verification:
      - kind: other
        ref: "npm run build && npm run test -- --run -- frontend/, ProfileAppliedBanner.tsx task commit"
        status: pass
    human_judgment: true
    rationale: "The plan's own Task 3 verification explicitly assigns banner-tone conformance to gsd-ui-checker rather than a fabricated pixel unit test; the money-shot's END-TO-END browser proof (define -> upload -> resolve -> confirm -> re-upload -> zero amber + banner) is the Task 4 checkpoint's job, documented below under Manual UAT rather than executed live in this session (a running FastAPI + Vite dev server round-trip was not exercised, matching every prior plan in this phase's documented scope boundary)."

duration: ~14min
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 6: Review Screen + Confirm/Learn + Auto-Apply Money Shot Summary

**The full UI-03/04/05/06 Review screen -- side-by-side source/target panes, amber-at-rest uncertain FieldRows with Claude's reasoning + validator_note + D-02 chip/Accept/dropdown resolution, a sticky ConfirmGate mirroring the server's is_ready gate, post-confirm ExportBar, and the accent-toned ProfileAppliedBanner that makes the "0 Claude calls" learning loop visible.**

## Performance

- **Duration:** ~14 min (commits span 12:58:57-13:06:11)
- **Started:** 2026-07-11T12:58:57+04:00 (RED test commit)
- **Completed:** 2026-07-11T13:06:11+04:00 (Task 3 commit)
- **Tasks:** 4 (Task 1 `tdd="true"`: RED test commit, then GREEN implementation commit; Task 2/3 auto; Task 4 checkpoint documented below, not executed live)
- **Files modified:** 12 (9 created, 3 modified)

## Accomplishments

- `state/review.ts` (TDD, RED then GREEN): a pure module -- `isReady` (mirrors `domain/models.py::MappingProposal.is_ready` exactly, including the empty-mapping-never-ready guard), `resolutionProgress`, the three D-02 resolution paths (`resolveByChip`/`resolveByAccept`/`resolveByDropdown`, each an immutable single-field update), `toConfirmPayload` (the exact `/api/confirm` request shape, no trusted `ready` flag anywhere on the wire), and `isAutoApplied` (UI-06's banner gate) -- 15 new vitest tests, confirmed genuinely RED first (`Cannot find module './review'`).
- `lib/api.ts`: real `confirm(payload)` POSTing `ConfirmRequest` JSON to `/api/confirm`; a 422 is mapped to a typed `GateRejected(unclearFields)` (never a bare `ApiError`) so the Review screen's catch block can distinguish a server gate rejection from any other failure by `instanceof`.
- `screens/Review.tsx` + `components/ReviewTable.tsx` + `FieldRow.tsx` + `ConfidenceChip.tsx` + `ConfirmGate.tsx` + `ExportBar.tsx` (UI-03/04/05, the centerpiece): the full two-pane review UI. `ReviewTable` renders the source-column names left (mono list, with a note that sample values aren't in the wire response -- see Decisions) and one `FieldRow` per `FieldMapping` right, in declared order, inside a horizontally-scrolling `min-w-[960px]` container so the page body itself never scrolls horizontally. `FieldRow`'s clear state shows a thin `success`-tinted left border with reasoning collapsed behind "Why?"; its amber (`needs_confirmation`) state shows the full `uncertain` wash with Claude's reasoning ALWAYS visible at rest (D-01's hard rule, never hover), `validator_note` on its own distinct sub-line when present (omitted entirely when `null`), `ConfidenceChip`s for every alternative (D-02a), an "Accept" button (D-02b), and a manual `Select` populated with every source column (D-02c) -- the guaranteed escape hatch. `ConfirmGate`'s disabled state derives directly from `state/review.ts`'s `isReady`, with the verbatim disabled-tooltip copy ("Resolve {n} more uncertain field(s) before confirming."). On confirm, a `GateRejected` (422) shows the verbatim rejection `Alert` and does NOT render `ExportBar` -- only a 200 `ConfirmResponse.export` does (P1, T-04-18).
- `components/ProfileAppliedBanner.tsx` (UI-06, the money shot's second half): built as a minimal-but-real placeholder in Task 2 (so `Review.tsx` compiled and the conditional render wired correctly at that commit boundary, mirroring 04-05's precedent for mutually-dependent files), then replaced in Task 3 with the full implementation -- accent (teal/`--primary`) toned, `RefreshCw` icon, verbatim Copywriting Contract copy plus the "Not right? Edit anyway." no-op link. Renders only when `isAutoApplied(mapping.provenance)` is true.
- `App.tsx`/`Upload.tsx`: threaded the selected `FieldSetPayload` from `Upload.tsx`'s `selectedTemplate` through `onMapped` into `App.tsx`'s `lastFieldSet` state, since `Review.tsx` needs it to build `toConfirmPayload`'s `field_set`. Replaced the Plan-05 `ReviewPlaceholder` with the real `<Review>`, keyed by `mapping.upload_token` so every fresh upload (including a same-signature re-upload) remounts with fresh local resolution state rather than carrying over stale edits.
- Every `/api/confirm` call from the Review screen sends `save_profile: true, export: true` -- the "Confirm & Save Mapping" CTA always saves the learned profile and always requests export links, which is what makes a subsequent same-signature upload return `provenance: "auto-applied-from-profile"` with zero amber rows (the UI-06 loop this plan makes visible in the browser; the API-level proof of the same sequence already existed and passed in 04-03's `tests/api/test_money_shot.py`).
- `npm run build` (`tsc -b` + `vite build`) and `npm run test -- --run` (47 tests: 15 new + 32 pre-existing) both pass at every task boundary. `npm run lint` (oxlint) shows only the same pre-existing shadcn-block warnings 04-04/04-05 already documented, nothing new.

## Task Commits

Each task was committed atomically; Task 1 (`tdd="true"`) followed a genuine RED -> GREEN split:

1. **Task 1a: review state + api.confirm tests (RED)** - `dd315e0` (test) -- confirmed genuinely RED (`Cannot find module './review'`) before the implementation commit
2. **Task 1b: review state + api.confirm implementation (GREEN)** - `e6acbe2` (feat)
3. **Task 2: Review screen -- side-by-side panes, amber rows, D-02 controls, sticky gate** - `cf42c2d` (feat) -- includes a minimal `ProfileAppliedBanner` placeholder so the app compiles at this commit boundary, plus the required `App.tsx`/`Upload.tsx` wiring (see Decisions)
4. **Task 3: ProfileAppliedBanner -- full UI-06 implementation** - `6a84894` (feat) -- replaces the placeholder body with the accent-toned final version

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `frontend/src/state/review.ts` - pure resolution/gate/confirm-payload logic
- `frontend/src/state/review.test.ts` - 15 vitest tests covering every function + api.confirm
- `frontend/src/lib/api.ts` - real `confirm()` + `GateRejected` typed error
- `frontend/src/components/ReviewTable.tsx` - the two-pane container (UI-03)
- `frontend/src/components/FieldRow.tsx` - one target field's clear/amber state (UI-04, D-02)
- `frontend/src/components/ConfidenceChip.tsx` - one ranked-alternative chip (D-02a)
- `frontend/src/components/ConfirmGate.tsx` - sticky confirm/export control (UI-05)
- `frontend/src/components/ExportBar.tsx` - post-confirm export links
- `frontend/src/components/ProfileAppliedBanner.tsx` - UI-06 auto-apply transparency banner
- `frontend/src/screens/Review.tsx` - orchestrates all of the above + the confirm/GateRejected flow
- `frontend/src/App.tsx` - wires `Review` into the "Review" tab (keyed by upload_token), threads `FieldSetPayload`
- `frontend/src/screens/Upload.tsx` - `onMapped` now carries the selected template's `FieldSetPayload`

## Decisions Made

See `key-decisions` in frontmatter above: the Source Columns pane is names-only (the wire contract carries no sample values, a documented gap versus 04-UI-SPEC.md's literal description); `resolveByChip`/`resolveByDropdown` set a fresh confidence value while `resolveByAccept` leaves it untouched; Accept is enabled even for the `inferred_value`-only case; Review.tsx has no own loading/error state (Upload.tsx already owns that per 04-05's architecture); the two-pane height budget is a reasoned approximation, not pixel-verified; `App.tsx`/`Upload.tsx` wiring was required despite not being in this plan's declared file list (mirrors 04-04's precedent).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `App.tsx`/`Upload.tsx` needed to thread the selected `FieldSetPayload` through to Review**
- **Found during:** Task 2 (writing `Review.tsx`'s `handleConfirm`)
- **Issue:** `toConfirmPayload` (this plan's own Task 1 deliverable) requires a `FieldSetPayload` to build `ConfirmRequest.field_set`, but `App.tsx`'s prior `onMapped: (response: MappingResponse) => void` seam (04-05) never carried one -- without it, the plan's own must-have ("the confirm request carries the upload_token + edited field_mappings the /api/confirm gate rebuilds") would be unreachable in the running app.
- **Fix:** Extended `Upload.tsx`'s `onMapped` prop to `(response, fieldSet) => void`, passing `selectedTemplate.field_set` at both call sites (fresh upload and hint-resolve); `App.tsx` now stores `lastFieldSet` alongside `lastMapping` and passes both into `<Review>`.
- **Files modified:** `frontend/src/App.tsx`, `frontend/src/screens/Upload.tsx`
- **Verification:** `npm run build` succeeds; `Review.tsx`'s `handleConfirm` compiles against a non-nullable `fieldSet` after the screen's own null-guard.
- **Committed in:** `cf42c2d` (Task 2 commit)

**2. [Rule 3 - Blocking] `04-UI-SPEC.md`'s "1-2 truncated sample values" description cannot be implemented against the actual `/api/upload` wire contract**
- **Found during:** Task 2 (writing `ReviewTable.tsx`'s Source Columns pane)
- **Issue:** `MappingResponse.source_columns` (`api/wire.py`, built in 04-02) is `list[str]` -- column names only, never sample cell values, on either the headers-only or fresh-Claude path. The UI-SPEC's Source Columns pane description ("each with 1-2 truncated sample values shown as small muted chips") describes data the backend never returns to the browser.
- **Fix:** Rendered the pane as a names-only list (matching what the wire response actually carries) with a short muted note explaining sample values aren't part of the response, rather than fabricating fake sample data or silently omitting the sub-bullet with no explanation. Adding real sample values would require a new backend wire field -- a schema change outside this plan's declared `files_modified` (backend files are not listed) and Rule-4 architectural territory (a new response field, not a bug fix).
- **Files modified:** `frontend/src/components/ReviewTable.tsx`
- **Verification:** `npm run build` succeeds; the pane renders correctly against the real `MappingResponse` shape with no `undefined`/runtime error.
- **Committed in:** `cf42c2d` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing-critical wiring, 1 blocking wire-contract mismatch handled by adapting to the real shape).
**Impact on plan:** Both were necessary for the plan's own stated success criteria (a working confirm flow, a working side-by-side review) and neither adds new backend surface or scope beyond this plan's own files. No architectural change was made (Rule 4 was explicitly NOT invoked -- the fix was "render what the contract carries," not "add a new backend field").

## Issues Encountered

None beyond the two deviations documented above.

## User Setup Required

None - no external service configuration required. (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` remain the only credential this project ever needs; a live browser round-trip through Confirm against a running backend needs one configured, exactly as `/api/upload`'s fresh-Claude branch does.)

## Manual UAT

**Task 4 (checkpoint:human-verify, gate="blocking") was NOT executed live this session** -- per this plan's explicit sequential-executor instruction, the checkpoint is documented here rather than blocking on a human mid-execution. The orchestrator/user should run the following before treating Phase 4 (and the Phase 5 demo recording) as ready:

1. Build the frontend (`cd frontend && npm run build`) and run `uvicorn assayingest.api.app:app` (with `ANTHROPIC_API_KEY` set) from the repo root.
2. Open the app, go to **Define Fields**, create/save a field set (e.g. the assay-potency preset shape).
3. Go to **Upload**, upload `data/synthetic/novascreen_batch01.csv` (or another synthetic file) with that field set.
   - **Expected:** the Review screen loads with several amber `FieldRow`s. Each shows Claude's reasoning inline (with the Sparkles prefix) always visible -- never behind hover -- plus `validator_note` on its own line where present, ranked `ConfidenceChip`s, an "Accept" button, and a manual dropdown.
4. Resolve every amber field via a mix of chip-click / Accept / manual dropdown.
   - **Expected:** each resolved row transitions to the green/clear state with a brief background transition; "Confirm & Save Mapping" stays disabled (with the tooltip) until the LAST field clears, then becomes enabled.
5. Click **Confirm & Save Mapping**.
   - **Expected:** a success toast, and the sticky footer switches to `ExportBar` (Export CSV / Export Excel / Export JSON / Download Manifest) -- all four links should download real files.
6. Go back to **Upload**, upload a byte-identical-header sibling file (e.g. `data/synthetic/novascreen_batch02.csv`) with the SAME field set.
   - **Expected:** the Review screen loads directly showing the accent-toned `ProfileAppliedBanner` ("Auto-mapped from a saved profile — 0 Claude calls.") above the table, with **ZERO** amber `FieldRow`s, and "Confirm & Save Mapping" already enabled.
7. Optionally toggle **Headers only** on a fresh upload of a structurally-ambiguous file and confirm the `StructuralHintPanel` preview (04-05) shows no cell values.

If every expectation above holds, the money shot (SC4) is demo-ready for the Phase 5 recording. Any deviation should be filed as a bug against this plan before recording.

## Next Phase Readiness

- The full browser loop is wired end-to-end at the code level: define fields (04-04) -> upload + resolve structural hints (04-05) -> review, resolve amber fields, confirm + save (this plan) -> re-upload the same signature and see the auto-apply banner with zero amber (this plan, UI-06). The API-level proof of the identical sequence already passes in `tests/api/test_money_shot.py` (04-03); this plan makes the same sequence visible and operable in the browser.
- Phase 5 (demo + submission) can proceed once the Manual UAT steps above are confirmed live against a running backend + built frontend -- this was NOT exercised in this execution session (the plan explicitly forbids running the dev server interactively during execution).
- No Profiles-management screen or `ProfileStore.delete`/list-all method was introduced (W2 descope, as directed) -- the learning loop is demonstrated entirely by the `ProfileAppliedBanner` on a same-signature re-upload.
- No blockers.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: frontend/src/state/review.ts
- FOUND: frontend/src/state/review.test.ts
- FOUND: frontend/src/components/ReviewTable.tsx
- FOUND: frontend/src/components/FieldRow.tsx
- FOUND: frontend/src/components/ConfidenceChip.tsx
- FOUND: frontend/src/components/ConfirmGate.tsx
- FOUND: frontend/src/components/ExportBar.tsx
- FOUND: frontend/src/components/ProfileAppliedBanner.tsx
- FOUND: frontend/src/screens/Review.tsx
- FOUND commits: dd315e0, e6acbe2, cf42c2d, 6a84894
- `npm run build` (frontend/): passes
- `npm run test -- --run` (frontend/): 47/47 tests pass

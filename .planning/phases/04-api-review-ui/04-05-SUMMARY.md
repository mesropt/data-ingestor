---
phase: 04-api-review-ui
plan: 05
subsystem: ui
tags: [react, vite, vitest, typescript, structural-hint, privacy]

# Dependency graph
requires:
  - phase: 04-api-review-ui
    provides: "04-04's frontend scaffold (D-01 tokens, AppShell, lib/types.ts, lib/api.ts's typed uploadFile/resolveStructuralHint stubs) and 04-02/04-03's POST /api/upload + POST /api/structural-hint/resolve (the discriminated MappingResponse | StructuralQuestionResponse contract this plan's state machine and components consume)"
provides:
  - "frontend/src/state/upload.ts + upload.test.ts -- a pure, vitest-covered reducer (idle -> fileSelected -> uploading -> mapping | structuralQuestion -> resolving -> mapping | structuralQuestion, plus an error branch preserving the selected file) and buildHintPayload (only-answered-dimensions StructuralHintIn builder)"
  - "lib/api.ts -- real uploadFile (multipart POST /api/upload) and resolveHint (JSON POST /api/structural-hint/resolve), replacing 04-04's typed stubs"
  - "screens/Upload.tsx + components/UploadDropzone.tsx + FieldSetPicker.tsx + HeadersOnlyToggle.tsx -- UI-02: pick a field set, toggle headers-only (P2), drop/select a file, submit; five dropzone states (idle/file-selected/uploading/error/locked)"
  - "components/StructuralHintPanel.tsx -- the D-04 inline structural-hint form: answer controls derived from whichever StructuralHint dimensions are non-null on the question's proposal, a headers-only-safe evidence preview (P2/CR-01), and the unsupported-shape guidance copy when answerable_by_hint is false"
  - "App.tsx wires Upload into the 'Upload' tab and a minimal ReviewPlaceholder into 'Review' (proves the mapping-response navigation seam for Plan 06, does not pre-build the real Review screen)"
affects: [04-06-review-confirm-flow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "state/upload.ts stays a pure reducer with no React import (mirrors state/fieldSet.ts's own split) -- Upload.tsx is the only caller, dispatching actions and driving the two async API calls (uploadFile/resolveHint) around it"
    - "The reducer's own 'resolving' phase intentionally carries no response payload (pinned by upload.test.ts) -- Upload.tsx keeps the last-seen StructuralQuestionResponse in a screen-local useState purely so StructuralHintPanel stays rendered (with its own submitting spinner) while a hint resolve is in flight, the same 'screen-local helper beats growing the tested module's surface' pattern 04-04 established with fieldSetPayloadToDraft"
    - "StructuralHintPanel derives which answer controls to show from question.proposal's non-null StructuralHint keys (header_row_index/sheet_name/delimiter/decimal_separator), never from unsure_about's free-text wording -- unsure_about is a human-readable sentence (e.g. 'file.csv: which row is the real header'), not a stable enum the UI could safely switch on"
    - "P2/CR-01 is enforced entirely client-side in StructuralHintPanel: the wire response's evidence_rows still carries real cell values under headers_only (the server does not strip them on the hint-resolve path), so the component -- not the server -- is the thing that renders zero cell values when the toggle is on, using the same headersOnly state threaded into the /api/upload request"
    - "uploadFile never sets a Content-Type header on its FormData POST -- api.ts's shared parseResponse() (factored out of the pre-existing JSON request() helper) decodes both the multipart upload response and every JSON response the same way, so ApiError stays the one error type every screen catches"

key-files:
  created:
    - frontend/src/state/upload.ts
    - frontend/src/state/upload.test.ts
    - frontend/src/components/UploadDropzone.tsx
    - frontend/src/components/FieldSetPicker.tsx
    - frontend/src/components/HeadersOnlyToggle.tsx
    - frontend/src/components/StructuralHintPanel.tsx
    - frontend/src/screens/Upload.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/App.tsx

key-decisions:
  - "lib/api.ts's Plan-04 stub named resolveStructuralHint was renamed to resolveHint -- the plan's own Task 1/Task 3 action text names the function resolveHint, and the stub had zero callers yet (Plan 05 is the first plan to fill it in), so this is a rename with no call-site migration cost, not a breaking change to shipped behavior."
  - "Task 2's Upload.tsx and Task 3's StructuralHintPanel.tsx are mutually dependent (Upload.tsx renders the panel on kind:structural_question) but are separate atomic task commits per the plan -- resolved by building a real-but-minimal StructuralHintPanel in Task 2 (header + reason text only, a 'built in Task 3' placeholder body) so the app compiles and routes correctly at Task 2's own commit boundary, then replacing its body with the full answer-controls/evidence-preview implementation in Task 3's commit. Mirrors 04-02's own documented precedent (Task 1's routes/upload.py was 'intentionally minimal' so Task 2's RED tests would genuinely fail first)."
  - "The Upload screen's dropzone gets a fifth state, 'locked', beyond 04-UI-SPEC.md's declared idle/file-selected/uploading/error -- once a structural question is showing (or its hint resolve is in flight), the dropzone freezes on its file chip with no Remove/Upload controls, because the inline StructuralHintPanel below now owns the next action; offering a second, conflicting 'Upload & Map' at the same time would let a curator resubmit the exact same ambiguous file instead of answering the question. Not a deviation from the UI-SPEC's four named states -- it is the necessary rendering of the reducer's own structuralQuestion/resolving phases, which the UI-SPEC's dropzone-state list did not enumerate because it lists the dropzone's states, not the whole screen's."
  - "The Upload screen navigates a kind:mapping response to a screen-local ReviewPlaceholder in App.tsx, not a real Review screen -- Plan 06 owns UI-03/04/05's full two-pane review UI; this plan's own must-haves only require proving the navigation seam ('routes to Review... passing the response + upload_token'), so the placeholder renders the exact Empty-state copy from 04-UI-SPEC.md's Copywriting Contract plus a one-line proof (upload_token, resolved-field count) rather than any component Plan 06 would otherwise need to replace."
  - "delimiter is a fully wired answer-control dimension in StructuralHintPanel even though no current parser code path (parsing/table.py) ever sets StructuralHint.delimiter on a StructureQuestion.proposal -- the UI-SPEC explicitly lists delimiter alongside header_row_index/sheet_name/decimal_separator as an answerable dimension, and the panel's control-visibility logic is generic over proposal's non-null keys, so this is forward-compatible dead code today rather than a gap."

patterns-established:
  - "A component reads which of several optional answer dimensions are 'in question' by inspecting which keys are non-null on a partial proposal object, rather than switching on a free-text description field -- the same discipline as reading domain state off structured fields instead of parsing a human-readable string."
  - "When two tasks in the same plan build mutually-dependent files, the earlier task ships a real-but-minimal version of the later task's file (buildable, wired into the app, but with its full body replaced next commit) rather than either merging both tasks into one commit or leaving the app non-compiling mid-plan."

requirements-completed: [UI-02]

coverage:
  - id: D1
    description: "The upload/hint state machine (idle -> fileSelected -> uploading -> mapping | structuralQuestion -> resolving -> mapping | structuralQuestion, error branches preserving the selected file, upload_token threading) and buildHintPayload (only-answered dimensions) are vitest-covered"
    requirement: "UI-02"
    verification:
      - kind: unit
        ref: "frontend/src/state/upload.test.ts (18 tests: uploadReducer x11, buildHintPayload x4, api client x3) -- npm run test -- --run"
        status: pass
    human_judgment: false
  - id: D2
    description: "api.uploadFile sends a real multipart POST /api/upload (file + field_set JSON + headers_only + optional sheet, no hand-set Content-Type) and api.resolveHint sends a real JSON POST /api/structural-hint/resolve ({upload_token, hint}); both parse the discriminated kind response"
    requirement: "UI-02"
    verification:
      - kind: unit
        ref: "frontend/src/state/upload.test.ts#'api client -- upload/hint' (3 tests, mocked fetch) -- npm run test -- --run"
        status: pass
    human_judgment: false
  - id: D3
    description: "A user can pick a field set, toggle headers-only, and upload a file through the real Upload screen; the dropzone reflects idle/file-selected/uploading/error/locked; a mapping response routes to the Review placeholder and a structural question renders StructuralHintPanel inline"
    requirement: "UI-02"
    verification:
      - kind: other
        ref: "npm run build (tsc -b && vite build) -- frontend/, all task commits"
        status: pass
    human_judgment: true
    rationale: "The screen's visual conformance to 04-UI-SPEC.md (dropzone states, toggle helper copy verbatim, spacing, color, the inline-not-modal placement of StructuralHintPanel) requires the dedicated gsd-ui-checker pass this executor does not run itself, and no live browser round-trip against a running FastAPI backend + Vite dev server was exercised this session (the plan explicitly forbids running the dev server interactively during execution) -- the build proving the wiring compiles is not the same as a human/UAT confirmation that the screen renders and behaves per spec."
  - id: D4
    description: "StructuralHintPanel is inline (never a modal/wizard), hides all cell values in the evidence preview when headers-only is on (showing only column/row counts with the verbatim P2/CR-01 copy), shows answer controls only for the dimensions in question (header_row_index/sheet_name/delimiter/decimal_separator, pre-filled from proposal but never auto-applied), and shows only reason+evidence+unsupported-shape guidance (no controls) when answerable_by_hint is false"
    requirement: "UI-02"
    verification:
      - kind: other
        ref: "npm run build && npm run test -- --run -- frontend/, StructuralHintPanel.tsx task commit"
        status: pass
    human_judgment: true
    rationale: "The plan's own Task 3 verification explicitly assigns this to gsd-ui-checker ('validates the panel is inline (not modal), the headers-only preview hides cell values, and the not-answerable state hides answer controls -- against 04-UI-SPEC.md') rather than fabricated pixel unit tests; the component logic (proposal-key-driven control visibility, headers-only branch rendering no cell values, answerable_by_hint branch rendering no controls) is implemented and type-checks/builds cleanly, but a human/UAT pass against a live render is the declared verification path for this deliverable."

duration: ~2h (session wall-clock across research + implementation; commits span 10:33-12:39)
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 5: Upload Screen + Inline Structural-Hint Form + Headers-Only Toggle Summary

**Upload screen (field-set picker, P2 headers-only toggle, five-state dropzone) wired to a vitest-covered upload/hint state machine, with the D-04 inline StructuralHintPanel deriving its answer controls from the StructureQuestion's own proposal and enforcing the headers-only privacy guarantee (P2/CR-01) entirely client-side.**

## Performance

- **Duration:** ~2h session wall-clock (includes reading 04-02/04-03/04-04's summaries, the wire.py/upload.py/structural_hint.py/hint.py source, and 04-UI-SPEC.md before implementing); commits span 10:33-12:39
- **Started:** 2026-07-11T10:33:32+04:00 (RED test commit)
- **Completed:** 2026-07-11T12:38:34+04:00 (Task 3 commit)
- **Tasks:** 3 (Task 1 was `tdd="true"`: RED test commit, then GREEN implementation commit; Tasks 2/3 auto)
- **Files modified:** 9 (7 created, 2 modified)

## Accomplishments

- `state/upload.ts` (TDD, RED then GREEN): a pure reducer covering the full flow -- `idle -> fileSelected -> uploading -> mapping | structuralQuestion`, then `structuralQuestion -> resolving -> mapping | structuralQuestion` (a re-submitted hint can itself still be ambiguous), with `UPLOAD_ERROR`/`HINT_ERROR` branches that preserve the selected file rather than losing it. Every non-idle phase threads `uploadToken` straight off the server's discriminated response. `buildHintPayload` builds exactly the `StructuralHintIn` wire shape from only the dimensions a human actually answered (an unanswered dimension is omitted, not sent as `null`) -- 18 new vitest tests, all passing, confirmed genuinely RED first (`Cannot find module './upload'`).
- `lib/api.ts`: real `uploadFile` (multipart `POST /api/upload` -- file + `field_set` JSON + `headers_only` + optional `sheet`, deliberately never setting `Content-Type` so the browser generates the multipart boundary) and `resolveHint` (JSON `POST /api/structural-hint/resolve`, `{upload_token, hint}`), replacing 04-04's typed stubs. A shared `parseResponse()` was factored out of the pre-existing `request()` helper so both the multipart and JSON paths raise the same typed `ApiError`.
- `screens/Upload.tsx` + `components/UploadDropzone.tsx` + `FieldSetPicker.tsx` + `HeadersOnlyToggle.tsx` (UI-02, P2): the full Upload screen -- `FieldSetPicker` (a `Select` of saved templates via `listFieldSets`), `HeadersOnlyToggle` (verbatim Copywriting Contract helper text), `UploadDropzone` (idle dashed-card prompt, file-selected chip + enabled CTA, uploading spinner label "Mapping…", error red border + destructive `Alert`, and a fifth `locked` state once a structural question owns the flow). Submit calls `api.uploadFile` with the selected template's `field_set` and the toggle's `headersOnly`; a `kind:"mapping"` response calls `onMapped` (App.tsx routes to the Review placeholder); a `kind:"structural_question"` response renders `StructuralHintPanel` inline below the dropzone.
- `components/StructuralHintPanel.tsx` (D-04, P2/CR-01, the centerpiece of this plan): renders directly below the dropzone in the same flow (a `Card`, never a `Dialog`). Header + `question.reason`. Which answer controls appear (`header_row_index` number stepper + row-click, `sheet_name`/`delimiter`/`decimal_separator` selects) is derived by inspecting which keys are non-null on `question.proposal` -- never a hardcoded assumption about `unsure_about`'s free-text wording, since the real question-builders (`parsing/table.py`) attach different `StructuralHint` fields per question type (verified against `_ambiguous_locale_question`, `_sheet_ambiguous_question`, `_header_uncertain_question`). Under headers-only, the evidence grid renders zero cell values -- only "Cell values hidden — headers-only mode is on. Showing column names and row count only." plus the counts -- proven necessary because the wire response's `evidence_rows` still carries real values under `headers_only` (the server does not strip them on this path; `StructureQuestion.to_dict()` and `structural_hint.py` both confirmed to pass evidence through unfiltered). When `answerable_by_hint` is `false`, only the reason, evidence, and the unsupported-shape guidance copy render -- no controls. The CTA ("Use This and Re-parse") calls `onResolve` with `buildHintPayload`'s output, which the Upload screen threads into `api.resolveHint(uploadToken, hint)`.
- `App.tsx`: wires `<Upload onMapped={...}>` into the "Upload" tab and adds a minimal `ReviewPlaceholder` (using the exact Empty-state copy from the Copywriting Contract, plus a one-line proof of the received mapping) into "Review" -- proves the navigation seam Plan 06 will replace, without pre-building Plan 06's own UI-03/04/05 work.
- `npm run build` (`tsc -b` + `vite build`) and `npm run test -- --run` (32 tests: 18 new + 14 pre-existing) both pass at every task boundary. `npm run lint` (oxlint) shows only pre-existing shadcn-block warnings, nothing new.

## Task Commits

Each task was committed atomically; Task 1 (`tdd="true"`) followed a genuine RED -> GREEN split:

1. **Task 1a: upload state machine + api client tests (RED)** - `e15aa96` (test) -- confirmed genuinely RED (`Cannot find module './upload'`) before the implementation commit
2. **Task 1b: upload state machine + api.uploadFile/resolveHint (GREEN)** - `540b132` (feat)
3. **Task 2: Upload screen -- dropzone, field-set picker, headers-only toggle** - `90796e0` (feat) -- includes a minimal `StructuralHintPanel` placeholder so the app compiles/routes at this commit boundary (see Decisions Made)
4. **Task 3: inline StructuralHintPanel with headers-only-safe evidence preview** - `1e95fee` (feat) -- replaces the placeholder body with the full implementation

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `frontend/src/state/upload.ts` - pure reducer (idle/fileSelected/uploading/mapping/structuralQuestion/resolving/error) + `buildHintPayload`
- `frontend/src/state/upload.test.ts` - 18 vitest tests covering every reducer transition, `buildHintPayload`, and the `uploadFile`/`resolveHint` api client
- `frontend/src/lib/api.ts` - real `uploadFile` (multipart) + `resolveHint` (JSON), shared `parseResponse()` helper
- `frontend/src/components/UploadDropzone.tsx` - idle/file-selected/uploading/error/locked dropzone states
- `frontend/src/components/FieldSetPicker.tsx` - `Select` of saved field-set templates
- `frontend/src/components/HeadersOnlyToggle.tsx` - P2 privacy toggle, verbatim copy
- `frontend/src/components/StructuralHintPanel.tsx` - the D-04 inline hint form (final implementation)
- `frontend/src/screens/Upload.tsx` - orchestrates the reducer + the four components + the two API calls
- `frontend/src/App.tsx` - wires `Upload` into the "Upload" tab, adds `ReviewPlaceholder` for "Review"

## Decisions Made

See `key-decisions` in frontmatter above: `resolveStructuralHint` renamed to `resolveHint` (matching the plan's own naming, zero prior callers); Task 2's minimal `StructuralHintPanel` placeholder mirroring 04-02's own precedent for mutually-dependent files across task boundaries; the dropzone's `locked` fifth state; the `ReviewPlaceholder` scope boundary versus Plan 06; `delimiter` left as forward-compatible dead code since no current parser path sets it.

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing-critical-functionality, or blocking issues were found during execution. The one structural choice worth flagging (splitting `StructuralHintPanel.tsx` into a Task 2 placeholder + Task 3 full implementation, rather than one file built once) is documented under Decisions Made rather than as a deviation: it does not add, remove, or change any planned behavior, only sequences the SAME file's construction across the two commits the plan already specifies, so the app never has a broken build between them.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** None — plan executed as specified; every task's own `<done>` criteria and the plan's `must_haves.truths` are met.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` remain the only credential this project ever needs; a live browser round-trip through this screen against a running backend needs one configured, exactly as `/api/upload`'s fresh-Claude branch does.)

## Next Phase Readiness

- The full browser upload flow is live end-to-end at the wiring level: define fields (04-04) -> pick a field set + toggle headers-only + upload (this plan) -> resolve an inline structural hint if the parser is unsure (this plan, D-04/P2) -> a `kind:"mapping"` response is handed to `onMapped` with its `upload_token` intact.
- Plan 06 (Review + confirm/learn) has everything it needs: `App.tsx`'s `lastMapping`/`onMapped` seam already carries a real `MappingResponse` (including `upload_token`, `source_columns`, `field_mappings`) into the "Review" tab -- Plan 06 replaces `ReviewPlaceholder` with the real two-pane UI-03/04/05 screen and wires its `Confirm & Save Mapping` CTA to `api.confirm` (04-04's still-stubbed function, untouched by this plan).
- **Not yet exercised this session:** a live browser round-trip against a running FastAPI backend + Vite dev server, including the actual D-04 hint-resolve loop and the P2 headers-only evidence-hiding behavior rendered in a real browser (the plan explicitly forbids running the dev server interactively during execution). The vitest suite proves the reducer/api-client logic; a manual UAT pass (start `uvicorn`, start `npm run dev`, upload one of the `data/synthetic/` files that triggers a structural question, e.g. an ambiguous-header or ambiguous-sheet file, toggle headers-only on/off, answer the hint, confirm zero cell values ever appear under headers-only) is the natural verification step, alongside the gsd-ui-checker visual pass the plan's own verification block calls for.
- No blockers.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: frontend/src/state/upload.ts
- FOUND: frontend/src/state/upload.test.ts
- FOUND: frontend/src/components/UploadDropzone.tsx
- FOUND: frontend/src/components/FieldSetPicker.tsx
- FOUND: frontend/src/components/HeadersOnlyToggle.tsx
- FOUND: frontend/src/components/StructuralHintPanel.tsx
- FOUND: frontend/src/screens/Upload.tsx
- FOUND commits: e15aa96, 540b132, 90796e0, 1e95fee
- `npm run build` (frontend/): passes
- `npm run test -- --run` (frontend/): 32/32 tests pass

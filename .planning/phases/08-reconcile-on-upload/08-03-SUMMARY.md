---
phase: 08-reconcile-on-upload
plan: 03
subsystem: reconcile-frontend
tags: [reconcile, frontend, react, upload, reducer, tdd, vitest, auth-mirror]
requires:
  - 08-02 api.wire.ReconcileQuestionResponse / ReconcileChoiceIn / ReconcileResolveRequest
  - 08-02 "/api/upload map-file branch + POST /api/reconcile/resolve"
  - Phase 07 lib/api.listSchemas + components/SchemaControls (selector/auth-mirror pattern)
  - Phase 06 auth store (signedIn/verified mirror, onRequireSignIn)
  - Phase 05 StructuralHintPanel + state/upload.ts two-step reducer (mirrored)
provides:
  - lib/types.ts ReconcileConflict / ReconcileQuestionResponse / ReconcileChoice + 3-arm UploadResponse union
  - state/upload.ts reconcileQuestion / resolvingReconcile phases + SUBMIT/SUCCESS/ERROR_RECONCILE trio
  - state/reconcile.ts initialReconcileChoices / setChoice / buildResolvePayload (pure, vitest-covered)
  - lib/api.ts uploadFile map-file options + resolveReconcile wrapper
  - components/ReconcilePanel.tsx + MapFileControls.tsx
  - screens/Upload.tsx reconcile threading (map-file attach + inline panel)
affects:
  - "Phase 09 (future): the Mapping Registry table + Docs page will reuse these types + the schema selector"
tech-stack:
  added: []
  patterns:
    - "Discriminated UploadResponse kind = mapping | structural_question | reconcile_question routed through one reducer (Pattern 5, mirrored on the client)"
    - "Pure logic module (state/reconcile.ts) vitest-covered; rendering (panels) checker/build-validated -- the existing state/*.ts split"
    - "Optional trailing options bag on uploadFile keeps the plain-upload multipart body byte-identical (regression guard)"
    - "Client signedIn/verified is a UX mirror only; the server re-enforces require-verified-user on the augment path"
key-files:
  created:
    - frontend/src/state/reconcile.ts
    - frontend/src/state/reconcile.test.ts
    - frontend/src/components/ReconcilePanel.tsx
    - frontend/src/components/MapFileControls.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/upload.ts
    - frontend/src/state/upload.test.ts
    - frontend/src/screens/Upload.tsx
    - frontend/src/App.tsx
decisions:
  - "MapFileControls fetches its own Schema list via listSchemas on mount (self-contained), rather than threading a schema reducer down from Upload -- keeps the Upload screen thin and mirrors SchemaControls' selector without importing Review's state/schema store."
  - "The reconcile per-conflict choice uses a shadcn Select (keep-master vs take-map-file) since the repo has no RadioGroup primitive -- exactly what StructuralHintPanel does for its dimensions."
  - "api.ts (Task-2-assigned) was implemented in the Task 1 GREEN commit because its wrapper tests live co-located in state/upload.test.ts (Task 1's file); this keeps every commit's own test set green in isolation."
metrics:
  duration_minutes: 9
  tasks_completed: 3
  tests_added: 15
  files_created: 4
  files_modified: 6
  completed: 2026-07-11
status: complete
---

# Phase 8 Plan 03: Reconcile-on-Upload Frontend Summary

Threads the Phase-08 reconcile flow through the browser by mirroring the existing
inline structural-hint pattern (D-08-06): the Upload screen gains an optional
map-file attach plus target-Schema/vendor selection, a new inline `ReconcilePanel`
(mirroring `StructuralHintPanel`) lists each conflict with keep-master /
take-map-file choices and re-submits to `/api/reconcile/resolve`, and on
no-conflict (or after resolution) the flow proceeds silently to the existing
Review + confirm gate. The upload reducer now routes all three response kinds
(`mapping | structural_question | reconcile_question`) through one code path.

## What was built

Three tasks, tests-first where the plan marks it (RED → GREEN on Task 1's
reducers + api wrappers):

1. **Reconcile types + upload/reconcile reducers + api wrappers** — `lib/types.ts`
   adds `ReconcileConflict` (the four-key `ReconcileConflict.to_dict()` shape
   verbatim), `ReconcileQuestionResponse` (`kind` / `upload_token` /
   `schema_name` / `vendor` / `conflicts`), and `ReconcileChoice`
   (`decision: "keep_master" | "take_map_file"`), and widens `UploadResponse`
   to the three-arm union. `state/upload.ts` gains `reconcileQuestion` +
   `resolvingReconcile` phases and the `SUBMIT_RECONCILE` /`RECONCILE_SUCCESS` /
   `RECONCILE_ERROR` trio mirroring the hint trio; `fromResponse` maps
   `kind="reconcile_question"` onto the new phase (mapping/structural branches
   unchanged). `state/reconcile.ts` is a pure module: `initialReconcileChoices`
   defaults every conflict to `keep_master` (the safe no-op-against-master
   default, P1/D-08-02), `setChoice` updates only the matching
   `(vendor, source_column)` pair immutably, and `buildResolvePayload` emits
   exactly the `/api/reconcile/resolve` body. `lib/api.ts` extends `uploadFile`
   with an optional trailing `{mapFile, schemaName, vendor}` bag (appended only
   when a map file is attached — a plain upload's body stays byte-identical) and
   adds `resolveReconcile(uploadToken, choices)`.

2. **ReconcilePanel + MapFileControls** — `ReconcilePanel.tsx` mirrors
   `StructuralHintPanel`'s Card/Label/Select/Button structure: one row per
   conflict showing the source column + vendor and a keep-master (→ master_field)
   / take-map-file (→ map_file_field) `Select`, keep-master preselected, driven
   by `state/reconcile.ts` and submitted via `onResolve(buildResolvePayload(...).choices)`.
   All vendor/column/field text renders escape-by-default (no
   `dangerouslySetInnerHTML`, T-08-11). `MapFileControls.tsx` is the compact
   Upload-screen control: a target-Schema selector (populated by `listSchemas`),
   a vendor `Input`, and an auth-gated optional map-file `<input type="file"
   accept="application/json,.json">` with a clear "optional" affordance and a
   remove chip. The attach affordance is gated on the signedIn/verified mirror
   (T-08-12); the server remains authoritative.

3. **Upload screen threading** — `MapFileControls` renders above the dropzone;
   `handleSubmitUpload` passes the map-file options only when a file is attached
   and routes the response through a shared `handleResponse` that branches
   `mapping` → `onMapped` (silent to Review), `reconcile_question` → keep the
   panel, `structural_question` → the existing hint panel. `handleResolveReconcile`
   dispatches `SUBMIT_RECONCILE`, calls `resolveReconcile`, and on `mapping`
   proceeds to Review (else re-shows the panel defensively). `toDropzonePhase`
   locks the two new phases; `App.tsx` threads `signedIn` / `verified` /
   `onRequireSignIn` into `Upload`. The plain-upload path (no map file) is
   unchanged.

## Key links (as-built)

`Upload.tsx` → `MapFileControls` (schema/vendor/mapFile) →
`uploadFile(file, fieldSet, headersOnly, undefined, {mapFile, schemaName, vendor})`
→ reducer `UPLOAD_SUCCESS` → `fromResponse` maps `reconcile_question` →
`reconcileQuestion` phase → `ReconcilePanel` → `onResolve(choices)` →
`handleResolveReconcile` → `resolveReconcile(token, choices)` → `mapping` →
`onMapped(response, fieldSet)` → existing Review + `/api/confirm` gate. No
conflict/augment/pre-fill logic on the client — all of it stays in 08-01/08-02's
server `service`.

## Deviations from Plan

### Auto-fixed / structural adjustments

**1. [Rule 3 - Blocking] `handleResolveHint` narrowing broke under the 3-arm union**
- **Found during:** Task 3 (build)
- **Issue:** widening `UploadResponse` to three arms (Task 1) made the existing
  `else { setLastQuestion(response) }` in `handleResolveHint` receive
  `Structural | Reconcile`, which no longer assigns to a
  `StructuralQuestionResponse | null` setter (TS2345).
- **Fix:** routed `handleResolveHint` (and the fresh-upload branch) through a
  new shared `handleResponse(response, fieldSet)` that explicitly branches all
  three kinds — no behavior change for the existing hint/mapping paths.
- **Files modified:** frontend/src/screens/Upload.tsx
- **Commit:** 4f642af

**2. api.ts folded into Task 1's GREEN commit (commit-granularity)**
- The plan assigns `api.ts` to Task 2, but its wrapper tests (`uploadFile`
  map-file params, `resolveReconcile`) live in `state/upload.test.ts` — Task 1's
  file. To keep each commit's own test set green in isolation, `api.ts` was
  implemented in the Task 1 GREEN commit (ae0b9ff) alongside the reducers. Task 2
  then delivered the two components. No functional impact.

## Threat surface

Plan-registered mitigations satisfied: T-08-11 (all conflict/alias text rendered
escape-by-default by React; no `dangerouslySetInnerHTML` anywhere in the new
components), T-08-12 (the signedIn/verified mirror gates only the attach UX
affordance; the server re-enforces `require_verified_user` on the augment path,
08-02), T-08-13 (accept — the map file is the user's own master-map JSON, sent
only to the governed credentialed endpoint). No frontend network/auth surface
beyond the plan's register was introduced.

## Tests

- `state/reconcile.test.ts` (new, 8 tests): `initialReconcileChoices` keep-master
  default + empty-list; `setChoice` matches only the exact pair, does not mutate,
  no-op on no match; `buildResolvePayload` emits the exact body + empty-list case.
- `state/upload.test.ts` (extended, +7 tests): `reconcile_question` UPLOAD_SUCCESS
  → `reconcileQuestion`; `SUBMIT_RECONCILE` → `resolvingReconcile`;
  `RECONCILE_SUCCESS` (mapping) → mapping; defensive re-ask; `RECONCILE_ERROR`;
  plus api wrappers — plain upload byte-identical (no map_file keys), map-file
  params appended only when attached, `resolveReconcile` POSTs
  `{upload_token, choices}` with credentials.

Full frontend suite: **6 files, 97 tests passed** (`npx vitest run`).
`npx tsc --noEmit` clean; `npm run build` (tsc -b + vite) green.

## Known Stubs

None. `MapFileControls` initial `null`/`""` values are ordinary React controlled
state; the Schema selector is wired to real `listSchemas` data.

## Self-Check: PASSED

All 4 created files present on disk; all 4 task commits (1 RED test + 3 GREEN
feat) verified in git history. `npx tsc --noEmit` clean, `npm run build` green,
full vitest suite 97 passed.

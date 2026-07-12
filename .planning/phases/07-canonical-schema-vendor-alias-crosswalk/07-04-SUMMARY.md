---
phase: 07-canonical-schema-vendor-alias-crosswalk
plan: 04
subsystem: frontend (governed Schema controls + crosswalk vendor threading)
tags: [schema, crosswalk, promote, master-map, vendor, alias, auth-gate, react, vitest]
status: complete
requires:
  - phase: 07-02
    provides: /api/schemas (create/list/export/import) + SchemaOut wire shape
  - phase: 07-03
    provides: ConfirmRequest optional schema_name + vendor (server records aliases)
  - phase: 06
    provides: state/auth.ts isGovernedActionAllowed + signedIn/verified mirror
provides:
  - lib/types.ts SchemaOut/SchemaSummary/CanonicalFieldPayload/AliasPayload/MasterMapEnvelope mirrors + additive ConfirmRequest.schema_name/vendor
  - lib/api.ts promoteSchema/listSchemas/importMasterMap/masterMapDownloadUrl
  - state/schema.ts pure LOADED/SELECT/CLEAR reducer + selectedSchema
  - state/review.ts toConfirmPayload additive schema_name/vendor carry
  - components/SchemaControls.tsx (promote / selector / download / import / vendor), auth-gated
  - screens/Review.tsx wires SchemaControls + threads selected schema + vendor into confirm
affects: [Phase 09 rich Registry table + Docs page (out of scope here)]
tech-stack:
  added: []
  patterns:
    - "Pure reducer + selectors, no React import (mirrors state/auth.ts / state/review.ts logic-tested split)"
    - "Additive wire fields spread into a request ONLY when defined (byte-identical no-schema payload)"
    - "Governed mutation buttons gated on signedIn && verified; server require_verified_user is the authority"
    - "Master-map download is a plain <a download> GET (ExportBar idiom); import parses JSON client-side for convenience, server re-validates"
key-files:
  created:
    - frontend/src/state/schema.ts
    - frontend/src/state/schema.test.ts
    - frontend/src/components/SchemaControls.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/review.ts
    - frontend/src/state/review.test.ts
    - frontend/src/screens/Review.tsx
decisions:
  - "Vendor input defaults to fieldSet.name (closest available source label in Review's props) rather than the uploaded file's stem, which is not threaded into Review — avoided restructuring App.handleMapped to carry the File (deviation, documented)."
  - "Crosswalk is threaded into confirm ONLY when a Schema is selected AND vendor is non-empty; the server needs all three (schema+vendor+confirmed_by) to record, so a partial pass would be a silent no-op anyway."
  - "SchemaSummary is a lighter id/name/created_by shape; listSchemas' SchemaOut[] is structurally assignable to it for the selector reducer."
  - "Download master-map is NOT auth-gated (server GET is public read); only Promote + Import (server require_verified_user) are gated in the UI."
metrics:
  duration: ~5m
  completed: 2026-07-11
  tasks: 2
  files_created: 3
  files_modified: 5
  commits: 3
  tests_added: 8
requirements: [SCHEMA-01, SCHEMA-02, SCHEMA-03, ALIAS-04]
---

# Phase 7 Plan 04: Minimal Schema/Crosswalk Frontend Controls Summary

Ships the governed Phase-07 controls into the browser (D-07-07): a curator
can promote the current field set into a named Schema, pick a Schema, download
and re-import its master-map file, and set a vendor label that threads into the
existing confirm so aliases accrete into the crosswalk (ALIAS-04) — all on the
shipped shadcn/dark shell, with no rich Registry table or Docs page (Phase 09).

## What was built

**Task 1 — types + API client + selector state (TDD)**
- `lib/types.ts`: TS mirrors of the 07-02 wire shapes — `AliasPayload`,
  `CanonicalFieldPayload` (`FieldPayload` + embedded `aliases`), `SchemaOut`,
  `SchemaSummary`, `MasterMapEnvelope` — plus additive optional `schema_name`
  / `vendor` on `ConfirmRequest` (matching the 07-03 wire additions; no
  existing field changed).
- `lib/api.ts`: `promoteSchema(name, fieldSet)` → `POST /api/schemas`,
  `listSchemas()` → `GET /api/schemas`, `importMasterMap(name, envelope)` →
  `POST /api/schemas/{name}/master-map`, and `masterMapDownloadUrl(name)`
  helper for a plain `<a download>` GET — all through the shared credentialed
  `request()` wrapper (session cookie gates the mutations).
- `state/schema.ts`: a pure `schemaReducer` (`LOADED`/`SELECT`/`CLEAR`) +
  `selectedSchema` selector, no React import. LOADED preserves a still-present
  selection and drops one that vanished from the server list.
- `state/review.ts`: `toConfirmPayload` additively spreads `schema_name` /
  `vendor` into the request ONLY when supplied — the no-schema payload stays
  byte-identical to Plan 06's.

**Task 2 — SchemaControls wired into Review, auth-gated**
- `components/SchemaControls.tsx`: promote-name input + "Promote to Schema"
  button, a Schema `Select`, "Download master map" (`<a download>` to
  `masterMapDownloadUrl`) and "Import master map" (hidden file picker →
  `file.text()` → `JSON.parse` → `importMasterMap`) buttons, and a vendor
  `Input`. Built entirely from existing shadcn primitives (Button/Input/
  Select/Label/Tooltip, `buttonVariants`, lucide icons, sonner toasts) — no
  new design system. Promote + Import are disabled unless `signedIn &&
  verified`; when signed out they route to `onRequireSignIn` rather than
  failing silently; invalid JSON and `ApiError` surface as distinct toasts.
- `screens/Review.tsx`: holds the schema list via the pure reducer
  (`useReducer(schemaReducer, …)`), loads it on mount + after any
  promote/import via `reloadSchemas()`, holds the vendor string, renders
  `SchemaControls` above the ConfirmGate/ExportBar region, and threads the
  selected Schema + vendor into `handleConfirm`'s `toConfirmPayload` (only
  when both present) so a confirm with a selected Schema records aliases —
  and, with none selected, confirms exactly as before.

## Requirements surfaced

- **SCHEMA-01** — promote the current field set into a named governed Schema.
- **SCHEMA-02** — download a Schema's master-map JSON file.
- **SCHEMA-03** — import a master-map file to augment a Schema.
- **ALIAS-04** — a vendor label threads into confirm so aliases accrete.

## Verification

- `npm run test -- --run src/state/schema.test.ts src/state/review.test.ts` —
  **33 passed** (RED→GREEN gate observed: RED commit `3d46a6f` precedes GREEN
  `e4ca762`).
- `npm run test -- --run` (full suite) — **82 passed / 5 files** (auth.test.ts,
  fieldSet.test.ts, upload.test.ts, review.test.ts, schema.test.ts all green;
  no regressions).
- `npx tsc --noEmit` — clean (exit 0).
- `npm run build` (tsc -b + vite) — succeeds (488 kB bundle, exit 0).
- Human-check (promote → select → set vendor → confirm → download → re-import)
  is `human_verify_mode=end-of-phase`, verified at phase close, not blocking.

## Threat Model Compliance

- **T-07-14 (EoP — promote/import buttons):** gated on `signedIn && verified`
  (mirrors `isGovernedActionAllowed`); the server's `require_verified_user`
  (07-02) is the actual authority — the UI gate is UX only.
- **T-07-15 (Tampering — client-parsed master-map):** the browser only
  `JSON.parse`s the chosen file for convenience; the server re-validates every
  field name + augment semantic (07-02). A malformed file surfaces as a toast,
  a hostile one cannot bypass the server guard.
- **T-07-16 (Spoofing — vendor label):** accepted; `vendor` is free-text with
  no authority (D-07-06); the authoritative provenance actor is the
  server-resolved email (07-03).
- **T-07-SC (supply chain):** no new npm packages — reuses existing shadcn /
  lucide / sonner primitives already in package.json.

## Deviations from Plan

**1. [Rule 3 — blocking detail] Vendor default source**
- **Found during:** Task 2 (wiring SchemaControls' `defaultVendor`).
- **Issue:** The plan suggested defaulting the vendor input to "the uploaded
  file's stem when available", but Review's props do not carry the uploaded
  `File` (App's `handleMapped` threads only the mapping response + field set,
  not the filename).
- **Fix:** Defaulted the vendor to `fieldSet.name` (the closest available
  source label already in Review's props), overridable by the curator, rather
  than restructuring `App.tsx` to thread the File through — kept the change
  minimal and localized per the phase scope.
- **Files modified:** frontend/src/screens/Review.tsx
- **Commit:** 8044440

## Known Stubs

None — every control is wired to a real endpoint; no placeholder/mock data
paths. (The rich visual crosswalk registry table + Docs page are intentionally
deferred to Phase 09 per D-07-07, not stubbed here.)

## Self-Check: PASSED

- All 3 created + 5 modified files present on disk.
- All 3 task commits (`3d46a6f`, `e4ca762`, `8044440`) present in git history.
- tsc clean, `npm run build` succeeds, full vitest suite 82 passed.

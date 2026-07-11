---
phase: 09-mapping-registry-documentation
plan: 01
subsystem: frontend
tags: [registry, crosswalk, provenance, react, escape-by-default]
requires:
  - "GET /api/schemas (listSchemas) — Phase 07"
  - "GET /api/schemas/{name}/master-map (MasterMapEnvelope) — Phase 07/08"
  - "lib/types.ts MasterMapEnvelope / CanonicalFieldPayload / AliasPayload"
provides:
  - "getMasterMap(name) api wrapper"
  - "state/registry.ts pure crosswalk data-shaping (groupFieldRows/formatProvenance/formatWhen/isSchemaEmpty)"
  - "RegistryTable presentational crosswalk component"
  - "Registry screen + Registry shell tab"
affects:
  - frontend/src/App.tsx
tech-stack:
  added: []
  patterns:
    - "Pure tested state-module + thin escape-by-default presentational wrapper (mirrors state/schema.ts)"
    - "Router-free activeTab tab wiring (D-09-01)"
    - "Deterministic locale-independent UTC timestamp humaniser (test-stable)"
key-files:
  created:
    - frontend/src/state/registry.ts
    - frontend/src/state/registry.test.ts
    - frontend/src/components/RegistryTable.tsx
    - frontend/src/screens/Registry.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/App.tsx
decisions:
  - "formatWhen uses a fixed UTC 'YYYY-MM-DD HH:MM UTC' form (not relative 'N hours ago') so unit tests stay time-independent."
  - "Provenance returned as structured {kind,label,actor,when}, never markup — the component escapes each part (T-09-01)."
  - "Registry viewing is ungated per D-09-05; the master-map GET is a public read."
metrics:
  duration: ~6m
  completed: 2026-07-11
requirements: [REG-01, REG-02]
status: complete
---

# Phase 9 Plan 1: Mapping Registry Summary

A read-only **Registry** tab that renders the whole crosswalk for a selected Schema — canonical fields on the left, each vendor's alias name(s) + legible provenance on the right — built frontend-only on Phase 07's existing `GET /api/schemas` + `GET /api/schemas/{name}/master-map` endpoints, with all data-shaping isolated in a vitest-covered pure module and the React layer kept as a thin escape-by-default presentational wrapper.

## What Was Built

**Task 1 (TDD) — data-shaping + api wrapper**
- `state/registry.ts` (no React/DOM, mirrors `state/schema.ts`): `groupFieldRows` (one `FieldRow` per canonical field in envelope order, never re-sorted, `hasAliases` flag, aliases verbatim), `formatProvenance` (structured `{kind,label,actor,when}` — `manual` → "manual", `from_map_file` → "from map file", unknown kind falls back to raw text, never throws), `formatWhen` (deterministic UTC `YYYY-MM-DD HH:MM UTC` + `"unknown date"` fallback for empty/invalid), `isSchemaEmpty` (true for zero fields OR all-fields-empty).
- `lib/api.ts`: `getMasterMap(name): Promise<MasterMapEnvelope>` next to `listSchemas`/`masterMapDownloadUrl`, reusing the existing `request` helper.
- `state/registry.test.ts`: 13 cases covering field order, quiet metadata + verbatim aliases, empty-aliases row, both provenance kinds, unknown-kind fallback, ISO + offset-normalisation + empty + invalid timestamps, and both `isSchemaEmpty` branches.

**Task 2 — table + screen + tab**
- `components/RegistryTable.tsx`: per-canonical-field row group — left identity + quiet mono metadata (`type · unit · min · max · allowed:…`, each rendered only when present), right vendor-alias rows (`vendor maps source_column` + a provenance chip: outline Badge label, escaped actor span, humanised `when`). A `hasAliases:false` field shows an explicit "no vendor aliases recorded yet" line. All crosswalk text is plain escaped JSX children; **no `dangerouslySetInnerHTML`** anywhere (T-09-01).
- `screens/Registry.tsx`: schema selector (ui/select, "Choose a Schema…" / "No schemas yet") → `getMasterMap` fetch with a skeleton loading state; resolves every branch to a visible surface — no-schemas first-run hint, nothing-selected hint, whole-Schema empty state (Review/Import hint), and a fetch-error card with a "Try again" re-fetch (T-09-02). Optional per-Schema "Download master map" affordance reusing `masterMapDownloadUrl`. Ungated (D-09-05).
- `App.tsx`: added `{ value: "registry", label: "Registry" }` after "review" and `{activeTab === "registry" && <Registry />}` to the render switch. No routing dependency added; auth overlay + `/verify` landing untouched.

## Verification

- `npx vitest run src/state/registry.test.ts` — 13/13 green.
- `npx vitest run` (full suite) — **110/110 passed, 7 files**.
- `npx tsc -b --noEmit` — clean.
- `npm run build` — production build succeeds (pre-existing >500 kB chunk-size advisory only; out of scope).
- `grep dangerouslySet` over both new files — 0 matches (T-09-01 gate passes).

## TDD Gate Compliance

Task 1 followed RED → GREEN: `test(09-01)` commit `de94eaf` (12 failing / 1 trivially-passing) preceded `feat(09-01)` commit `1b131ae` (13 passing). No refactor commit needed.

## Deviations from Plan

None — plan executed as written. The `>500 kB` Vite chunk advisory is pre-existing and unrelated to this plan's files (out of scope per SCOPE BOUNDARY).

## Threat Flags

None — no new network surface, auth path, or trust boundary introduced. The two ungated reads (`GET /api/schemas`, `GET /api/schemas/{name}/master-map`) already existed (Phase 07) and are deliberately public per D-09-05 (T-09-03 accepted).

## Commits

- `de94eaf` test(09-01): add failing tests for registry data-shaping (RED)
- `1b131ae` feat(09-01): implement registry data-shaping + getMasterMap wrapper (GREEN)
- `e45090d` feat(09-01): add Registry table, screen, and shell tab

## Self-Check: PASSED

All created files present on disk; all three task commits (`de94eaf`, `1b131ae`, `e45090d`) exist in history; `getMasterMap` exported from `lib/api.ts`.

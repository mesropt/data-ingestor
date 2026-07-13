---
phase: 10-frictionless-correct-ingest
plan: 06
subsystem: frontend
tags: [react, typescript, vitest, shadcn, schemas, auth-gate, soft-delete, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 04
    provides: "The five verified-user-gated Schema edit endpoints (add/edit/remove field, add/remove alias) + seed_schemas' 4 preset Schemas at startup"
  - phase: 10-frictionless-correct-ingest plan 02
    provides: "SchemaStore tombstone (soft-delete) semantics + tombstone-filtered read paths -- the reason a deleted field stays deleted across a refresh"
provides:
  - "screens/Schemas.tsx -- the single editable Schemas page (constraints + vendor aliases, both editable) replacing Define Fields and Registry"
  - "components/SchemaFieldRow / SchemaFieldConstraintsForm / SchemaFieldAliasList"
  - "components/SignInRequiredGate -- the app-wide signed-out interstitial for Schemas/Upload/Review"
  - "lib/api: addSchemaField / updateSchemaField / deleteSchemaField / addSchemaAlias / deleteSchemaAlias"
  - "lib/types: SchemaFieldIn, SchemaAliasIn"
  - "state/schemaEdit: toFieldPayload / fromCanonicalField / fieldSummaryLine / canAddField / deleteFieldWarning / MAX_FIELDS"
  - "App.tsx TABS -> exactly four: schemas / upload / review / docs"
affects: [10-frictionless-correct-ingest plan 07, 10-frictionless-correct-ingest plan 08 (gap-closure)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "The row-expansion accordion is plain conditional JSX + local useState (mirroring StructuralHintPanel/ReconcilePanel's existing conditionally-rendered inline block) -- ZERO new shadcn primitives, zero new design tokens, zero new npm packages. components.json and index.css are byte-unchanged (verified via git diff --stat)."
    - "After every successful edit the screen re-renders from the SchemaOut the server returned, never a locally patched copy -- this is what makes a server-rejected edit structurally impossible to render as success."
    - "state/routing.ts is byte-unchanged. Shrinking TABS from five to four is the WHOLE deleted-bookmark fix: /define-fields and /registry stop being allowlist members, so tabFromPath's EXISTING unknown-path fallback resolves them to TAB_VALUES[0] ('schemas') -- the same fallback a garbage path already took. Proven by new tests, not assumed (T-10-29)."
    - "Every mutating control is disabled with the existing Tooltip 'Verify your email to…' pattern for a signed-in-but-unverified user -- a MIRROR of Plan 04's require_verified_user, never a replacement. No client-side check is load-bearing (T-10-27)."
    - "Every alias's vendor / source column / provenance actor renders as escaped React text via state/registry.ts's formatProvenance, which returns STRUCTURED fields (label/actor/when as separate strings), never pre-concatenated markup. dangerouslySetInnerHTML appears nowhere (T-10-26/T-09-01)."
    - "Every path segment AND query value in the five new api.ts functions is encodeURIComponent-ed -- a field name / vendor / source column is untrusted text that could otherwise carry a '/' or '?' and corrupt the request URL (T-10-28)."

key-files:
  created:
    - frontend/src/screens/Schemas.tsx
    - frontend/src/components/SchemaFieldRow.tsx
    - frontend/src/components/SchemaFieldConstraintsForm.tsx
    - frontend/src/components/SchemaFieldAliasList.tsx
    - frontend/src/components/SignInRequiredGate.tsx
    - frontend/src/state/schemaEdit.ts
    - frontend/src/state/schemaEdit.test.ts
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/routing.test.ts
    - frontend/src/App.tsx
    - frontend/src/components/AppShell.tsx
  deleted:
    - frontend/src/screens/DefineFields.tsx
    - frontend/src/screens/Registry.tsx
    - frontend/src/components/FieldSetToolbar.tsx
    - frontend/src/components/RegistryTable.tsx

key-decisions:
  - "state/schemaEdit.ts's toFieldPayload is written fresh rather than importing state/fieldSet.ts's identically-named private helper, because fieldSet.ts is out of this plan's declared files_modified scope. Both target the SAME FieldPayload wire contract (fields.loader.from_dict) -- this is a second IMPLEMENTATION of one contract, never a second hand-derived SHAPE. If a future plan widens scope to fieldSet.ts, the two should be collapsed into one exported helper."
  - "SchemaFieldConstraintsForm holds its draft in LOCAL state (not lifted to the parent Schemas screen) so a failed save preserves every in-progress edit untouched -- the 10-UI-SPEC error-state contract ('nothing lost') is satisfied structurally, not by a save-failure recovery path."
  - "The Schema selector's latestRequestRef race guard, EmptyCard idiom, and 3-Skeleton loading state were carried forward from Registry.tsx VERBATIM -- Schemas is Registry grown up, not a rewrite. RegistryTable.tsx's AliasRow visual was likewise reproduced verbatim inside SchemaFieldAliasList (same markup, same escape-by-default rendering) before the file was deleted; state/registry.ts (formatProvenance/formatWhen) is KEPT and is now consumed by SchemaFieldAliasList."
  - "SchemaControls.tsx's promote affordance was deliberately NOT carried to the Schemas toolbar (per plan): promoting a field set no longer makes sense once Schemas exist independently. Only its Download/Import master-map affordances moved across. SchemaControls.tsx / FieldSetPicker.tsx / fieldSetSelection.ts remain on disk -- Upload/Review still import them, and they are Plan 07's to delete."

requirements-completed: [INGEST-06]
requirements-partial: [INGEST-05]

coverage:
  - id: D1
    description: "Define Fields and Registry are gone; the tabs are exactly Schemas / Upload / Review / Docs (D-10-09)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "npx tsc --noEmit + npm run build clean with all four files git rm'd; grep for 'define-fields'/'\"registry\"' returns nothing outside routing.test.ts's fallback assertions"
        status: pass
      - kind: human
        ref: "Checkpoint item 1 -- tabs read Schemas/Upload/Review/Docs signed out"
        status: pass
    human_judgment: true
  - id: D2
    description: "A bookmarked /define-fields or /registry resolves silently to the Schemas tab -- never a 404 or blank screen (T-10-29)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "frontend/src/state/routing.test.ts -- 4 new cases incl. the mechanism check asserting a deleted-page path takes the IDENTICAL fallback a garbage path takes (both simply fail the allowlist)"
        status: pass
      - kind: human
        ref: "Checkpoint item 2 -- both paths land on Schemas silently"
        status: pass
    human_judgment: true
  - id: D3
    description: "One row per canonical field carries BOTH its constraints and its vendor aliases with provenance -- both editable through Plan 04's explicit endpoints (D-10-10/D-10-11)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "frontend/src/state/schemaEdit.test.ts (19 tests: toFieldPayload/fromCanonicalField round-trip, empty-string->null, allowed_values null-not-[], type-dependent min/max/date_format, fieldSummaryLine's clean omission of absent parts, canAddField at MAX_FIELDS, deleteFieldWarning's 0/1/N pluralization)"
        status: pass
      - kind: human
        ref: "Checkpoint items 5-8 -- pencil expands in place, Save Field updates the summary, Add Alias records manual provenance + the signed-in email, X removes it under destructive confirm"
        status: pass
    human_judgment: true
  - id: D4
    description: "A tombstoned (deleted) canonical field does NOT reappear after a page refresh -- Plan 02's tombstone read-path filters hold end-to-end through the UI (D-10-15)"
    requirement: "INGEST-05"
    verification:
      - kind: human
        ref: "Checkpoint item 9 -- delete a field, refresh, re-select the Schema: it stays gone, and it is absent from the downloaded master map"
        status: pass
    human_judgment: true
  - id: D5
    description: "Signed out, Schemas/Upload/Review each render the sign-in interstitial; Docs stays open (D-10-13, INGEST-06)"
    requirement: "INGEST-06"
    verification:
      - kind: human
        ref: "Checkpoint item 1 -- all three gated tabs show 'Sign in to use Data Ingestor'; Docs shows real content"
        status: pass
    human_judgment: true
  - id: D6
    description: "Every mutating control is disabled with the existing tooltip for a signed-in-but-unverified user -- mirroring, never replacing, the server gate (T-10-27)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "Plan 04's 10 route auth-gate tests (401 signed-out / 403 unverified, nothing persisted) remain the actual authority -- unchanged and green"
        status: pass
      - kind: human
        ref: "Checkpoint item 10 -- unverified tier disabled + tooltipped, viewing unaffected"
        status: pass
    human_judgment: true
  - id: D7
    description: "Zero new shadcn primitives, zero new design tokens, zero new npm packages (T-10-30, T-10-SC)"
    requirement: "INGEST-05"
    verification:
      - kind: unit
        ref: "git diff --stat frontend/components.json frontend/src/index.css -- both byte-unchanged; grep for Collapsible|Accordion|Sheet|Drawer|RadioGroup finds no new usage; package.json untouched"
        status: pass
    human_judgment: false

duration: ~30min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 06: The Editable Schemas Page + App-Wide Sign-In Gate Summary

**Define Fields is deleted and Registry is renamed to Schemas — one page, one table, one row per canonical field, carrying BOTH the field's constraints and its vendor aliases with provenance, both editable through Plan 04's five verified-user-gated endpoints; the tabs shrink to Schemas / Upload / Review / Docs, with a shared sign-in interstitial on the first three (Docs stays deliberately open) and stale `/define-fields` / `/registry` bookmarks landing silently on Schemas via the EXISTING allowlist fallback — zero new shadcn primitives, zero new tokens, zero new packages.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-07-12
- **Tasks:** 4 (3 implementation + 1 blocking human-verification checkpoint, APPROVED)
- **Files:** 7 created, 5 modified, 4 deleted

## Test Counts

| Suite | Baseline | Final | Delta |
|-------|----------|-------|-------|
| Backend (`uv run pytest -q`) | 792 passed, 4 skipped | **792 passed, 4 skipped** | 0 (this plan is frontend-only — the baseline held exactly, zero regressions) |
| Frontend (`npx vitest run`) | 141 passed | **164 passed** | +23 (19 `schemaEdit.test.ts` + 4 `routing.test.ts`) |

`npx tsc --noEmit` and `npm run build` both clean.

## The Final TABS Array

```ts
const TABS: AppTab[] = [
  { value: "schemas", label: "Schemas" },
  { value: "upload",  label: "Upload"  },
  { value: "review",  label: "Review"  },
  { value: "docs",    label: "Docs"    },
];
```

`TAB_VALUES` stays derived (`TABS.map(t => t.value)`) — never a second hand-written list. `activeTab` stays DERIVED from the single `pathname` state, never a second state.

## The Exported Surface of `state/schemaEdit.ts`

| Symbol | Purpose |
|--------|---------|
| `MAX_FIELDS = 50` | Mirrors `fields/loader.py::MAX_FIELDS` — UX cap only; the server's `add_schema_field` re-checks it |
| `SchemaFieldDraftType` | `FieldType \| "none"` — the "no type declared" sentinel |
| `SchemaFieldDraft` | The constraints-form draft shape (mirrors `DraftField` minus its client-only `id`) |
| `toFieldPayload(draft)` | Serializes to exactly the `FieldPayload` shape `fields.loader.from_dict` accepts. Empty strings → `null`; `allowed_values` → `null` when empty (never `[]`); min/max only for numeric types; `date_format` only for `date` |
| `fromCanonicalField(field)` | The inverse — seeds a form from a `CanonicalFieldPayload`. Round-trips: `toFieldPayload(fromCanonicalField(f)) === f` minus its aliases |
| `fieldSummaryLine(field)` | The collapsed row's `type · unit · required · N alias(es)`, omitting absent parts cleanly (never `null · null · …`) |
| `canAddField(schema)` | `false` at `MAX_FIELDS` — the field-cap tooltip state |
| `deleteFieldWarning(field)` | The UI-SPEC's exact destructive copy, pluralized for 0 / 1 / N aliases |

No `react` import anywhere in the module (vitest runs in `environment: 'node'`).

## Deleted vs Kept, and Why

**DELETED (`git rm`):**

| File | Why |
|------|-----|
| `screens/DefineFields.tsx` | It edited a duplicate concept — `Schema → CanonicalField → Field` already carries every constraint (D-10-11), so deleting it loses no data |
| `screens/Registry.tsx` | Became `Schemas.tsx` — its Schema selector, `latestRequestRef` race guard, `EmptyCard` idiom, and skeleton loading state were all carried forward verbatim |
| `components/FieldSetToolbar.tsx` | Folded into the Schemas toolbar (Add Field + the field-cap tooltip) |
| `components/RegistryTable.tsx` | Its `AliasRow` visual was reproduced verbatim inside `SchemaFieldAliasList` — logic reused, file gone |

**KEPT (deliberately):**

| File | Why |
|------|-----|
| `state/registry.ts` (+ its test) | `formatProvenance` / `formatWhen` are now consumed by `SchemaFieldAliasList` — the structured, escape-by-default provenance shape (T-09-01) is the whole reason the alias list is XSS-safe |
| `state/fieldSet.ts`, `components/FieldEditorRow.tsx` | `SchemaFieldConstraintsForm` reuses `FieldEditorRow`'s EXACT grid, because `CanonicalField`'s constraints ARE `Field`'s constraints (D-10-11) |
| `components/SchemaControls.tsx`, `FieldSetPicker.tsx`, `state/fieldSetSelection.ts` | **Plan 07's to delete** — Upload/Review still import them. Deleting them here would have broken the build mid-plan |
| `state/routing.ts` | **Byte-unchanged.** Its allowlist fallback IS the deleted-bookmark fix; touching it would have replaced an existing guarantee with new code |

## Task Commits

1. **Task 1 (RED):** `d73ecce` — `test(10-06): add failing tests for the schema-edit pure state module`. `schemaEdit.test.ts` genuinely RED (`Cannot find module './schemaEdit'`); `routing.test.ts`'s 4 new cases were green on arrival, which is the POINT — they prove the deleted-bookmark fallback needs zero new code.
2. **Task 1 (GREEN):** `be3a70b` — `feat(10-06): add the schema-edit API client and its pure state module`
3. **Task 2:** `abe84a0` — `feat(10-06): add the editable Schemas page replacing Define Fields and Registry`
4. **Task 3:** `ae09e3d` — `feat(10-06): make sign-in required, shrink the tabs, and delete Define Fields and Registry`

_TDD Gate Compliance: the `test(10-06)` commit precedes both `feat(10-06)` implementation commits. Tasks 2 and 3 build React components, which this repo structurally cannot unit-test (`vite.config.ts` sets `test.environment: 'node'` — there is no jsdom and no `@testing-library/react`); that is precisely why the plan carried a blocking human-verification checkpoint, which was driven end-to-end in a browser and APPROVED._

## Human Checkpoint (Task 4) — APPROVED

The developer drove all 11 checks in a real browser against a live stack (Postgres + uvicorn + Vite dev server, all started by the executor): the four-tab shell, the sign-in interstitial on Schemas/Upload/Review with Docs open, both stale-bookmark paths landing on Schemas, the four seeded Schemas, the collapsed summary lines, in-place row expansion + Save Field, Add Alias with manual provenance + the signed-in email as actor, destructive-confirmed alias removal, destructive-confirmed field deletion **that survived a page refresh** (the tombstone read-path proof), the unverified disabled tier, and dark mode. **Approved.**

## Deviations from Plan

None. The plan executed as written — no auto-fixes (Rules 1–3) were needed, and no architectural change (Rule 4) was required.

---

## ⚠️ Known Gaps — BOTH must be closed by gap-closure plan **10-08**, which runs BEFORE plan 10-07

These are reported honestly rather than worked around silently. Neither was fixable inside this plan's declared `files_modified` scope.

### GAP-1 (this plan): "Create Schema" cannot create an empty Schema — a **422**

The Schemas toolbar's **"Create Schema"** button calls the only creation endpoint that exists: `POST /api/schemas` (Plan 07/04's `promoteSchema`). That route parses its body through `fields/loader.py::from_dict`, which **rejects an empty `fields: []` list** with a 422 (`"Cannot load field set: the file declares no fields."`). And `add_schema_field` requires the Schema to already exist. **There is therefore no backend path today to create a brand-new, empty Schema at all.**

**Consequence — state this plainly:** **INGEST-05's "a verified user creates a Schema there" is NOT yet delivered.** The requirement's *edit* half (constraints + aliases on an existing Schema) IS delivered and human-verified; its *create* half is not. This is why `requirements-completed` above lists only `INGEST-06`, with `INGEST-05` recorded as `requirements-partial`.

Practically, clicking "Create Schema" today surfaces an honest error toast (not a crash, not a silent failure). It did not block any of the 11 checkpoint items, all of which exercise the 4 pre-seeded Schemas.

The fix lives in `service.py` / `fields/loader.py` / `api/routes/schemas.py` — **all three out of this plan's `files_modified`**, so fixing it inline would have violated the plan's own file-scope contract. Two candidate shapes for 10-08 to choose between:
- allow an empty `fields` list on the Schema-creation path specifically (the `FieldSet` cap/name guards still apply), or
- require the UI to always create a Schema with one initial field (a UX change, and a weaker one — it forces a curator to invent a field before they have decided on any).

### GAP-2 (inherited from plan **10-05**, cross-referenced here so it cannot be missed)

Plan 10-05's own SUMMARY records a second, structurally related gap: **`service.confirm()` never threads a resolved `date_formats` override into its re-validation.** `confirm()` calls `validate()` / `canonical.assemble()` with no `date_formats` / `date_contradictions` argument at all, so a date field whose order was just resolved via the new `POST /api/date-format/resolve` step (or resolved on `resolve_or_map`'s own first pass) is **RE-FLAGGED amber the moment `/api/confirm` re-validates it from scratch** — silently undoing the entire point of D-10-04..08's date-order resolution the instant a curator tries to actually confirm and export.

10-05 correctly declined to fix it inline (`confirm.py` / `service.py` were outside *its* `files_modified` too) and logged it. It is now restated here because **plan 10-07 builds the Review/Confirm surface and would inherit a broken date path**.

**Both gaps are assigned to gap-closure plan 10-08, which must run BEFORE plan 10-07.**

## Threat Flags

None. Every new surface in this plan renders untrusted crosswalk text (vendor, source column, provenance actor, field name) as escaped React children only, `encodeURIComponent`s every path segment and query value, and adds no new network endpoint, auth path, file-access pattern, or schema change at a trust boundary — it consumes Plan 04's already-gated endpoints.

## Next Phase Readiness

- **BLOCKER for plan 10-07:** gap-closure plan **10-08** must land first (both gaps above).
- `SchemaControls.tsx`, `FieldSetPicker.tsx`, and `state/fieldSetSelection.ts` are still on disk and still imported by Upload/Review — **Plan 07 deletes them**, per its own scope.
- Dev servers were left running for the next plans: Postgres (`docker compose db`), uvicorn on `:8000`, Vite on `:5173`.
- `frontend/dist` was rebuilt (`npm run build`) so the change reaches the site uvicorn serves on `:8000`. It is gitignored and was never force-added.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 7 created files confirmed present on disk; all 4 deleted files confirmed gone; all 4 task commit hashes (`d73ecce`, `be3a70b`, `abe84a0`, `ae09e3d`) confirmed present in git log. Full suites re-verified green after the last commit: **backend 792 passed / 4 skipped** (baseline held exactly — zero regressions from this frontend-only plan) and **frontend 164 passed** (141 baseline + 23 new). `npx tsc --noEmit` and `npm run build` clean. `frontend/components.json`, `frontend/src/index.css`, and `frontend/src/state/routing.ts` confirmed byte-unchanged via `git diff --stat`.

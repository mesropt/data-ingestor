---
phase: 04-api-review-ui
plan: 04
subsystem: ui
tags: [react, vite, shadcn, tailwindcss, vitest, typescript, base-ui]

# Dependency graph
requires:
  - phase: 04-api-review-ui
    provides: "04-03's GET/POST /api/field-sets + GET /api/field-sets/{id} (FieldSetTemplateStore over the same SQLite file), built through fields.loader.from_dict for the same validation a file-loaded field set gets"
provides:
  - "frontend/ -- a from-scratch Vite + React + TS app, shadcn initialized (base-nova style, official registry only) with Tailwind CSS v4"
  - "src/index.css -- the D-01 design-token system (light :root default + [data-theme=\"dark\"]) replacing every shadcn-generated neutral-gray default, plus the 28/20/16/13 type scale and project-wide tabular-nums digits"
  - "Inter (variable) + JetBrains Mono self-hosted under public/fonts/ via @font-face -- zero CDN font dependency, verified against the built dist/ bundle"
  - "AppShell.tsx + ThemeToggle.tsx -- three-tab top bar (Define Fields / Upload / Review; Profiles descoped for v1 per W2) + localStorage-persisted light/dark toggle"
  - "lib/types.ts + lib/api.ts -- TS mirrors of api/wire.py's HTTP shapes, fetch wrappers for /api/field-sets (save/list/get) with a typed ApiError, and typed stubs for uploadFile/resolveStructuralHint/confirm for Plans 05/06 to fill in"
  - "state/fieldSet.ts -- pure, vitest-covered reducer (addField/removeField/editField/toFieldSetPayload) that is the DefineFields screen's single source of state"
  - "screens/DefineFields.tsx + FieldEditorRow.tsx + FieldSetToolbar.tsx -- UI-01: create/edit/delete fields and save/load a named field-set template through the real /api/field-sets endpoints"
affects: [04-05-upload-structural-hint, 04-06-review-confirm-flow]

# Tech tracking
tech-stack:
  added:
    - "Vite 8 + React 19 + TypeScript 6 (frontend/, net-new to this repo)"
    - "shadcn (base-nova style, official registry: button/card/input/label/select/switch/tabs/tooltip/alert-dialog/badge/separator/sonner/alert/skeleton), Tailwind CSS v4 (@tailwindcss/vite)"
    - "@base-ui/react (shadcn's current primitive layer -- Radix-equivalent, not literally @radix-ui)"
    - "vitest 4 (pure-logic unit tests, environment: node)"
    - "Self-hosted Inter Variable + JetBrains Mono woff2 files extracted once from @fontsource packages into public/fonts/, then those npm packages were uninstalled (only the static font files are kept/committed)"
  patterns:
    - "D-01 tokens live as CSS custom properties on :root (light, default) and [data-theme=\"dark\"] (dark), registered into Tailwind's utility classes via @theme inline -- shadcn components (bg-card, text-muted-foreground, etc.) automatically pick up the D-01 hex values with zero per-component edits"
    - "Type-scale roles (Display/Heading/Body/Label + mono variant) are hand-rolled utility classes (.text-display etc.) in @layer utilities rather than remapping Tailwind's built-in text-sm/text-xs scale, so shadcn's internal component sizing is untouched while screen-level content uses the exact 28/20/16/13 contract"
    - "state/fieldSet.ts is pure (no React import) so vitest exercises the add/remove/edit/serialize logic without rendering anything; DefineFields.tsx is the only caller of the untested inverse conversion (fieldSetPayloadToDraft), kept screen-local rather than growing the tested module's public surface for one caller"
    - "ApiError carries the server's decoded {\"detail\": ...} body verbatim so a screen can render FastAPI's own consequence-first message rather than a second, hand-written one"

key-files:
  created:
    - frontend/src/index.css
    - frontend/src/components/AppShell.tsx
    - frontend/src/components/ThemeToggle.tsx
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/fieldSet.ts
    - frontend/src/state/fieldSet.test.ts
    - frontend/src/screens/DefineFields.tsx
    - frontend/src/components/FieldEditorRow.tsx
    - frontend/src/components/FieldSetToolbar.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/vite.config.ts

key-decisions:
  - "shadcn init -d (autonomous defaults) resolved to style \"base-nova\" on this shadcn@4.13.0, not the plan's literal \"New York\" -- the upstream registry's default style set changed since the plan/UI-SPEC was authored. Not treated as a deviation requiring a checkpoint: the plan's binding requirement is the D-01 token/typography/spacing SUBSTANCE (verified by the zinc/slate grep + gsd-ui-checker), not a specific named shadcn preset, and every generated CSS variable was replaced regardless of which base style produced them."
  - "Dark-theme selector is [data-theme=\"dark\"] (a data attribute the custom ThemeToggle sets), not shadcn's default .dark class -- matches 04-UI-SPEC.md's Color section literally (\"dark theme on [data-theme=\\\"dark\\\"]\") and keeps ThemeToggle's localStorage-persisted toggle independent of any theme-provider library."
  - "Self-hosted fonts were extracted from @fontsource-variable/inter and @fontsource/jetbrains-mono (their static woff2 files copied into public/fonts/), then both npm packages were uninstalled -- avoids a permanent dependency on a font-distribution package for files that, once copied, never need re-fetching; JetBrains Mono's Latin subset (not a digits-only subset, which fontsource doesn't ship) is the closest available match to the UI-SPEC's \"subset to Latin + digits\" intent."
  - "toFieldSetPayload's field_set.name and the outer FieldSetIn.name (the saved template's name) are the SAME string from one name input -- the app has no product need for a field set's own domain name to diverge from its storage template name in v1, and FieldSet.to_dict()'s name key is otherwise unused by the API beyond round-tripping."
  - "fieldSetPayloadToDraft (the inverse of Task 2's vitest-covered toFieldSetPayload) lives in DefineFields.tsx, not state/fieldSet.ts -- it has exactly one caller (the Load-template flow) and Task 2's TDD behavior list never specified it, so it stays out of the tested module's public surface rather than growing it un-reviewed."

patterns-established:
  - "A screen-local pure function (fieldSetPayloadToDraft) is an acceptable alternative to growing a shared, tested module's surface for a single caller -- keep the reducer module's public API exactly as TDD-specified."
  - "self-hosted font extraction via a throwaway @fontsource install, copy the woff2 files, then uninstall the package -- gets exact, correctly-subsetted font files without a live CDN fetch and without a permanent font-distribution dependency in package.json."

requirements-completed: [UI-01]

coverage:
  - id: D1
    description: "frontend/ builds and its vitest suite passes end-to-end (npm run build && npm run test -- --run)"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "npm run test -- --run (frontend/src/state/fieldSet.test.ts, 14 tests)"
        status: pass
      - kind: other
        ref: "npm run build (tsc -b && vite build) -- frontend/"
        status: pass
    human_judgment: false
  - id: D2
    description: "src/index.css replaces every shadcn-generated default with the 04-UI-SPEC.md D-01 hex values (light :root + [data-theme=dark]) and self-hosts Inter + JetBrains Mono with zero CDN font URL in the built bundle"
    requirement: "UI-01"
    verification:
      - kind: other
        ref: "grep -i 'zinc|slate' frontend/src/index.css -- no match"
        status: pass
      - kind: other
        ref: "dist/fonts/*.woff2 present after npm run build; grep for a CDN URL (fonts.googleapis.com etc.) in dist/assets/*.css -- no match"
        status: pass
    human_judgment: true
    rationale: "Full visual/typography/spacing/registry conformance to 04-UI-SPEC.md (the 6-dimension gsd-ui-checker sign-off the plan's own <verification> block calls for) requires the dedicated checker pass this executor does not run itself -- these two automated checks prove the token substitution and font self-hosting are structurally correct, not that every pixel matches the contract."
  - id: D3
    description: "A user can add/edit/delete fields (name/description/type/allowed_values/unit/required/min/max/date_format) and save/load a named field-set template through the real POST /api/field-sets and GET /api/field-sets/{id} endpoints (UI-01)"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "frontend/src/state/fieldSet.test.ts -- toFieldSetPayload/addField/removeField/editField + api client tests against a mocked fetch (14 tests, all pass)"
        status: pass
    human_judgment: true
    rationale: "The reducer/serialization logic and the api.ts wrapper are vitest-proven against a mocked fetch, but this session did not start the Vite dev server or FastAPI backend (the plan explicitly forbids running the dev server interactively) -- a live browser round-trip against a running /api/field-sets has not been exercised end-to-end and needs human/UAT confirmation."
  - id: D4
    description: "The field-set editor's add/remove/edit/MAX_FIELDS-cap/type-dependent-serialization logic is vitest-covered; the screen's visual rendering is left to gsd-ui-checker rather than fabricated pixel unit tests"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "frontend/src/state/fieldSet.test.ts#addField/removeField/editField/toFieldSetPayload (10 tests)"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-07-11
status: complete
---

# Phase 4 Plan 4: Frontend Scaffold + D-01 Tokens + AppShell + Define Fields Summary

**A from-scratch Vite/React/shadcn app with the D-01 design-token system (self-hosted Inter + JetBrains Mono, light-default/dark-token-complete), a three-tab AppShell, and the Define Fields screen (UI-01) wired to the real POST/GET /api/field-sets endpoints, backed by a vitest-covered pure reducer.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-07-11T05:45:00Z (approx.)
- **Completed:** 2026-07-11T06:07:00Z
- **Tasks:** 3 (Task 2 was `tdd="true"`: RED test commit, then GREEN implementation commit)
- **Files modified:** 42 (frontend/ is entirely new to this repo)

## Accomplishments

- Scaffolded `frontend/` (Vite + React 19 + TypeScript 6), initialized shadcn (official registry only: button/card/input/label/select/switch/tabs/tooltip/alert-dialog/badge/separator/sonner, plus `alert`/`skeleton` added in Task 3 for Define Fields' error/loading states) on top of Tailwind CSS v4.
- Replaced every shadcn-generated CSS variable in `src/index.css` with the 04-UI-SPEC.md D-01 hex values on `:root` (light, default) and `[data-theme="dark"]` (dark, token-complete but not the demo default); added the exact 28/20/16/13 type scale as utility classes and project-wide `tabular-nums` digits. Verified clean via `grep -i "zinc|slate" src/index.css` (no match).
- Self-hosted Inter (variable) and JetBrains Mono under `public/fonts/` via `@font-face` -- extracted the woff2 files from `@fontsource-variable/inter`/`@fontsource/jetbrains-mono`, then uninstalled both packages so only the static files remain committed. Verified the built `dist/` bundle references `/fonts/*.woff2` and contains zero external font CDN URLs.
- `AppShell.tsx`: top-bar wordmark + three-tab nav (Define Fields / Upload / Review -- the UI-SPEC's fourth "Profiles" tab is intentionally absent per W2's v1 descope) + `ThemeToggle.tsx` (Sun/Moon, localStorage-persisted, light default, with a pre-paint inline script in `index.html` to avoid a dark-mode flash on reload).
- `lib/types.ts`: TypeScript mirrors of `api/wire.py`'s wire models plus `fields/models.py::Field.to_dict()`/`FieldSet.to_dict()`. `lib/api.ts`: `saveFieldSet`/`listFieldSets`/`getFieldSet` against the real endpoints with a typed `ApiError` (carries the server's decoded `detail`), plus typed stubs for `uploadFile`/`resolveStructuralHint`/`confirm` for Plans 05/06.
- `state/fieldSet.ts` (TDD, RED then GREEN): a pure reducer -- `addField`/`removeField`/`editField`/`toFieldSetPayload` -- with `MAX_FIELDS=50`/`MAX_NAME_LENGTH=64` as UX-only mirrors of `fields/loader.py`'s authoritative server-side caps. `toFieldSetPayload` produces exactly `FieldSet.to_dict()`'s `{name, fields}` shape, with min/max serializing only for number/integer and date_format only for date. 14 vitest tests, all passing.
- `screens/DefineFields.tsx` + `FieldEditorRow.tsx` + `FieldSetToolbar.tsx`: the full UI-01 screen -- add/edit/delete fields (name 64-char cap, description, type select, allowed-values chip input, unit, required switch default ON, min/max shown only for number/integer, date_format shown only for date), empty state, loading skeleton on template load, destructive inline `Alert` on save/load error, and the verbatim `MAX_FIELDS` tooltip copy ("Field sets are capped at 50 fields."). Save posts `toFieldSetPayload(draft)` through `api.saveFieldSet`; Load reads a template through `api.getFieldSet` and rebuilds draft state.
- `npm run build` (tsc -b + vite build) and `npm run test -- --run` (14 tests) both pass at every task boundary.

## Task Commits

Each task was committed atomically; Task 2 (`tdd="true"`) followed a genuine RED -> GREEN split:

1. **Task 1: Vite + React + shadcn scaffold, D-01 tokens, fonts, AppShell** - `728107c` (feat)
2. **Task 2a: field-set editor state + API client tests (RED)** - `47dbe6e` (test) -- confirmed genuinely RED (`Cannot find module './fieldSet'`) before the implementation commit
2. **Task 2b: field-set editor state + API client implementation (GREEN)** - `43067eb` (feat)
3. **Task 3: Define Fields screen (UI-01) wired to /api/field-sets** - `66f5365` (feat)

**Plan metadata:** (this commit, once created)

## Files Created/Modified

- `frontend/src/index.css` - D-01 design tokens (light + dark), self-hosted @font-face rules, type-scale utility classes
- `frontend/src/components/AppShell.tsx` - top bar, three-tab nav, bounded content area
- `frontend/src/components/ThemeToggle.tsx` - Sun/Moon toggle, localStorage-persisted
- `frontend/index.html` - title + pre-paint theme-flash-avoidance inline script
- `frontend/vite.config.ts` - `@/` path alias, `/api` dev proxy to `localhost:8000`, vitest `test` config (node environment)
- `frontend/src/lib/types.ts` - TS mirrors of `api/wire.py` + `fields/models.py`'s wire shapes
- `frontend/src/lib/api.ts` - `saveFieldSet`/`listFieldSets`/`getFieldSet` + `ApiError` + Plan 05/06 stubs
- `frontend/src/state/fieldSet.ts` - pure reducer (add/remove/edit/toFieldSetPayload), `MAX_FIELDS`/`MAX_NAME_LENGTH`
- `frontend/src/state/fieldSet.test.ts` - 14 vitest tests covering the reducer and the api client
- `frontend/src/screens/DefineFields.tsx` - UI-01 screen: empty/loading/error states, save/load wiring
- `frontend/src/components/FieldEditorRow.tsx` - one field's full declaration + delete
- `frontend/src/components/FieldSetToolbar.tsx` - load-template dropdown, name input, Add Field, Save Field Set
- `frontend/src/App.tsx` - wires `DefineFields` into the "Define Fields" tab, mounts `<Toaster/>`
- `frontend/src/components/ui/*.tsx` - shadcn official-registry blocks (button/card/input/label/select/switch/tabs/tooltip/alert-dialog/badge/separator/sonner/alert/skeleton)
- `frontend/public/fonts/*.woff2` - self-hosted Inter Variable + JetBrains Mono 400/600

## Decisions Made

See `key-decisions` in frontmatter above (shadcn "base-nova" vs. plan's literal "New York"; `[data-theme="dark"]` vs. shadcn's default `.dark`; font extraction-then-uninstall pattern; single name field mapping to both `FieldSetIn.name` and `FieldSet.name`; `fieldSetPayloadToDraft` kept screen-local).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed deprecated `baseUrl` from tsconfig.json/tsconfig.app.json**
- **Found during:** Task 1 (`npm run build` verification)
- **Issue:** `tsc -b` errored with `TS5101: Option 'baseUrl' is deprecated and will stop functioning in TypeScript 7.0` after adding the shadcn `@/*` path alias with a `baseUrl: "."` companion.
- **Fix:** Kept `"paths": {"@/*": ["./src/*"]}` alone (valid without `baseUrl` under `moduleResolution: "bundler"`), removed `baseUrl` from both tsconfig files.
- **Files modified:** `frontend/tsconfig.json`, `frontend/tsconfig.app.json`
- **Verification:** `npm run build` succeeds cleanly.
- **Committed in:** `728107c` (Task 1 commit)

**2. [Rule 3 - Blocking] `vitest`'s `test` config block didn't type-check under `defineConfig` from `'vite'`**
- **Found during:** Task 2 (`npm run build` after adding `test:` to `vite.config.ts`)
- **Issue:** `TS2769: ... 'test' does not exist in type 'UserConfigExport'` -- Vite's own `defineConfig` doesn't know about vitest's config extension.
- **Fix:** Imported `defineConfig` from `'vitest/config'` instead of `'vite'` (the standard vitest-recommended re-export that merges the `test` field's types).
- **Files modified:** `frontend/vite.config.ts`
- **Verification:** `npm run build` succeeds; `npm run test -- --run` still picks up the same config.
- **Committed in:** `43067eb` (Task 2 GREEN commit)

**3. [Rule 3 - Blocking] Test file used `global.fetch`, which doesn't exist in the browser-lib TS target, and a reused mocked `Response` broke a two-call assertion**
- **Found during:** Task 2 (`npm run build` / `npm run test -- --run`)
- **Issue:** `TS2304: Cannot find name 'global'` (the app's `tsconfig.app.json` only includes `"vite/client"` types, no Node globals); separately, the 422-error test called `saveFieldSet` twice against one `mockResolvedValue(new Response(...))`, and `Response.json()` can only be read once per instance, so the second call's `detail` came back `null`.
- **Fix:** Switched to `globalThis.fetch` (works under both the vitest node environment and a browser target); changed that one mock to `mockImplementation(async () => new Response(...))` so each call gets a fresh `Response`.
- **Files modified:** `frontend/src/state/fieldSet.test.ts`
- **Verification:** `npm run build` and `npm run test -- --run` (14/14) both pass.
- **Committed in:** `43067eb` (Task 2 GREEN commit) -- the RED commit (`47dbe6e`) already had `global.fetch`; fixed before the GREEN commit was made, so RED itself was never re-committed with the fix.

**4. [Rule 3 - Blocking] The `alert-dialog` block alone (Task 1's list) didn't cover Task 3's plain-banner `Alert` / loading-skeleton needs**
- **Found during:** Task 3 (writing `DefineFields.tsx`'s error and loading states)
- **Issue:** 04-UI-SPEC.md's Component Inventory lists a standalone `Alert`/`Toast` component distinct from `AlertDialog` (a modal confirm), and a loading-skeleton primitive, but Task 1's literal block list (`button, card, input, label, select, switch, tabs, tooltip, alert-dialog, badge, separator, sonner`) omitted plain `alert` and `skeleton`.
- **Fix:** Ran `npx shadcn@latest add alert skeleton -y` -- both from the same official registry already vetted for this project (Registry Safety table), no third-party registry involved.
- **Files modified:** `frontend/src/components/ui/alert.tsx`, `frontend/src/components/ui/skeleton.tsx` (new)
- **Verification:** `npm run build` succeeds; the error/loading states render using these components.
- **Committed in:** `66f5365` (Task 3 commit)

**5. [Rule 2 - Missing Critical] `App.tsx` needed to actually render `DefineFields` for the screen to be reachable**
- **Found during:** Task 3
- **Issue:** Task 3's declared `files_modified` list (`DefineFields.tsx`, `FieldEditorRow.tsx`, `FieldSetToolbar.tsx`) didn't include `App.tsx`, but without wiring the new screen into the "Define Fields" tab, the plan's own must-have ("A user can add/edit/remove fields ... and save the set") would be unreachable in the running app.
- **Fix:** Updated `App.tsx` to render `<DefineFields/>` on the `"define-fields"` tab (replacing the Task 1 placeholder) and mounted `<Toaster/>` once (unused until Plan 06's confirm-success toast, but harmless and already installed).
- **Files modified:** `frontend/src/App.tsx`
- **Verification:** `npm run build` succeeds; `DefineFields` renders as the default tab.
- **Committed in:** `66f5365` (Task 3 commit)

---

**Total deviations:** 5 auto-fixed (2 bug/build-blocking TS config fixes, 1 test-authoring bug, 1 missing shadcn blocks, 1 missing App.tsx wiring).
**Impact on plan:** All five were necessary for the plan's own stated success criteria (a working build, a green vitest suite, and a reachable Define Fields screen). No scope creep -- no new backend logic, no components beyond what 04-UI-SPEC.md's inventory already calls for.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required. `npm`/`node` availability (via `nvm`) was already documented as an environment prerequisite; no new credentials or dashboard configuration needed.

## Next Phase Readiness

- `frontend/` now has a working build pipeline, the full D-01 token system, and a real, endpoint-backed Define Fields screen -- Plan 05 (Upload + structural-hint + headers-only toggle) and Plan 06 (Review + confirm/learn money-shot) can both build directly on `AppShell`, `lib/api.ts`'s `ApiError`/typed stubs, and `lib/types.ts`'s wire mirrors without re-deriving any of them.
- `lib/api.ts`'s `uploadFile`/`resolveStructuralHint`/`confirm` are typed stubs that throw "implemented in Plan 05/06" -- Plan 05 must replace `uploadFile`/`resolveStructuralHint`'s bodies; Plan 06 must replace `confirm`'s body. Their call signatures are already correct against `lib/types.ts`.
- **Not yet exercised this session:** a live browser round-trip against a running FastAPI backend + Vite dev server (the plan explicitly forbids running the dev server interactively during execution). The vitest suite proves the reducer/serialization/api-client logic; a manual UAT pass (start `uvicorn`, start `npm run dev`, actually add a field, save it, reload the page, load it back) is the natural verification step before/alongside Plan 05.
- No blockers.

---
*Phase: 04-api-review-ui*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: frontend/src/index.css
- FOUND: frontend/src/components/AppShell.tsx
- FOUND: frontend/src/components/ThemeToggle.tsx
- FOUND: frontend/src/lib/types.ts
- FOUND: frontend/src/lib/api.ts
- FOUND: frontend/src/state/fieldSet.ts
- FOUND: frontend/src/state/fieldSet.test.ts
- FOUND: frontend/src/screens/DefineFields.tsx
- FOUND: frontend/src/components/FieldEditorRow.tsx
- FOUND: frontend/src/components/FieldSetToolbar.tsx
- FOUND commits: 728107c, 47dbe6e, 43067eb, 66f5365
- `npm run build` (frontend/): passes
- `npm run test -- --run` (frontend/): 14/14 tests pass

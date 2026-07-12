---
phase: quick-260712-e0e
plan: 01
subsystem: api, ui
tags: [fastapi, lifespan, react, vitest, sqlite, field-sets]

requires: []
provides:
  - "Startup seeding of the 4 shipped presets (assay-potency, clinical-labs, pk-parameters, reagent-inventory) into the field-set template store"
  - "Upload screen auto-selects a field set (last-used-else-first) instead of landing blank"
  - "Upload & Map button is honestly disabled with a visible reason when no field set is resolved"
affects: [upload, field-sets, frontend-state]

tech-stack:
  added: []
  patterns:
    - "FastAPI lifespan resolves DI-overridable dependencies via app.dependency_overrides.get(dep, dep) since lifespan runs outside the request cycle"
    - "Insert-if-absent seeding (never upsert) to keep an SQLite store idempotent and id-stable across restarts"
    - "Pure logic modules under frontend/src/state/ tested in vitest's node environment; window access guarded with typeof checks inside functions, never at module scope"

key-files:
  created:
    - src/assayingest/fields/presets.py
    - src/assayingest/learning/seed.py
    - tests/api/test_preset_seeding.py
    - frontend/src/state/fieldSetSelection.ts
    - frontend/src/state/fieldSetSelection.test.ts
  modified:
    - src/assayingest/api/app.py
    - frontend/src/screens/Upload.tsx
    - frontend/src/components/UploadDropzone.tsx

key-decisions:
  - "Seeding is insert-if-absent against store.list(), never store.save() unconditionally -- SqliteFieldSetStore.save upserts and mints a fresh uuid4 id on every call, so seeding on every restart would have churned every preset's id and broken the frontend's persisted last-used id"
  - "app.py's lifespan resolves the store through app.dependency_overrides.get(get_field_set_store, get_field_set_store) rather than calling get_field_set_store() directly, since FastAPI does not apply dependency overrides outside the request cycle -- without this a test overriding the store would still seed the real .assayingest/profiles.db"
  - "readLastTemplateId/writeLastTemplateId mirror ThemeToggle.tsx's localStorage idiom (typeof window guard inside the function body, never at module scope) so the module imports cleanly under vitest's node test environment"

requirements-completed: [FIELD-05, UI-01, UI-02]

coverage:
  - id: D1
    description: "seed_presets(store) seeds all 4 shipped presets into an empty field-set store"
    requirement: "FIELD-05"
    verification:
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_presets_on_an_empty_store_seeds_all_4"
        status: pass
    human_judgment: false
  - id: D2
    description: "Seeding is idempotent and id-stable across repeated calls (no duplicate rows, no id churn)"
    requirement: "FIELD-05"
    verification:
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_presets_is_idempotent_and_id_stable"
        status: pass
    human_judgment: false
  - id: D3
    description: "Seeding never overwrites a pre-existing user row, including one sharing a preset's exact name"
    requirement: "FIELD-05"
    verification:
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_presets_leaves_a_pre_existing_user_row_untouched"
        status: pass
      - kind: unit
        ref: "tests/api/test_preset_seeding.py#test_seed_presets_does_not_overwrite_a_user_row_sharing_a_preset_name"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/field-sets returns the 4 presets after the app's lifespan runs on a fresh startup, and a second startup does not duplicate rows or remint ids"
    requirement: "FIELD-05"
    verification:
      - kind: integration
        ref: "tests/api/test_preset_seeding.py#test_get_field_sets_returns_the_4_presets_after_a_fresh_startup"
        status: pass
      - kind: integration
        ref: "tests/api/test_preset_seeding.py#test_a_second_startup_against_the_same_store_does_not_duplicate_or_remint_ids"
        status: pass
    human_judgment: false
  - id: D5
    description: "pickDefaultTemplateId resolves last-used-else-first-else-null, falling back to first when the last-used id is stale/deleted"
    requirement: "UI-01"
    verification:
      - kind: unit
        ref: "frontend/src/state/fieldSetSelection.test.ts#pickDefaultTemplateId"
        status: pass
    human_judgment: false
  - id: D6
    description: "submitBlockedReason returns a curator-facing hint when unresolved, null once a field set is selected"
    requirement: "UI-02"
    verification:
      - kind: unit
        ref: "frontend/src/state/fieldSetSelection.test.ts#submitBlockedReason"
        status: pass
    human_judgment: false
  - id: D7
    description: "Upload screen auto-selects a field set on load and Upload & Map is disabled with visible helper text when none is resolved; no regression in either full suite"
    requirement: "UI-02"
    verification:
      - kind: unit
        ref: "npx vitest run (118 passed)"
        status: pass
      - kind: unit
        ref: "uv run pytest -q (615 passed, 4 skipped)"
        status: pass
    human_judgment: true
    rationale: "Visual/interactive confirmation that the Upload screen actually renders the auto-selected picker and the disabled-with-hint button in a browser is not exercised by these pure-logic/unit tests (vitest runs in a DOM-less node environment) -- a human should confirm the rendered behavior once."

duration: ~10min
completed: 2026-07-12
status: complete
---

# Phase quick-260712-e0e: Seed the 4 presets into the web field-set store Summary

**Server now seeds its 4 shipped field-set presets into the template store on startup (idempotent, id-stable, never touching user rows), and the Upload screen auto-selects a field set instead of landing on a silently-broken blank picker.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-07-12
- **Tasks:** 3/3 completed
- **Files modified:** 8 (2 new backend modules, 1 new backend test, 1 modified backend module, 1 new frontend module, 1 new frontend test, 2 modified frontend components)

## Accomplishments

- `GET /api/field-sets` returns the 4 shipped presets (`assay-potency`, `clinical-labs`, `pk-parameters`, `reagent-inventory`) after any fresh server start, seeded through a new `FastAPI` lifespan handler.
- Seeding is insert-if-absent: a restart never duplicates rows, never re-mints a template's id, and never overwrites a curator's own row -- including one that happens to be named after a preset.
- The Upload screen now auto-selects a field set (last-used from `localStorage`, else the first available template) instead of initializing to a blank picker.
- "Upload & Map" is disabled with visible helper text whenever no field set is resolved -- the previous silent no-op (an enabled button whose click handler early-returned with no feedback) is gone.
- Rebuilt `frontend/dist` so the bundle uvicorn serves at `:8000` carries both fixes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Seed the 4 shipped presets into the field-set store at startup (idempotently)**
   - `56b8dda` (test) — RED: failing store-level + HTTP-level seeding tests
   - `c758886` (feat) — GREEN: `fields/presets.py`, `learning/seed.py`, `api/app.py` lifespan wire
2. **Task 2: Auto-select a field set on Upload, and disable "Upload & Map" when none is resolved**
   - `5d45341` (test) — RED: failing `fieldSetSelection.test.ts`
   - `d2d40b4` (feat) — GREEN: `fieldSetSelection.ts`, `Upload.tsx`, `UploadDropzone.tsx`
3. **Task 3: Rebuild `frontend/dist` and prove the whole suite is still green**
   - No commit — build-artifact-only task; `frontend/dist` is gitignored and was correctly left unstaged.

_Note: both TDD tasks show the RED → GREEN commit pair; no REFACTOR commit was needed._

## Files Created/Modified

- `src/assayingest/fields/presets.py` - Resolves the shipped presets directory (repo checkout AND installed wheel) and loads each through `fields.loader.load`; exposes `preset_paths()` and `load_presets()`.
- `src/assayingest/learning/seed.py` - `seed_presets(store)`: insert-if-absent against `store.list()`, returns the names actually seeded.
- `src/assayingest/api/app.py` - Adds a `lifespan` handler (`asynccontextmanager`) that resolves the field-set store through the DI-override seam and seeds presets on startup; failures are caught and logged as a warning, never re-raised.
- `tests/api/test_preset_seeding.py` - RED-first store-level (idempotency, id-stability, user-row preservation) and HTTP-level (`with TestClient(app) as client:` to actually run lifespan) tests.
- `frontend/src/state/fieldSetSelection.ts` - Pure `pickDefaultTemplateId`, `submitBlockedReason`, plus thin `readLastTemplateId`/`writeLastTemplateId` localStorage accessors.
- `frontend/src/state/fieldSetSelection.test.ts` - RED-first tests for the two pure functions above.
- `frontend/src/screens/Upload.tsx` - Defaults `selectedTemplateId` functionally after the field-set fetch; wraps the picker's `onChange` to persist the choice; derives `blockedReason` and passes `canSubmit`/`blockedReason` to `UploadDropzone`.
- `frontend/src/components/UploadDropzone.tsx` - Adds required `canSubmit`/`blockedReason` props; the submit button's `disabled` expression now includes `!canSubmit`, and the blocked reason renders as helper text beneath it.

## Decisions Made

- Seeding uses insert-if-absent (read `store.list()` once, skip any name already present) rather than calling `store.save()` unconditionally, because `SqliteFieldSetStore.save` upserts on `UNIQUE(name)` and mints a brand-new uuid4 id on every call -- an unconditional seed-on-every-startup would have silently re-minted every preset's id on each restart, breaking the frontend's persisted last-used template id and reverting any curator edit made under a preset's name.
- The lifespan handler resolves the field-set store via `app.dependency_overrides.get(get_field_set_store, get_field_set_store)` instead of calling `get_field_set_store()` directly -- FastAPI does not apply `dependency_overrides` outside the request cycle, so a test overriding the store for isolation would otherwise still have lifespan seed the real `.assayingest/profiles.db`.
- `readLastTemplateId`/`writeLastTemplateId` mirror `ThemeToggle.tsx`'s existing localStorage idiom exactly (a `typeof window === "undefined"` guard inside each function, never at module scope) so the module imports cleanly under vitest's DOM-less `node` test environment.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The web Upload screen is now usable out of the box against a fresh server: a curator lands with a field set already chosen and gets an honest, disabled "Upload & Map" with a visible reason on the rare case nothing is available (e.g. an empty store with no presets directory found). `frontend/dist` has been rebuilt with both fixes. No blockers for subsequent work; a human should do a quick manual browser smoke-test of the auto-select + disabled-button behavior per the coverage note above (D7), since vitest's node environment does not exercise the actual rendered DOM.

---
*Phase: quick-260712-e0e*
*Completed: 2026-07-12*

## Self-Check: PASSED

All created/modified files verified present on disk (`src/assayingest/fields/presets.py`, `src/assayingest/learning/seed.py`, `tests/api/test_preset_seeding.py`, `frontend/src/state/fieldSetSelection.ts`, `frontend/src/state/fieldSetSelection.test.ts`, `src/assayingest/api/app.py`, `frontend/src/screens/Upload.tsx`, `frontend/src/components/UploadDropzone.tsx`, `frontend/dist/index.html`). All 4 task commits verified present in `git log` (`56b8dda`, `c758886`, `5d45341`, `d2d40b4`).

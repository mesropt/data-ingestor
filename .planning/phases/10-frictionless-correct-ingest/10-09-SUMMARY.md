---
phase: 10-frictionless-correct-ingest
plan: 09
subsystem: auth
tags: [fastapi, pydantic, sqlalchemy, alembic, vitest, vite, tsconfig, gap-closure, tdd]

# Dependency graph
requires:
  - phase: 10-frictionless-correct-ingest plan 06
    provides: "require_user/require_verified_user (deps.py) and the Schemas page's copy vocabulary this plan sweeps"
  - phase: 10-frictionless-correct-ingest plan 07
    provides: "the collapsed three-control Upload screen and the Review screen's escalation summary, whose Vendor input this plan rewires"
  - phase: 10-frictionless-correct-ingest plan 08
    provides: "MappingResponse.escalation's additive-optional-field precedent, mirrored here for remembered_vendor*"
provides:
  - "frontend/src/state/copy.test.ts -- permanent gate: fails if user-visible 'field set' copy reappears in screens/ or components/"
  - "tests/api/conftest.py -- the shared verified_user()/unverified_user() TestClient builders every auth-affected API test file now imports"
  - "require_user enforced server-side on POST /api/upload, /api/structural-hint/resolve, /api/date-format/resolve (D-10-13/INGEST-06)"
  - "src/assayingest/service.py::recall_vendor + VendorMemory -- the profile-then-crosswalk vendor lookup that refuses to guess on ambiguity"
  - "profiles.vendor (nullable, alembic 2dadb963fae6) -- the vendor learned at confirm time"
  - "frontend/src/state/vendorMemory.ts -- pure prefill/hint decision consumed by Review.tsx"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Auth test fixtures override get_current_user (the single root DI dependency), never require_verified_user alone -- the one override that satisfies both require_user and require_verified_user simultaneously, since FastAPI resolves each Depends callable independently."
    - "recall_vendor mirrors D-10-03's own escalation shape (profile -> crosswalk -> empty), each stage running only if the previous found nothing, and refuses to tie-break an ambiguous crosswalk match by any heuristic (alias count, recency, match count) -- ambiguity is returned to the human, never resolved silently."
    - "A source-scanning vitest test (copy.test.ts) strips comment lines and regexes the remaining source text for a banned user-visible string, without touching the internal identifier of the same name -- a permanent regression gate that cannot be defeated by renaming the internal type."

key-files:
  created:
    - frontend/src/state/copy.test.ts
    - tests/api/conftest.py
    - tests/api/test_upload_auth_gate.py
    - tests/test_vendor_memory.py
    - alembic/versions/2dadb963fae6_profile_vendor.py
    - frontend/src/state/vendorMemory.ts
    - frontend/src/state/vendorMemory.test.ts
  modified:
    - frontend/src/screens/Schemas.tsx
    - frontend/src/screens/Documentation.tsx
    - src/assayingest/api/routes/upload.py
    - src/assayingest/api/routes/structural_hint.py
    - src/assayingest/api/routes/date_format.py
    - src/assayingest/api/wire.py
    - src/assayingest/service.py
    - src/assayingest/learning/profile.py
    - src/assayingest/learning/postgres_store.py
    - src/assayingest/persistence/models.py
    - tests/api/test_reconcile.py
    - tests/api/test_upload.py
    - tests/api/test_upload_schema_target.py
    - tests/api/test_date_format_route.py
    - tests/api/test_confirm_dates.py
    - tests/api/test_hint_and_export.py
    - tests/api/test_money_shot.py
    - tests/test_profile_store.py
    - frontend/src/lib/types.ts
    - frontend/src/screens/Review.tsx
    - frontend/src/state/upload.test.ts
    - frontend/src/state/review.test.ts
    - frontend/tsconfig.app.json

key-decisions:
  - "D-10-02 WINS over 10-UI-SPEC.md:203, which specifies the leaking 'Field sets are capped at 50 fields.' tooltip copy verbatim -- the locked decision supersedes the design contract; recorded here so the spec and the code do not silently disagree a third time."
  - "The blast-radius table in the plan predicted test_confirm_gate.py would need 1 fix; audited and found it needs zero -- none of its tests hit a newly-gated route (all target /api/confirm, which stays require_verified_user, unchanged). test_reconcile.py absorbed the difference: its 1 predicted fix required a genuine premise reversal (renamed + a new sibling test), so the total breaking-test count (44 observed vs 46 predicted, +2 from Task 2's own additions) still nets to the same final count."
  - "tsconfig.app.json gained \"node\" in its types array -- Task 1's copy.test.ts (node:fs/node:path/__dirname) broke `tsc -b` under the app project config, which previously carried only vite/client. Scoped fix, not a new dependency: @types/node was already a devDependency (used only by tsconfig.node.json's vite.config.ts project before this)."

requirements-completed: [INGEST-01, INGEST-02, INGEST-06]

coverage:
  - id: D1
    description: "Zero user-visible 'field set' copy remains in frontend/src/screens or frontend/src/components, and a permanent test gate fails if it reappears (D-10-02/INGEST-01)"
    requirement: "INGEST-01"
    verification:
      - kind: unit
        ref: "frontend/src/state/copy.test.ts#has zero matches across screens/ and components/"
        status: pass
      - kind: other
        ref: "grep -rniE 'field[ -]sets?' --include='*.ts' --include='*.tsx' frontend/src/screens frontend/src/components | grep -vE comment-lines | wc -l == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "An anonymous client cannot reach the mapper or retain an upload -- POST /api/upload with no session cookie returns 401 and the mapper is never invoked (D-10-13/INGEST-06)"
    requirement: "INGEST-06"
    verification:
      - kind: unit
        ref: "tests/api/test_upload_auth_gate.py#test_anonymous_upload_is_401_and_never_reaches_the_mapper"
        status: pass
      - kind: other
        ref: "curl -X POST localhost:8000/api/upload -F file=@data/synthetic/novascreen_batch01.csv -F schema_name=assay-potency (no cookie) -> 401, live-verified"
        status: pass
    human_judgment: false
  - id: D3
    description: "A signed-in but unverified user can still upload (the gate is sign-in, not verification); the map-file path still requires verification"
    requirement: "INGEST-06"
    verification:
      - kind: unit
        ref: "tests/api/test_upload_auth_gate.py#test_signed_in_unverified_user_can_still_upload"
        status: pass
      - kind: unit
        ref: "tests/api/test_reconcile.py#test_upload_map_file_unverified_is_403"
        status: pass
    human_judgment: false
  - id: D4
    description: "/api/structural-hint/resolve and /api/date-format/resolve also 401 anonymously -- a signed-out client cannot drive a retained upload to completion via either resolve route"
    requirement: "INGEST-06"
    verification:
      - kind: unit
        ref: "tests/api/test_upload_auth_gate.py#test_anonymous_structural_hint_resolve_is_401"
        status: pass
      - kind: unit
        ref: "tests/api/test_upload_auth_gate.py#test_anonymous_date_format_resolve_is_401"
        status: pass
    human_judgment: false
  - id: D5
    description: "All 46 enumerated blast-radius tests authenticate and pass; none were deleted (test count only grows)"
    requirement: "INGEST-06"
    verification:
      - kind: unit
        ref: "uv run pytest tests/api/ -q -- 196 passed"
        status: pass
      - kind: other
        ref: "grep -rn 'def test_' tests/ | wc -l -- 693 (pre-plan) -> 711 (final), never decreasing"
        status: pass
    human_judgment: false
  - id: D6
    description: "A returning file whose columns were already confirmed for a vendor arrives with the Vendor input pre-filled and labelled as remembered (profile match)"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "tests/test_vendor_memory.py#test_recall_vendor_exact_profile_match_is_unambiguous_by_construction"
        status: pass
      - kind: unit
        ref: "frontend/src/state/vendorMemory.test.ts#initialVendor > returns the remembered vendor when the server resolved one"
        status: pass
    human_judgment: false
  - id: D7
    description: "A file matching exactly one vendor's crosswalk aliases (no profile yet) is remembered via the crosswalk fallback; two or more matching vendors pre-fill NOTHING and name both, sorted -- the tool never guesses"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "tests/test_vendor_memory.py#test_recall_vendor_crosswalk_fallback_single_vendor"
        status: pass
      - kind: unit
        ref: "tests/test_vendor_memory.py#test_recall_vendor_two_vendors_refuses_to_guess_and_names_both"
        status: pass
      - kind: unit
        ref: "frontend/src/state/vendorMemory.test.ts#vendorHint > names both candidates on an ambiguous match, joined with 'and'"
        status: pass
    human_judgment: false
  - id: D8
    description: "A tombstoned alias contributes no vendor candidate; the schema-name default on Review's Vendor input is removed"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "tests/test_vendor_memory.py#test_recall_vendor_a_tombstoned_alias_contributes_no_candidate"
        status: pass
      - kind: other
        ref: "grep -c 'schemaName ?? \"\"' frontend/src/screens/Review.tsx == 0"
        status: pass
    human_judgment: false
  - id: D9
    description: "The profiles.vendor migration is proven reversible against the real database"
    verification:
      - kind: other
        ref: "uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head -- ROUND-TRIP OK"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-07-12
status: complete
---

# Phase 10 Plan 09: Gap Closure -- Server-Side Sign-In Gate, Copy Sweep, Remembered Vendor Summary

**Closed the three findings from Phase 10's own human verification: swept the last "field set" copy leak behind a permanent regression gate, put `require_user` on the three Anthropic-reaching routes so the sign-in gate is enforced server-side (not just in the UI) with the map-file path's stronger verified-user check preserved, and added a profile-then-crosswalk vendor memory that pre-fills the Vendor input on a repeat signature or names both candidates on a genuine tie -- never guessing.**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-07-12T18:14:26+04:00 (first commit)
- **Completed:** 2026-07-12T18:40:13+04:00
- **Tasks:** 3
- **Files modified:** 30 (7 created, 23 modified)

## Accomplishments

- **Copy leak (D-10-02/INGEST-01):** a new source-scanning vitest test (`frontend/src/state/copy.test.ts`) walks every `.ts`/`.tsx` under `screens/`/`components/`, strips comment lines, and asserts zero case-insensitive `field[ -]sets?` matches. It failed with exactly the three predicted hits before any fix -- `Schemas.tsx:466` (the Add Field cap tooltip) and `Documentation.tsx:49`/`:66` (two how-to steps describing the deleted field-set picker and a "promote to Schema" flow that no longer exists). All three rewritten in the surviving Schema vocabulary; zero identifier renames (`FieldSet`/`fieldSet`/`field_set`/`FieldSetPayload` untouched, by design). **`10-UI-SPEC.md:203` itself specifies the leaking tooltip copy verbatim -- D-10-02 (a locked decision) wins over the design contract**, recorded here so the two artifacts do not silently disagree a third time.
- **Server-side auth gate (D-10-13/INGEST-06):** `POST /api/upload` moved from `user: User | None = Depends(get_current_user)` to `user: User = Depends(require_user)` -- the gate that already existed (`deps.py:102`) and was simply never applied. `/api/structural-hint/resolve` and `/api/date-format/resolve` gained the same gate (previously no auth dependency at all), closing the "retained upload driven to completion by a signed-out client" hole on both continuation routes. The map-file branch's now-unreachable inline `if user is None: raise 401` was deleted as dead code; its `if not user.is_verified: raise 403` stays untouched (D-10-12/D-08-05). Live-verified: `curl -X POST localhost:8000/api/upload ...` with no cookie now returns 401 (the exact repro the orchestrator used to find the bug).
- **The 46-test blast radius**, enumerated by the plan, was authenticated by injecting a signed-in user via `app.dependency_overrides[get_current_user]` -- never `require_verified_user` alone, since FastAPI resolves each `Depends` callable independently and only the root dependency satisfies both gates at once. A new shared `tests/api/conftest.py` (`verified_user()`/`unverified_user()`, lifted from `test_reconcile.py`'s own pre-existing shape) is now imported by every affected file instead of being redefined per-file. **Observed count: 44 failures after the route change (not 46)** -- audited and found `test_confirm_gate.py` needed zero changes (none of its tests hit a newly-gated route; it only exercises `/api/confirm`, unchanged) and `test_reconcile.py`'s predicted 1 was proactively fixed as part of the RED commit (a genuine premise reversal: `test_plain_upload_no_map_file_stays_open_and_returns_mapping` renamed to `test_plain_upload_no_map_file_now_requires_sign_in` and now asserts 401, with a new sibling `test_plain_upload_signed_in_no_map_file_returns_mapping` preserving the original 200 regression guard). No test was deleted; `grep -c 'def test_' tests/` went 693 -> 711 (net +18: the 4 new auth-gate tests, the 1 reconcile split, the 13 vendor-memory tests).
- **Remembered vendor (INGEST-02):** `LearnedProfile` gained a `vendor: str | None = None` field (additive, emitted from `to_dict()`), persisted at the exact seam `service.confirm()` already had -- immediately before `_record_aliases`. A new `profiles.vendor` column (nullable, `alembic/versions/2dadb963fae6_profile_vendor.py`, proven reversible: `upgrade head -> downgrade -1 -> upgrade head` against the live dev database). `service.recall_vendor(table, field_set, schema, store)` resolves in a fixed escalation order mirroring D-10-03's own shape: (1) an exact learned-profile match -- unambiguous *by construction* via `ProfileRow`'s own `UniqueConstraint(field_set_signature, column_signature)`; (2) a crosswalk fallback over the Schema's live (non-tombstoned) aliases -- exactly one distinct matching vendor resolves cleanly, **two or more refuses to pick one and returns both names, sorted** (the load-bearing anti-guessing test), zero returns empty; (3) otherwise empty. `MappingResponse` gained `remembered_vendor`/`remembered_vendor_source`/`vendor_candidates` (additive, defaulted, mirroring `escalation`'s own precedent exactly), threaded from both `/api/upload`'s happy path and `/api/date-format/resolve` (so a file needing a date question is not arbitrarily worse off than a clean one).
- **The schema-name default is dead.** `Review.tsx`'s `useState(schemaName ?? "")` -- which silently pre-filled the Vendor input with the *Schema's own name* (writing a vendor literally called `assay-potency` into the governed crosswalk on an inattentive confirm) -- is replaced by `useState(mapping ? initialVendor(mapping) : "")`, backed by a new pure module `frontend/src/state/vendorMemory.ts` (`initialVendor`/`vendorHint`, unit-tested with no DOM). A muted helper line beneath the input explains WHY it is pre-filled (profile vs crosswalk) or, on ambiguity, names both candidates and says the tool won't guess. **Consequence stated plainly: with the default gone, a confirm submitted with a blank Vendor now records no aliases** (`service._record_aliases` already no-ops without a vendor) -- correct, since it stops fabricating vendor data, and it does not touch the money shot (`test_money_shot.py`, still green), which rides the learned *profile* (signature -> auto-apply), not the crosswalk.

## Task Commits

Each task was committed atomically (TDD RED then GREEN per task; Task 3 additionally split backend/frontend GREEN since the frontend implementation file was written before its test by mistake and had to be temporarily removed to re-prove RED):

1. **Task 1: Sweep the "field set" copy leak and gate it permanently (D-10-02, INGEST-01)** - test `41abec8`, feat `2ade752`
2. **Task 2: Enforce sign-in on the server, not just in the UI (D-10-13, INGEST-06)** - test `d0ef756`, feat `627817d`
3. **Task 3: Remember the vendor instead of re-asking it (INGEST-02)** - test (backend) `7f23f5a`, test (frontend) `d792d98`, feat (backend) `5edd350`, feat (frontend) `fec1dee`

_TDD Gate Compliance: every task's `test(10-09)` commit precedes its `feat(10-09)` commit, verified in git log order._

## Files Created/Modified

- `frontend/src/state/copy.test.ts` - permanent gate against the field-set copy regression
- `frontend/src/screens/Schemas.tsx` - Add Field cap tooltip rewritten in Schema vocabulary
- `frontend/src/screens/Documentation.tsx` - two how-to steps rewritten to describe the surviving Schema/crosswalk reality
- `tests/api/conftest.py` - shared `verified_user()`/`unverified_user()` TestClient builders
- `tests/api/test_upload_auth_gate.py` - anonymous 401 (+ zero mapper calls) / signed-in-unverified 200, on all three gated routes
- `src/assayingest/api/routes/upload.py` - `require_user` on `/api/upload`; dead 401 branch removed from the map-file path; calls `recall_vendor` on the happy path
- `src/assayingest/api/routes/structural_hint.py` - `require_user` gate added (pure gate, unused value)
- `src/assayingest/api/routes/date_format.py` - `require_user` gate added; calls `recall_vendor` via a newly-injected `get_schema_store`
- `tests/api/test_reconcile.py` - imports shared builders; one test's premise reversed + a sibling added
- `tests/api/test_upload.py`, `test_upload_schema_target.py`, `test_date_format_route.py`, `test_confirm_dates.py`, `test_hint_and_export.py`, `test_money_shot.py` - each client-construction site gains the `get_current_user` override
- `tests/test_vendor_memory.py` - the remembered-vendor lookup, including the two-vendors-refuse-to-guess and tombstone-exclusion tests
- `src/assayingest/learning/profile.py` - `LearnedProfile.vendor: str | None = None`, emitted from `to_dict()`
- `src/assayingest/persistence/models.py` - `ProfileRow.vendor` nullable column
- `alembic/versions/2dadb963fae6_profile_vendor.py` - the migration, proven reversible
- `src/assayingest/learning/postgres_store.py` - `vendor` threaded through `save()`'s insert AND upsert-SET clause, and `_entity_to_profile()`
- `src/assayingest/service.py` - `save_profile_if_ready`/`confirm` thread `vendor`; new `VendorMemory` + `recall_vendor`
- `src/assayingest/api/wire.py` - `MappingResponse` gains the three additive vendor-memory fields
- `tests/test_profile_store.py` - the `to_dict()` key-set pin updated for the new additive `vendor` key
- `frontend/src/lib/types.ts` - `MappingResponse` gains the three vendor-memory fields
- `frontend/src/state/vendorMemory.ts` + `.test.ts` - `initialVendor`/`vendorHint`, pure and unit-tested
- `frontend/src/screens/Review.tsx` - schema-name vendor default replaced; hint line rendered
- `frontend/src/state/upload.test.ts`, `review.test.ts` - existing `MappingResponse` fixtures updated for the new required wire fields
- `frontend/tsconfig.app.json` - `"node"` added to the app project's `types` array (deviation, see below)

## Decisions Made

- D-10-02 supersedes `10-UI-SPEC.md:203`'s literal tooltip copy -- the locked decision wins; recorded so this cannot silently regress a third time.
- Auth-gate test fixtures override `get_current_user`, never `require_verified_user` alone, per the plan's own mechanism note -- verified this holds for every one of the 8 affected test files.
- `recall_vendor` is a NEW pure function; it does not modify `_vendor_agnostic_alias_index`/`_prefill_coverage`, preserving 10-05/10-08's pinned escalation counts exactly as instructed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tsc -b` broke under `tsconfig.app.json` once `copy.test.ts` existed**
- **Found during:** Task 1, verifying the frontend build after adding `copy.test.ts`
- **Issue:** `copy.test.ts` uses `node:fs`/`node:path`/`__dirname`. `tsconfig.app.json` (which covers all of `src/`, including test files) only declared `"types": ["vite/client"]` -- no Node ambient declarations, so `tsc -b --noEmit` failed with `TS2591`/`TS2304` on this one new file. Confirmed via a before/after check (moving the file aside made the baseline build clean again) that this was newly introduced, not pre-existing.
- **Fix:** Added `"node"` to `tsconfig.app.json`'s `types` array. `@types/node` was already a project devDependency (previously scoped only to `tsconfig.node.json`'s `vite.config.ts`), so this is a scoped config change, not a new dependency (the threat model's `T-10-SC` "no new dependencies" constraint holds).
- **Files modified:** `frontend/tsconfig.app.json`
- **Verification:** `npx tsc -b --force --noEmit` clean; `npx vitest run` still 186 passed; `npm run build` succeeds and `frontend/dist` was rebuilt.
- **Committed in:** `fec1dee` (Task 3's frontend feat commit -- discovered while finishing Task 3's build verification, though the root cause was Task 1's file; documented here rather than retroactively amending Task 1's commit, per the "never amend, always a new commit" rule)

**2. [Rule 1 - Bug] `tests/test_profile_store.py`'s `to_dict()` key-set pin broke on the additive `vendor` key**
- **Found during:** Task 3, running the full backend suite after adding `LearnedProfile.vendor`
- **Issue:** `test_to_dict_shape_matches_the_manifest_base` asserted an exact key set that predated the new additive `vendor` field; the plan's `files_modified` list did not name this test file, but it is a direct, unavoidable consequence of an additive change explicitly specified by the plan (`to_dict()` must emit `vendor`).
- **Fix:** Added `"vendor"` to the expected key set with an explanatory comment.
- **Files modified:** `tests/test_profile_store.py`
- **Verification:** `uv run pytest tests/test_profile_store.py -q` -- 8 passed.
- **Committed in:** `5edd350` (Task 3's backend feat commit)

---

**Total deviations:** 2 auto-fixed (1 blocking config fix, 1 direct-fallout test update)
**Impact on plan:** Both are narrow, necessary consequences of the plan's own additive changes (a new test file needing Node types; a new struct field appearing in an existing exact-key-set assertion). No scope creep, no architectural changes, no unplanned features.

## Issues Encountered

- Wrote `frontend/src/state/vendorMemory.ts` before its test by mistake (violating strict TDD RED-first). Corrected by moving the implementation aside, confirming the test file genuinely failed (`Cannot find module './vendorMemory'`), committing that as the RED commit, then restoring the implementation for GREEN -- the final git history still shows a clean test-then-feat order with no shortcut taken.
- The plan's own blast-radius table predicted 46 breaking tests across 8 files; the observed count after the route change was 44 (`test_confirm_gate.py`'s predicted 1 was actually 0 on audit; `test_reconcile.py`'s predicted 1 was pre-emptively fixed during the RED commit). Documented as a key-decision above rather than silently reconciled -- the final state (zero deletions, count only grows) matches every acceptance criterion regardless of the intermediate arithmetic.

## User Setup Required

None - no external service configuration required. Dev servers (Postgres, uvicorn `--reload` on :8000, Vite on :5173) were left running throughout and picked up every change live; `frontend/dist` was rebuilt via `npm run build` so the change reaches :8000 without a server restart.

## Next Phase Readiness

- This was the last plan of Phase 10 (`gap_closure: true`, no `depends_on` blocking further work). All three findings from the phase's own human verification are closed:
  - INGEST-01's copy sweep is now permanently gated, not just fixed once.
  - INGEST-06 (`require_user`/no anonymous upload path) is enforced server-side, closing the real security hole (an anonymous client could previously burn Anthropic credits at will).
  - INGEST-02's vendor-remembering closes the last piece of "stop asking for what the tool can work out for itself" while structurally refusing to guess on genuine ambiguity.
- Backend suite: 824 passed, 4 skipped (806 baseline + 18 net new, zero regressions). Frontend suite: 186 passed (178 baseline + 8 net new). Both suites grew, never shrank, per the plan's own success criteria.
- No blockers for milestone completion review.

---
*Phase: 10-frictionless-correct-ingest*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 7 newly-created files confirmed present on disk (`frontend/src/state/copy.test.ts`, `tests/api/conftest.py`, `tests/api/test_upload_auth_gate.py`, `tests/test_vendor_memory.py`, `alembic/versions/2dadb963fae6_profile_vendor.py`, `frontend/src/state/vendorMemory.ts`, `frontend/src/state/vendorMemory.test.ts`). All 8 task commit hashes (`41abec8`, `2ade752`, `d0ef756`, `627817d`, `7f23f5a`, `d792d98`, `5edd350`, `fec1dee`) confirmed present in `git log`. Full suite re-verified green: backend 824 passed / 4 skipped; frontend 186 passed; `tsc -b` clean; alembic round-trip (`upgrade head` -> `downgrade -1` -> `upgrade head`) proven against the live dev database; live curl repro confirms all three routes now 401 anonymously.

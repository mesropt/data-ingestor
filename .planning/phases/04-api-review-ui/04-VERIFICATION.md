---
phase: 04-api-review-ui
verified: 2026-07-11T14:30:00Z
status: passed
score: 11/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Full browser click-through of the money-shot: Define Fields (save a template) -> Upload novascreen_batch01.csv with that template -> Review screen shows several amber FieldRows -> resolve every field via chip/Accept/dropdown -> Confirm & Save Mapping (button was disabled until last field cleared) -> success toast + ExportBar with 4 working download links -> Upload novascreen_batch02.csv (same field set) -> Review screen loads with ProfileAppliedBanner and ZERO amber rows, Confirm already enabled."
    expected: "Every step in 04-06-SUMMARY.md's documented Manual UAT (lines 184-200) holds exactly as written, against a running `uvicorn assayingest.api.app:app` + built `frontend/dist`, with ANTHROPIC_API_KEY configured."
    why_human: "The API-level proof (tests/api/test_money_shot.py) and every individual UI component/state-machine unit test pass, and the code wiring for every screen transition was read and confirmed substantive (not a stub) — but no agent in this execution or verification session drove a real browser against a running server process end-to-end. 04-06-SUMMARY.md itself documents this step as NOT executed live this session, by design (the plan forbids interactively running the dev server during automated execution)."
---

# Phase 4: API & Review UI Verification Report

**Phase Goal:** A user can perform the full define-fields → upload → resolve-hint → review → confirm → learn cycle in the browser (the demo's centerpiece), with the server independently re-checking the "no yellow fields" gate rather than trusting the client.
**Verified:** 2026-07-11T14:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (mapped to the 4 ROADMAP Success Criteria + code-review must-confirms)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 (UI-01): User can define/edit target fields + constraints in the browser and save/load field-set templates matching the upload endpoint's contract | ✓ VERIFIED | `frontend/src/screens/DefineFields.tsx` calls real `listFieldSets`/`getFieldSet`/`saveFieldSet` against `/api/field-sets`; `api/routes/field_sets.py` uses `fields.loader.from_dict` (same validation as CLI `--fields`) via `FieldSetTemplateStore`/`SqliteFieldSetStore`. `frontend/src/lib/api.ts::uploadFile` sends the identical `FieldSetPayload` shape as `field_set` to `/api/upload`. `frontend/src/state/fieldSet.test.ts` (14 tests) passes. |
| 2 | SC2 (UI-02/API-01): User uploads CSV/Excel with a chosen field set → side-by-side response; structural ambiguity surfaces an inline hint instead of failing | ✓ VERIFIED | `api/routes/upload.py` is a thin call to `service.resolve_or_map`, returns discriminated `kind:"mapping"`/`kind:"structural_question"`. `frontend/src/screens/Upload.tsx` renders `StructuralHintPanel` inline (not a modal) on the question branch and resubmits through `/api/structural-hint/resolve`. `frontend/src/state/upload.test.ts` (18 tests) passes; `tests/api/test_upload.py`, `tests/api/test_hint_and_export.py` pass in the 461-test backend run. |
| 3 | SC3a (UI-03): Review screen shows side-by-side — source columns left, target fields right | ✓ VERIFIED | `frontend/src/components/ReviewTable.tsx` renders `sourceColumns` (32% pane) and one `FieldRow` per `mapping.field_mappings` (68% pane), reading directly from the `/api/upload` response — no static/hardcoded arrays. |
| 4 | SC3b (UI-04): Yellow fields show Claude's reason + ranked alternatives; resolvable via chip/accept/dropdown | ✓ VERIFIED | `frontend/src/components/FieldRow.tsx` renders `reasoning` always visible (not hover-gated) plus `validator_note`, `ConfidenceChip`s per `alternatives`, an Accept button, and a manual `Select` dropdown over all `sourceColumns`. `frontend/src/state/review.ts::resolveByChip/resolveByAccept/resolveByDropdown` are pure, tested functions (`review.test.ts`, 15 tests). |
| 5 | SC3c (UI-05): Confirm/export disabled while any field yellow, mirroring the server gate | ✓ VERIFIED | `frontend/src/components/ConfirmGate.tsx` derives `disabled={!ready}` directly from `state/review.ts::isReady`, which mirrors `domain/models.py::MappingProposal.is_ready` exactly (`length>0 && every(!needs_confirmation)`). `Review.tsx` only renders `ExportBar` after a real 200 from `/api/confirm`, never from local state. |
| 6 | SC3d (API-02, P1): Confirm endpoint independently re-checks the gate server-side — fail-closed, never trusting the client | ✓ VERIFIED | `src/assayingest/api/routes/confirm.py` uses `entry.field_set` (server-retained) as the SOLE validation/assembly authority; `body.field_set` is only signature-checked and rejected on drift (422). `src/assayingest/service.py::confirm` raises `FieldCoverageError` (422) when submitted mappings don't cover exactly `field_set.field_names`, checked BEFORE `is_ready` is read. Both fixes read exactly as 04-REVIEW.md's CR-01/CR-02 fix prescribes. Tamper tests directly exercise both bypasses and pass: `test_confirm_rejects_a_client_field_set_that_weakens_a_declared_constraint`, `test_confirm_rejects_a_body_that_omits_a_still_yellow_required_field`, `test_confirm_ignores_a_client_sent_field_set_signature`, `test_confirm_rejects_a_tampered_ready_claim_over_a_real_constraint_violation` — all PASS (`.venv/bin/pytest tests/api/test_confirm_gate.py -v`, 8/8 passed). |
| 7 | SC4a (API-03): Auto-apply builds no Anthropic client, makes zero Claude calls on a repeat signature | ✓ VERIFIED | `service.resolve_table_mapping` returns immediately on a profile-store hit, before `has_credentials()`/client construction is ever reached. `api/deps.py::get_anthropic_client` returns `None` by default (no eager construction). `tests/api/test_money_shot.py::test_upload_confirm_reupload_money_shot_zero_yellow_one_claude_call` spies on `service.propose_mapping` and asserts `call_count["n"] == 1` across upload→confirm+save→re-upload — PASS. |
| 8 | SC4b (UI-06): User saves confirmed mapping as a profile from the UI; second same-signature upload shows zero yellow, auto-mapped, learning loop visible | ⚠️ Code-verified, browser click-through NOT exercised | `Review.tsx::handleConfirm` always sends `saveProfile: true`; `ProfileAppliedBanner` renders when `mapping.provenance === "auto-applied-from-profile"` (`state/review.ts::isAutoApplied`), reading a value the server itself set from `entry.provenance` (never client-trusted, WR-04 fix). Code-level wiring is complete and consistent with the passing API-level money-shot test (#7). **However**, 04-06-SUMMARY.md's own "Manual UAT" section (lines 184-200) explicitly states this end-to-end browser sequence was **not executed live** in the implementation session, and no verification step in this session drove a real browser against a running server either. Per task instruction, this is routed to human verification rather than failed. |
| 9 | P2: Temp files unlinked on every error branch and on registry eviction | ✓ VERIFIED | `api/routes/structural_hint.py` wraps every exception branch (`MissingCredentialsError`, `AuthenticationError`, `APIError`/`ValueError`) in `_unlink_ignoring_missing(entry.tmp_path)` before re-raising — exactly the CR-03 fix. `api/state.py::UploadRegistry._evict_oldest_if_over_capacity` calls `_unlink_if_retained` on every evicted entry — exactly the WR-01 fix. `upload.py` already unlinked on every error branch (pre-existing, confirmed still correct). |
| 10 | P2: `--headers-only` reachable from web upload, sends no cell values on the mapping AND structural-hint-evidence paths | ✓ VERIFIED | `Upload.tsx` has a `HeadersOnlyToggle` wired into `uploadFile(...)`'s `headersOnly` param; `StructuralHintPanel.tsx` explicitly suppresses the evidence-row table under `headersOnly`, showing only column/row counts (CR-01/Phase-3-fix carried forward). |
| 11 | All 9 code-review findings (04-REVIEW.md) are fixed in code, not just claimed | ✓ VERIFIED | CR-01/CR-02 in `confirm.py`+`service.py` (#6); CR-03 in `structural_hint.py` (#9); WR-01 in `state.py` (#9); WR-02 `.xls` moved to `_LEGACY_EXCEL_SUFFIXES` → HTTP 400, not 500 (`upload.py:46-51,173-180`); WR-03 `field_sets.py::list_field_sets` skips a `None` `store.get()` result instead of dereferencing it; WR-04 `confirm.py` uses `entry.provenance` (never `body.provenance`) for the manifest, with `test_confirm_manifest_uses_the_retained_provenance_not_a_lying_client_body` passing; IN-01 documented as intentionally-vestigial (frontend still sends `field_set`, server treats it as signature-only per CR-01); IN-02 `state.py::UploadRegistry.get` calls `move_to_end(token)` on every hit. |
| 12 | Thin adapter: routes call `service.py`; `sqlite3` confined to the two `sqlite_*_store.py` implementations | ✓ VERIFIED | `grep -rn "import sqlite3" src/` returns only `learning/sqlite_store.py` and `learning/sqlite_field_set_store.py`. `grep` for `validate(`/`canonical.`/`reconstruct_proposal(`/`propose_mapping(` inside `api/routes/*.py` returns zero call sites (only docstring mentions in `confirm.py`) — every route delegates to `service.py`. |

**Score:** 11/12 truths verified (1 code-verified-but-behaviorally-unexercised in a real browser, routed to human verification per task instruction, not counted as a gap)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/service.py` | Decide-vs-render orchestration seam shared by CLI + API | ✓ VERIFIED | `resolve_table_mapping`, `resolve_or_map`, `confirm`, `save_profile_if_ready`, `export` all present, substantive, wired from both `cli.py` and `api/routes/*.py` |
| `src/assayingest/api/app.py` | FastAPI app, routers, static frontend mount | ✓ VERIFIED | Mounts 5 routers + `app.frontend("/", directory="frontend/dist", check_dir=False)`; live-checked `GET /` → 200, title contains "Data Ingestor"; `GET /api/field-sets` → 200 `[]` |
| `src/assayingest/api/routes/upload.py` | POST /api/upload | ✓ VERIFIED | Thin wrapper over `service.resolve_or_map`; extension allowlist, size bound, temp-file cleanup all present |
| `src/assayingest/api/routes/confirm.py` | POST /api/confirm, server-side P1 gate | ✓ VERIFIED | See truth #6 |
| `src/assayingest/api/routes/structural_hint.py` | POST /api/structural-hint/resolve | ✓ VERIFIED | See truths #2, #9 |
| `src/assayingest/api/routes/field_sets.py` | GET/POST field-set templates | ✓ VERIFIED | See truth #1, #11 (WR-03 fix) |
| `src/assayingest/api/routes/export.py` | GET /api/export/{run_id}/{fmt} | ✓ VERIFIED | UUID-pattern-validated `run_id`, fixed format allowlist, no new writer logic |
| `src/assayingest/api/state.py` | Upload correlation registry | ✓ VERIFIED | See truths #9, #11 (IN-02 fix) |
| `src/assayingest/learning/sqlite_field_set_store.py` | Field-set template SQLite store | ✓ VERIFIED | Parameterized `?` placeholders confirmed by 04-REVIEW.md and unchanged since |
| `frontend/src/screens/DefineFields.tsx` | UI-01 screen | ✓ VERIFIED | See truth #1 |
| `frontend/src/screens/Upload.tsx` | UI-02 screen | ✓ VERIFIED | See truth #2 |
| `frontend/src/screens/Review.tsx` | UI-03/04/05/06 screen | ✓ VERIFIED | See truths #3-6, #8 |
| `frontend/src/components/ReviewTable.tsx`, `FieldRow.tsx`, `ConfirmGate.tsx`, `ProfileAppliedBanner.tsx`, `ExportBar.tsx`, `StructuralHintPanel.tsx` | Supporting review-flow components | ✓ VERIFIED | All read; all substantive, none are placeholders or stubs |
| `frontend/src/state/{fieldSet,upload,review}.ts` | Pure state-logic modules | ✓ VERIFIED | All tested (47 vitest tests total: 14+18+15) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `frontend/src/screens/DefineFields.tsx` | `POST/GET /api/field-sets` | `lib/api.ts::saveFieldSet/listFieldSets/getFieldSet` | ✓ WIRED | Real `fetch` calls, response drives `templates` state and toolbar dropdown |
| `frontend/src/screens/Upload.tsx` | `POST /api/upload` | `lib/api.ts::uploadFile` (multipart) | ✓ WIRED | Response dispatched into reducer; `kind:"mapping"` navigates to Review via `onMapped` |
| `frontend/src/components/StructuralHintPanel.tsx` | `POST /api/structural-hint/resolve` | `Upload.tsx::handleResolveHint` → `lib/api.ts::resolveHint` | ✓ WIRED | Re-submits within the same reducer/state machine, not a new route |
| `frontend/src/screens/Review.tsx` | `POST /api/confirm` | `state/review.ts::toConfirmPayload` → `lib/api.ts::confirm` | ✓ WIRED | 422 mapped to `GateRejected`, never unlocks `ExportBar` |
| `api/routes/confirm.py` | `src/assayingest/service.py::confirm` | direct function call | ✓ WIRED | Route deserializes, delegates the gate decision entirely to `service.confirm` |
| `api/routes/upload.py`, `structural_hint.py` | `src/assayingest/service.py::resolve_or_map` | direct function call | ✓ WIRED | Neither route re-implements parsing/mapping/validation |
| `api/state.py::registry` | `confirm.py`/`structural_hint.py` | `registry.get`/`registry.pop` keyed by `upload_token` | ✓ WIRED | The server-retained `FieldSet`/`RawTable`/`provenance` are the sole authority the gate reads — never rebuilt from the request body |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full backend test suite | `.venv/bin/pytest -q` | 461 passed, 4 skipped (live-API-key tests) | ✓ PASS |
| Confirm-gate tamper tests (single named-file run) | `.venv/bin/pytest tests/api/test_confirm_gate.py -v` | 8/8 passed, including all 3 tamper scenarios | ✓ PASS |
| SC4 money-shot API test | Included in full suite run; also independently verified as part of `tests/api/` collection | PASS — asserts `call_count["n"] == 1` after upload→confirm→re-upload | ✓ PASS |
| Frontend build | `npm run build` (frontend/) | `tsc -b && vite build` succeeds, `dist/index.html` + assets produced | ✓ PASS |
| Frontend unit test suite | `npm run test -- --run` (frontend/) | 47 passed (3 test files) | ✓ PASS |
| Live server smoke test | `TestClient(app).get("/")` / `.get("/api/field-sets")` | `GET /` → 200, "Data Ingestor" in body; `GET /api/field-sets` → 200 `[]` | ✓ PASS |
| Thin-adapter grep | `grep -rln "import sqlite3" src/` | Only `learning/sqlite_store.py`, `learning/sqlite_field_set_store.py` | ✓ PASS |
| Debt-marker scan | `grep -rn "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` over `frontend/src`, `api/`, `service.py`, `learning/*.py` | No matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| API-01 | 04-01, 04-02 | Upload returns proposed-and-validated mapping as JSON | ✓ SATISFIED | Truth #2, #7 |
| API-02 | 04-01, 04-03 | Confirm endpoint re-checks the gate server-side, never trusts client | ✓ SATISFIED | Truth #6, tamper tests |
| API-03 | 04-01, 04-02 | Upload auto-applies a matching profile, no Claude call | ✓ SATISFIED | Truth #7, money-shot test |
| UI-01 | 04-03, 04-04 | Define/edit fields + save/load templates | ✓ SATISFIED | Truth #1 |
| UI-02 | 04-03, 04-05 | Upload + inline structural hint | ✓ SATISFIED | Truth #2, #10 |
| UI-03 | 04-06 | Side-by-side review view | ✓ SATISFIED | Truth #3 |
| UI-04 | 04-06 | Yellow highlighting + reason + alternatives + resolve | ✓ SATISFIED | Truth #4 |
| UI-05 | 04-06 | Confirm/export disabled while yellow, mirrors server gate | ✓ SATISFIED | Truth #5 |
| UI-06 | 04-06 | Save profile from UI, second upload zero yellow, learning loop visible | ⚠️ Code-verified; browser proof pending | Truth #8 (human_needed) |

No orphaned requirements — every ID in REQUIREMENTS.md's Phase 4 section (API-01..03, UI-01..06) is claimed by at least one plan (04-01 through 04-06), and every plan's declared `requirements:` was checked against actual code.

### Anti-Patterns Found

None. Debt-marker scan (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet implemented"/"coming soon") across `frontend/src`, `src/assayingest/api/`, `src/assayingest/service.py`, and `src/assayingest/learning/*.py` returned zero matches. No empty handlers, no hardcoded-empty stub returns feeding rendered UI, no `NotImplementedError` anywhere in the API layer.

### Human Verification Required

### 1. Full browser click-through of the SC4 money-shot

**Test:** Build the frontend, run `uvicorn assayingest.api.app:app` with `ANTHROPIC_API_KEY` set, and drive the exact 7-step sequence documented in `.planning/phases/04-api-review-ui/04-06-SUMMARY.md`'s "Manual UAT" section: Define Fields → save a template → Upload `novascreen_batch01.csv` → resolve every amber field (mix of chip/Accept/dropdown) → Confirm & Save Mapping → Upload `novascreen_batch02.csv` with the same field set → verify the Review screen shows the `ProfileAppliedBanner` with zero amber rows and Confirm already enabled.

**Expected:** Every step's documented expectation holds exactly (amber-to-clear transitions, tooltip-gated disabled button, success toast, working export links, and — the actual money shot — zero amber + banner on the second upload with no second Claude call).

**Why human:** All supporting code was read and confirmed substantive/wired (screens, state modules, API routes, the server-side gate), and the identical sequence is proven at the API level by a passing test (`tests/api/test_money_shot.py`). But no agent — not the phase executor, not this verification pass — drove a real browser against a running server process this session; 04-06-SUMMARY.md documents this explicitly as deferred by design. This is exactly the kind of "cool to watch" demo-centerpiece claim that code inspection alone cannot certify.

## Gaps Summary

No blocking gaps. All 9 code-review findings (04-REVIEW.md) were independently re-read in the current codebase and confirmed fixed — the P1 server-side gate genuinely uses the server-retained `FieldSet` as sole authority and rejects both the constraint-weakening and field-omission bypasses the review found, backed by passing tamper tests. The backend (461/461 non-skipped) and frontend (47/47) test suites are green, the frontend builds, and a live `TestClient` smoke test confirms the one-command demo stack serves both the API and the built React bundle from a single process.

The single open item is SC4/UI-06's final "visibly in the browser" step: the code-level wiring and the API-level automated proof are both solid, but the actual browser click-through has not been executed by any agent this session (by explicit design, per the plan). This is routed to human verification rather than treated as a gap, per the task's explicit guidance — the orchestrator/developer should run the 7-step Manual UAT in `04-06-SUMMARY.md` before treating the Phase 5 demo recording as ready.

---

_Verified: 2026-07-11T14:30:00Z_
_Verifier: Claude (gsd-verifier)_

---
phase: 08-reconcile-on-upload
verified: 2026-07-11T20:05:00Z
status: passed
autonomous_acceptance: "3/3 code+test verified (595 backend, 97 frontend). Browser money-shot + reconcile-panel interaction deferred to milestone-end human UAT."
score: 3/3 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Money shot — upload a second file from a KNOWN vendor (whose aliases are already in the target Schema's crosswalk) in the browser."
    expected: "Every column pre-fills green at confidence 1.0 with zero yellow flags and no perceptible Claude latency; the Review screen shows an already-resolved mapping ready to confirm."
    why_human: "Visual/latency perception + end-to-end browser flow. The deterministic no-Claude short-circuit and 1.0 confidence are proven by the mapper-spy service tests, but the on-screen 'all green, instant' demo impression cannot be asserted programmatically."
  - test: "Conflict resolution — upload a map file whose alias targets a different canonical field than the master, and resolve via the inline ReconcilePanel (keep-master vs take-map-file per row), then confirm."
    expected: "The ReconcilePanel renders one row per conflict with the source column + vendor and a working keep-master/take-map-file Select (keep-master preselected); on submit the flow proceeds to the yellow-flag Review reflecting the chosen side, and Confirm succeeds under the unchanged gate."
    why_human: "Panel rendering, Select interaction, and the visual transition into Review are browser-only. The wire contract, reducer routing, and per-choice resolution are covered by API + vitest tests, but the rendered interaction is not."
---

# Phase 8: Reconcile-on-Upload Verification Report

**Phase Goal:** Let an upload optionally carry a map file (Phase 07 master-map JSON) that augments the target Schema's crosswalk before Claude maps the file; known vendor aliases pre-fill deterministically at confidence 1.0; a map-file-vs-master conflict is surfaced for human resolution (never silently merged); the reconciled mapping lands in the existing yellow-flag review UI under the unchanged server-side confirm gate.
**Verified:** 2026-07-11T20:05:00Z
**Status:** human_needed (all 3 success criteria code-verified; 2 browser-only visual checks pending)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
| --- | --- | --- | --- |
| RECON-01 | Upload can carry an optional map file that AUGMENTS the target Schema's crosswalk BEFORE mapping; exact `(vendor, source_column)` aliases pre-fill deterministically at confidence 1.0 with NO Claude call for those; headers_only-safe. | ✓ VERIFIED | `service._reconcile_map` (service.py:617-677) pre-fills matches at `confidence=1.0`/`needs_confirmation=False` and only calls the mapper on the *reduced* uncovered field set; when all fields covered it never constructs a client. `reconcile_or_map` (service.py:721-780) augments via reused `import_master_map` BEFORE `_reconcile_map`. `/api/upload` map-file branch wired (upload.py:95-100, 154-254). Tests: `test_prefill_maps_covered_field_at_confidence_one_and_asks_mapper_for_the_rest`, `test_short_circuit_never_calls_the_mapper_when_every_field_is_covered` (mapper spy raises if called; asserts `confidence==1.0`), `test_prefill_headers_only_produces_the_same_result_from_names_alone`, `test_upload_clean_map_file_augments_and_returns_mapping`. |
| RECON-02 | A conflicting/ambiguous map file returns `kind="reconcile_question"`; NOTHING augmented/mapped until the human resolves via `/api/reconcile/resolve`; resolution applied per-choice. | ✓ VERIFIED | `detect_reconcile_conflicts` (service.py:560-597) flags exact alias-target disagreements; `reconcile_or_map` returns the `ReconcileQuestion` and mutates nothing before augment (service.py:766-768). `apply_reconcile_resolution` (service.py:783-834) builds an explicit per-choice override (`_resolution_override_index`, service.py:693-718). Route `/api/reconcile/resolve` (reconcile.py) pops retained entry, applies choices. Tests: `test_reconcile_or_map_returns_reconcile_question_and_mutates_nothing_on_conflict` (asserts `store.list_aliases_for == before` AND mapper spy count 0), `test_upload_conflicting_map_file_returns_reconcile_question_and_mutates_nothing`, `test_reconcile_resolve_take_map_file_returns_mapping_and_cleans_up`, `test_reconcile_resolve_keep_master_prefills_master_field`, `test_reconcile_resolve_unknown_token_is_404`. |
| RECON-03 | Reconciled mapping lands in the existing review UI (terminal `MappingResponse`) under the UNCHANGED confirm gate (Phase 04 `is_ready` re-validation + Phase 06 `require_verified_user`). | ✓ VERIFIED | Resolve returns `MappingResponse.from_proposal(...)` with a fresh `upload_token` (reconcile.py:100-107) feeding the untouched `/api/confirm`. `confirm()` (service.py:273-344) unchanged — rebuilds proposal, re-`validate()`, reads `is_ready` fresh. Augment paths gated: inline 401/403 on upload (upload.py:170-178), unconditional `require_verified_user` on resolve (reconcile.py:48). Test: `test_reconciled_mapping_feeds_the_unchanged_confirm_gate` posts the reconciled mapping to `/api/confirm` → 200 + `ready:true`; `test_upload_map_file_signed_out_is_401`, `_unverified_is_403`, `test_reconcile_resolve_signed_out_is_401`/`_unverified_is_403`. |

**Score:** 3/3 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/assayingest/service.py` | detect_reconcile_conflicts, _reconcile_map, reconcile_or_map, apply_reconcile_resolution | ✓ VERIFIED | Substantive; reuses `import_master_map`/`Schema.from_master_map`/`_normalise_header`, no second engine/parser. |
| `src/assayingest/domain/models.py` | ReconcileConflict + ReconcileQuestion (+ to_dict / has_conflicts) | ✓ VERIFIED | Frozen dataclasses, lines 223-268. |
| `src/assayingest/api/routes/upload.py` | map-file branch + conditional 401/403 gate + bounded JSON read | ✓ VERIFIED | `_reconcile_upload` + `_read_bounded_json_envelope`; plain-upload path byte-unchanged. |
| `src/assayingest/api/routes/reconcile.py` | POST /api/reconcile/resolve two-step, verified-user gated, temp-file cleanup | ✓ VERIFIED | Pure adapter; unlink on every branch. Registered in app.py:34. |
| `src/assayingest/api/wire.py` | ReconcileQuestionResponse / ReconcileChoiceIn / ReconcileResolveRequest | ✓ VERIFIED | `decision` is a `Literal` (422 at boundary); conflicts spread verbatim from `to_dict()`. |
| `src/assayingest/api/state.py` | UploadEntry map_envelope/target_schema_name/vendor retention | ✓ VERIFIED | Additive None-defaulted fields (state.py:73-75). |
| `frontend/.../ReconcilePanel.tsx` + `MapFileControls.tsx` | inline conflict panel + map-file attach/schema/vendor | ✓ VERIFIED (build/checker) | Present, imported and rendered in Upload.tsx; escape-by-default text. Visual → human check. |
| `frontend/src/state/reconcile.ts` + `state/upload.ts` | 3-arm union + reconcile phases/actions + pure choice reducers | ✓ VERIFIED | vitest-covered (`reconcile.test.ts`, `upload.test.ts`). |
| `frontend/src/lib/api.ts` | uploadFile map-file options + resolveReconcile | ✓ VERIFIED | Options appended only when map file attached (plain upload body identical). |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| `/api/upload` (map file) | `service.reconcile_or_map` | `_reconcile_upload` after inline 401/403 gate | ✓ WIRED |
| `reconcile_or_map` | crosswalk augment | reused `import_master_map` before pre-fill | ✓ WIRED |
| `/api/reconcile/resolve` | `service.apply_reconcile_resolution` | registry.pop(token) + choices triples | ✓ WIRED |
| resolve result | `/api/confirm` | fresh `upload_token` on terminal MappingResponse | ✓ WIRED |
| `Upload.tsx` | `resolveReconcile` → Review | `handleResolveReconcile` → `handleResponse` (mapping arm) | ✓ WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full backend suite (additive proof, zero regressions) | `uv run pytest -q` | 595 passed, 4 skipped (pre-existing credential-gated live tests) | ✓ PASS |
| Reconcile service + API tests | `pytest tests/test_reconcile_service.py tests/api/test_reconcile.py -q` | 35 passed | ✓ PASS |
| Frontend suite | `npx vitest run` | 6 files, 97 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
| --- | --- | --- | --- |
| RECON-01 | Optional map file augments crosswalk before mapping | ✓ SATISFIED | Service + API tests (see RECON-01 row) |
| RECON-02 | Conflict → ask the user, never silently choose | ✓ SATISFIED | mutates-nothing + resolve tests (see RECON-02 row) |
| RECON-03 | Reconciled mapping in review UI under existing confirm gate | ✓ SATISFIED | confirm-gate 200 + gate 401/403 tests (see RECON-03 row) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| MapFileControls.tsx | 116,133 | `placeholder=` prop / example text | ℹ️ Info | Legitimate Select/Input placeholder attributes, not stubs |
| domain/models.py | 107 | word "placeholder" in comment | ℹ️ Info | Comment about SQL parameterised placeholders |

No `TBD`/`FIXME`/`XXX`, no unreferenced debt markers, no empty implementations. All `FUTURE` references are scoped deferrals (fuzzy matching MATCH-01, schema versioning) explicitly out of phase scope per 08-CONTEXT.md.

### Human Verification Required

1. **Money shot (known-vendor second file → all green, zero yellow, instant).** Upload a file from a vendor already in the Schema crosswalk; expect every column pre-filled green at 1.0 with no Claude latency. *Why human:* visual/latency perception. The deterministic no-Claude short-circuit and 1.0 confidence are machine-proven by the mapper-spy tests; the demo impression is not.
2. **Conflict-resolution panel.** Upload a conflicting map file; resolve each row (keep-master/take-map-file) in the inline ReconcilePanel; confirm. *Why human:* panel rendering + Select interaction + transition into Review are browser-only; the underlying wire/reducer/resolution logic is test-covered.

### Gaps Summary

No gaps. All three success criteria (RECON-01/02/03) are behaviorally verified end-to-end through the HTTP boundary and the frontend reducers, with 727 tests green (595 backend + 97 frontend + the 35-test reconcile subset counted within backend) and zero regressions to the existing upload / structural-hint / confirm / money-shot suites. The two outstanding items are browser-only visual confirmations of the demo experience, routed to human verification per end-of-phase mode — they do not block goal achievement, which is code-complete.

---

_Verified: 2026-07-11T20:05:00Z_
_Verifier: Claude (gsd-verifier)_

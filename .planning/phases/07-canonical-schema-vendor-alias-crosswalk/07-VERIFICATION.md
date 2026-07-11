---
phase: 07-canonical-schema-vendor-alias-crosswalk
verified: 2026-07-11T14:54:41Z
status: human_needed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run the app (uvicorn + npm run dev), sign in as a verified user, promote the current field set to a Schema, select it, set a vendor, confirm a mapping, then Download the master-map and re-Import it."
    expected: "The downloaded master-map JSON contains the recorded manual alias (vendor + provenance manual/actor=your email); the re-import reports augment success and does not discard existing fields/aliases."
    why_human: "End-to-end browser flow across auth session + file download + file re-import; the anchor <a download> GET and hidden file-picker JSON round-trip are not observable by grep/unit tests. Deferred by Plan 04 as human_verify_mode=end-of-phase (non-blocking)."
---

# Phase 7: Canonical Schema + Vendor-Alias Crosswalk Verification Report

**Phase Goal:** Turn a disposable field set into a governed canonical model per domain (a "Schema") whose canonical fields each carry vendor aliases with provenance, downloadable/importable as a JSON master map file; confirming a reviewed mapping records resolved source columns as aliases into the Schema's crosswalk.
**Verified:** 2026-07-11T14:54:41Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SCHEMA-01 — promote a field set into a named governed Schema, `created_by` = server user | ✓ VERIFIED | `service.promote` (`service.py:461-484`) stamps `created_by` from arg; route `schemas.py:34-51` passes `user.email` from `require_verified_user`, has no `created_by` body field. Tests: `test_promote_two_field_sets_yields_isolated_schemas`, route `test_post_schemas_verified_creates_with_server_resolved_created_by` (asserts `attacker@evil.com` body is ignored, actor = `curator@example.com`). |
| 2 | SCHEMA-02 — download a Schema as JSON master map file | ✓ VERIFIED | `Schema.to_master_map()` versioned envelope (`models.py:173-183`); `service.export_master_map` (`service.py:487-492`); `GET /api/schemas/{name}/master-map` returns envelope, 404 when absent (`schemas.py:59-64`). Test `test_export_...envelope` + route export test. Frontend `masterMapDownloadUrl` + `<a download>` wired (SchemaControls.tsx). Browser download itself in human_verification. |
| 3 | SCHEMA-03 — import master map augments existing Schema (add fields+aliases, never discard) | ✓ VERIFIED | `service.import_master_map` (`service.py:495-542`) adds missing fields then unions aliases via INSERT OR IGNORE; `SchemaNotFoundError` on unknown target. Test `test_export_import_round_trip_preserves_existing_manual_alias` proves B keeps its own field + gains A's field AND pre-existing manual alias provenance survives the from_map_file import. |
| 4 | SCHEMA-04 — multiple Schemas isolated (structural, not name-filtered) | ✓ VERIFIED | `schema_id`/`canonical_field_id` FKs + per-schema WHERE filtering + `PRAGMA foreign_keys=ON` (`sqlite_schema_store.py:50-98,162-170,217-238`). Test `test_schemas_are_isolated_no_shared_fields_or_aliases` asserts B sees none of A's fields/aliases via FK, not name filter. |
| 5 | ALIAS-01 — each canonical field carries vendor aliases | ✓ VERIFIED | `CanonicalField.aliases: tuple[Alias,...]` (`models.py:139-154`); `_row_to_schema` attaches per-field aliases (`sqlite_schema_store.py:225-247`); `list_aliases_for`. Test `test_list_aliases_for_preserves_vendor_and_full_provenance`. |
| 6 | ALIAS-02 — alias records which vendor | ✓ VERIFIED | `Alias.vendor` (`models.py:111`); persisted column + `_row_to_alias` (`sqlite_schema_store.py:271-280`). Asserted across store/service tests. |
| 7 | ALIAS-03 — provenance manual(user) vs from_map_file(source) + timestamp, immutable | ✓ VERIFIED | `Alias.provenance_kind/actor/created_at` (`models.py:99-136`); INSERT OR IGNORE on `UNIQUE(canonical_field_id, vendor, source_column)`, no ON CONFLICT DO UPDATE (`sqlite_schema_store.py:64-73,135-160`). Test `test_add_alias_is_idempotent_and_provenance_is_immutable` + round-trip preservation test. |
| 8 | ALIAS-04 — confirming records resolved source columns as aliases w/ provenance; CLI/no-schema path records nothing | ✓ VERIFIED | `_record_aliases` (`service.py:335-374`) no-op unless store+name+vendor all present; actor = `confirmed_by`; recorded only after gate passes. Tests: `test_confirm_records_manual_actor_aliases_for_each_resolved_column`, `test_confirm_without_schema_or_vendor_records_nothing`, idempotency + gate-rejection tests; route test asserts client `provenance_actor=attacker@evil.com` ignored. Existing confirm suite green. |

**Score:** 8/8 truths verified (0 present, behavior-unverified). Each behavior-dependent invariant (isolation, augment-never-discard, immutable provenance, no-op-on-CLI) has a passing named behavioral test.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/domain/models.py` | Alias/CanonicalField/Schema + master-map round-trip | ✓ VERIFIED | Frozen dataclasses; `to_master_map`/`from_master_map` re-validate field names via shared loader guard |
| `src/assayingest/learning/schema_store.py` | SchemaStore ABC seam | ✓ VERIFIED | 6 abstract methods mirroring ProfileStore |
| `src/assayingest/learning/sqlite_schema_store.py` | SQLite impl on shared DB, structural isolation | ✓ VERIFIED | Same `_DEFAULT_DB_PATH`; FKs, UNIQUE constraints, parameterised SQL, boundary translators |
| `src/assayingest/service.py` | promote/export/import + confirm alias recording | ✓ VERIFIED | All present, wired, typed errors |
| `src/assayingest/api/routes/schemas.py` | gated create/list/export/import | ✓ VERIFIED | Both mutations depend on `require_verified_user`; typed errors → 404/422 |
| `src/assayingest/api/deps.py` | get_schema_store DI + require_verified_user | ✓ VERIFIED | Factory `deps.py:43-49`; gate `deps.py:98+` |
| `src/assayingest/api/routes/confirm.py` | threads schema_store + schema_name/vendor | ✓ VERIFIED | `confirm.py:93-104`, actor = `user.email` |
| `frontend/src/components/SchemaControls.tsx` | promote/selector/download/import/vendor, auth-gated | ✓ VERIFIED | `governed = signedIn && verified` gates promote/import; download not gated (public GET) |
| `frontend/src/state/schema.ts` + `lib/api.ts` | reducer + API client | ✓ VERIFIED | Pure reducer; promoteSchema/listSchemas/importMasterMap/masterMapDownloadUrl |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `schemas.py` POST routes | `require_verified_user` | `Depends(require_verified_user)` — gate before store work | ✓ WIRED (401/403 tests) |
| `confirm.py` | `service.confirm` | `schema_store` + `schema_name` + `vendor` + `confirmed_by=user.email` | ✓ WIRED |
| `_record_aliases` | `SchemaStore.add_alias` | `provenance_actor=confirmed_by`, `provenance_kind="manual"` | ✓ WIRED |
| `import_master_map` | `add_alias` | `provenance_kind="from_map_file"`, actor=source_name | ✓ WIRED |
| `SchemaControls.tsx` | `/api/schemas`, `/api/confirm` | promoteSchema / importMasterMap / vendor thread | ✓ WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full backend suite | `uv run python -m pytest -q` | 560 passed, 4 skipped (pre-existing live-API) | ✓ PASS |
| Phase-07 named tests | `pytest test_schema_store.py test_schema_service.py test_confirm_records_aliases.py` | 26 passed | ✓ PASS |
| Frontend suite | `npm run test -- --run` | 82 passed / 5 files | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|------------|--------|----------|
| SCHEMA-01 | 07-02, 07-04 | ✓ SATISFIED | promote service + gated route + UI |
| SCHEMA-02 | 07-02, 07-04 | ✓ SATISFIED | export envelope + GET route + download |
| SCHEMA-03 | 07-02, 07-04 | ✓ SATISFIED | augment-only import + round-trip test |
| SCHEMA-04 | 07-01, 07-02 | ✓ SATISFIED | structural FK isolation test |
| ALIAS-01 | 07-01, 07-03 | ✓ SATISFIED | CanonicalField.aliases + list_aliases_for |
| ALIAS-02 | 07-01, 07-03 | ✓ SATISFIED | Alias.vendor persisted/round-tripped |
| ALIAS-03 | 07-01, 07-02, 07-03 | ✓ SATISFIED | immutable provenance (INSERT OR IGNORE) |
| ALIAS-04 | 07-03, 07-04 | ✓ SATISFIED | confirm records aliases; no-schema = no-op |

No orphaned requirements — all 8 Phase-07 IDs are claimed by plans and verified.

### Anti-Patterns Found

None. No TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER markers in any Phase-07 source or frontend file. No stub/empty-implementation patterns; every frontend control is wired to a real endpoint (Plan 04 "Known Stubs: None" confirmed).

### Human Verification Required

Deferred by Plan 04 as `human_verify_mode=end-of-phase` (non-blocking):

1. **Browser end-to-end crosswalk flow**
   - **Test:** Run the app (uvicorn + `npm run dev`), sign in as a verified user, promote the current field set to a Schema, select it, set a vendor, confirm a mapping, then Download the master-map and re-Import it.
   - **Expected:** The downloaded master-map JSON contains the recorded manual alias (vendor + provenance `manual`, actor = your email); the re-import reports augment success and discards nothing.
   - **Why human:** The `<a download>` GET and hidden file-picker JSON round-trip across an authenticated session are browser behaviors not observable by grep/unit tests. The server contract underneath (export envelope, augment-only import, alias recording, auth gate) is fully covered by passing automated tests.

### Gaps Summary

No gaps. All 8 success criteria are observably true in the codebase, each backed by a passing behavioral test (structural isolation, augment-never-discard, immutable provenance, server-resolved actor, and no-op-on-CLI are all directly asserted, not inferred from symbol presence). The P1 governance gate is enforced on the endpoints (401/403 tests), and the provenance actor is the server-resolved `user.email`, never a client field (attacker-body tests). Status is `human_needed` solely because of the single intentionally-deferred end-of-phase browser E2E check — the automated layer is complete and green.

---

_Verified: 2026-07-11T14:54:41Z_
_Verifier: Claude (gsd-verifier)_

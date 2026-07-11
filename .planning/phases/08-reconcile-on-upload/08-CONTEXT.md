# Phase 8: Reconcile-on-Upload - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous overnight build — decisions by the orchestrator per the locked spec, not interactive discuss.

<domain>
## Phase Boundary

Let an upload optionally carry a **map file** that augments the target Schema's crosswalk **before** Claude maps the file, so known vendor aliases are applied up front (columns a Schema already knows map deterministically at confidence 1.0 — no Claude guess needed for them). When the map file **disagrees with or is ambiguous against** the master Schema, the tool **asks the human to resolve** instead of silently picking a side. The reconciled mapping lands straight in the **existing yellow-flag review UI** under the **same server-side confirm gate**.

This reuses Phase 07's crosswalk (the master map JSON envelope, `import_master_map` augment logic, and the `SchemaStore`) and the existing Phase 04 upload two-step **question/resolve token registry** pattern (`api/state.py` `registry` + `StructuralQuestionResponse`/`/api/structural-hint/resolve`). It does NOT introduce a second mapping engine — the deterministic alias pre-fill is a new layer that seeds/short-circuits the existing `service.resolve_or_map`, then Claude fills only the remaining columns.

Requirements: RECON-01, RECON-02, RECON-03.

Out of scope (later / FUTURE): the visual Mapping Registry page + Docs (Phase 09); schema versioning / drift history; fuzzy alias matching (v1 alias match is exact on `(vendor, source_column)`, mirroring the exact-signature learning loop — MATCH-01 fuzzy is deferred to v2/FUTURE); auto-un-pivot of wide layouts (still detect-and-flag). The map file format IS Phase 07's master-map JSON envelope — no new file format.
</domain>

<binding_principles>
## Binding Principles (carry forward — still govern)

**P1 — Never guess silently; ask on ambiguity (Core Value).** A map-file-vs-master conflict is exactly the "ambiguous → offer options, never silently choose" case. The upload returns a **reconcile question** (the conflicts + options) via the existing token/registry two-step, never an auto-merged mapping. Only the human's resolution is applied.

**P2 — Server-side confirm gate is unchanged.** Reconcile only affects how the *proposal* is produced; the confirm/export gate (Phase 04, server-side, re-validates + `is_ready`) and the Phase 06 `require_verified_user` gate on `/api/confirm` still stand. A deterministically alias-mapped column is still a normal `FieldMapping` in the proposal — subject to the validator like any other.

**P3 — Augment-never-discard + provenance (from Phase 07).** Augmenting the crosswalk from a map file records aliases as `from_map_file` + the file's source name, never discarding existing aliases. Applying the map file to the master is the same `import_master_map` augment path — reused, not reimplemented.

**P4 — Privacy.** The `--headers-only` upload toggle still holds: reconcile works on column NAMES (aliases are name-level), so alias pre-fill is fully compatible with headers-only (it never needs cell values). Do not regress the headers-only path.
</binding_principles>

<decisions>
## Implementation Decisions (orchestrator's calls — planner may refine)

### D-08-01 — Map file = Phase 07 master-map JSON envelope
The optional uploaded map file is a Phase 07 master-map file (`{"schema_version":1,"name":...,"fields":[... with aliases ...]}`). No new format. It is attached to the `/api/upload` multipart form as an optional second file, alongside an optional target Schema name + vendor.

### D-08-02 — Reconcile pipeline: detect-conflicts → (ask | augment) → alias pre-fill → Claude fills rest
A new `service.reconcile_or_map` (or an extension of `resolve_or_map`) that, when a map file + target Schema are supplied:
1. **Detect conflicts** between the map file and the master Schema BEFORE mutating anything. A conflict = the map file asserts an alias `(vendor, source_column) → canonical field A` while the master already holds `(vendor, source_column) → canonical field B`, A≠B (alias-target disagreement). (Field-constraint differences may also be surfaced, but alias-target disagreement is the primary case.)
2. **If conflicts exist → return a reconcile question** (list of conflicts, each with options: keep master / take map file) via the token registry; DO NOT augment or map yet. A `/api/reconcile/resolve` endpoint applies the human's per-conflict choices, then continues.
3. **If no conflicts (or after resolution) → augment** the master Schema's crosswalk from the map file (reuse Phase 07 `import_master_map`, provenance `from_map_file`).
4. **Alias pre-fill:** for each source column in the uploaded table that EXACTLY matches a known alias `(vendor, source_column)` on the target Schema, deterministically pre-map it to that canonical field at confidence 1.0 (provenance = crosswalk), NOT sent to Claude as an open question.
5. **Claude fills the rest:** remaining unmapped canonical fields go through the existing mapper. Merge into ONE `MappingProposal` for the existing review UI.

### D-08-03 — Reuse the token/registry two-step, do not fork it
The reconcile question/resolve reuses `api/state.py`'s `registry` + `UploadEntry` and mirrors `StructuralQuestionResponse` / `/api/structural-hint/resolve` exactly (retain the uploaded table + map file + target schema/vendor under the token until resolved; clean up on resolve). A single upload can surface EITHER a structural question OR a reconcile question OR go straight to mapping — the discriminated response shape stays consistent (`kind="mapping" | "structural_question" | "reconcile_question"`).

### D-08-04 — Exact alias match only (v1), mirroring the exact-signature learning loop
Alias pre-fill matches `(vendor, source_column)` exactly (after the same normalisation the crosswalk stores). No fuzzy matching this milestone (MATCH-01 fuzzy is FUTURE). A column whose header doesn't exactly match a known alias simply falls through to Claude — safe, fail-open to the existing review flow.

### D-08-05 — Auth & gating
Reconcile/upload itself does not need to be a governed (signed-in) action to *propose* a mapping (reading is fine), but **augmenting the master crosswalk from a map file mutates governed state** — so applying the map file requires `require_verified_user`, consistent with Phase 07's import gate. Decision: the reconcile flow requires a signed-in verified user when a target Schema + map file are supplied (because it will augment the master); a plain upload with no map file/schema stays open as today. Provenance actor for any manual conflict-resolution choice = the server-resolved user.

### D-08-06 — Frontend: reconcile mirrors the inline structural-hint panel
Add an optional map-file attach control + target-schema/vendor selection to the upload flow, and a **ReconcilePanel** (inline, mirroring `StructuralHintPanel`) that renders the conflict list with keep-master/take-map-file choices and re-submits to `/api/reconcile/resolve`. On no-conflict, the flow proceeds silently to Review with alias-prefilled (green) rows visibly already-resolved. Keep the shadcn/`data-theme` aesthetic; do NOT build the Registry table (Phase 09).

### Claude's Discretion (planner decides)
- Exact conflict-detection breadth (alias-target only vs also field-constraint differences) — alias-target disagreement is the MUST; constraint diffs optional.
- Whether `reconcile_or_map` is a new service fn or a branch inside `resolve_or_map`; how the deterministic pre-fill merges with the Claude proposal (seed vs post-merge).
- Exact multipart form fields and the reconcile wire models (`ReconcileQuestionResponse`, `ReconcileResolveRequest`); reuse `MappingResponse` for the terminal state.
- Whether alias pre-fill also short-circuits the Claude call entirely when ALL fields are covered by known aliases (a nice "second file from a known vendor = zero Claude, zero yellow" money-shot — encouraged if cheap).
- Frontend placement of the map-file attach + reconcile panel.
</decisions>

<canonical_refs>
## Canonical References — downstream agents MUST read before planning/implementing

### Reuse / extend (do NOT fork)
- `src/assayingest/api/routes/upload.py` — the `/api/upload` route + `_resolve_field_set` + bounded temp file + the StructureQuestion branch to extend with a reconcile branch.
- `src/assayingest/api/routes/structural_hint.py` — the question/resolve two-step to mirror for `/api/reconcile/resolve`.
- `src/assayingest/api/state.py` — the token `registry` + `UploadEntry` (extend to retain map file + target schema/vendor).
- `src/assayingest/service.py` — `resolve_or_map` (the mapping entry to seed/branch), `confirm` (gate unchanged), and Phase 07's `import_master_map` / `promote` (reused for the augment step).
- `src/assayingest/domain/models.py` — `Schema`/`Alias`/`CanonicalField` + `from_master_map` (parse the uploaded map file), `MappingProposal`/`FieldMapping` (the proposal the alias pre-fill contributes to).
- `src/assayingest/learning/schema_store.py` + `sqlite_schema_store.py` — crosswalk read (known aliases for the alias pre-fill) + augment.
- `src/assayingest/api/deps.py` — `get_schema_store`, `require_verified_user` (Phase 07/06 gate to apply on the augmenting path).
- `src/assayingest/api/wire.py` — `MappingResponse`, `StructuralQuestionResponse`, `ConfirmRequest` (schema_name/vendor already added) — add the reconcile wire models here.

### Frontend
- `frontend/src/components/StructuralHintPanel.tsx` — the inline panel pattern the `ReconcilePanel` mirrors.
- `frontend/src/components/UploadDropzone.tsx`, `screens/Upload.tsx`, `state/upload.ts`, `lib/api.ts`, `lib/types.ts`, `components/SchemaControls.tsx` (Phase 07 selector) — where the map-file attach + reconcile flow thread in.
</canonical_refs>

<success_criteria>
## Success Criteria (from ROADMAP — what must be TRUE)

1. **RECON-01** — On upload a user can optionally attach a map file alongside the Excel/CSV, and its aliases augment the target Schema's crosswalk before Claude maps the file.
2. **RECON-02** — When the uploaded map file conflicts with or is ambiguous against the master Schema, the tool asks the user to resolve rather than silently choosing.
3. **RECON-03** — The reconciled mapping is shown immediately in the existing review UI for edit/approve, reusing the yellow-flag review and the server-side confirm gate.
</success_criteria>

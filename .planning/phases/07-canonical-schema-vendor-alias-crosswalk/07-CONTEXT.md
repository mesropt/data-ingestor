# Phase 7: Canonical Schema + Vendor-Alias Crosswalk - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous overnight build — decisions by the orchestrator per the locked spec (memory `canonical-master-milestone.md`), not interactive discuss.

<domain>
## Phase Boundary

The backbone of v2.0: turn a disposable field set into a **governed canonical model per domain (a "Schema")** whose canonical fields each carry **vendor aliases with provenance**, and make that crosswalk **downloadable/importable as a JSON master map file**. Confirming a reviewed mapping (the existing Phase 4 confirm path, now signed-in per Phase 6) **records the resolved source columns as aliases** into the Schema's crosswalk.

This phase EXTENDS the existing v1.0 machinery — it does NOT duplicate it:
- The **profile store** (`learning/`, keyed by `(field_set_signature, column_signature)`) stays exactly as-is for local auto-apply. The Schema/crosswalk is a NEW, separate governed store behind its own repository seam — it is the *human-curated master*, not the *learned-mapping cache*.
- The **`Field`/`FieldSet`** models (`fields/models.py`) are REUSED as the canonical-field shape; a Schema's canonical fields ARE `Field`s plus governance metadata.
- The **`service.confirm`** path (already threads `confirmed_by` from Phase 6) is EXTENDED additively to upsert aliases; the CLI call site (no user, no schema) keeps recording nothing.

Locked terminology (do not rename): **Schema** (one canonical model per domain; its JSON export is the master map file) · **Field** (a canonical field in a Schema) · **Alias** (a vendor's name for a field, with provenance).

Requirements: SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03, ALIAS-04.

Out of scope (later phases / FUTURE): the visual **Mapping Registry page** and Documentation page (Phase 09 — this phase ships only the minimal promote/export/import UI controls + a schema selector); **reconcile-on-upload** with a map file that augments the master and prompts on conflict (Phase 08 — RECON); schema **versioning**, **org multi-tenancy**, and **roles** (FUTURE). SCHEMA-03 import is augment-only here; the interactive conflict-resolution UX is Phase 08's job.
</domain>

<binding_principles>
## Binding Principles (carry forward — still govern)

**P1 — Server-side governance gate.** Creating or editing a Schema (promote, import, and any crosswalk mutation) requires a signed-in, **verified** user via Phase 6's `require_verified_user` dependency, enforced on the endpoint. A manual alias's provenance actor is the server-resolved `user.email`, never a client-supplied field (mirrors AUTH-04's `confirmed_by` handling).

**P2 — Local-first, repository seam.** The Schema/crosswalk persists in the **same local SQLite DB** the profile + field-set + user stores use, behind a NEW `SchemaStore` ABC + `SqliteSchemaStore` impl + `deps.get_schema_store()` DI factory — mirroring `ProfileStore`/`FieldSetTemplateStore`/`UserStore` exactly. Tests override it with a tmp-path store. Domain models are pure frozen dataclasses; wire models stay at the API edge; infrastructure rows map to domain at the boundary.

**P3 — Augment, never silently discard (data lineage).** Import (SCHEMA-03) and confirm-records-aliases (ALIAS-04) are **additive**: they add canonical fields and aliases that are missing and never delete an existing field or alias. Every alias carries immutable provenance (`manual` + which user, or `from map file` + which file) and a timestamp — this is the audit trail; do not overwrite provenance on re-observation (keep first-seen, or record occurrences, but never lose who/when).
</binding_principles>

<decisions>
## Implementation Decisions (orchestrator's calls — planner may refine within these)

### D-07-01 — Schema & Alias domain model (reuse Field)
- `Alias` (frozen dataclass): `vendor: str`, `source_column: str` (the vendor's raw column name), `provenance_kind: Literal["manual","from_map_file"]`, `provenance_actor: str` (user email for manual, file/source name for map-file), `created_at: str` (ISO). Optional: `confidence`/note if cheap.
- `CanonicalField` = the existing `Field` (name + constraints) PLUS its `aliases: tuple[Alias, ...]`. Prefer composing (`Field` + a parallel alias list keyed by field name) over subclassing, to keep `Field` untouched and reusable.
- `Schema` (frozen dataclass): `name: str` (the domain identity — unique per owner), `fields: tuple[Field, ...]`, the per-field alias lists, `created_by: str | None`, `created_at: str`, and an `id`. Provide `to_master_map()` / `from_master_map()` JSON round-trip (this JSON IS the downloadable master map file, SCHEMA-02/03).

### D-07-02 — SchemaStore behind a new DI seam (extends, not duplicates)
New `SchemaStore` ABC + `SqliteSchemaStore` on the same DB file (import the existing `_DEFAULT_DB_PATH`); `deps.get_schema_store()` overridable in tests. Tables: `schema(id, name, created_by, created_at)`, `canonical_field(id, schema_id, name, description, type, allowed_values_json, unit, required, min, max, date_format)`, `alias(id, canonical_field_id, vendor, source_column, provenance_kind, provenance_actor, created_at)`. Methods at least: `create_schema`, `get_schema(name|id)`, `list_schemas`, `add_or_update_fields` (augment), `add_alias` (idempotent upsert by `(canonical_field, vendor, source_column)` — never duplicates, never loses provenance), `list_aliases_for(schema)`.

### D-07-03 — Promote a field set → Schema (SCHEMA-01, SCHEMA-04)
A `promote` service + `POST /api/schemas` (gated) that takes a named field set (or explicit fields) and creates a governed Schema whose canonical fields are those fields, `created_by = user.email`. Schema name is the domain identity and is unique per owner; two Schemas (e.g. `assay-potency`, `reagent-inventory`) never share canonical fields or aliases (SCHEMA-04 — enforced structurally by the `schema_id` foreign key, and covered by an isolation test).

### D-07-04 — Master map file JSON export/import (SCHEMA-02, SCHEMA-03)
- Export: `GET /api/schemas/{name}/master-map` returns the Schema's `to_master_map()` JSON (canonical fields + their aliases + provenance) as a downloadable file.
- Import: `POST /api/schemas/{name}/master-map` (gated) parses a master map file and **augments** the target Schema: add missing canonical fields, union in missing aliases (provenance recorded as `from_map_file` + the file's declared/derived source name), NEVER discard. On a benign field-constraint difference, keep the existing definition (do not overwrite); genuine interactive conflict resolution is deferred to Phase 08 (RECON-02) — here, augment-only with a recorded note is acceptable.

### D-07-05 — Confirm records aliases (ALIAS-01..04) — additive extension of service.confirm
Extend `service.confirm` (and the `/api/confirm` route) with an optional target Schema + vendor: after the existing gate passes and the mapping is confirmed, upsert each resolved `(canonical field ← source column)` as an `Alias` on that Schema's matching canonical field, with `provenance_kind="manual"`, `provenance_actor=confirmed_by` (the authenticated email from Phase 6), and `vendor` from the request. Purely additive: when no Schema/vendor is supplied (e.g. the CLI path), nothing is written — existing confirm tests stay green. This is what makes the crosswalk *accrete* from real review work.

### D-07-06 — Vendor is a free-text label (no vendor registry in v2.0)
`vendor` is a string the user supplies at confirm/upload time (the lab/source name) or that the map file declares at import time. Default at confirm: the uploaded file's stem or an explicit field. No separate vendor entity/registry this milestone.

### D-07-07 — Minimal UI for this phase (rich Registry is Phase 09)
Frontend adds only: a **"Promote to Schema"** control (from the field-set toolbar / after a confirmed mapping), a **Schema selector**, and **Download master map / Import master map** buttons — plus threading an optional **vendor** field into the confirm call so aliases get recorded. The full visual crosswalk table (canonical left, vendor aliases + provenance right) and the Docs page are Phase 09. Keep these controls consistent with the shipped shadcn/`data-theme` dark aesthetic; do not build the registry table here.

### Claude's Discretion (planner decides)
- Exact table columns/indexes and whether alias provenance stores occurrences vs first-seen (must never LOSE who/when).
- Whether `CanonicalField` is a composed pair or a thin wrapper; exact `to_master_map` JSON schema (versioned envelope recommended: `{"schema_version": 1, "name": ..., "fields": [...]}`).
- Route module layout (`api/routes/schemas.py`) and wire-model shapes; whether export streams a file download vs JSON body the client saves.
- How the confirm route surfaces the optional schema/vendor (extend `ConfirmRequest` additively).
- Frontend placement of the promote/selector/import controls and the vendor input.
</decisions>

<canonical_refs>
## Canonical References — downstream agents MUST read before planning/implementing

### Reuse / extend (do NOT duplicate or fork)
- `src/assayingest/fields/models.py` — `Field` / `FieldSet` (`signature`, `to_dict`); canonical fields ARE `Field`s. `fields/loader.py` for YAML round-trip idiom.
- `src/assayingest/learning/store.py` + `sqlite_store.py` + `sqlite_field_set_store.py` — the ABC + SQLite impl + `_DEFAULT_DB_PATH` pattern the new `SchemaStore` mirrors exactly (same DB file, same connection idiom).
- `src/assayingest/auth/*` + `api/deps.py` (`require_verified_user`, `get_user_store`, DI factory idiom) — Phase 6 gate to apply to Schema mutations; `get_schema_store()` is added here in the same style.
- `src/assayingest/service.py` — `confirm()` (already threads `confirmed_by`); ALIAS-04 extends it additively. `export/writers.py::build_manifest` for the manifest shape.
- `src/assayingest/api/routes/confirm.py` + `api/wire.py` — the confirm route + wire boundary to extend with the optional schema/vendor.
- `src/assayingest/domain/models.py` — where `Schema`/`Alias`/`CanonicalField` domain dataclasses belong (frozen).

### Frontend
- `frontend/src/components/FieldSetToolbar.tsx`, `FieldSetPicker.tsx`, `ExportBar.tsx`, `screens/Review.tsx`, `state/fieldSet.ts`, `lib/api.ts`, `lib/types.ts` — where the promote/selector/import/vendor controls thread in (auth-gated via Phase 6's `state/auth.ts`).
</canonical_refs>

<success_criteria>
## Success Criteria (from ROADMAP — what must be TRUE)

1. **SCHEMA-01** — A user can promote a field set into a named, governed canonical Schema (one per domain) whose fields are the canonical fields.
2. **SCHEMA-02** — A user can download a Schema's canonical model as a JSON master map file.
3. **SCHEMA-03** — A user can import a master map file to augment an existing Schema (add canonical fields and aliases without discarding existing ones).
4. **SCHEMA-04** — Multiple named Schemas coexist and stay isolated (assay and reagent-inventory never share canonical fields or aliases).
5. **ALIAS-01** — Each canonical field carries a list of vendor aliases.
6. **ALIAS-02** — Every alias records which vendor it came from.
7. **ALIAS-03** — Every alias records provenance: `manual` (which user) vs `from map file` (which source) + a timestamp.
8. **ALIAS-04** — Confirming a reviewed mapping records each resolved source column as an alias on the matching canonical field, with provenance, into the Schema's crosswalk.
</success_criteria>

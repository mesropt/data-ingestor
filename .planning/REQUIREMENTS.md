# Requirements — Milestone v2.0: Canonical Schemas, Crosswalk & Governance

> Scoped requirements for milestone v2.0. v1.0 requirements shipped across Phases 01–05 and are recorded in PROJECT.md → Validated (full v1.0 requirements archived at `.planning/archive/v1.0/REQUIREMENTS-v1.0.md`). Phase numbering continues from Phase 05 (v2.0 starts at Phase 06).

**Milestone goal:** Evolve from disposable per-file field sets to a governed **canonical data model + vendor-alias crosswalk** per domain, with authenticated attribution — so every mapping decision accretes into a reusable, auditable master map that new files reconcile against.

**Locked terminology:** Schema = one canonical model per domain (its JSON export is the master map file) · Field = a canonical field in a schema · Alias = a vendor's name for a field, with provenance · Organization = owner of a set of schemas (FUTURE).

---

## v2.0 Requirements

### Auth & attribution (AUTH)

- [x] **AUTH-01**: A user can create an account and sign in; creating/editing a Schema or confirming a mapping requires being signed in.
- [x] **AUTH-02**: A user can sign in with Google OAuth (implemented behind a feature flag; dev build uses placeholder credentials and keeps OAuth off by default).
- [x] **AUTH-03**: A user can verify their email address; in the dev build the verification link is printed to the server console instead of emailed.
- [x] **AUTH-04**: Every manual mapping edit or confirmation is attributed to the signed-in user (their identity is recorded for alias provenance).

### Canonical schema (SCHEMA)

- [x] **SCHEMA-01**: A user can promote a field set into a named, governed canonical Schema (one Schema per domain) whose fields are the canonical fields.
- [x] **SCHEMA-02**: A user can download a Schema's canonical model as a JSON master map file.
- [x] **SCHEMA-03**: A user can import a master map file to augment an existing Schema (add canonical fields and aliases without discarding existing ones).
- [x] **SCHEMA-04**: Multiple named Schemas coexist and stay isolated from each other (e.g. assay and reagent-inventory never share canonical fields or aliases).

### Vendor-alias crosswalk (ALIAS)

- [x] **ALIAS-01**: Each canonical field in a Schema carries a list of vendor aliases (the vendor column names that map to it).
- [x] **ALIAS-02**: Every alias records which vendor it came from.
- [x] **ALIAS-03**: Every alias records its provenance — `manual` (with the user who set it) vs `from map file` (with the file/source name) — plus a timestamp.
- [x] **ALIAS-04**: Confirming a reviewed mapping records each resolved source column as an alias on the matching canonical field, with provenance, into the Schema's crosswalk.

### Reconcile-on-upload (RECON)

- [x] **RECON-01**: On upload, a user can optionally attach a map file alongside the Excel/CSV; the map file augments the target Schema's crosswalk before Claude maps the file.
- [x] **RECON-02**: When the uploaded map file conflicts with or is ambiguous against the master Schema, the tool asks the user to resolve the conflict rather than silently choosing.
- [x] **RECON-03**: The reconciled mapping is shown immediately in the review UI for edit/approve (reuses the existing yellow-flag review + confirm gate).

### Registry & documentation (REG / DOCS)

- [x] **REG-01**: A user can open a Mapping Registry page showing a table: canonical fields on the left, each vendor's name(s) for that field on the right.
- [x] **REG-02**: The Mapping Registry shows each alias's provenance (how it was mapped, by whom/what, and when).
- [x] **DOCS-01**: A user can open an in-app Documentation page with a how-to and a glossary of the locked terms (Schema / Field / Alias / Organization).

### Frictionless & correct ingest (INGEST)

- [ ] **INGEST-01**: The Upload screen asks for exactly three things: the target **Schema**, an optional map file (merged into the master map), and the headers-only toggle. Nothing else. The target fields are the selected Schema's canonical fields — the field-set picker is removed from the UI entirely, and "field set" survives only as an internal code concept.
- [ ] **INGEST-02**: Mapping resolves in a fixed escalation order — deterministic Python first (match the file's headers against the Schema's crosswalk aliases), then Claude for whatever Python could not resolve, then the human for whatever Claude could not resolve confidently. The cheap deterministic pass always runs before an LLM call is spent.
- [ ] **INGEST-04**: Every mapped date is normalized to ISO 8601. The format is detected by pure server-side Python (no LLM, so `headers_only` is unaffected — it restricts what *Claude* sees, not what the server reads). An unambiguous format normalizes automatically; an ambiguous one (`03/04/2025` — DD/MM or MM/DD?) fails closed and asks the human once per column, applying that answer to every row. A declared `date_format` is a human claim, checked against the data, not blindly trusted (supersedes D-13's "declared = permission to convert"). Excel numeric date serials normalize like any other date.
- [ ] **INGEST-05**: The Define Fields and Registry pages are replaced by a single **Schemas** page. A verified user creates a Schema there, edits its canonical fields' constraints (`type`, `unit`, `allowed_values`, `required`, `min`, `max`, `date_format`), and edits the vendor aliases mapped to each field. This needs an explicit edit endpoint — the existing `POST /api/schemas/{name}/master-map` stays augment-only (D-07-04: a machine may only add; only a human may remove, and only explicitly).
- [ ] **INGEST-06**: The four shipped presets are seeded as Schemas at startup so a signed-in user has something to select immediately. Use of the tool requires sign-in — there is no anonymous upload path.

### Multi-sheet ingest (SHEET)

- [x] **SHEET-01**: On a multi-sheet workbook, **the human chooses** which sheets to ingest. The tool presents every sheet with what it knows about each — row count, column signature, and the best-matching Schema with its coverage — and the human selects. Selecting N sheets yields **N independent datasets**, each with its own Schema, its own confirm gate, and its own export; the tool **never merges** (SHEET-02 struck). Today exactly one sheet is chosen automatically and every other sheet is silently discarded (`parsing/table.py::_resolve_sheet`) — correct for a data sheet plus a legend, wrong for one-plate-per-sheet or one-timepoint-per-sheet workbooks. Picking a single sheet stays a first-class choice, not a fallback.
- ~~**SHEET-02**~~: **STRUCK 2026-07-13** — merging sheets into one dataset. Ruled out of the product by the builder ("Без мёрджа. Его не должно быть вообще."), not merely out of this phase. Selecting several sheets produces several *independent* datasets (SHEET-01), never a combined one. See Out of Scope.
- [ ] **SHEET-03**: Every ingested row records **which sheet it came from**, so a reviewer can trace any value back to its source sheet, and so a bad sheet can be identified after the fact rather than being anonymous. Written on **every** ingest, single-sheet included — a traceability column that only sometimes exists is not a traceability column.
- [ ] **SHEET-04**: Each selected sheet passes the existing structural gates **independently** — header row, table shape, decimal locale, and (from Phase 10) date order. A sheet that fails a gate is surfaced with its own question, never dropped. (The original cross-sheet clause — "where two sheets resolve the same column differently, surface the disagreement" — is **moot** now that SHEET-02 is struck: each sheet is its own dataset and resolves its own columns for itself.)
- [ ] **SHEET-05**: The tool **proposes which Schema fits each sheet** — the human never has to know that in advance. Today the Schema is picked from a dropdown *before* upload, blind: the file has not been parsed and no header has been seen (`SchemaPicker.tsx`; `api/routes/upload.py::_resolve_field_set` requires `schema_name`), so the human guesses the Schema while the tool guesses the sheet. This inverts that order — parse first, propose per sheet second, human confirms third. For each sheet the tool scores every governed Schema against that sheet's column signature in **pure Python, no LLM** (exact learned-profile hit first via `learning/signature.py::column_signature` + `store.find`, then crosswalk alias coverage via `service.py::_vendor_agnostic_alias_index` / `_prefill_coverage`) and shows the coverage it found (e.g. "6/7 canonical fields matched"). The proposal is pre-filled but always overridable — the tool proposes, the human disposes. Different sheets may legitimately resolve to **different** Schemas. A sheet with zero coverage is proposed as *skip*, never force-mapped; on a tie or a weak match the tool refuses to auto-apply and asks.

---

## Future Requirements (deferred beyond v2.0)

- **INGEST-03 (deferred 2026-07-12)**: Split a merged key/value column across two target fields (header `Age / Sex`, cell `65 / M`). Claude would *propose* the split with confidence and the human confirm it — never automatic, since `/` is not always a separator (`N/A`, `mg/mL`, `Ratio A/B`). Deferred out of Phase 10 by the builder: it changes the mapping logic itself, and Phase 10 deliberately does not touch that.
- **ORG-\***: Organizations / multi-tenancy — isolated org space per customer, users scoped to an org, per-org schema sets. (Multiple *named* schemas are in scope now; org-level isolation is not.)
- **VER-\***: Schema versioning to track vendor format drift over time.
- **ROLE-\***: Governance roles — who is permitted to change a master Schema.
- Real email delivery provider (dev build prints the verification link to console).
- Real Google OAuth credentials wired to a live client (dev build ships placeholders behind a flag; the user provisions these).

## Out of Scope (explicit exclusions)

- **Any hardcoded field list, domain, or controlled vocabulary** — unchanged from v1.0; all domain knowledge stays in user-defined Schemas.
- **Confidence-threshold auto-approve without a human step** — still an anti-feature; the confirm gate remains.
- **Writing to any production/external system** — the tool only proposes and exports a reviewed draft plus its master map file.
- **Automatic un-pivot of wide/transposed layouts** — still detect-and-flag / ask-the-human only (deferred from v1.0).
- **Mock/reuse of any employer platform or real confidential data** — synthetic demo data only.
- **Merging several sheets into one dataset** (was SHEET-02, struck 2026-07-13) — the tool never combines sheets. Selecting N sheets yields N independent datasets, each with its own Schema, its own confirm gate, and its own export. A merge would produce a dataset belonging to no governed Schema, which the validator, the export path, and the learning store all key on.

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 06 | Complete |
| AUTH-02 | Phase 06 | Complete |
| AUTH-03 | Phase 06 | Complete |
| AUTH-04 | Phase 06 | Complete |
| SCHEMA-01 | Phase 07 | Complete |
| SCHEMA-02 | Phase 07 | Complete |
| SCHEMA-03 | Phase 07 | Complete |
| SCHEMA-04 | Phase 07 | Complete |
| ALIAS-01 | Phase 07 | Complete |
| ALIAS-02 | Phase 07 | Complete |
| ALIAS-03 | Phase 07 | Complete |
| ALIAS-04 | Phase 07 | Complete |
| RECON-01 | Phase 08 | Complete |
| RECON-02 | Phase 08 | Complete |
| RECON-03 | Phase 08 | Complete |
| REG-01 | Phase 09 | Complete |
| REG-02 | Phase 09 | Complete |
| DOCS-01 | Phase 09 | Complete |
| INGEST-01 | Phase 10 | Not started |
| INGEST-02 | Phase 10 | Not started |
| INGEST-04 | Phase 10 | Not started |
| INGEST-05 | Phase 10 | Not started |
| INGEST-06 | Phase 10 | Not started |
| SHEET-01 | Phase 11 | Not started |
| SHEET-02 | — | Struck (Out of Scope) |
| SHEET-03 | Phase 11 | Not started |
| SHEET-04 | Phase 11 | Not started |
| SHEET-05 | Phase 11 | Not started |

*Coverage: 27/27 requirements mapped, each to exactly one phase (18 v2.0 + 5 INGEST + 4 SHEET). INGEST-03 (column split) was deferred out of Phase 10 — see Future Requirements. SHEET-02 (merge) was struck from the product on 2026-07-13 — see Out of Scope.*

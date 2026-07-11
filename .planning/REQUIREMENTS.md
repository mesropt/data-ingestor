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

- [ ] **REG-01**: A user can open a Mapping Registry page showing a table: canonical fields on the left, each vendor's name(s) for that field on the right.
- [ ] **REG-02**: The Mapping Registry shows each alias's provenance (how it was mapped, by whom/what, and when).
- [ ] **DOCS-01**: A user can open an in-app Documentation page with a how-to and a glossary of the locked terms (Schema / Field / Alias / Organization).

---

## Future Requirements (deferred beyond v2.0)

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
| REG-01 | Phase 09 | Pending |
| REG-02 | Phase 09 | Pending |
| DOCS-01 | Phase 09 | Pending |

*Coverage: 18/18 v2.0 requirements mapped, each to exactly one phase.*

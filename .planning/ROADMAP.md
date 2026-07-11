# Roadmap: Data Ingestor (domain-independent)

## Overview

The project pivoted from a fixed 7-field assay schema to a **domain-independent** tool: the user defines the target fields at runtime (in the UI or via a saved template), and Claude's structured-output schema is built dynamically from that field set — nothing about fields, domains, or vocabularies is hardcoded anywhere in the tool. Day 1 (parser, Claude structured-output mapper, CLI review gate) is already committed on `feat/assayingest-core` and is reused, not re-phased, but its fixed-schema and reference-dictionary assumptions are generalized below. This roadmap covers the remaining scope before the 2026-07-13 21:00 ET deadline, in dependency order: first, hardening the parser to handle diverse file structures *by structure* — and, when structure is genuinely unfamiliar, asking the human for a hint instead of crashing or guessing; then generalizing fields and the mapper so the user defines what to extract and Claude's schema is built from that at runtime, with an optional preset library shipped as editable data; then a no-LLM validator that checks each field against the *user's own declared constraints* (not a built-in vocabulary) plus a SQLite-backed learning loop keyed by (field set + column signature) that survives a vendor's format drifting over time and remembers structural hints — provable end-to-end from the CLI alone before any UI exists; then a FastAPI backend and React review screen that mirror that same loop, letting a user define fields, upload, resolve a structural hint inline, review, and confirm in the browser; and finally the multi-domain synthetic demo data, rehearsed video, and README needed to submit and prove the tool is genuinely universal. Each phase only depends on layers already built, so from Phase 3 onward a CLI-provable demo of the full learning loop remains a legitimate fallback if UI time runs short.

## Milestone v2.0 — Canonical Schemas, Crosswalk & Governance

v1.0 (Phases 01–05) shipped a disposable per-file learning loop: a confirmed mapping is saved as a profile keyed by (field set + column signature), and a same-signature repeat file auto-maps. **v2.0 evolves that store into a governed canonical data model + vendor-alias crosswalk per domain, with authenticated attribution** — so every mapping decision accretes into a reusable, auditable master map that new files reconcile against, rather than a set of opaque per-signature profiles. Numbering continues from Phase 05; v2.0 runs Phase 06 → 09 in dependency order. **Auth comes first** because attributing a manual mapping to a named person is the governance backbone the crosswalk's provenance depends on (a manual alias must record *which user* set it). The **canonical Schema + crosswalk domain model and its persistence** is the backbone the rest builds on — and it *extends* v1.0's existing SQLite learning store and confirm/export path (confirming a mapping already saves a profile; ALIAS-04 makes that same confirm path also record aliases with provenance) rather than introducing a parallel store. **Reconcile-on-upload** then lets an optional map file augment the master before mapping, resolving conflicts through the human. Finally the **Mapping Registry** and **Documentation** pages — pure frontend on top of the finished backbone — surface the crosswalk and its governed vocabulary. Auth uses a dev fallback: email verification prints its link to the server console and Google OAuth ships behind a feature flag with placeholder credentials (off by default); wiring live providers is the user's to do later and is out of scope for success criteria. The existing stack (FastAPI, Vite+React with shadcn + dark data-theme, Anthropic dynamic mapper, pandas/openpyxl, SQLite learning store, pytest) is reused throughout under the same Clean Architecture conventions (wire↔domain boundary, single level of abstraction, log-or-raise).

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### Milestone v1.0 (shipped)

- [x] **Phase 1: Robust File Reading** - The parser handles diverse file structures by structure — header position, delimiter, decimal locale, sheet selection, table shape — never by hardcoded per-vendor rules; when structure is genuinely unfamiliar it asks the human for a hint instead of crashing or guessing (completed 2026-07-10)
- [x] **Phase 2: User-Defined Fields + Dynamic Mapper** - The user defines the target fields (and optional constraints) at runtime, reusable as templates or optional presets; Claude's structured-output schema is built dynamically from that field set — zero hardcoded domain knowledge in the mapper (completed 2026-07-10)
- [x] **Phase 3: Validator + Learning Loop** - Each mapped field is checked in pure Python against the constraints the user declared for it, and a fully-clear confirmed mapping is saved as a profile keyed by field set + column signature so repeat files auto-map — safely across vendor format drift, remembering structural hints too (completed 2026-07-10)
- [x] **Phase 4: API & Review UI** - The full define-fields → upload → resolve-hint → review → confirm → learn cycle works in the browser, with the export gate re-enforced server-side (completed 2026-07-11)
- [ ] **Phase 5: Demo Assets & Submission** - Multi-domain synthetic files, a rehearsed ≤3-minute video, README, and submission summary prove the tool is universal and are ready to submit

### Milestone v2.0 — Canonical Schemas, Crosswalk & Governance

- [x] **Phase 06: Auth & Attribution** - A signed-in named user is required before any governed action (create/edit a Schema, confirm a mapping), with an overnight-friendly dev fallback (console-printed email verification, Google OAuth flagged off), and every manual mapping decision is attributed to that person for alias provenance (completed 2026-07-11)
- [x] **Phase 07: Canonical Schema + Vendor-Alias Crosswalk** - A field set graduates into a named, governed Schema (one per domain) whose canonical fields carry a provenance-stamped vendor-alias crosswalk; the Schema exports/imports as a JSON master map file, and confirming a mapping extends the existing store to also record aliases (completed 2026-07-11)
- [x] **Phase 08: Reconcile-on-Upload** - An upload can carry an optional map file that augments the target Schema's crosswalk before Claude maps; master↔map-file conflicts are surfaced to the human, and the reconciled mapping is shown in the existing yellow-flag review gate (completed 2026-07-11)
- [ ] **Phase 09: Mapping Registry & Documentation** - A Registry page shows the whole crosswalk (canonical fields left, per-vendor names + provenance right) and an in-app Documentation page explains the how-to and the glossary of locked terms

## Phase Details

### Phase 1: Robust File Reading

**Goal**: The parser reads any messy Excel/CSV structurally — where the header row sits, what delimiter and decimal locale is used, which sheet holds the data, and whether the table shape is even supported — by detecting structure, not by hardcoding rules per vendor; when a file's structure is genuinely unfamiliar, the tool never crashes or emits garbage — it asks the human for a structural hint and proceeds.
**Mode:** mvp
**Depends on**: Nothing (first phase; hardens the already-validated Day 1 parser before fields, mapping, and validation depend on a structurally-clean table)
**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05, PARSE-06
**Success Criteria** (what must be TRUE):

  1. A file with several banner/title rows above the real table (e.g. a source-name banner, a report header) has its true header row detected structurally — not row 0 — regardless of how many rows precede it.
  2. A semicolon-delimited CSV, or one with leading comment lines, is sniffed and read as a proper multi-column table, not collapsed into one junk column.
  3. A locale-formatted number using comma as the decimal separator (e.g. `14,771`) is normalized to the correct value without a 1000x corruption, and a genuinely ambiguous number is flagged for confirmation rather than guessed.
  4. A multi-sheet workbook has its data sheet selected automatically, skipping legend/notes/metadata sheets; a shape that is not a simple row-per-record table (a wide matrix, a transposed layout, several tables on one sheet) is detected and flagged as unsupported rather than mapped to a silently-wrong structured result.
  5. An unfamiliar-structure file triggers a request for a human structural hint (which row is the header, which sheet/region holds the data) rather than a crash or garbage output; the tool proceeds using the hint for that run.

**Plans**: 5/5 plans complete
Plans:

- [x] 01-01-PLAN.md — CSV slice + structural-question contract (delimiter/comment sniff, decimal-locale annotation, StructuralHint/StructureQuestion, parse() entry, CLI ask-branch) — PARSE-02, PARSE-03, PARSE-06
- [x] 01-02-PLAN.md — Excel header-row detection (openpyxl normal-mode grid reader, width+type scoring) — PARSE-01
- [x] 01-03-PLAN.md — Sheet selection + drawings/chartsheet/image guards + drawing fixtures + defusedxml XXE hardening — PARSE-04, PARSE-06
- [x] 01-04-PLAN.md — Table-shape classification (wide_matrix/transposed → question, no RawTable) — PARSE-05
- [x] 01-05-PLAN.md — Claude structural-proposal layer (pre-fills the question, never auto-applies) completes the three-layer pipeline — PARSE-06

### Phase 2: User-Defined Fields + Dynamic Mapper

**Goal**: A user defines the target fields they want to extract — each with a name, optional description, and optional constraints (type, allowed values, expected unit) — reusable as named templates or loaded from shared files; Claude's structured-output schema is built at runtime from that field set, with zero fields, domains, or vocabularies hardcoded in the mapper; an optional starter library of example field-set presets ships as editable data, never compiled-in tool logic.
**Mode:** mvp
**Depends on**: Phase 1 (the mapper needs a structurally-clean, header-resolved table to map source columns from)
**Requirements**: FIELD-01, FIELD-02, FIELD-03, FIELD-04, FIELD-05, MAP-01, MAP-02, EXPORT-01
**Success Criteria** (what must be TRUE):

  1. A user can define a field set from nothing — each field with a name, an optional description, and optional constraints (type, allowed values, expected unit) — with no fields pre-loaded or hardcoded by the tool.
  2. A user can save a defined field set as a reusable named template, reload it later, and load a field set shared as a file, so fields need not be re-entered each time.
  3. A user defines a brand-new field set (e.g. a non-life-sciences one) and Claude maps a messy file to it correctly with no code change — proving the mapper's structured-output schema is built dynamically from the field set, not hardcoded.
  4. For an ambiguous field, Claude returns 2-3 ranked alternative source columns with a plain-English reason; a value with no matching column may be inferred but is always flagged for confirmation, never silently trusted.
  5. Loading one of the shipped starter presets (spanning multiple domains, e.g. life-sciences, PK, and a non-life-sciences set) works with zero code changes, confirming presets are editable data rather than compiled-in tool logic.
  6. Applying a proposed mapping produces a single canonical tidy result — one row per record, columns = the user's fields, values normalised (decimal-comma fixed, units as declared) — that every later export format derives from.

**Plans**: 3/3 plans complete
Plans:

- [x] 02-01-PLAN.md — Field-set model + safe YAML/JSON loader + runtime `create_model` schema + emptied domain sites + `--fields` CLI + exit code 5 (FIELD-01, FIELD-02, FIELD-03, FIELD-04, MAP-01, MAP-02)
- [x] 02-02-PLAN.md — Canonical tidy form: decimal-comma/date conversion, units recorded-never-converted, shown in the CLI (EXPORT-01)
- [x] 02-03-PLAN.md — Three-domain preset library (assay/PK/reagent) shipped in the wheel + European-thousands & Excel-native-date corpus fixtures (FIELD-05)

### Phase 3: Validator + Learning Loop

**Goal**: Each field Claude proposes — including every ranked alternative, not only the top pick — is checked in pure Python against the constraints the *user declared* for that field (no built-in vocabulary, zero LLM calls), and any objection forces the field back to needs-confirmation regardless of Claude's own reported confidence; a curator can confirm a fully-clear mapping and save it as a profile keyed by (field set, column signature) so a repeat file from the same source auto-maps at confidence 1.0 — safely across a vendor's format drifting over time, and remembering any structural hint given in Phase 1 so the odd layout parses automatically next time.
**Mode:** mvp
**Depends on**: Phase 2 (validation checks the constraints the user declared on their own fields, and learning saves/reuses a mapping Claude already proposed against that field set)
**Requirements**: VAL-01, VAL-02, VAL-03, LEARN-01, LEARN-02, LEARN-03, LEARN-04, LEARN-05, LEARN-06, EXPORT-02, EXPORT-03, EXPORT-04
**Success Criteria** (what must be TRUE):

  1. A field with a user-declared allowed-value set (or type/unit constraint) is flagged when a mapped value violates it, with no LLM call.
  2. A field the validator objects to is forced to needs-confirmation regardless of Claude's reported confidence, and every one of Claude's ranked alternatives for that field is checked, not only the top pick.
  3. A field with no declared constraints is never silently trusted — it still depends on Claude's confidence and the human-review gate, and the validator's objection (or lack of one) is shown alongside Claude's own reasoning.
  4. Two files whose headers differ only in order, case, or incidental whitespace produce the identical column signature; a curator can save a confirmed mapping as a profile keyed by (field set, signature) only when it is fully clear (zero yellow fields), and re-running on a matching-signature file for the same field set auto-applies the stored mapping at confidence 1.0 without a Claude call — while a signature mismatch, including one caused by a vendor's format changing over time, never auto-applies a stale profile and instead falls back to a fresh Claude proposal that can itself be learned as an additional profile.
  5. A structural hint the user gave for an unfamiliar file in Phase 1 is saved with its profile, so the same odd layout parses automatically next time without asking the user again.
  6. From the CLI a curator can export the confirmed data as CSV, Excel (`.xlsx`), and JSON — all derived from the one canonical form — and every export is accompanied by a JSON manifest recording the field set, column signature, field→source mapping, inferred/confirmed flags, and per-field confidence.

**Plans**: 3/3 plans complete
Plans:

- [x] 03-01-PLAN.md — Learning loop: column signature + profile model + repository seam + SQLite store + auto-apply reconstruction (column-resolution hazard) + money-shot CLI wiring (LEARN-01..06)
- [x] 03-02-PLAN.md — No-LLM validator: reuse canonical.flagged + allowed_values/min-max + validate alternatives, additive-only gate, validator_note, fail-closed strictness, runs on both paths (VAL-01, VAL-02, VAL-03)
- [x] 03-03-PLAN.md — Export CSV/xlsx/JSON + provenance manifest, is_ready export gate, and the `--headers-only` privacy branch (EXPORT-02, EXPORT-03, EXPORT-04)

### Phase 4: API & Review UI

**Goal**: A user can perform the full define-fields → upload → resolve-hint → review → confirm → learn cycle in the browser — the demo's centerpiece — with the server independently re-checking the "no yellow fields" gate rather than trusting the client.
**Mode:** mvp
**Depends on**: Phase 3 (the API wraps the field-definition, parsing, mapping, validation, and learning-store logic already built; it does not reimplement it)
**Requirements**: API-01, API-02, API-03, UI-01, UI-02, UI-03, UI-04, UI-05, UI-06
**Success Criteria** (what must be TRUE):

  1. A user can define/edit target fields and optional constraints in the browser and save/load field-set templates, matching the field-set contract the upload endpoint expects.
  2. A user can upload a CSV/Excel file with a chosen field set and see a side-by-side view — source columns on the left, the user's target fields on the right — matching the JSON the upload endpoint returns; if the tool is unsure about the file's structure, the user can give a structural hint inline instead of the upload failing.
  3. Uncertain (yellow) fields are visibly highlighted with Claude's reason and ranked alternatives; a user can resolve a yellow field by picking an alternative or accepting the proposal; the confirm/export control stays disabled while any field is yellow, and the confirm endpoint independently re-checks the same gate server-side before persisting, never trusting the client alone.
  4. A user can save a confirmed mapping as a profile from the UI, and uploading a second same-signature file (same field set) shows zero yellow fields, auto-mapped without another Claude call — the learning loop is visibly demonstrated end-to-end in the browser.

**Plans**: 6/6 plans complete
Plans:

- [x] 04-01-PLAN.md — Service seam: extract public service.py (behavior-preserving CLI refactor), typed exceptions, loader.from_dict, add fastapi/uvicorn/multipart (API-01/02/03)
- [x] 04-02-PLAN.md — FastAPI app + /api/upload + auto-apply spy + app.frontend() serving (API-01, API-03)
- [x] 04-03-PLAN.md — Server-side confirm gate + FieldSetTemplateStore + field-sets/structural-hint/export endpoints + money-shot API test (API-02, UI-01, UI-02)
- [x] 04-04-PLAN.md — Frontend scaffold + D-01 tokens/fonts + AppShell + Define Fields screen (UI-01)
- [x] 04-05-PLAN.md — Upload screen + inline structural-hint form + headers-only toggle (UI-02)
- [x] 04-06-PLAN.md — Review screen (amber/chips/Accept/dropdown/gate) + confirm/learn money-shot + Profiles (UI-03/04/05/06)

**UI hint**: yes

### Phase 5: Demo Assets & Submission

**Goal**: The repo and a recorded video credibly demonstrate the full define → propose → validate → confirm → learn loop to a judge in under 3 minutes, backed by multi-domain synthetic data that proves the tool has no built-in domain knowledge and exercises the real structural hazards it guards against.
**Mode:** mvp
**Depends on**: Phase 4 (records the working browser loop; Phase 3's CLI loop remains a legitimate fallback if UI recording isn't ready)
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Success Criteria** (what must be TRUE):

  1. The repo contains synthetic files spanning at least two different domains (e.g. an assay-style set and a PK-report-style set), including at least one same-source pair sharing an identical column signature, proving the tool is universal — it has no built-in knowledge of either domain.
  2. The synthetic corpus exercises the key hazards — unit ambiguity, ambiguous/serial dates, blank/duplicate headers, preamble rows, delimiter variance, multi-sheet selection, and an unfamiliar-structure file that needs a human hint.
  3. A rehearsed, ≤3-minute demo video shows: defining target fields → uploading a messy file → clean structured output (~5s); the learning loop (second same-source file, zero yellow); and a human structural hint resolving an unfamiliar file — back to back.
  4. The repo has a README and a 100-200 word submission summary ready to paste into the submission form.

**Plans**: TBD

---

### Phase 06: Auth & Attribution

**Goal**: Any governed action — creating or editing a Schema, or confirming a mapping — requires a signed-in, named user, so that a manual mapping decision can be attributed to a specific person for the crosswalk's provenance. The build stays runnable overnight without live provider secrets: email verification prints its link to the server console and Google OAuth ships behind a feature flag (off by default, placeholder credentials). Wiring live OAuth/email providers is the user's own follow-up and is out of scope here.
**Depends on**: Phase 4 (adds an auth/session layer and identity to the existing FastAPI app and React shell; the confirm endpoint it gates already exists) — first v2.0 phase because alias provenance (Phase 07 ALIAS-03) needs a named user to attribute manual mappings to.
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04
**Success Criteria** (what must be TRUE):

  1. A visitor can create an account and sign in; attempting to create/edit a Schema or confirm a mapping while signed out is blocked and prompts sign-in — the gate is enforced server-side on the endpoint, not only hidden in the UI. (AUTH-01)
  2. A user can request email verification and complete it by following the link the dev build prints to the server console — no live email provider is required. (AUTH-03)
  3. A "Sign in with Google" path exists behind a feature flag that is off by default with placeholder credentials, so the overnight build runs end-to-end without live OAuth secrets. (AUTH-02)
  4. When a signed-in user confirms a mapping or edits a field mapping, their identity is recorded and available to stamp onto alias provenance downstream. (AUTH-04)

**Plans**: 3 plans
Plans:

- [x] 06-01-PLAN.md — Auth substrate: deps (itsdangerous/pwdlib/authlib) + User domain model + SqliteUserStore (same local DB) + password/session/token seams + deps.py DI (get_user_store/get_current_user/require_user/require_verified_user) — AUTH-01, AUTH-03
- [x] 06-02-PLAN.md — Auth HTTP surface: signup (console verify link)/login/logout/verify/config routes + feature-flagged Google OAuth (501 off) + gate /api/confirm with require_verified_user + thread confirmed_by into the manifest — AUTH-01, AUTH-02, AUTH-03, AUTH-04
- [x] 06-03-PLAN.md — Frontend auth surface: auth store + credentials:'include' + Sign Up/Sign In/Verify views + conditional Google button + AppShell identity/Sign Out + ConfirmGate auth-gate mirror — AUTH-01, AUTH-02, AUTH-03

**UI hint**: yes

### Phase 07: Canonical Schema + Vendor-Alias Crosswalk

**Goal**: A disposable field set graduates into a named, governed **Schema** (one canonical model per domain) whose canonical **Fields** each carry a vendor-**Alias** crosswalk with full provenance. The Schema is the master map: it downloads as a JSON master map file and re-imports to augment an existing Schema without discarding what is there. This is the milestone's backbone and it **extends v1.0's existing SQLite learning store and confirm/export path** — confirming a mapping already saves a profile; here that same confirm path additionally records each resolved source column as an alias with provenance — rather than standing up a parallel store.
**Depends on**: Phase 06 (a manual alias records *which signed-in user* set it, so attribution must exist first) and the v1.0 learning store + confirm service it evolves.
**Requirements**: SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, ALIAS-01, ALIAS-02, ALIAS-03, ALIAS-04
**Success Criteria** (what must be TRUE):

  1. A signed-in user can promote a field set into a named canonical Schema (one per domain); multiple named Schemas coexist and stay isolated — e.g. an assay Schema and a reagent-inventory Schema never share canonical fields or aliases. (SCHEMA-01, SCHEMA-04)
  2. A user can download a Schema as a JSON master map file, and re-import a master map file to augment an existing Schema — adding canonical fields and aliases without discarding existing ones. (SCHEMA-02, SCHEMA-03)
  3. Each canonical field carries a list of vendor aliases, and every alias records which vendor it came from. (ALIAS-01, ALIAS-02)
  4. Every alias records its provenance — `manual` (with the signed-in user who set it) versus `from map file` (with the source/file name) — plus a timestamp. (ALIAS-03)
  5. Confirming a reviewed mapping records each resolved source column as an alias on the matching canonical field, with provenance, by extending the existing confirm/learning path — not a duplicate write. (ALIAS-04)

**Plans**: 4 plans
Plans:

- [x] 07-01-PLAN.md — Schema/Alias/CanonicalField domain models (versioned master-map round-trip) + SchemaStore ABC + SqliteSchemaStore on the shared DB (SCHEMA-04 isolation, ALIAS-01/02/03 storage, immutable provenance)
- [x] 07-02-PLAN.md — promote service + master-map export/import (augment-only) + gated /api/schemas routes + get_schema_store DI (SCHEMA-01/02/03/04)
- [x] 07-03-PLAN.md — additive service.confirm + /api/confirm record aliases with manual+user provenance and a vendor; CLI/no-schema path records nothing (ALIAS-04)
- [x] 07-04-PLAN.md — minimal frontend: promote-to-Schema control, schema selector, download/import master-map buttons, vendor input threaded into confirm (auth-gated) (SCHEMA-01/02/03, ALIAS-04)

**UI hint**: yes

### Phase 08: Reconcile-on-Upload

**Goal**: An upload can carry an optional map file that augments the target Schema's crosswalk *before* Claude maps the file, so known vendor aliases are applied up front. When the map file disagrees with or is ambiguous against the master Schema, the tool never silently picks a side — it asks the human to resolve — and the reconciled result lands straight in the existing yellow-flag review UI for edit/approve under the same confirm gate.
**Depends on**: Phase 07 (reconciliation augments and conflicts against the canonical Schema + crosswalk backbone) and Phase 04's upload + review UI it reuses.
**Requirements**: RECON-01, RECON-02, RECON-03
**Success Criteria** (what must be TRUE):

  1. On upload a user can optionally attach a map file alongside the Excel/CSV, and its aliases augment the target Schema's crosswalk before Claude maps the file. (RECON-01)
  2. When the uploaded map file conflicts with or is ambiguous against the master Schema, the tool asks the user to resolve the conflict rather than silently choosing. (RECON-02)
  3. The reconciled mapping is shown immediately in the existing review UI for edit/approve, reusing the yellow-flag review and the server-side confirm gate. (RECON-03)

**Plans**: 3 plans
Plans:

- [x] 08-01-PLAN.md — Reconcile core (service + domain): conflict detection, exact-alias pre-fill + mapper short-circuit, reconcile_or_map/apply_reconcile_resolution, headers_only-safe (RECON-01, RECON-02)
- [x] 08-02-PLAN.md — API wiring: /api/upload optional map-file branch + verified-user gate, /api/reconcile/resolve two-step, reconcile wire models + token registry retention (RECON-01, RECON-02, RECON-03)
- [x] 08-03-PLAN.md — Frontend: map-file attach + Schema/vendor selection, inline ReconcilePanel (mirrors StructuralHintPanel), Upload-screen threading into the existing review (RECON-01, RECON-02, RECON-03)

**UI hint**: yes

### Phase 09: Mapping Registry & Documentation

**Goal**: With the backbone in place, two frontend pages surface it: a **Mapping Registry** that renders the whole crosswalk (canonical fields on the left, each vendor's name(s) and provenance on the right — the Profiles tab descoped in v1.0, now realized), and an in-app **Documentation** page giving a how-to plus a glossary of the locked terms so a curator can learn the governed vocabulary without leaving the app.
**Depends on**: Phase 07 (renders the Schema + crosswalk and its provenance) and Phase 06 (provenance names the signed-in user); builds last, on top of the finished backend.
**Requirements**: REG-01, REG-02, DOCS-01
**Success Criteria** (what must be TRUE):

  1. A user can open a Mapping Registry page showing a table with canonical fields on the left and each vendor's name(s) for that field on the right. (REG-01)
  2. The Mapping Registry shows each alias's provenance — how it was mapped, by whom or from what source, and when. (REG-02)
  3. A user can open an in-app Documentation page with a how-to and a glossary of the locked terms Schema / Field / Alias / Organization. (DOCS-01)

**Plans**: 2 plans
Plans:

- [ ] 09-01-PLAN.md — Mapping Registry: getMasterMap wrapper + tested crosswalk/provenance data-shaping + Registry table/screen + tab wiring (REG-01, REG-02)
- [ ] 09-02-PLAN.md — Documentation page: static how-to + locked-term glossary + Docs tab wiring (DOCS-01)

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 06 → 07 → 08 → 09

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Robust File Reading | 5/5 | Complete   | 2026-07-10 |
| 2. User-Defined Fields + Dynamic Mapper | 3/3 | Complete    | 2026-07-10 |
| 3. Validator + Learning Loop | 3/3 | Complete    | 2026-07-10 |
| 4. API & Review UI | 6/6 | Complete    | 2026-07-11 |
| 5. Demo Assets & Submission | 0/TBD | Not started | - |
| 06. Auth & Attribution | 3/3 | Complete    | 2026-07-11 |
| 07. Canonical Schema + Vendor-Alias Crosswalk | 4/4 | Complete    | 2026-07-11 |
| 08. Reconcile-on-Upload | 3/3 | Complete    | 2026-07-11 |
| 09. Mapping Registry & Documentation | 0/2 | Not started | - |

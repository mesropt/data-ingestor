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
- [x] **Phase 09: Mapping Registry & Documentation** - A Registry page shows the whole crosswalk (canonical fields left, per-vendor names + provenance right) and an in-app Documentation page explains the how-to and the glossary of locked terms (completed 2026-07-11)
- [ ] **Phase 10: Frictionless & Correct Ingest** - Upload collapses to Schema + optional map file + headers-only; the field-set concept leaves the UI and Define Fields/Registry merge into one editable Schemas page; mapping escalates Python → Claude → human; every date lands as ISO 8601 with its ambiguity asked once per column, never guessed
- [x] **Phase 11: Multi-Sheet Ingest** - On a multi-sheet workbook the human chooses which sheets to ingest and which Schema applies to each, and the tool makes that choice informed rather than making it silently: it parses first, shows every sheet with its signature and the best-matching Schema with the coverage behind that proposal, never auto-applies, ingests each selected sheet as its own independent dataset (sheets are never merged), and records which sheet every ingested row came from
- [ ] **Phase 12: Claude Reads the Structure** - A sheet's shape is judged by Claude, not by Python heuristics that a real key-value workbook walks straight past, and a sheet that is not one-row-per-record is actually READ rather than refused: Claude judges the layout from a bounded evidence grid and the human confirms, then Python performs the extraction over every row — the model never touches a cell value

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

- [x] 09-01-PLAN.md — Mapping Registry: getMasterMap wrapper + tested crosswalk/provenance data-shaping + Registry table/screen + tab wiring (REG-01, REG-02)
- [x] 09-02-PLAN.md — Documentation page: static how-to + locked-term glossary + Docs tab wiring (DOCS-01)

### Phase 10: Frictionless & Correct Ingest

**Goal**: The tool collapses to what it actually is. A curator signs in, picks a **Schema**, optionally attaches a map file, optionally hides cell values, and uploads — that is the whole Upload screen. The Schema *is* the target, so nothing asks for a "field set" ever again; the two competing concepts (field-set template vs governed Schema) merge into one, and Define Fields and Registry merge into a single editable **Schemas** page. Underneath, mapping escalates honestly — deterministic Python first, Claude only for what Python cannot resolve, the human only for what Claude cannot resolve confidently — and every date lands as ISO 8601, its format detected in pure server-side Python and its ambiguity asked once per column rather than guessed.
**Depends on**: Phase 07 (`Schema`/`CanonicalField` already carry both the constraints and the vendor aliases this phase surfaces) and Phase 06 (sign-in is now required for all use).
**Requirements**: INGEST-01, INGEST-02, INGEST-04, INGEST-05, INGEST-06
**Success Criteria** (what must be TRUE):

  1. The Upload screen shows exactly three controls: Schema selector, optional map file, headers-only toggle. No field-set picker exists in the UI. (INGEST-01)
  2. Mapping escalates Python → Claude → human: deterministic alias matching against the Schema's crosswalk runs first, and an LLM call is spent only on the columns it could not resolve. (INGEST-02)
  3. Every mapped date is normalized to ISO 8601. The format is detected by pure server-side Python, so `headers_only` behaves identically. An unambiguous format converts on its own; an ambiguous one (`03/04/2025`) fails closed, asks once per column, and applies the answer to every row. A declared `date_format` is checked against the data, not blindly trusted. Excel date serials normalize like any other date. (INGEST-04)
  4. Define Fields and Registry are gone. One **Schemas** page creates a Schema and edits both its canonical fields' constraints and its vendor aliases, behind an explicit edit endpoint — while the map-file path stays augment-only (a machine may add; only a human may remove). (INGEST-05)
  5. The four shipped presets exist as Schemas on a fresh start, and there is no anonymous path — sign-in is required to use the tool. (INGEST-06)

**Plans**: 9 plans
Plans:

- [ ] 10-01-PLAN.md — Pure date-order ambiguity classifier + DateFormatConflict/Question domain types (wave 1)
- [ ] 10-02-PLAN.md — Soft-delete tombstones, partial unique indexes, and the SchemaStore edit methods (wave 1)
- [ ] 10-03-PLAN.md — Python→Claude escalation, always-run date resolution, Schema→FieldSet adapter (wave 2)
- [ ] 10-04-PLAN.md — Explicit governed-Schema edit endpoints + the four presets seeded as Schemas (wave 3)
- [ ] 10-05-PLAN.md — /api/upload targets a Schema; the date_question 4th arm + /api/date-format/resolve (wave 4)
- [ ] 10-06-PLAN.md — The editable Schemas page, the sign-in gate, and deleting Define Fields + Registry (wave 5)
- [ ] 10-07-PLAN.md — Upload's three controls, the inline date-order panel, and Review's escalation summary (wave 6)
- [ ] 10-08-PLAN.md — Gap closure: the answered date order survives the confirm gate (INGEST-04); a new Schema can actually be created (INGEST-05) (wave 6)
- [ ] 10-09-PLAN.md — Gap closure: server-side sign-in gate on /api/upload (INGEST-06, D-10-13 was UI-only); the last user-visible "field set" copy swept + gated (INGEST-01); the vendor remembered instead of re-asked (INGEST-02) (wave 7)

**UI hint**: yes

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 06 → 07 → 08 → 09 → 10 → 11

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
| 09. Mapping Registry & Documentation | 2/2 | Complete    | 2026-07-11 |
| 10. Frictionless & Correct Ingest | 0/7 | Planned | - |
| 11. Multi-Sheet Ingest | 0/TBD | Not started | - |

### Phase 11: Multi-Sheet Ingest

**Goal**: On a multi-sheet workbook, **the human decides** which sheets to ingest and **which Schema applies to which sheet**; the tool's job is to make those decisions informed ones, never to make them silently. Two silent guesses meet here today. First, `_resolve_sheet` (`parsing/table.py:349`) picks exactly one sheet (ranking them structurally, asking only when no sheet wins clearly) and discards every other sheet without a word — right for a data sheet plus a legend, wrong for a workbook holding one plate, one timepoint, or one batch per sheet. Second, the Schema must be chosen from a dropdown *before* upload, blind, with the file unparsed and no header yet seen (`SchemaPicker.tsx`; `upload.py::_resolve_field_set`) — so the human guesses the Schema while the tool guesses the sheet, and no code path maps a column signature back to a candidate Schema. This phase inverts that order: parse the workbook first, then surface every sheet with what the tool knows about it — row count, column signature, **and the Schema that best fits it, with the coverage that produced the proposal** — then let the human confirm or override. Different sheets may legitimately need **different** Schemas. Selecting several sheets produces several **independent** datasets — one per sheet, each with its own Schema, its own confirm gate, and its own export. **Sheets are never merged** (SHEET-02 struck 2026-07-13: the capability is out of the product, not merely out of this phase). Nothing is dropped or mapped to a Schema on the tool's own initiative, and every ingested row remembers which sheet it came from.
**Depends on**: Phase 1 (the structural gates — header row, shape, decimal locale — must now run per sheet, independently) and Phase 10 (the Python-first escalation the Schema scorer joins as a zero-cost first layer; the per-column date-order question, which each sheet now resolves for itself; and the governed Schema — seeded, editable — which is what SHEET-05 proposes per sheet).
**Requirements**: SHEET-01, SHEET-03, SHEET-04, SHEET-05
**Success Criteria** (what must be TRUE):

  1. On a multi-sheet workbook the human is shown every sheet with what the tool knows about each, and chooses which to ingest. Selecting N sheets yields N **independent** datasets — never a combined one. Picking a single sheet remains a first-class choice, and the existing single-sheet path (a Schema chosen upfront) does not regress. (SHEET-01)
  2. Every ingested row records the sheet it came from, so a reviewer can trace any value back to its source sheet — on every ingest, single-sheet included. The provenance travels as a reserved export column, not as a target field, so the Schema stays clean and no learned profile is invalidated. (SHEET-03)
  3. Each selected sheet passes the existing structural gates independently (header row, table shape, decimal locale, date order). A sheet that fails a gate is surfaced with its own question, never dropped. (SHEET-04)
  4. The human no longer has to know in advance which Schema fits which sheet. For each sheet the tool proposes the best-matching governed Schema — computed in pure Python with no LLM (exact learned-profile hit first, then crosswalk alias coverage) — and shows the coverage behind the proposal ("6/7 canonical fields matched"). The proposal is always pre-filled and never auto-applied: a human confirms every time. Different sheets may resolve to different Schemas, a zero-coverage sheet is proposed as *skip* rather than force-mapped, and a tie is shown as a tie rather than broken by the tool. (SHEET-05)

**Plans**: 10 plans
Plans:

- [ ] 11-01-PLAN.md — describe_sheets: per-sheet headers/rows/status above parse(), a broken sheet marked never dropped — SHEET-01, SHEET-04
- [ ] 11-02-PLAN.md — Starter crosswalk: preset alias data + tombstone-safe seeding, so the Schema scorer is not empty on day one — SHEET-05
- [ ] 11-03-PLAN.md — Row provenance: RawTable.origin_sheet → CanonicalTable.record_sources → the reserved __source_sheet column in all three writers, on every ingest — SHEET-03
- [ ] 11-04-PLAN.md — Schema scorer: _covered_fields + own-name implicit alias + propose_schemas_for_sheet + describe_workbook (pure Python, visible coverage, no threshold) — SHEET-05
- [ ] 11-05-PLAN.md — Claude Schema-ranker: the scorer's third stage, only when both deterministic stages find nothing — SHEET-05
- [ ] 11-06-PLAN.md — structural_hint bugfix: pass schema=/sheet=/strictness= and ask the date question (closes the re-created Confirm dead-end) — SHEET-04
- [ ] 11-07-PLAN.md — Sheet question + run group: the 5th/6th wire arms, the always-shown manifest, POST /api/sheets/resolve → N independent datasets — SHEET-01, SHEET-04, SHEET-05
- [ ] 11-08-PLAN.md — Group archive: run bookkeeping at confirm + GET /api/export/group/{id}/archive (zip, zip-slip-safe) — SHEET-01
- [ ] 11-09-PLAN.md — SheetQuestionPanel: the sheet manifest on screen with the coverage that produced each proposal — SHEET-01, SHEET-05
- [ ] 11-10-PLAN.md — Tabbed Review over N members (forceMount, per-member gates, Download All) + the provenance line — SHEET-01, SHEET-03

**UI hint**: yes

### Phase 12: Claude Reads the Structure

**Goal**: A sheet's **shape** is judged by **Claude**, not by Python heuristics — and a sheet that is not one-row-per-record (a key-value / label-value layout, a transposed sheet) is **actually read** rather than merely refused. The division of labour is the point: **Claude judges the layout, Python performs the extraction.** Claude sees a bounded evidence grid (~20 rows × ~10 cols — the cost is capped no matter how large the file), returns a structured verdict (shape, orientation, where the header or the labels sit), and the human confirms it on the sheet screen Phase 11 already built. Python then reads every row deterministically per that verdict. **No cell value ever passes through the model** — "trust the numbers" is not weakened by this phase, it is restated as a requirement.

**Why now — the Python classifier does not merely mis-*read* these sheets, it cannot reliably *detect* them.** `classify_shape` (`parsing/structure/shape.py:48-78`) has **no key-value predicate at all**, and its thresholds are corpus-tuned. Measured on a real 8-sheet workbook: the `Summary` sheet (key-value) was ruled `unsupported_shape` **only by accident** — it happens to contain a blank separator row, which trips the *unrelated* `multiple_tables` test — while `Patient Info`, the **identical layout without that blank row**, classified as `row_per_record`: a perfectly good table. Only low header confidence stopped a patient's name shipping to the curator as a column header. The `transposed` inversion metric is **exactly 0.000** on such a sheet (an all-strings grid makes rows and columns equally type-homogeneous), nowhere near the 0.1 margin it would need. Any new layout walks straight past these thresholds. The builder's ruling: *"давай может тогда без python code — пусть claude сам изначально и парсит файл, раз уж python code не может такие вещи различать."*

**Mostly wiring, not invention:** `parsing/structure_assist.py::propose_structure` **already exists** (Phase 1, plan 01-05) and already returns a structural proposal that "pre-fills the question, never auto-applies". Its only production call site is `cli.py:405` — the API path never calls it, and `api/routes/structural_hint.py:6-13` says so verbatim. What is genuinely missing is the **transform**: there is no un-pivot function anywhere in `src/`.

**Depends on**: Phase 11 (the sheet manifest and sheet-selection screen are where the structural verdict is surfaced and confirmed) and Phase 1 (`structure_assist`, `StructuralHint`, and the ask-and-resolve loop that is being wired to the API).
**Requirements**: SHAPE-01, SHAPE-02, SHAPE-03, SHAPE-04
**Success Criteria** (what must be TRUE):

  1. On the 8-sheet workbook, **both** `Summary` **and** `Patient Info` are identified as key-value layouts — the second being precisely the sheet today's classifier calls a normal table — and neither ever presents a patient's name as a column header. (SHAPE-01)
  2. A key-value sheet can be **ingested**, not merely refused: the human confirms Claude's structural proposal and the sheet becomes a real dataset flowing through the existing mapper, validator, amber gate and export. (SHAPE-02)
  3. **The model never writes a value.** Claude may see a *bounded* sample in order to judge — the mapper's existing 6 sample rows stay, and the structure judge gets a capped grid — but **every value in the output is read from the file by Python**, over every row. No un-pivoted or mapped value is ever transcribed by the model. (SHAPE-03)
  4. `headers_only` still judges the shape correctly, using a **redacted type grid** (`str(12)` / `num` / `date` / `blank` per cell instead of `TAYLOR, James` / `12.4`); a test proves no real cell value appears in the outbound request in that mode. (SHAPE-04)
  5. Every existing row-per-record file in `data/synthetic/` still ingests exactly as it does today — removing the Python classifier regresses nothing. (SHAPE-01)

**Accepted consequences** (chosen by the builder, not stumbled into):

  - **No offline path.** Without the Python classifier, every upload needs a model call to know the shape. Today 1132 backend tests run with zero network calls; structural tests will run against an injected fake.
  - **No second opinion.** If Claude misjudges a shape, no deterministic check contradicts it — **the human is the check**, on the sheet screen they already confirm (D-11-06: always shown, never auto-applied).

**Plans**: 4/9 plans executed
Plans:

- [x] 12-01-PLAN.md — Pure foundations: layout.py verdict types, unpivot.py transform, StructuralHint.layout round-trip (Wave A)
- [x] 12-02-PLAN.md — The judge: one batched call per workbook, runtime-Literal wire model, index clamp, type-bucket redaction (Wave A)
- [x] 12-03-PLAN.md — Parse-path dispatch: hint.layout drives parse(); key-value un-pivots into a real RawTable; gate unmoved (Wave A)
- [x] 12-04-PLAN.md — Manifest onto the verdict: judge_fn seam, the shared judging_client fixture, suppression widened, THE fails-on-main regression test (Wave B)
- [ ] 12-05-PLAN.md — API wiring: row_per_record null hypothesis, UNKNOWN attaches, both human answers round-trip, SHAPE-04 captured-outbound proof both directions
- [ ] 12-06-PLAN.md — Frontend: sheet-card layout line + badges + disagree action; StructuralHintPanel becomes the one answer surface
- [ ] 12-09-PLAN.md — The CLI's verdict source, the header_row_index=row_per_record rule, and the runnable SC5 parity sweep
- [ ] 12-07-PLAN.md — Wave C deletion: heuristic classifier removed, fail-closed unknown question, enumerated collateral closed, CSV gap recorded
- [ ] 12-08-PLAN.md — The eval deliverable: layout_truth.json (~50 sheets), gated live eval, measured bars reported for VERIFICATION.md

**UI hint**: yes

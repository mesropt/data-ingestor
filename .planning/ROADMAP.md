# Roadmap: AssayIngest (domain-independent)

## Overview

The project pivoted from a fixed 7-field assay schema to a **domain-independent** tool: the user defines the target fields at runtime (in the UI or via a saved template), and Claude's structured-output schema is built dynamically from that field set — nothing about fields, domains, or vocabularies is hardcoded anywhere in the tool. Day 1 (parser, Claude structured-output mapper, CLI review gate) is already committed on `feat/assayingest-core` and is reused, not re-phased, but its fixed-schema and reference-dictionary assumptions are generalized below. This roadmap covers the remaining scope before the 2026-07-13 21:00 ET deadline, in dependency order: first, hardening the parser to handle diverse file structures *by structure* — and, when structure is genuinely unfamiliar, asking the human for a hint instead of crashing or guessing; then generalizing fields and the mapper so the user defines what to extract and Claude's schema is built from that at runtime, with an optional preset library shipped as editable data; then a no-LLM validator that checks each field against the *user's own declared constraints* (not a built-in vocabulary) plus a SQLite-backed learning loop keyed by (field set + column signature) that survives a vendor's format drifting over time and remembers structural hints — provable end-to-end from the CLI alone before any UI exists; then a FastAPI backend and React review screen that mirror that same loop, letting a user define fields, upload, resolve a structural hint inline, review, and confirm in the browser; and finally the multi-domain synthetic demo data, rehearsed video, and README needed to submit and prove the tool is genuinely universal. Each phase only depends on layers already built, so from Phase 3 onward a CLI-provable demo of the full learning loop remains a legitimate fallback if UI time runs short.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Robust File Reading** - The parser handles diverse file structures by structure — header position, delimiter, decimal locale, sheet selection, table shape — never by hardcoded per-vendor rules; when structure is genuinely unfamiliar it asks the human for a hint instead of crashing or guessing
- [ ] **Phase 2: User-Defined Fields + Dynamic Mapper** - The user defines the target fields (and optional constraints) at runtime, reusable as templates or optional presets; Claude's structured-output schema is built dynamically from that field set — zero hardcoded domain knowledge in the mapper
- [ ] **Phase 3: Validator + Learning Loop** - Each mapped field is checked in pure Python against the constraints the user declared for it, and a fully-clear confirmed mapping is saved as a profile keyed by field set + column signature so repeat files auto-map — safely across vendor format drift, remembering structural hints too
- [ ] **Phase 4: API & Review UI** - The full define-fields → upload → resolve-hint → review → confirm → learn cycle works in the browser, with the export gate re-enforced server-side
- [ ] **Phase 5: Demo Assets & Submission** - Multi-domain synthetic files, a rehearsed ≤3-minute video, README, and submission summary prove the tool is universal and are ready to submit

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

**Plans**: 2/5 plans executed
Plans:

- [x] 01-01-PLAN.md — CSV slice + structural-question contract (delimiter/comment sniff, decimal-locale annotation, StructuralHint/StructureQuestion, parse() entry, CLI ask-branch) — PARSE-02, PARSE-03, PARSE-06
- [x] 01-02-PLAN.md — Excel header-row detection (openpyxl normal-mode grid reader, width+type scoring) — PARSE-01
- [ ] 01-03-PLAN.md — Sheet selection + drawings/chartsheet/image guards + drawing fixtures + defusedxml XXE hardening — PARSE-04, PARSE-06
- [ ] 01-04-PLAN.md — Table-shape classification (wide_matrix/transposed → question, no RawTable) — PARSE-05
- [ ] 01-05-PLAN.md — Claude structural-proposal layer (pre-fills the question, never auto-applies) completes the three-layer pipeline — PARSE-06

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

**Plans**: TBD

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

**Plans**: TBD

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

**Plans**: TBD
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

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Robust File Reading | 2/5 | In Progress|  |
| 2. User-Defined Fields + Dynamic Mapper | 0/TBD | Not started | - |
| 3. Validator + Learning Loop | 0/TBD | Not started | - |
| 4. API & Review UI | 0/TBD | Not started | - |
| 5. Demo Assets & Submission | 0/TBD | Not started | - |

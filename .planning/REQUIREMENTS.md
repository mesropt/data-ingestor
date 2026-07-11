# Requirements: AssayIngest (domain-independent)

**Defined:** 2026-07-09
**Core Value:** Claude proposes a mapping of a messy file onto whatever fields the user asked for, with honest per-field confidence; a human disposes; nothing is saved until every uncertain field is cleared. Zero hardcoded domain.

> The user defines the target fields at runtime in the UI. Nothing about fields, domains, or vocabularies is hardcoded. Potency assays / PK parameters are only example field sets a user could create.

## v1 Requirements

Requirements for the hackathon submission. Each maps to a roadmap phase. (Day-1 capabilities — messy-file parsing, the structured-output mapping pattern, per-field confidence/flags, and the review gate — are Validated in PROJECT.md; the fixed 7-field schema is being generalized below.)

### Fields (user-defined schema)

- [x] **FIELD-01**: In the UI, a user can define the target fields to extract — each with a name and an optional description. No fields are shipped or hardcoded.
- [x] **FIELD-02**: A user can attach optional constraints to a field — a type (e.g. number, integer, date), a set of allowed values, and/or an expected unit — used by the no-LLM validator.
- [x] **FIELD-03**: A user can save a set of defined fields as a reusable named template, reload it later, and load a field set shared as a file, so fields need not be re-entered each time.
- [x] **FIELD-04**: The mapper builds its structured-output schema at runtime from the user's field set — nothing about the target fields is hardcoded in the mapper.
- [x] **FIELD-05**: The tool ships an optional starter library of example field-set presets spanning multiple domains (e.g. a life-sciences assay set, a PK set, and at least one non-life-sciences set), as editable data files the user can load, modify, or ignore — presets are data, never compiled-in tool logic.

### Parsing (robust, structure-driven, human-assisted)

- [x] **PARSE-01**: When title/metadata rows sit above the real table, the parser detects the true header row instead of treating row 0 as the headers.
- [x] **PARSE-02**: The parser sniffs the CSV delimiter (comma vs semicolon) and skips leading comment lines, so a non-comma export is read as a real table rather than one junk column.
- [x] **PARSE-03**: The parser recognises decimal-comma numbers (e.g. `14,771`) in a locale-comma file and normalises them without corrupting the value by 1000×, flagging when genuinely ambiguous.
- [x] **PARSE-04**: For a multi-sheet workbook, the tool selects the data sheet and skips obvious non-data sheets (legend/notes/metadata) instead of mapping every sheet.
- [x] **PARSE-05**: For a shape that is not a simple row-per-record table (a wide matrix, a transposed layout, several tables on one sheet), the tool detects it and flags it rather than emitting a silently-wrong result.
- [x] **PARSE-06**: When the structure is unfamiliar and the tool cannot confidently locate the table or fields, it does not crash or emit garbage — it explains what it is unsure about and lets the user give a structural hint (which row is the header, which sheet/region holds the data), then proceeds using the hint and remembers it for next time.

### Mapping (Claude, dynamic schema)

- [x] **MAP-01**: Given a parsed table and the user's field set, Claude proposes a source-column→field mapping with per-field confidence and a plain-English reason for each field.
- [x] **MAP-02**: An ambiguous field gets 2–3 ranked alternative source columns; a value with no matching column may be inferred but is always flagged for confirmation, never silently trusted.

### Export (output formats)

- [x] **EXPORT-01**: After a mapping is applied, the tool assembles the result into a single canonical tidy form — one row per record, columns = the user's fields — with values normalised (decimal-comma fixed, units as declared). Every export format derives from this one representation.
- [x] **EXPORT-02**: A user can export the confirmed data as CSV and as Excel (`.xlsx`) — the human-facing deliverable a scientist opens and checks.
- [x] **EXPORT-03**: A user can export the confirmed data as JSON (an array of records), the same shape the API returns — the programmatic/pipeline path.
- [x] **EXPORT-04**: Every export is accompanied by a mapping manifest (JSON) recording the field set, column signature, field→source-column mapping, inferred/confirmed flags, and per-field confidence — the provenance/audit trail, and the same data persisted as the saved profile.

### Validation (no-LLM, constraint-driven)

- [x] **VAL-01**: The validator checks each mapped field against the constraints the user declared for it (type, allowed values, expected unit) with no LLM call, and flags violations.
- [x] **VAL-02**: A field the validator objects to is forced to needs-confirmation (yellow) regardless of Claude's reported confidence, and all of Claude's ranked alternatives are validated, not only the top pick.
- [x] **VAL-03**: A field with no declared constraints is never silently trusted — it still depends on Claude's confidence and the human-review gate; the validator's objection is shown alongside Claude's reasoning.

### Learning (profiles)

- [x] **LEARN-01**: The system computes an order-independent, normalised column signature for a source file (whitespace/case-folded header set → hash).
- [x] **LEARN-02**: A curator can save a confirmed mapping as a profile keyed by `(field set, column signature, mapping)`; the save is blocked unless the mapping is fully clear (no yellow fields).
- [x] **LEARN-03**: When a new file's signature exactly matches a saved profile for the chosen field set, the system auto-applies the stored mapping at confidence 1.0 without calling Claude.
- [x] **LEARN-04**: A signature mismatch never auto-applies a stored profile — it falls back to the Claude mapper rather than guessing silently.
- [x] **LEARN-05**: A vendor's format may change over time, so one vendor can hold several profiles (one per signature). A changed layout (new signature) falls back to Claude and can be learned as an additional profile; old-format files keep matching their old profile.
- [x] **LEARN-06**: A structural hint the user gave for an unfamiliar file (PARSE-06) is saved with its profile, so the same odd layout parses automatically next time without re-asking.

### API (FastAPI)

- [x] **API-01**: A user can upload a CSV/Excel file with a chosen field set and receive the proposed-and-validated mapping as JSON.
- [x] **API-02**: A user can confirm a mapping via an endpoint; the server re-checks the all-clear gate server-side before persisting a profile, never trusting the client's own gate.
- [x] **API-03**: On upload, the backend auto-applies a matching profile when the (field set + signature) is already known.

### UI (React review)

- [x] **UI-01**: A user can define/edit the target fields (and optional constraints) in the browser and save/load field-set templates.
- [x] **UI-02**: A user can upload a file; if the tool is unsure about the structure, the user can give a structural hint inline (PARSE-06) instead of the tool failing.
- [x] **UI-03**: The review screen shows a side-by-side view — source columns on the left, the user's target fields on the right.
- [x] **UI-04**: Uncertain (yellow) fields are highlighted with Claude's reason and, where present, the ranked alternative columns; a user can resolve a field to clear its yellow state.
- [x] **UI-05**: The confirm/export button stays disabled while any field is yellow, mirroring the server-side gate.
- [x] **UI-06**: A user can save the confirmed mapping as a profile, and a subsequent upload of a same-signature file (same field set) shows zero yellow — the learning loop is visible in the UI.

### Demo (submission assets)

- [x] **DEMO-01**: The repo contains synthetic files spanning at least two different domains (e.g. an assay-style set and a PK-report-style set) to prove the tool is universal — it has no built-in knowledge of either.
- [x] **DEMO-02**: The corpus exercises the key hazards — unit ambiguity, ambiguous/serial dates, blank/duplicate headers, preamble rows, delimiter variance, multi-sheet selection, and an unfamiliar-structure file that needs a human hint.
- [ ] **DEMO-03**: A ≤3-minute demo video shows: define target fields → upload a messy file → clean structured output (~5s); the learning loop; and a human structural hint resolving an unfamiliar file.
- [x] **DEMO-04**: The repo has a README and a 100–200 word submission summary.

## v2 Requirements

Deferred beyond the hackathon submission.

### Accounts & Deployment

- **DEPLOY-01**: Multi-user accounts / authentication
- **DEPLOY-02**: Hosted deployment beyond a local demo
- **DEPLOY-03**: Persist uploaded files / an ingest history/audit log

### Matching

- **MATCH-01**: Fuzzy / near-miss signature matching with a confirmation step (exact-match only for v1)

### Parsing

- **PARSE-V2-01**: Automatic un-pivot of wide-matrix and transposed layouts (v1 detects/flags or asks the human)
- **PARSE-V2-02**: Automatic extraction of multiple tables from a single report sheet (v1 targets one chosen table)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Any hardcoded field list / domain / controlled vocabulary | The tool is domain-agnostic by design — all domain knowledge comes from user field definitions |
| Full multi-table DMPK report engine | Target one chosen table per file; unusual structure handled via human hint |
| Confidence-threshold auto-approve (no human step) | Violates Core Value and removes the demo's central moment — anti-feature |
| Fuzzy signature auto-apply | Would silently apply a stale mapping at zero yellow — deferred to v2 with a confirmation step |
| Writing to any production/external system | Tool only proposes and exports a reviewed draft |
| Real/confidential vendor data in the repo | Synthetic data only — no real/confidential vendor files (competition rules) |

## Traceability

Each v1 requirement maps to exactly one roadmap phase (`.planning/ROADMAP.md`).

| Requirement | Phase | Status |
|-------------|-------|--------|
| FIELD-01 | Phase 2 | Complete |
| FIELD-02 | Phase 2 | Complete |
| FIELD-03 | Phase 2 | Complete |
| FIELD-04 | Phase 2 | Complete |
| FIELD-05 | Phase 2 | Complete |
| PARSE-01 | Phase 1 | Complete |
| PARSE-02 | Phase 1 | Complete |
| PARSE-03 | Phase 1 | Complete |
| PARSE-04 | Phase 1 | Complete |
| PARSE-05 | Phase 1 | Complete |
| PARSE-06 | Phase 1 | Complete |
| MAP-01 | Phase 2 | Complete |
| MAP-02 | Phase 2 | Complete |
| EXPORT-01 | Phase 2 | Complete |
| EXPORT-02 | Phase 3 | Complete |
| EXPORT-03 | Phase 3 | Complete |
| EXPORT-04 | Phase 3 | Complete |
| VAL-01 | Phase 3 | Complete |
| VAL-02 | Phase 3 | Complete |
| VAL-03 | Phase 3 | Complete |
| LEARN-01 | Phase 3 | Complete |
| LEARN-02 | Phase 3 | Complete |
| LEARN-03 | Phase 3 | Complete |
| LEARN-04 | Phase 3 | Complete |
| LEARN-05 | Phase 3 | Complete |
| LEARN-06 | Phase 3 | Complete |
| API-01 | Phase 4 | Complete |
| API-02 | Phase 4 | Complete |
| API-03 | Phase 4 | Complete |
| UI-01 | Phase 4 | Complete |
| UI-02 | Phase 4 | Complete |
| UI-03 | Phase 4 | Complete |
| UI-04 | Phase 4 | Complete |
| UI-05 | Phase 4 | Complete |
| UI-06 | Phase 4 | Complete |
| DEMO-01 | Phase 5 | Pending |
| DEMO-02 | Phase 5 | Pending |
| DEMO-03 | Phase 5 | Pending |
| DEMO-04 | Phase 5 | Pending |

**Coverage:**

- v1 requirements: 39 total (FIELD-01..05, PARSE-01..06, MAP-01..02, EXPORT-01..04, VAL-01..03, LEARN-01..06, API-01..03, UI-01..06, DEMO-01..04)
- Mapped to phases: 39/39
- Unmapped: 0

---
*Requirements defined: 2026-07-09*
*Last updated: 2026-07-09 — added EXPORT-01..04 (canonical records + CSV/Excel/JSON + manifest), mapped to Phases 2-3; 39/39 coverage*

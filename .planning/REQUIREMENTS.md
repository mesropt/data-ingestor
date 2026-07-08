# Requirements: AssayIngest

**Defined:** 2026-07-09
**Core Value:** Claude proposes a column mapping with honest per-field confidence, and a human disposes — nothing is trusted or saved until every uncertain field is cleared.

## v1 Requirements

Requirements for the hackathon submission. Each maps to a roadmap phase. (Day 1 capabilities — parser, Claude mapper, reference dictionary, CLI review gate — are already Validated in PROJECT.md and are not re-listed here.)

### Parsing (robust file reading)

- [ ] **PARSE-01**: When title/metadata rows sit above the real table (a lab banner, a study header), the parser detects the true header row instead of treating row 0 as the headers.
- [ ] **PARSE-02**: The parser sniffs the CSV delimiter (comma vs semicolon) and skips leading comment lines, so a non-comma export is read as a real table rather than one junk column.
- [ ] **PARSE-03**: The parser recognises decimal-comma numbers (e.g. `14,771`) in a locale-comma file and normalises them without corrupting the value by 1000×, flagging when genuinely ambiguous rather than guessing.
- [ ] **PARSE-04**: For a multi-sheet workbook, the tool selects the data sheet and skips obvious non-data sheets (legend/notes/metadata) instead of mapping every sheet.
- [ ] **PARSE-05**: When a file's shape is not a supported row-per-record table (a wide compound×target matrix, or a transposed layout), the tool detects it and flags the file as an unsupported shape for human attention — it never emits a silently-wrong mapping.

### Validation (no-LLM)

- [ ] **VAL-01**: The system checks each proposed `assay_type` value against the reference vocabulary and flags any unrecognised value for confirmation — it never silently rewrites the value.
- [ ] **VAL-02**: The system checks each proposed `unit` value against the allowed units (µM/nM/%), normalising known spellings deterministically (e.g. `uM`→`µM`), and flags any unrecognised unit.
- [ ] **VAL-03**: The system flags any `assay_type`/`unit` pairing the reference dictionary marks as incompatible (e.g. IC50 reported in %).
- [ ] **VAL-04**: A field the validator objects to is forced back to needs-confirmation (yellow) regardless of Claude's reported confidence, and all of Claude's ranked alternatives are validated, not only the top pick.
- [ ] **VAL-05**: Validation runs with no LLM call (pure Python) and its objection is shown to the curator alongside Claude's own reasoning.

### Learning (lab profiles)

- [ ] **LEARN-01**: The system computes an order-independent, normalised column signature for a source file (whitespace/case-folded header set → hash).
- [ ] **LEARN-02**: A curator can save a confirmed mapping as a lab profile `(lab_name, signature, mapping)` in SQLite; the save is blocked unless the mapping is fully clear (no yellow fields).
- [ ] **LEARN-03**: When a new file's signature exactly matches a saved lab profile, the system auto-applies the stored mapping at confidence 1.0 without calling Claude.
- [ ] **LEARN-04**: A signature mismatch never auto-applies a stored profile — a near-miss falls back to the Claude mapper rather than guessing silently.
- [ ] **LEARN-05**: A vendor's format may change over time, so one vendor can hold several saved profiles (one per column signature). When a known vendor sends a file in a changed/new layout (a new signature), the tool falls back to Claude and can learn that layout as an additional profile for the vendor — old-format files keep matching their old profile.

### CLI (end-to-end loop)

- [ ] **CLI-01**: The CLI runs the full propose → validate → (auto-apply on signature hit) flow and reports one merged view of confidence and flags per field.
- [ ] **CLI-02**: A curator can confirm and save a lab profile from the CLI; re-running on a second same-signature file then auto-maps with zero yellow fields — the learning loop is demonstrable CLI-only, before any UI exists.

### API (FastAPI)

- [ ] **API-01**: A user can upload a CSV/Excel file to a backend endpoint and receive the proposed-and-validated mapping as JSON.
- [ ] **API-02**: A user can confirm a mapping via an endpoint; the server re-checks the all-clear gate server-side before persisting a profile, never trusting the client's own gate.
- [ ] **API-03**: On upload, the backend auto-applies a matching lab profile when the file's signature is already known.

### UI (React review)

- [ ] **UI-01**: A user can upload a file in the browser and see a side-by-side view — source columns on the left, recognised target fields on the right.
- [ ] **UI-02**: Uncertain (yellow) fields are visually highlighted with Claude's reason and, where present, the ranked alternative columns.
- [ ] **UI-03**: A user can resolve a yellow field (pick an alternative or accept the proposal), clearing its yellow state.
- [ ] **UI-04**: The confirm/export button stays disabled while any field is yellow, mirroring the server-side gate.
- [ ] **UI-05**: A user can save the confirmed mapping as a lab profile, and a subsequent upload of a same-lab file shows zero yellow — the learning loop is visible in the UI.

### Demo (submission assets)

- [ ] **DEMO-01**: The repo contains 3–4 synthetic different-lab files, including at least one same-lab pair with an identical column signature (authored against the chosen signature function) to demonstrate the learning loop.
- [ ] **DEMO-02**: The synthetic corpus exercises the key life-sciences hazards — unit ambiguity (µM/nM), ambiguous/serial dates, and blank/duplicate headers.
- [ ] **DEMO-03**: A ≤3-minute demo video shows the money shot (messy file in → clean structure out in ~5s) and the learning loop.
- [ ] **DEMO-04**: The repo has a README and a 100-200 word submission summary.

## v2 Requirements

Deferred beyond the hackathon submission.

### Accounts & Deployment

- **DEPLOY-01**: Multi-user accounts / authentication
- **DEPLOY-02**: Hosted deployment beyond a local demo
- **DEPLOY-03**: Persist uploaded files / an ingest history/audit log

### Matching

- **MATCH-01**: Fuzzy / near-miss signature matching with a confirmation step (exact-match only for v1 to avoid silent mis-application)

### Parsing

- **PARSE-V2-01**: Correct ingestion (un-pivot) of wide compound×target matrices and transposed layouts — v1 only detects and flags these shapes (PARSE-05)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Confidence-threshold auto-approve (no human step) | Directly violates the three principles and removes the demo's central moment — an anti-feature, never build |
| Fuzzy signature auto-apply | Would silently apply a stale mapping at zero yellow, violating "never guess silently" — deferred to v2 with a confirmation step |
| Writing to any production/external system | Tool only proposes and exports a reviewed draft (Core Value) |
| Assay types / units beyond the fixed reference vocabulary | Deliberately bounded for the demo |
| Mock/reuse of any employer platform | Confidentiality + "no rights you don't have" competition rule |

## Traceability

Each requirement maps to exactly one roadmap phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PARSE-01 | Phase 1 | Pending |
| PARSE-02 | Phase 1 | Pending |
| PARSE-03 | Phase 1 | Pending |
| PARSE-04 | Phase 1 | Pending |
| PARSE-05 | Phase 1 | Pending |
| VAL-01 | Phase 2 | Pending |
| VAL-02 | Phase 2 | Pending |
| VAL-03 | Phase 2 | Pending |
| VAL-04 | Phase 2 | Pending |
| VAL-05 | Phase 2 | Pending |
| LEARN-01 | Phase 3 | Pending |
| LEARN-02 | Phase 3 | Pending |
| LEARN-03 | Phase 3 | Pending |
| LEARN-04 | Phase 3 | Pending |
| LEARN-05 | Phase 3 | Pending |
| CLI-01 | Phase 3 | Pending |
| CLI-02 | Phase 3 | Pending |
| API-01 | Phase 4 | Pending |
| API-02 | Phase 4 | Pending |
| API-03 | Phase 4 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| UI-05 | Phase 4 | Pending |
| DEMO-01 | Phase 5 | Pending |
| DEMO-02 | Phase 5 | Pending |
| DEMO-03 | Phase 5 | Pending |
| DEMO-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 29 total (PARSE-01..05, VAL-01..05, LEARN-01..05, CLI-01..02, API-01..03, UI-01..05, DEMO-01..04)
- Mapped to phases: 29/29
- Unmapped: 0

---
*Requirements defined: 2026-07-09*
*Last updated: 2026-07-09 after roadmap re-derivation added Phase 1 (Robust File Reading, PARSE-01..05) and folded vendor format-drift (LEARN-05) into Phase 3 (Learning Loop)*

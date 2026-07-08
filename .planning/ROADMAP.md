# Roadmap: AssayIngest

## Overview

Day 1 (parser, Claude structured-output mapper, reference dictionary, CLI review gate) is already committed and validated on `feat/assayingest-core` — it is not re-phased here. This roadmap covers the remaining scope before the 2026-07-13 21:00 ET deadline, in dependency order: first, hardening the parser to handle diverse vendor file structures *by structure* (header position, delimiter, sheet selection, table shape) rather than by hardcoded per-vendor rules, detecting and flagging shapes it cannot safely map instead of guessing; then a no-LLM validator that never silently rewrites a value; then a SQLite-backed learning loop — provable end-to-end from the CLI alone before any UI exists — that tolerates a vendor's format changing over time by holding multiple profiles per lab, never silently mis-applying a stale one; then a FastAPI backend and React review screen that mirror that same loop in the browser; and finally the synthetic demo data, rehearsed video, and README needed to submit. Each phase only depends on layers already built, so from Phase 3 onward a CLI-provable demo of the full learning loop remains a legitimate fallback if UI time runs short.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Robust File Reading** - The parser handles diverse vendor file structures by structure — header position, delimiter, sheet selection, table shape — never by hardcoded per-vendor rules, and detects/flags shapes it cannot safely map instead of guessing
- [ ] **Phase 2: No-LLM Validator** - Claude's proposed mapping is checked against the reference dictionary in pure Python and any objection is surfaced, never silently fixed
- [ ] **Phase 3: Learning Loop (Signature + Store + CLI)** - A confirmed mapping is saved as a lab profile, the next same-signature file auto-maps at confidence 1.0, and a vendor whose format changes gets a fresh Claude proposal and a second profile rather than a silent stale mapping — demonstrable CLI-only
- [ ] **Phase 4: API & Review UI** - The full upload → review → confirm → learning-loop cycle works in the browser, with the export gate re-enforced server-side
- [ ] **Phase 5: Demo Assets & Submission** - Synthetic multi-lab files, a rehearsed ≤3-minute video, README, and submission summary are ready to submit

## Phase Details

### Phase 1: Robust File Reading
**Goal**: The parser handles the structural diversity of CRO vendor files — where the header row sits, what delimiter is used, which sheet holds the data, and whether the table shape is even supported — by detecting structure, not by hardcoding rules per vendor; when a file's shape genuinely isn't a supported row-per-record table, the tool detects and flags it rather than emitting a silently-wrong mapping.
**Mode:** mvp
**Depends on**: Nothing (first phase; hardens the already-validated Day 1 parser before validation and learning depend on a structurally-clean table)
**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05
**Success Criteria** (what must be TRUE):
  1. A file with several banner/title rows above the real table (a lab banner, a study header) has its true header row detected structurally — not row 0 — regardless of how many rows precede it.
  2. A semicolon-delimited CSV, or one with leading comment lines, is sniffed and read as a proper multi-column table, not collapsed into one junk column.
  3. A locale-formatted number using comma as the decimal separator (e.g. `14,771`) is normalized to the correct value without a 1000x corruption, and a genuinely ambiguous number is flagged for confirmation rather than guessed.
  4. A multi-sheet workbook has its data sheet selected automatically, skipping legend/notes/metadata sheets, instead of mapping every sheet.
  5. A wide compound×target matrix or a transposed layout is detected and flagged as an unsupported shape for human attention — it is never mapped to a silently-wrong structured result.
**Plans**: TBD

### Phase 2: No-LLM Validator
**Goal**: Claude's proposed mapping — including every ranked alternative, not only the top pick — is checked against the reference dictionary (assay-type vocabulary, unit vocabulary, assay-type/unit compatibility) by pure Python with zero LLM calls, and any objection forces the field back to needs-confirmation regardless of Claude's own reported confidence.
**Mode:** mvp
**Depends on**: Phase 1 (validation presumes a structurally-clean table; a wrongly-shaped file must already be flagged before it reaches the validator)
**Requirements**: VAL-01, VAL-02, VAL-03, VAL-04, VAL-05
**Success Criteria** (what must be TRUE):
  1. An `assay_type` value outside the reference vocabulary is flagged yellow with a validator-authored reason and is never silently rewritten.
  2. A `unit` value with a known-alias spelling (e.g. `uM`) is deterministically normalized to its canonical form (`µM`) and the normalization is shown to the curator; an unrecognized unit is flagged instead of guessed.
  3. An `assay_type`/`unit` pairing the reference dictionary marks incompatible (e.g. IC50 reported in `%`) is flagged even when Claude reported high confidence.
  4. Every one of Claude's ranked alternatives for a field is checked against the reference dictionary, not only the top pick.
  5. Validation runs with zero LLM calls, and its objection text is shown in the CLI review report alongside Claude's own reasoning.
**Plans**: TBD

### Phase 3: Learning Loop (Signature + Store + CLI)
**Goal**: A curator can confirm a fully-clear mapping and save it as a lab profile keyed by an order-independent column signature; because a vendor's file format can change over time, one vendor may accumulate several saved profiles (one per signature) — an exactly matching signature auto-applies the stored mapping at confidence 1.0, while a changed layout produces a new signature that never matches an old profile, instead falling back to a fresh Claude proposal and becoming learnable as an additional profile, all proven end-to-end from the CLI before any web layer exists.
**Mode:** mvp
**Depends on**: Phase 2 (a mapping must pass validation before "fully clear" has meaning, and the propose→validate→auto-apply sequence needs both ends built)
**Requirements**: LEARN-01, LEARN-02, LEARN-03, LEARN-04, LEARN-05, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Two files whose headers differ only in order, case, or incidental whitespace produce the identical column signature; two files with genuinely different headers produce different signatures.
  2. A curator can save a confirmed mapping as a lab profile only when the mapping has zero yellow fields — the save is blocked otherwise.
  3. Re-running the CLI on a second file with an exactly matching signature returns the stored mapping at confidence 1.0 with zero yellow fields and without a Claude API call.
  4. A vendor whose file format changes (a new or different column layout) produces a new signature that does not match the vendor's existing profile; the file falls back to a fresh Claude proposal — never a silent mis-application of the old mapping — and the new layout can be confirmed and saved as a second profile for the same vendor, while files in the old format still match their original profile.
  5. The CLI reports one merged view of confidence and flags per field, for both the fresh-propose path and the auto-apply path, and a curator can confirm-and-save a profile directly from the CLI.
**Plans**: TBD

### Phase 4: API & Review UI
**Goal**: A curator can perform the full upload → review → confirm → learning-loop cycle in the browser — the demo's centerpiece — with the server independently re-checking the "no yellow fields" gate rather than trusting the client.
**Mode:** mvp
**Depends on**: Phase 3 (the application layer, validator, signature builder, and learning store must exist for the API to wrap rather than re-implement)
**Requirements**: API-01, API-02, API-03, UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. A user can upload a CSV/Excel file in the browser and see a side-by-side view — source columns on the left, recognized target fields on the right — matching the JSON the upload endpoint returns.
  2. Uncertain (yellow) fields are visibly highlighted with Claude's reason and ranked alternatives; a user can resolve a yellow field by picking an alternative or accepting the proposal, clearing its yellow state.
  3. The confirm/export control stays disabled in the UI while any field is yellow, and the confirm endpoint independently re-checks the same gate server-side before persisting, never trusting the client alone.
  4. A user can save a confirmed mapping as a lab profile from the UI, and uploading a second same-lab file shows zero yellow fields, auto-mapped without another Claude call.
  5. On upload, the backend transparently auto-applies a matching lab profile when the file's signature is already known, visible to the user as a fully-resolved, non-yellow result.
**Plans**: TBD
**UI hint**: yes

### Phase 5: Demo Assets & Submission
**Goal**: The repo and a recorded video credibly demonstrate the full propose → validate → confirm → learn loop to a judge in under 3 minutes, backed by synthetic data that exercises the real life-sciences hazards the tool guards against.
**Mode:** mvp
**Depends on**: Phase 4 (records the working UI loop; Phase 3's CLI loop remains a legitimate fallback if UI recording isn't ready)
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Success Criteria** (what must be TRUE):
  1. The repo contains 3-4 synthetic different-lab files, including at least one same-lab pair sharing an identical column signature under the chosen signature function.
  2. The synthetic corpus exercises unit ambiguity (µM/nM), ambiguous/serial dates, and blank/duplicate headers across the files.
  3. A rehearsed, ≤3-minute demo video shows the money shot (messy file in → clean structure out in ~5s) and the learning loop (second same-lab file, zero yellow) back to back.
  4. The repo has a README and a 100-200 word submission summary ready to paste into the submission form.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Robust File Reading | 0/TBD | Not started | - |
| 2. No-LLM Validator | 0/TBD | Not started | - |
| 3. Learning Loop (Signature + Store + CLI) | 0/TBD | Not started | - |
| 4. API & Review UI | 0/TBD | Not started | - |
| 5. Demo Assets & Submission | 0/TBD | Not started | - |

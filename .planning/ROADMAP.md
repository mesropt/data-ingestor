# Roadmap: AssayIngest

## Overview

Day 1 (parser, Claude structured-output mapper, reference dictionary, CLI review gate) is already committed and validated on `feat/assayingest-core` — it is not re-phased here. This roadmap covers the remaining ~3 working days before the 2026-07-13 21:00 ET deadline: a no-LLM validator that never silently rewrites a value, a SQLite-backed learning loop that is provable end-to-end from the CLI alone before any UI exists, a FastAPI backend and React review screen that mirror that same loop in the browser, and the synthetic demo data, rehearsed video, and README needed to submit. Each phase only depends on layers already built, so from Phase 2 onward a CLI-provable demo of the full learning loop remains a legitimate fallback if UI time runs short.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: No-LLM Validator** - Claude's proposed mapping is checked against the reference dictionary in pure Python and any objection is surfaced, never silently fixed
- [ ] **Phase 2: Learning Loop (Signature + Store + CLI)** - A confirmed mapping is saved as a lab profile and the next same-lab file auto-maps at confidence 1.0, demonstrable CLI-only
- [ ] **Phase 3: API & Review UI** - The full upload → review → confirm → learning-loop cycle works in the browser, with the export gate re-enforced server-side
- [ ] **Phase 4: Demo Assets & Submission** - Synthetic multi-lab files, a rehearsed ≤3-minute video, README, and submission summary are ready to submit

## Phase Details

### Phase 1: No-LLM Validator
**Goal**: Claude's proposed mapping — including every ranked alternative, not only the top pick — is checked against the reference dictionary (assay-type vocabulary, unit vocabulary, assay-type/unit compatibility) by pure Python with zero LLM calls, and any objection forces the field back to needs-confirmation regardless of Claude's own reported confidence.
**Mode:** mvp
**Depends on**: Nothing (first phase; builds on the already-validated Day 1 parser/mapper/CLI)
**Requirements**: VAL-01, VAL-02, VAL-03, VAL-04, VAL-05
**Success Criteria** (what must be TRUE):
  1. An `assay_type` value outside the reference vocabulary is flagged yellow with a validator-authored reason and is never silently rewritten.
  2. A `unit` value with a known-alias spelling (e.g. `uM`) is deterministically normalized to its canonical form (`µM`) and the normalization is shown to the curator; an unrecognized unit is flagged instead of guessed.
  3. An `assay_type`/`unit` pairing the reference dictionary marks incompatible (e.g. IC50 reported in `%`) is flagged even when Claude reported high confidence.
  4. Every one of Claude's ranked alternatives for a field is checked against the reference dictionary, not only the top pick.
  5. Validation runs with zero LLM calls, and its objection text is shown in the CLI review report alongside Claude's own reasoning.
**Plans**: TBD

### Phase 2: Learning Loop (Signature + Store + CLI)
**Goal**: A curator can confirm a fully-clear mapping, save it as a lab profile keyed by an order-independent column signature, and have the next file from the same lab with an exactly matching signature auto-map at confidence 1.0 with zero yellow fields — proven end-to-end from the CLI, before any web layer exists.
**Mode:** mvp
**Depends on**: Phase 1 (a mapping must pass validation before "fully clear" has meaning, and the propose→validate→auto-apply sequence needs both ends built)
**Requirements**: LEARN-01, LEARN-02, LEARN-03, LEARN-04, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Two files whose headers differ only in order, case, or incidental whitespace produce the identical column signature; two files with genuinely different headers produce different signatures.
  2. A curator can save a confirmed mapping as a lab profile only when the mapping has zero yellow fields — the save is blocked otherwise.
  3. Re-running the CLI on a second file with an exactly matching signature returns the stored mapping at confidence 1.0 with zero yellow fields and without a Claude API call.
  4. A file whose signature doesn't exactly match any saved profile falls through to a fresh Claude proposal — a near-miss never silently auto-applies a stale mapping.
  5. The CLI reports one merged view of confidence and flags per field, for both the fresh-propose path and the auto-apply path, and a curator can confirm-and-save a profile directly from the CLI.
**Plans**: TBD

### Phase 3: API & Review UI
**Goal**: A curator can perform the full upload → review → confirm → learning-loop cycle in the browser — the demo's centerpiece — with the server independently re-checking the "no yellow fields" gate rather than trusting the client.
**Mode:** mvp
**Depends on**: Phase 2 (the application layer, validator, signature builder, and learning store must exist for the API to wrap rather than re-implement)
**Requirements**: API-01, API-02, API-03, UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. A user can upload a CSV/Excel file in the browser and see a side-by-side view — source columns on the left, recognized target fields on the right — matching the JSON the upload endpoint returns.
  2. Uncertain (yellow) fields are visibly highlighted with Claude's reason and ranked alternatives; a user can resolve a yellow field by picking an alternative or accepting the proposal, clearing its yellow state.
  3. The confirm/export control stays disabled in the UI while any field is yellow, and the confirm endpoint independently re-checks the same gate server-side before persisting, never trusting the client alone.
  4. A user can save a confirmed mapping as a lab profile from the UI, and uploading a second same-lab file shows zero yellow fields, auto-mapped without another Claude call.
  5. On upload, the backend transparently auto-applies a matching lab profile when the file's signature is already known, visible to the user as a fully-resolved, non-yellow result.
**Plans**: TBD
**UI hint**: yes

### Phase 4: Demo Assets & Submission
**Goal**: The repo and a recorded video credibly demonstrate the full propose → validate → confirm → learn loop to a judge in under 3 minutes, backed by synthetic data that exercises the real life-sciences hazards the tool guards against.
**Mode:** mvp
**Depends on**: Phase 3 (records the working UI loop; Phase 2's CLI loop remains a legitimate fallback if UI recording isn't ready)
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Success Criteria** (what must be TRUE):
  1. The repo contains 3-4 synthetic different-lab files, including at least one same-lab pair sharing an identical column signature under the chosen signature function.
  2. The synthetic corpus exercises unit ambiguity (µM/nM), ambiguous/serial dates, and blank/duplicate headers across the files.
  3. A rehearsed, ≤3-minute demo video shows the money shot (messy file in → clean structure out in ~5s) and the learning loop (second same-lab file, zero yellow) back to back.
  4. The repo has a README and a 100-200 word submission summary ready to paste into the submission form.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. No-LLM Validator | 0/TBD | Not started | - |
| 2. Learning Loop (Signature + Store + CLI) | 0/TBD | Not started | - |
| 3. API & Review UI | 0/TBD | Not started | - |
| 4. Demo Assets & Submission | 0/TBD | Not started | - |

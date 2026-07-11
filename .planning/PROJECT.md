# Data Ingestor

> **Direction note (2026-07-09):** The product is now **domain-independent**. The original `CLAUDE.md` brief framed it around a fixed set of 7 potency-assay fields; that framing is **superseded** — no fields, domains, or vocabularies are hardcoded. The user defines the fields they need at runtime. Potency assays and PK parameters are merely *examples* a user could set up, not built-in. The name "Data Ingestor" is now narrower than the product (possible rename deferred).

## What This Is

A domain-independent AI ingest tool for **any messy Excel/CSV data file — not just life sciences**. The user defines the target fields they want (in the UI), or loads a ready-made field-set preset; the tool reads the messy file — locating the real table even in awkwardly structured files, and asking the human for a hint when the structure is unfamiliar rather than breaking — and Claude maps the source columns onto the user's fields with per-field confidence. The human reviews and confirms; the tool learns each vendor's layout so repeat files map automatically. **No fields or domain are baked into the tool logic**; domain knowledge lives only in user-supplied field sets (which may be shipped as optional, editable presets for different industries). The hackathon is the Life Sciences track, so the demo ships at least one life-sciences preset — but the tool itself is general-purpose.

## Core Value

Claude proposes a mapping of a messy file onto whatever fields the user asked for, with honest per-field confidence; a human disposes; nothing is trusted or saved until every uncertain field is cleared. Fully general — zero hardcoded domain knowledge.

## Business Context

<!-- Hackathon entry, not monetized. Kept for judging-criteria prioritization. -->

- **Customer**: Anyone who reformats messy vendor data files by hand — a drug-discovery data curator is the lead example, but the tool is not tied to that.
- **Revenue model**: n/a — hackathon submission ("Built with Claude: Life Sciences", Builder track).
- **Success metric**: Judging score — Demo 30%, Claude Use 25%, Impact 25%, Depth & Execution 20%.
- **Strategy notes**: `CLAUDE.md` holds the original (now partly superseded) assay-specific brief; this PROJECT.md is the current source of truth for direction.

## Requirements

### Validated

<!-- Shipped in Day 1 as domain-general capabilities (the fixed 7-field schema is being generalized). -->

- ✓ Parse messy CRO CSV/Excel (multi-sheet, blank/dirty headers) into a clean raw table — existing (Day 1), reusable
- ✓ Claude structured-output mapping pattern: source columns → target fields with per-field confidence, reasoning, ranked alternatives, and flags — existing (Day 1), to be made schema-dynamic
- ✓ Human-review gate: export blocked while any field is uncertain (yellow) — existing (Day 1)
- ✓ Clean wire→domain boundary and CLI scaffolding — existing (Day 1), reusable

### Active

<!-- The universal redesign. Hypotheses until shipped. -->

- [ ] User-defined fields: the user declares the target fields (name + optional description) in the UI; nothing is hardcoded
- [ ] Optional per-field constraints (type, allowed values, expected unit) that drive no-LLM validation — user-declared, not baked in
- [ ] Reusable field-set templates: save a set of defined fields under a name, reload it, and load field sets shared as files — plus an optional starter library of industry presets (data-only, editable; not compiled into the tool)
- [ ] Dynamic mapper: Claude's structured-output schema is built at runtime from the user's field set
- [ ] Structure-driven robust parser + human-assisted parsing: unfamiliar structure → the tool asks the human for a hint (header row, data sheet, region) instead of crashing, and remembers the hint
- [ ] Generalized no-LLM validator: checks each field against the constraints the user declared (no built-in vocabulary)
- [ ] Learning loop: a confirmed mapping is saved as a profile keyed by (field set + column signature); repeat files auto-map at confidence 1.0; format-drift safe (multiple profiles per vendor)
- [ ] FastAPI + React review UI: define fields → upload → review yellow → confirm → learn
- [ ] Synthetic multi-domain demo data (e.g. an assay-style file set and a PK-report-style file set — the tool has no built-in knowledge of either) + 3-min video + README + 100–200 word summary

### Out of Scope

- **Any hardcoded field list, domain, or controlled vocabulary** — the tool ships domain-agnostic; all domain knowledge comes from the user's field definitions
- Full multi-table DMPK report engine — the tool targets one chosen table per file; unusual structure is handled via a human hint, not fully automatic reshaping
- Correct auto un-pivot of wide-matrix / transposed layouts — detect and flag (or ask the human) in v1
- Confidence-threshold auto-approve without a human step — anti-feature, violates Core Value
- Writing to any production/external system — the tool only proposes and exports a reviewed draft
- Mock/reuse of any employer platform or real confidential data — synthetic demo data only (competition rules)

## Context

- **Technical environment:** Python 3.13, FastAPI + Anthropic SDK (structured output via tool-use / JSON schema, built dynamically per field set), pandas/openpyxl for parsing, pydantic wire models, SQLite for the learning store, Vite + React for the UI. Managed with `uv`; tests with pytest.
- **Architecture:** Clean Architecture — dependencies point toward the domain; infrastructure models mapped to domain models at the boundary. See `.planning/codebase/` (mapped 2026-07-09).
- **Prior work:** Day 1 shipped a *fixed* 7-field assay pipeline on branch `feat/assayingest-core`. The universal redesign generalizes the fixed schema and reference dictionary into user-defined fields/constraints; the parser, confidence/flag model, review gate, and boundary pattern are reused.
- **Data policy:** the public repo uses synthetic data only — no real or confidential vendor files.

## Constraints

- **Timeline**: Submissions due Mon 2026-07-13, 9:00 PM ET — ~3.5 working days. Prioritise a working end-to-end money-shot early; CLI-first keeps a fallback if the UI runs long.
- **Scope risk**: Domain-independence is more ambitious than the original fixed-domain plan (dynamic schema + a field-editor UI). Keep each field set small in the demo.
- **Tech stack**: Anthropic personal org (UUID `474eb356-d20a-4417-997d-0c59c21e897a`), not employer's.
- **Licensing**: Open-source, MIT (in LICENSE); new work only, fresh repo.
- **Process**: gsd-core (Discuss → Plan → Execute → Verify → Ship) with living artifacts under `.planning/`.
- **Coding conventions**: Clean Architecture; single level of abstraction per function; log-or-raise never both; error messages describe the consequence. See `CLAUDE.md` and `.planning/codebase/CONVENTIONS.md`.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Domain-independent: fields are user-defined at runtime, zero hardcode | Maximum generality; one tool for any messy vendor file, not just assays | — Pending (supersedes fixed 7-field brief) |
| Day-1 fixed assay schema + reference dict → generalized to user fields/constraints | Reuse the pipeline, drop the baked-in domain | — Pending |
| No-LLM validator checks user-declared constraints (not a built-in vocabulary) | Keep the guardrail without hardcoding a domain | — Pending |
| Parser is structure-driven + human-assisted (ask for a hint on unknown structure, remember it) | Never break on unfamiliar files; make hard layouts tractable via HITL | — Pending |
| Learning profile keyed by (field set + column signature), exact-match, multiple per vendor | Safe auto-map; survives vendor format drift | — Pending |
| Claude proposes, human disposes; nothing saved until clear | The whole point — LLM never touches truth directly | ✓ Good (Day 1) |
| Synthetic data only in the repo; no real/confidential vendor files | Confidentiality + "no rights you don't have" competition rule | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-09 after pivot to a domain-independent (user-defined fields) design*

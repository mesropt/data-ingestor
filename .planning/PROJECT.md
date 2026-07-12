# Data Ingestor

> **Direction note (2026-07-09):** The product is now **domain-independent**. The original `CLAUDE.md` brief framed it around a fixed set of 7 potency-assay fields; that framing is **superseded** — no fields, domains, or vocabularies are hardcoded. The user defines the fields they need at runtime. Potency assays and PK parameters are merely *examples* a user could set up, not built-in. The name "Data Ingestor" is now narrower than the product (possible rename deferred).

## What This Is

A domain-independent AI ingest tool for **any messy Excel/CSV data file — not just life sciences**. The user defines the target fields they want (in the UI), or loads a ready-made field-set preset; the tool reads the messy file — locating the real table even in awkwardly structured files, and asking the human for a hint when the structure is unfamiliar rather than breaking — and Claude maps the source columns onto the user's fields with per-field confidence. The human reviews and confirms; the tool learns each vendor's layout so repeat files map automatically. **No fields or domain are baked into the tool logic**; domain knowledge lives only in user-supplied field sets (which may be shipped as optional, editable presets for different industries). The hackathon is the Life Sciences track, so the demo ships at least one life-sciences preset — but the tool itself is general-purpose.

## Core Value

Claude proposes a mapping of a messy file onto whatever fields the user asked for, with honest per-field confidence; a human disposes; nothing is trusted or saved until every uncertain field is cleared. Fully general — zero hardcoded domain knowledge.

## Current Milestone: v2.0 Canonical Schemas, Crosswalk & Governance

**Goal:** Evolve from disposable per-file field sets to a governed **canonical data model + vendor-alias crosswalk** per domain, with authenticated attribution — so every mapping decision accretes into a reusable, auditable master map that new files reconcile against.

**Target features:**
- **Canonical schema per domain** — a field set "graduates" into a governed canonical model (Schema); JSON master map file always downloadable, and re-importable to augment an existing schema.
- **Vendor-alias crosswalk with provenance** — each canonical field carries vendor aliases; every alias records which vendor and how it was mapped (`manual` by a named user vs `from map file`) with a timestamp. Data lineage/governance.
- **Reconcile-on-upload** — upload Excel + optional map file; the map file augments the master; master↔map-file conflicts prompt the user to resolve; result shown immediately to edit/approve.
- **Mapping Registry page** — the Profiles tab descoped in v1.0, now realized: canonical fields left, per-vendor names + provenance right.
- **Mandatory auth (governance-justified)** — attribution of a manual mapping to a named person is audit, not a gratuitous wall. Google OAuth primary + email verification; dev fallback (console-printed link, OAuth behind a feature flag) for the overnight build.
- **In-app Documentation page** — how-to + glossary of the locked terms (Schema / Field / Alias / Organization).

**Locked terminology:** **Schema** = one canonical model per domain (its JSON export is the master map file) · **Field** = a canonical field in a schema · **Alias** = a vendor's name for a field, with provenance · **Organization** = owner of a set of schemas (FUTURE).

**Explicitly FUTURE (not this milestone):** Organizations / multi-tenancy (per-org isolation, per-org schema sets, roles inside an org); schema versioning for vendor format drift; governance roles for who may change a master. Having multiple *named* schemas stays in scope now.

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

- ✓ User-defined fields: the user declares the target fields (name + optional description); nothing is hardcoded — v1.0 (Phase 02)
- ✓ Optional per-field constraints (type, allowed values, expected unit) driving no-LLM validation — v1.0 (Phase 02/03)
- ✓ Reusable field-set templates + editable industry presets (data-only YAML) — v1.0 (Phase 02)
- ✓ Dynamic mapper: Claude's structured-output schema built at runtime from the user's field set — v1.0 (Phase 02)
- ✓ Structure-driven robust parser + human-assisted parsing hint (remembered) — v1.0 (Phase 01)
- ✓ Generalized no-LLM validator against user-declared constraints — v1.0 (Phase 03)
- ✓ Learning loop: confirmed mapping saved as profile keyed by (field set + column signature); repeat files auto-map at 1.0; format-drift safe — v1.0 (Phase 03)
- ✓ FastAPI + React review UI: define fields → upload → review yellow → confirm → learn — v1.0 (Phase 04)
- ✓ Synthetic multi-domain demo data + README + 100–200 word summary (video pending recording) — v1.0 (Phase 05)

### Active

<!-- Milestone v2.0 — canonical schemas, crosswalk, governance, auth. Hypotheses until shipped. -->

**Auth & attribution (AUTH)**
- [ ] User must authenticate before creating/editing schemas or confirming mappings — manual decisions attributable to a named person
- [ ] Google OAuth login (behind a feature flag; dev fallback with placeholder creds for the overnight build)
- [ ] Email verification (dev fallback: console-printed verification link)
- [ ] Manual mapping edits/confirmations attributed to the authenticated user (feeds alias provenance)

**Canonical schema (SCHEMA)**
- [ ] Promote a field set into a governed canonical Schema (one per domain), with named canonical fields
- [ ] Export a Schema's canonical model as a downloadable JSON master map file
- [ ] Import a master map file to augment an existing Schema
- [ ] Multiple named Schemas coexist, isolated from each other (assay vs reagent-inventory stay separate)

**Vendor-alias crosswalk (ALIAS)**
- [ ] Each canonical field carries a list of vendor aliases
- [ ] Every alias records which vendor it came from
- [ ] Every alias records provenance: `manual` (which user) vs `from map file` (name) + timestamp
- [ ] Confirming a mapping records its resolved source columns as aliases in the Schema's crosswalk with provenance

**Reconcile-on-upload (RECON)**
- [ ] Upload accepts Excel + optional map file; the map file augments the master before mapping
- [ ] Master↔map-file conflict/ambiguity prompts the user to resolve
- [ ] Reconciled mapping shown immediately for edit/approve (reuses the review UI)

**Registry & docs (REG / DOCS)**
- [ ] Mapping Registry page: table with canonical fields left, per-vendor names + provenance right
- [ ] In-app Documentation page: how-to + glossary of locked terms (Schema/Field/Alias/Organization)

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
| **v2.0:** Canonical model + crosswalk per domain (not one global master) | Assay vs reagent-inventory are different domains; each field set graduates into its own governed Schema | — Pending |
| **v2.0:** Auth now REQUIRED (reverses v1.0 "auth deferred as risky") | Attribution of a manual mapping to a named person is governance/audit, not a gratuitous login wall | — Pending |
| **v2.0:** Google OAuth primary + email verification; dev fallback overnight | Real OAuth client id/secret + email provider need the user's own accounts — flagged off with placeholders, wired later by the user | — Pending |
| **v2.0:** Organizations / multi-tenancy + versioning + roles → FUTURE | Keep the milestone shippable before the deadline; multiple named schemas stay in scope, org isolation does not | — Pending |

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
*Last updated: 2026-07-11 — started milestone v2.0 (Canonical Schemas, Crosswalk & Governance)*

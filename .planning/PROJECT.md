# AssayIngest

## What This Is

An AI ingest tool for contract-research-organisation (CRO) assay files. A data curator uploads any lab's messy Excel/CSV — every lab formats differently — and Claude maps its columns onto a fixed set of target fields on its own, returning a structured draft with per-field confidence and yellow flags on anything uncertain. The human reviews and confirms; only then is anything written. It turns manual reformatting into a one-click review.

## Core Value

Claude proposes a column mapping with honest per-field confidence, and a human disposes — nothing is trusted or saved until every uncertain field is cleared. "Trust the numbers": the LLM never touches production truth directly.

## Business Context

<!-- Hackathon entry, not monetized. Kept for judging-criteria prioritization. -->

- **Customer**: A drug-discovery data curator who reformats CRO result files by hand today.
- **Revenue model**: n/a — hackathon submission ("Built with Claude: Life Sciences", Builder track).
- **Success metric**: Judging score — Demo 30%, Claude Use 25%, Impact 25%, Depth & Execution 20%.
- **Strategy notes**: See `CLAUDE.md` (committed project brief — source of truth).

## Requirements

### Validated

<!-- Shipped in Day 1, committed on feat/assayingest-core, 32+1 tests green. -->

- ✓ Parse messy CRO CSV/Excel (multi-sheet, blank/dirty headers) into a clean raw table — existing (Day 1)
- ✓ Claude structured-output mapper: source columns → 7 target fields with per-field confidence, reasoning, and flags — existing (Day 1)
- ✓ Ambiguity handling: 2–3 ranked alternatives instead of a bare guess; unit inferred from value range when missing — existing (Day 1)
- ✓ CLI: JSON draft + colour-coded review report with an export gate (blocked while any field is yellow) — existing (Day 1)
- ✓ Reference dictionary of allowed assay types + compatible units, defined without any LLM — existing (Day 1)

### Active

<!-- Remaining hackathon scope: Day 2–4. Hypotheses until shipped. -->

- [ ] No-LLM validator: check Claude's proposed mapping against the reference dictionary (assay-type vocabulary, unit vocabulary, assay-type/unit compatibility) and force uncertain fields back to needs-confirmation
- [ ] SQLite learning store: save a curator-confirmed mapping as a lab profile keyed by column signature; auto-map the next file with the same signature at confidence 1.0
- [ ] Demonstrable learning loop: lab X's first file shows several yellow fields; the second file from the same lab maps with zero yellow, fully auto
- [ ] React review UI: side-by-side diff (source left, recognised right), uncertain cells highlighted yellow with Claude's reason, and a confirm button — the centre of the demo
- [ ] 3–4 synthetic "different-lab" demo files, a 3-minute demo video, README, and a 100–200 word summary for submission

### Out of Scope

- Any mock or reuse of an employer platform — standalone product on synthetic data only (confidentiality + "no rights you don't have" rule)
- Assets the builder lacks rights to; team > 2 people — competition rules
- Writing to any production/external system — the tool only proposes and exports a reviewed draft (Core Value)
- Assay types / units beyond the fixed reference vocabulary (IC50/EC50/Ki/Kd/%inhibition; µM/nM/%) — deliberately bounded for the demo

## Context

- **Technical environment:** Python 3.13, FastAPI + Anthropic SDK (structured output via tool-use / JSON schema), pandas/openpyxl for parsing, pydantic wire models, SQLite for the learning store, Vite + React for the UI. Managed with `uv`; tests with pytest.
- **Architecture:** Clean Architecture — dependencies point toward the domain. Infrastructure models (raw API responses) are mapped to domain models at the layer boundary. See `.planning/codebase/` for the full map produced on 2026-07-09.
- **Prior work:** Day 1 is committed on branch `feat/assayingest-core`. `.planning/codebase/CONCERNS.md` already flags the exact Day-2 gaps — reference dictionary not yet used to validate Claude's output, and no confirmation/persistence path.
- **Domain model:** target fields `compound_id`, `assay_type`, `value`, `unit`, `target`, `n_replicates`, `assay_date`.

## Constraints

- **Timeline**: Submissions due Mon 2026-07-13, 9:00 PM ET — ~4 working days. Prioritise the demo money-shot early.
- **Tech stack**: Anthropic personal org (UUID `474eb356-d20a-4417-997d-0c59c21e897a`), not employer's — competition rule.
- **Licensing**: Open-source, MIT (in LICENSE); new work only, fresh repo — competition rules.
- **Process**: gsd-core is the project process (Discuss → Plan → Execute → Verify → Ship) with living artifacts under `.planning/`.
- **Coding conventions**: Clean Architecture; single level of abstraction per function; log-or-raise never both; error messages describe the consequence, not the symptom. See `CLAUDE.md` and `.planning/codebase/CONVENTIONS.md`.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude proposes, human disposes (structured output + per-field confidence) | The whole point — the LLM never touches production truth directly | ✓ Good (Day 1 shipped) |
| Validator + reference dictionary are plain Python, no LLM | Ground truth for validation must not itself be a model | — Pending (Day 2) |
| Learning loop via SQLite lab profiles keyed by column signature | The differentiator; must be demonstrable on video | — Pending (Day 2) |
| Standalone product on synthetic data | Avoids confidentiality + "no rights you don't have" rule | ✓ Good |
| Adopt gsd-core as the process | Survives across environments (Windows ↔ WSL) and fresh sessions | — Pending |

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
*Last updated: 2026-07-09 after initialization*

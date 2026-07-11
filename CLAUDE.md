# Data Ingestor — project brief

> This file is the source of truth for the project context. It is committed to the repo so it survives across environments (Windows ↔ WSL) and fresh Claude Code sessions. Read it first.

## What this is

Hackathon project for **Built with Claude: Life Sciences** (Anthropic + Gladstone Institutes), **Builder track**. Solo builder: Mesrop Tarkhanyan (software engineer, drug-discovery informatics).

**Data Ingestor** — an AI ingest tool: upload any CRO assay Excel/CSV (every lab formats differently) → Claude maps its columns to the right target fields on its own → returns a structured draft with confidence flags on uncertain fields → a human reviews and clicks "confirm". Turns manual reformatting into a one-click review.

## The three principles (non-negotiable — this is the whole point)

1. **Claude proposes, human disposes.** Claude only returns a *proposed* mapping via structured output (tool-use / JSON schema) with per-field confidence. The human confirms; only then is anything written. Motto: *"trust the numbers"* — the LLM never touches production truth directly.
2. **Never guess silently.** Missing unit → infer from value range + flag for confirmation. Ambiguous column → offer 2-3 options with % confidence, never a bare "I don't know".
3. **Nothing saved until all fields are clear.** Export/confirm is blocked while any uncertain (yellow) field remains.

## The differentiator: learning loop

When a curator fixes a mapping for lab X once, save it as a **lab profile** (SQLite). The next file with the same column signature from lab X maps automatically at confidence 1.0. This must be *demonstrable* on video: lab X file first time = several yellow fields; second file same lab = zero, auto-mapped.

## Stack

- **Backend:** FastAPI + Anthropic SDK (Python 3.13).
- **Mapper core:** Claude structured output via tool-use / JSON schema → column mapping + per-field confidence + flags. The heart of the app.
- **Parsing:** pandas / openpyxl (messy Excel/CSV → raw table).
- **Validator + reference dictionary:** plain Python, NO LLM. Small YAML/JSON of allowed `assay_type` + compatible units; Claude's mapping is validated against it.
- **Learning store:** SQLite `lab_profile(lab_name, source_columns_signature, mapping_json)`.
- **Frontend:** Vite + React. Side-by-side review screen (source left, recognized right, uncertain cells yellow with Claude's reason) is the center of the demo.

## Domain model (public, non-confidential, standalone)

Target fields: `compound_id`, `assay_type` (IC50/EC50/Ki/Kd/%inhibition), `value`, `unit` (µM/nM/%), `target` (e.g. EGFR, JAK2), `n_replicates`, `assay_date`.

Standalone product on **synthetic data** — NOT a mock of any employer platform (avoids confidentiality + "no rights you don't have" rule).

## Constraints

- **Deadline:** submissions due **Mon 2026-07-13, 9:00 PM ET**. ~3-4 working days from 2026-07-08.
- **Submit:** 3-min demo video, open-source repo (MIT ✓ in LICENSE), 100-200 word summary.
- **Rules:** open source; new work only (fresh repo ✓); no assets you lack rights to; team ≤ 2; personal Anthropic org (UUID `474eb356-d20a-4417-997d-0c59c21e897a`), not employer's.

## Judging criteria → priorities

- **Demo 30%** — working, compelling, "cool to watch". Build the money shot (messy file in → clean structure out in ~5s) early.
- **Claude Use 25%** — beyond basic: structured output, confidence scoring, learning loop.
- **Impact 25%** — named user: a data curator reformatting CRO files by hand today.
- **Depth & Execution 20%** — push past the first idea; sound engineering.

## Rough plan

- **Day 1:** file upload → raw table → mapper agent (structured output) → valid JSON out. CLI, no UI. Core must work.
- **Day 2:** validator vs reference `assay_type`/units + confidence flags + learning store (save/apply lab profile).
- **Day 3:** React review UI — diff table, yellow highlight, confirm button. This makes the demo.
- **Day 4:** polish, generate 3-4 synthetic "different-lab" files, record 3-min video, README, 100-200 word summary.

## Process note

This project uses **gsd-core** (https://github.com/open-gsd/gsd-core) as its process — the only framework in play; any earlier "plain vertical slices, no GSD" instruction is superseded. The loop is **Discuss → Plan → Execute → Verify → Ship**, with living artifacts (`PROJECT.md`, `STATE.md`, `.planning/`). Start a session with `/gsd-new-project` (or `/gsd-map-codebase` to map existing code). gsd-core is installed globally under the WSL `~/.claude`; Linux Node is provided via nvm (`. ~/.nvm/nvm.sh`).

**Current state (as of adopting gsd-core):** Day 1 committed on branch `feat/assayingest-core` — parser (CSV/Excel, multi-sheet, blank/dirty headers) → Claude structured-output mapper (per-field confidence + flags) → CLI (JSON draft + review gate). 32 tests + 1 live integration test, all green. `data/synthetic/` holds 4 different-lab demo files. **Next:** Day 2 — no-LLM validator (assay_type/units vs reference dict) + SQLite learning store (lab profile → auto-map on repeat signature).

## Coding conventions (from the builder)

- Clean Architecture as the lens: dependencies point toward the domain, not outward. Map infrastructure models (raw API responses) to domain models at the layer boundary — don't mix layers in one dataclass.
- Single Level of Abstraction per function; extract low-level detail into named private methods.
- Log-or-raise, never both. Keep `try` minimal; success-path logic in `else`.
- Error messages describe the consequence (what didn't happen), not the symptom.
- `__init__.py`: absolute imports. Internal files: relative imports fine.
- Pagination exit condition relies on the current response (`len(results) < limit`), never accumulated counters.
- Git commit messages: English, capitalized, one short imperative line (≤150 chars).

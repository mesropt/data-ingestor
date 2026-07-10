---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 1
current_phase_name: Robust File Reading
status: executing
stopped_at: Completed 01-02-PLAN.md (Excel header-detection vertical slice)
last_updated: "2026-07-10T09:42:35.776Z"
last_activity: 2026-07-10
last_activity_desc: Phase 1 execution started
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 2
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-09)

**Core value:** Claude proposes a mapping of a messy file onto whatever fields the user asked for, with honest per-field confidence; a human disposes; nothing is trusted or saved until every uncertain field is cleared. Zero hardcoded domain.
**Current focus:** Phase 1 — Robust File Reading

## Current Position

Phase: 1 (Robust File Reading) — EXECUTING
Plan: 3 of 5
Status: Ready to execute
Last activity: 2026-07-10 — Phase 1 execution started

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 8 | 3 tasks | 10 files |
| Phase 01 P02 | 4min | 3 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pivot: the product is domain-independent — the user defines target fields at runtime (name, optional description, optional constraints); zero fields/domains/vocabularies are hardcoded anywhere in the tool. The original fixed 7-field assay brief in CLAUDE.md is superseded.
- Pre-pivot, still true: validator + reference checking are plain Python, no LLM — but the "reference" is now the constraints the *user* declares per field, not a built-in vocabulary.
- Pre-pivot, still true: learning loop via SQLite profiles, no fuzzy matching — the differentiator, must be demonstrable on video — now keyed by (field set, column signature), not just (lab, signature).
- Roadmap revision (pivot): parser hardening remains structure-driven (header position, delimiter, decimal locale, sheet selection, table shape); PARSE-06 adds a human-assisted fallback — an unfamiliar structure asks the user for a hint instead of crashing — kept as Phase 1 ahead of fields/mapping/validation so downstream phases operate on a structurally-clean table.
- Roadmap revision (pivot): fields and the mapper's structured-output schema are generalized into their own phase (Phase 2) ahead of validation/learning — FIELD-01..05 (user-defined fields, constraints, templates, dynamic schema, optional presets) plus MAP-01..02 (dynamic Claude mapping) — since validation and learning both depend on a user-declared field set existing first.
- Roadmap revision (pivot): a source's file format can change over time, so the learning store is keyed by (field set, column signature) and one source may hold several profiles, one per format version; a changed layout yields a new signature that never matches an old profile — it falls back to Claude and can be learned as an additional profile, while old-format files keep matching their original profile (LEARN-05, in Phase 3). A structural hint from Phase 1 is persisted with its profile (LEARN-06) so odd layouts stop requiring a repeated hint.
- [Phase ?]: The D-14 decimal-locale ambiguity predicate (variance in comma-digit-count proves decimal_comma; uniform 3-digit groups are ambiguous) implemented exactly per 01-RESEARCH.md Pattern 3, including the single-value-column edge case (Pitfall 7).
- [Phase ?]: parse() dispatches CSV through the new structural detector (structure/delimiter.py + structure/locale.py); Excel and parse_file() are untouched in this plan -- Excel structural detection is deferred to plans 02-04 of Phase 1.
- [Phase 01-02]: _CONFIDENCE_MARGIN set to 0.05 (not RESEARCH.md's tentative 0.1) so zephyr's real 0.086 header margin resolves confidently — RESEARCH.md flagged the threshold as unvalidated and asked it to be tuned during execution; 0.1 would have wrongly flagged the plan's own reference fixture as not-confident
- [Phase 01-02]: HeaderDetection.index is always the top-scoring row, even when confident=False — Lets parse() pre-fill StructureQuestion.proposal.header_row_index with a real best guess (D-02 propose-never-auto-apply pattern) instead of re-deriving one from raw scores
- [Phase 01-02]: cli.py left untouched — Excel still routes through the legacy parse_file() path, not parse()'s new header detection — Out of this plan's files_modified scope; sheet selection is a later wave's job per the plan's own constraint, and cli.py's docstring already documents the deferral

### Pending Todos

None yet.

### Blockers/Concerns

- Research (pre-pivot, still largely applicable) flags the column-signature exact-match design (normalize, sort, hash) as having no single canonical external source — validate empirically against the actual synthetic files in Phase 3, including the format-drift case and the new (field set, signature) compound key.
- Every safety mechanism (parser shape/hint detection, validator, signature match, export gate, edit re-validation) must be enforced server-side/structurally, never as a UI-only nicety or a per-domain hack — the confirm endpoint in Phase 4 must independently re-check the gate.
- The dynamic mapper schema (Phase 2) and the human-assisted parsing hint (Phase 1/PARSE-06, LEARN-06) are the two genuinely new mechanisms introduced by the pivot with no direct Day-1 precedent — de-risk both early with focused tests before building the validator/learning loop on top of them.
- Live Claude API calls during demo recording risk latency/nondeterminism/failure — rehearse end-to-end, pin model version, keep a backup file/cached response for Phase 5.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | DEPLOY-01/02/03 (accounts, hosted deployment, ingest history) | Deferred to v2 | Requirements definition |
| v2 | MATCH-01 (fuzzy signature matching with confirmation) | Deferred to v2 | Requirements definition |
| v2 | PARSE-V2-01 (correct un-pivot ingestion of wide/transposed layouts — v1 only detects and flags, PARSE-05) | Deferred to v2 | Requirements definition |
| v2 | PARSE-V2-02 (automatic extraction of multiple tables from a single report sheet — v1 targets one chosen table) | Deferred to v2 | Requirements definition |

## Session Continuity

Last session: 2026-07-10T09:42:35.769Z
Stopped at: Completed 01-02-PLAN.md (Excel header-detection vertical slice)
Resume file: None

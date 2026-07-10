# Phase 3: Validator + Learning Loop - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Three pure-Python subsystems layered onto the Phase 2 mapper, provable end-to-end from the CLI:

1. **Validator (VAL-01/02/03)** — checks each mapped field, and every ranked alternative, against the constraints the *user declared* for that field (type, allowed_values, unit, min/max). No built-in vocabulary, zero LLM calls. Any objection forces the field back to needs-confirmation regardless of Claude's reported confidence.
2. **Learning loop (LEARN-01..06)** — an order-independent column signature; a SQLite profile keyed by (field set, signature, mapping) saved only from a fully-clear mapping; auto-apply on an exact signature match without calling Claude; strict fallback to Claude on any mismatch; one vendor may hold several profiles across format drift; a saved structural hint replays automatically.
3. **Export (EXPORT-02/03/04)** — CSV, Excel, and JSON, all derived from the Phase 2 canonical table, each accompanied by a provenance manifest.

Out of scope: the FastAPI backend and React UI (Phase 4); demo assets (Phase 5); parser hardening (filed todos).
</domain>

<binding_principles>
## Binding Principles (govern every decision below)

**P1 — Accuracy over convenience. Lives are at stake.**
The user stated AssayIngest often handles data where human lives depend on the result, so parsing must be accurate above all. Fail-closed: any ambiguity, any signature mismatch, any doubt → stop and ask the human or fall back to a fresh Claude proposal. Never auto-apply a stale or approximate profile. Speed and convenience never justify a silent guess. (See memory: phase-3-accuracy-principle.)

**P2 — Data confidentiality. The content may be unpublished research / know-how.**
Field *values* may be confidential scientific IP that must not reach a competitor or a third party (including Anthropic). Today the mapper sends headers + the first 6 data rows to the Anthropic API. Phase 3 must actively minimise what leaves the machine:
- The learning loop is itself a privacy control: a known format auto-maps from the local profile with **zero** Claude calls, so its data never leaves the machine.
- A privacy mode (D-10) lets the mapper send headers only, no values.
- The profile store is local SQLite — memory never leaves the machine.
Legal/contractual angle (Anthropic API terms, zero-data-retention, data rights) and a fully-local model option are deferred and MUST be raised at the end (see memory: raise-medical-certification, which now also carries the confidentiality/legal item).
</binding_principles>

<decisions>
## Implementation Decisions

### Profile store (LEARN-02/03)
- **D-01:** SQLite file, default `.assayingest/profiles.db` in the working directory (add to `.gitignore`), overridable with `--profiles-db PATH`. Persists across CLI runs so the demo money-shot ("second file from lab X = zero yellow") works out of the box and the store's location is visible.

### Column signature and format drift (LEARN-01/05)
- **D-02:** Signature normalisation is **strict** (P1): case-fold + trim + collapse internal whitespace + Unicode NFC, then order-independent (sorted header set) → hash. It does NOT touch typos, punctuation, or column membership. A typo, a renamed column, or an added/removed column yields a *different* signature → a *different* profile. The header set and column count define the signature. Rationale: over-normalising would let one lab's profile apply to a different file, sliding a value into the wrong field — unacceptable for medical data.
- **D-05:** Auto-apply (LEARN-03) only on an *exact* signature match for the chosen field set → apply the stored column mapping at confidence 1.0 without calling Claude. Any mismatch, including a vendor's format drifting over time (LEARN-04/05), NEVER applies a stale profile: it falls back to a fresh Claude proposal, which can itself be saved as an additional profile. One vendor → several profiles, one per signature; old-format files keep matching their old profile.

### Validator always runs on values (VAL-01/02/03)
- **D-03:** The validator runs on **every** value, even when a saved profile auto-mapped the file at confidence 1.0 (P1). A profile records only *which column → which field*; the values in a new file are new and must be checked. A constraint violation forces the field to needs-confirmation despite the profile's 1.0 or Claude's own confidence. Every one of Claude's ranked alternatives is validated, not only the top pick (VAL-02).
- **D-04:** A field with no declared constraints is never silently trusted (VAL-03) — it still depends on Claude's confidence and the human gate; the validator's objection, or its explicit absence, is shown alongside Claude's own reasoning in the CLI review.

### Learning saves and transparency (LEARN-02/06)
- **D-06:** Saving a profile (LEARN-02) is blocked unless the mapping is fully clear (zero yellow). Key: (field set, signature, mapping).
- **D-07:** A structural hint the user gave for an unfamiliar file in Phase 1 (StructuralHint / PARSE-06) is saved with its profile, so the same odd layout parses automatically next time without re-asking (LEARN-06).
- **D-08:** An auto-applied profile is shown **explicitly** in output ("applied saved profile <id>"), never disguised as a fresh parse (P1/P2 transparency). The manifest records provenance: auto-applied-from-profile vs fresh-Claude.

### Export and manifest (EXPORT-02/03/04)
- **D-09:** Export produces CSV + `.xlsx` + JSON, all derived from the one Phase 2 canonical table (Phase 2 D-15). Blocked until the mapping is_ready (zero yellow). Each export is accompanied by a JSON manifest = the saved profile in structure (field set, column signature, field→source-column mapping, inferred/confirmed flags, per-field confidence). Output dir via `-o DIR`, default beside the source file. The tool never writes on its own — export is always an explicit human command (P1).

### Privacy mode (from P2)
- **D-10:** A `--headers-only` (a.k.a. `--no-sample-rows`) flag makes the mapper send column headers only, no data values, to Anthropic. Mapping is less confident (more yellow for the human to resolve) but no value ever leaves the machine. Small addition (one flag + a branch in `_render_table`); high priority under P2. If planner scope is tight it may drop to backlog, but it is wanted in this phase.

### Claude's Discretion
- Exact SQLite schema, hashing algorithm (e.g. sha256 of the normalised joined header set), and CLI subcommand shape (`export`, `--save-profile`, etc.) are the planner's call, within the decisions above.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/ROADMAP.md` §"Phase 3: Validator + Learning Loop" — goal, 6 success criteria, requirement list
- `.planning/REQUIREMENTS.md` — VAL-01..03, LEARN-01..06, EXPORT-02..04 (full text)

### Phase 2 foundations this builds on
- `src/assayingest/canonical.py` — the canonical tidy table (Phase 2 D-15); all exports derive from it
- `src/assayingest/domain/models.py` — `MappingProposal.is_ready` / `FieldMapping.needs_confirmation` (the yellow gate the validator forces and the save/export gates check)
- `src/assayingest/fields/models.py` — `Field` constraints (type, allowed_values, unit, min, max, required) the validator checks against
- `src/assayingest/mapping/mapper.py` — `_render_table` (the 6-row send site D-10 gates), `_to_domain` (alternatives to validate per VAL-02)
- `src/assayingest/parsing/hint.py` — `StructuralHint` saved with the profile (D-07/LEARN-06)

### Project principles
- `CLAUDE.md` / `.claude/CLAUDE.md` — "trust the numbers", propose-not-write, Clean Architecture, error-names-the-consequence
- `.planning/phases/02-user-defined-fields-dynamic-mapper/02-CONTEXT.md` — D-12 (never convert units), the unifying "act only on knowledge the human supplied" rule
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `canonical.CanonicalTable` — the single source every export format serialises (no re-deriving per format).
- `FieldMapping.needs_confirmation` / `MappingProposal.is_ready` — the existing yellow gate; the validator sets it, the save/export steps read it.
- `Field` already carries every constraint the validator needs; no new constraint model.
- `StructuralHint` is already JSON-serialisable (Phase 1) — ready to persist in a profile row.

### Established Patterns
- Clean Architecture boundary: keep the SQLite store in an infrastructure module; the validator and signature are pure domain logic (no I/O, no SQLite import).
- Wire↔domain mapping already isolates infrastructure; the profile row is infrastructure, the mapping it restores is domain.
- Optional-client seam in `propose_mapping` — the auto-apply path must be reachable with NO client at all (a matched profile never constructs an Anthropic client).

### Integration Points
- CLI `run()` gains: signature computation → profile lookup → (auto-apply | Claude) → validator → review → save/export.
- The validator sits between the mapper output and the review render, on BOTH the Claude path and the auto-apply path.
</code_context>

<specifics>
## Specific Ideas

- Demo money-shot depends on D-01 persistence: same lab, first file several yellow → confirm → save; second file same signature → zero yellow, auto-applied 1.0, no Claude call. Rehearse this exact sequence in Phase 5.
- Privacy framing for the pitch: "the more it learns, the less your data leaves the building" (D-10 + learning-as-privacy-control).
</specifics>

<deferred>
## Deferred Ideas — RAISE AT THE END (user explicitly asked)

- **Formal medical certification / regulatory path** — CLIA, IEC 62304, ISO 13485, FDA SaMD. The hackathon (synthetic data, MIT demo) does not cover it; the user wants the gap named explicitly at project close. (Memory: raise-medical-certification.)
- **Data-confidentiality legal/contractual angle** — Anthropic API terms, zero-data-retention configuration, data-ownership rights when values are sent for mapping. Raise together with certification.
- **Fully-local model option** — run the mapper on a local model so no data ever leaves the perimeter. Architectural fork; out of scope while the project is Claude-bound per competition rules.

### Not in Phase 3 scope
- Parser hardening (encoding detection, .xls, ragged rows, Excel hazards) — filed in `.planning/todos/pending/`, belongs to a parser-hardening phase.

</deferred>

---

*Phase: 3-validator-learning-loop*
*Context gathered: 2026-07-10*

# Phase 4: API & Review UI - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A FastAPI backend + Vite/React frontend that expose the *already-built* Phase 1–3 library — parsing, structural-hint resolution, dynamic mapping, the no-LLM validator, and the SQLite learning loop — as the browser experience that is the demo's centerpiece. The full cycle works end-to-end in the browser: **define fields → upload → resolve structural hint inline → review side-by-side → resolve yellow fields → confirm → learn (save profile) → re-upload same-signature file shows zero yellow, auto-mapped with no Claude call.**

The API is a thin wrapper: it MUST call the existing library (`cli.run()` / the mapper / validator / learning store), never reimplement mapping, validation, signature, or the gate. The server independently re-checks the "no yellow fields" gate before persisting — it never trusts the client's own gate.

Requirements: API-01/02/03, UI-01..06.

Out of scope: multi-user auth / accounts (local single-user demo); parser hardening (deferred todos); demo assets + video + README (Phase 5); Postgres (the D-01 repository seam already allows a future swap, not built here).
</domain>

<binding_principles>
## Binding Principles (carry forward from Phase 3 — still govern)

**P1 — Accuracy over convenience, fail-closed (lives at stake).** The confirm/export gate is enforced **server-side** (API-02): the server re-runs the validator + `is_ready` check before persisting a profile, regardless of what the client sent. The UI's disabled-button gate (UI-05) is a UX convenience that MIRRORS the server gate, never replaces it. A yellow field can never be cleared by the client alone.

**P2 — Confidentiality (values may be unpublished research IP).** The `--headers-only` privacy mode from Phase 3 (D-10) MUST be reachable from the web upload — a per-upload toggle that sends Claude column headers only, no cell values, on ALL paths (including the inline structural-hint evidence, per the Phase 3 CR-01 fix). The learning loop remains a privacy control (a known format auto-maps locally, zero Claude calls). The profile + field-set stores stay local (SQLite on the server host), never a network DB in v1. Highlight `--headers-only` for the judges (Phase 5).
</binding_principles>

<decisions>
## Implementation Decisions

### Visual design (D-01) — review screen is the money shot
- **D-01:** Clean clinical/lab aesthetic, **light theme**, restrained blue-green accent, monospaced/tabular numerics. Uncertain (yellow) fields render as an **amber-highlighted cell with Claude's reason shown beside it** (not hidden behind a hover). Professional and calm — the safe, credible look for medical-adjacent data. A proper `artifact-design`-grade design pass (real type scale, considered spacing, both-theme tokens even if light is primary) — this is 30% of judging ("cool to watch").

### Yellow-field resolution interaction (D-02) — "human disposes"
- **D-02:** Three complementary controls on a yellow field: (a) **click a ranked-alternative chip** to pick that source column (chips show Claude's % confidence), (b) an **"accept"** action to take Claude's top proposal as-is, and (c) a **manual full-column dropdown** as the fallback when the correct column is not among Claude's ranked alternatives. This covers every case — the chips keep Claude's ranked alternatives (VAL-02) visible, the dropdown guarantees the human can always reach any column. Resolving a field clears its yellow state locally; the server still re-validates on confirm.

### Field-set template storage (D-03)
- **D-03:** Field-set templates (UI-01) are stored **server-side in the same SQLite** as the learning profiles, behind the same repository-style seam (D-01 from Phase 3). Rationale: one consistent local store, templates survive across browsers/machines and are reachable by the API, and it stays Postgres-swappable later. Not localStorage.

### Inline structural-hint UX (D-04)
- **D-04:** When the parser is unsure of a file's structure (UI-02 / PARSE-06), the browser shows an **inline form within the upload flow** (not a separate wizard step, not a blocking modal) — it presents the tool's question with a small preview of the first rows and lets the user answer (e.g. "which row is the header?") and re-submit in one flow. Under the `--headers-only` privacy toggle, the preview shows **no cell values** (headers/derived shape only), honoring the Phase 3 CR-01 fix.

### Claude's Discretion (planner/UI-researcher decide)
- Exact FastAPI route shape and request/response schemas (wire ↔ domain boundary applies — reuse the existing wire models where possible).
- How React is served (Vite dev server proxying FastAPI in dev; FastAPI serving the built static bundle for the demo — planner's call).
- React state/data-fetching approach, component library vs hand-rolled, and the design-token implementation (subject to the D-01 aesthetic and a UI-SPEC from `/gsd-ui-phase` / gsd-ui-researcher).
- Endpoint that lists/saves field-set templates and profiles.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3 foundations the API wraps (do NOT reimplement)
- `src/assayingest/cli.py` — `run()` / `_map_one` orchestration: signature → profile lookup → (auto-apply | Claude) → validator → review gate → save/export; the `headers_only` and structural-hint-replay wiring. The API mirrors this flow.
- `src/assayingest/learning/store.py` + `src/assayingest/learning/sqlite_store.py` — the `ProfileStore` repository seam (field-set templates reuse this pattern; API-03 auto-apply).
- `src/assayingest/learning/signature.py`, `learning/reconstruct.py` — column signature + fail-closed auto-apply reconstruction.
- `src/assayingest/validation/validator.py` — the no-LLM validator the server re-runs for the API-02 gate.
- `src/assayingest/domain/models.py` — `MappingProposal.is_ready` / `FieldMapping.needs_confirmation` / `validator_note` (the yellow gate + reason the UI renders).
- `src/assayingest/mapping/mapper.py` — `propose_mapping`, `_render_table` `headers_only` branch (P2 privacy toggle for the web upload).
- `src/assayingest/fields/` — the `FieldSet` / `Field` model + signature (UI-01 field-definition contract; field-set templates).
- `src/assayingest/parsing/hint.py` + structure-assist — `StructuralHint` for the inline-hint UX (UI-02).
- `src/assayingest/export/writers.py` — CSV/xlsx/JSON + manifest (confirm/export from the browser).

### Phase decisions carried forward
- `.planning/phases/03-validator-learning-loop/03-CONTEXT.md` — D-01..D-11, P1/P2 (the gate, privacy mode, exact-signature match, repository seam).
- `.planning/ROADMAP.md` §"Phase 4" — goal + 4 success criteria.
- `.planning/REQUIREMENTS.md` — API-01/02/03, UI-01..06 full text.
- `CLAUDE.md` / `.claude/CLAUDE.md` — stack (FastAPI + Vite/React), "trust the numbers", Clean Architecture, error-names-consequence.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The entire Phase 1–3 library is the backend's domain layer — the API is a transport adapter over `cli.run()`-equivalent orchestration. No mapping/validation/signature logic is rewritten.
- `ProfileStore` seam already isolates SQLite behind an interface — field-set template storage (D-03) plugs into the same pattern; a future Postgres store (multi-user) drops in without touching domain.
- Wire↔domain boundary mapping already exists in the mapper — the API's request/response schemas extend that discipline (Pydantic wire models at the HTTP edge, domain models inside).

### Established Patterns
- Clean Architecture: HTTP/React are outer layers; dependencies point inward to the domain. FastAPI handlers stay thin.
- Optional-client seam: auto-apply (API-03) must construct no Anthropic client — the API's auto-apply path reuses that.
- Server-side gate (P1): the confirm endpoint re-runs the validator + `is_ready`, never trusting the client.

### Integration Points
- FastAPI endpoints: upload (parse → hint-or-map → validate → JSON), confirm (server-side gate re-check → persist profile), auto-apply-on-upload (API-03), field-set template list/save, structural-hint resolve, export.
- React review screen consumes the mapping JSON: source columns left, target fields right, yellow cells with reason + ranked-alternative chips + manual dropdown, confirm/export disabled while any field is yellow.
</code_context>

<specifics>
## Specific Ideas

- The demo money-shot must be reproducible in the browser exactly as in the CLI (ROADMAP SC4): upload lab-X file → several yellow → resolve + confirm → save profile → upload second same-signature lab-X file → **zero yellow, auto-mapped, no Claude call**. Rehearse this exact sequence for the Phase 5 video. Good CLI fixtures already exist (`novascreen_batch01/02`, the same-signature corpus files).
- Privacy framing for the pitch: the `--headers-only` web toggle + local learning loop → "the more it learns, the less your data leaves the building." Show it to the judges.
</specifics>

<deferred>
## Deferred Ideas

- **Multi-user / auth / accounts** — v1 is local single-user; a real deployment with the Postgres store (enabled by the D-01 seam) is post-hackathon.
- **Formal medical certification / regulatory path** (CLIA / IEC 62304 / ISO 13485 / FDA SaMD) and the **data-confidentiality legal/contractual angle** (Anthropic API terms, zero-data-retention, data rights) + a **fully-local model option** — all deferred and MUST be raised at project close (memory: raise-medical-certification).

### Reviewed Todos (not folded)
- `parser-encoding-detection.md`, `parser-excel-hazards.md`, `parser-legacy-xls.md`, `parser-ragged-and-preamble.md` — matched on csv/excel keywords but are **parser-hardening**, explicitly deferred to their own phase in the ROADMAP, NOT Phase 4 (API/UI) scope. Considered and left deferred.

</deferred>

---

*Phase: 4-api-review-ui*
*Context gathered: 2026-07-10*

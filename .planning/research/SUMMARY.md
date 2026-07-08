# Project Research Summary

**Project:** AssayIngest — Day 2-4 (validator, learning store, review UI, API)
**Domain:** Human-in-the-loop AI data-mapping / curation review tool (CRO assay ingest)
**Researched:** 2026-07-09
**Confidence:** MEDIUM-HIGH

## Executive Summary

AssayIngest is a human-in-the-loop AI data-mapping tool: Claude proposes a structured mapping from messy CRO assay files to a fixed 7-field schema, a no-LLM validator checks it against a reference vocabulary, and a curator confirms before anything is persisted. This is a well-understood pattern (OpenRefine reconciliation, document-AI review layers like Rossum/Nanonets) — the research confirms AssayIngest isn't inventing new UX, it's executing the standard propose-flag-confirm-write loop well, on a 4-day budget. The project's stated differentiator — an explicit, named lab profile keyed by a column-header signature that flips a second same-lab file from several-yellow to zero-yellow — is genuinely novel relative to competitors, who improve invisibly/statistically rather than via a legible, camera-ready before/after.

The recommended approach layers cleanly onto the existing Clean Architecture: a new pure `domain/validator.py` (no-LLM, stdlib only) and `domain/signature.py` (order-independent, normalized header hashing) sit beside the existing `parsing/`, `mapping/`, and `domain/` packages; a new thin `application/` layer (`ingest.py`, `confirm.py`) is shared by both the existing CLI and a new FastAPI layer, so business logic never forks between entry points; a `storage/lab_profile.py` SQLite repository sits behind a `ProfileRepository` Protocol so the domain never imports `sqlite3` directly. Stack additions (FastAPI 0.139, Vite 8 + React 19 + TypeScript, stdlib `sqlite3`, no ORM) are all uncontroversial, low-risk, and match what's already named in `CLAUDE.md`.

The dominant risk is not the stack or architecture — it's silent failure of the exact properties the app is supposed to guarantee. Pitfalls research converges on one theme: every safety mechanism (validator, signature match, export gate, edit re-validation) must be enforced explicitly and server-side, never as a UI nicety, because a silent bypass anywhere directly contradicts the project's three non-negotiable principles. The single highest-stakes engineering decision is the column-signature function: too strict and the demo's money-shot (second file, zero yellow) never fires; too fuzzy and it silently cross-applies one lab's mapping to another lab's file at full confidence. Build this — and a unit test proving both directions — before anything else in Day 2.

## Key Findings

### Recommended Stack

Day 1's stack (Python 3.13, pandas/openpyxl, Anthropic SDK, Pydantic, pytest, uv) is already decided and unchanged. Day 2-4 adds an HTTP layer and a frontend around the existing mapper, using boring, current-stable, low-dependency choices throughout.

**Core technologies:**
- FastAPI 0.139.0 + uvicorn 0.51.0 + python-multipart 0.0.32: HTTP API wrapping the existing mapper — already named in `CLAUDE.md`; `python-multipart` must be added explicitly (Starlette no longer bundles it)
- stdlib `sqlite3` (no ORM): learning store persistence behind a hand-written `LabProfileRepository`
- Vite 8 + React 19 + TypeScript (react-ts template): review UI, fastest path to a working typed UI
- Vite dev-server proxy (not `CORSMiddleware`): avoids CORS for local-only demo
- Declare mapper-calling FastAPI endpoints as plain `def`, not `async def`, since the mapper makes a blocking Anthropic call

Explicitly avoid: an ORM for the one-table learning store, `axios`, Redux/MobX/Recoil, and Flask/Django.

### Expected Features

**Must have (table stakes):**
- Side-by-side source vs. mapped view, field-level confidence highlighting
- Visible reasoning per flagged field
- Accept/edit per field, ranked alternatives picker for ambiguous fields
- Explicit "block until clear" export gate, enforced server-side
- Audit trail as a byproduct of confirm-then-save-profile

**Should have (the stated differentiator):**
- Explicit, named lab profile with a camera-ready "second file, zero yellow" auto-map moment
- No-LLM validator enforcing a controlled vocabulary
- Column-signature keyed matching (exact, normalized, order-independent) — not fuzzy

**Defer (v2+):**
- Fuzzy/statistical cross-lab learning, multi-user roles/review queues, admin UI for the reference dictionary, production persistence (Postgres/cloud), undo/versioned mapping history

### Architecture Approach

Extend the existing Clean Architecture with one new thin orchestration layer (`application/`) shared by the CLI and a new FastAPI layer. A new pure `domain/validator.py` and `domain/signature.py` require zero I/O. A `storage/` package implements a `ProfileRepository` Protocol defined in `domain/ports.py`, keeping SQLite out of domain/application. `api/schemas.py` is a separate wire-model boundary from `mapping/schema.py`.

**Major components:**
1. `domain/validator.py` — validates full proposal incl. alternatives against reference dictionary; pure, no-LLM, re-flags rather than silently corrects
2. `domain/signature.py` — order-independent, normalized header hash; the learning-store join key
3. `storage/lab_profile.py` (+ `domain/ports.py` Protocol) — SQLite `ProfileRepository`, exact-signature-only lookup, scoped per lab_name
4. `application/ingest.py` + `application/confirm.py` — shared orchestration; confirm re-checks the gate server-side before persisting
5. `api/` (FastAPI) + `frontend/` (Vite+React) — thin presentation layers, built last

Suggested build order: validator, signature builder, repository, application layer (refactor CLI onto it), FastAPI, React UI, demo polish. Every step depends only on layers already built, so a CLI-only demo of the full learning loop is a legitimate fallback throughout.

### Critical Pitfalls

1. **Validator silently "fixes" instead of flagging** — normalization must be surfaced in the UI as an explicit correction, never applied invisibly
2. **Column-signature breaks on reorder/case vs. is too coarse and collides across labs** — normalize+sort before hashing, but match must be exact-only, scoped per lab_name
3. **Export gate enforced only in the React UI** — the confirm/export endpoint must independently re-run the "any field uncertain" check server-side
4. **Manual edit clears yellow without re-validation** — every edit must flow through the same validator before turning green
5. **Live LLM calls during demo recording risk latency/nondeterminism/failure** — rehearse end-to-end beforehand, pin model version, keep a backup file

## Implications for Roadmap

### Phase 1: No-LLM Validator
**Rationale:** Smallest, lowest-risk, pure, testable with zero new infra; unblocks nothing else so build first.
**Delivers:** `domain/validator.py` validating full proposals against the reference dictionary; wired into `cli.py`.
**Addresses:** No-LLM validator differentiator; "trust the numbers" principle.
**Avoids:** Pitfalls 1, 2, 3, 9.

### Phase 2: Column Signature + Learning Store
**Rationale:** The demo's differentiator hinges on this; exact-match semantics must be correct before the SQLite schema is written.
**Delivers:** `domain/signature.py`, `domain/ports.py`, `storage/lab_profile.py`, unit-tested in isolation.
**Uses:** stdlib `sqlite3`, no ORM.
**Implements:** Repository-behind-a-Protocol pattern.
**Avoids:** Pitfalls 4 and 5 — dedicated unit tests before Day 3.

### Phase 3: Application Layer + CLI Refactor
**Rationale:** Lets CLI and future API share identical sequencing; proves the full learning loop via the CLI before any UI exists.
**Delivers:** `application/ingest.py`, `application/confirm.py`; `cli.py` refactored onto them.
**Uses:** Phase 1 + 2 components composed together.
**Implements:** Application-layer use-case pattern.

### Phase 4: FastAPI Layer
**Rationale:** Low risk once the application layer is proven — a thin wrapper, not new business logic.
**Delivers:** `api/app.py`, `api/routes.py` (`/upload`, `/confirm`), `api/schemas.py`; repository injected via `Depends()`.
**Uses:** FastAPI, uvicorn, python-multipart.
**Avoids:** Pitfall 6 — confirm endpoint independently re-validates server-side.

### Phase 5: React Review UI
**Rationale:** Last major piece — presentation over an already-correct backend.
**Delivers:** Side-by-side review screen, yellow highlighting + reason text, ranked-alternative picker, disabled Confirm button until zero yellow, "auto-mapped from lab profile" badge.
**Addresses:** Table-stakes UI features + differentiator legibility.
**Avoids:** Pitfall 7 — re-validation on edit built in from the start.

### Phase 6: Demo Data & Recording
**Rationale:** Content and rehearsal only; the capability to pin/replay a known-good response must exist by end of Phase 5.
**Delivers:** 3-4 synthetic different-lab files (one pair sharing a signature; one exercising each life-sciences hazard), a rehearsed recording script, 3-minute video, README, summary.
**Avoids:** Pitfall 8 — rehearse end-to-end, pin model version, keep a backup file and cached response.

### Phase Ordering Rationale

- Validator and signature-builder first: pure, dependency-free, independently testable, de-risk the two most failure-prone mechanisms early.
- Application layer before API layer: prevents inline sqlite3/Anthropic calls in route handlers.
- React UI last by design: a CLI-provable full loop is a legitimate fallback if UI time runs short.
- Demo data/recording last: depends on every prior phase being correct; its biggest risk is best mitigated by rehearsal time that only exists once the rest is stable.

### Research Flags

Needs deeper research: Phase 2 (exact-match signature design has no single canonical external source — validate empirically against the actual synthetic files); Phase 6 (live-demo reliability engineering is a hackathon-specific practice with thin prior art).

Standard patterns (skip research-phase): Phase 1 (rules-engine/guardrail pattern), Phase 3 (Clean Architecture use-case pattern, grounded in the mapped codebase), Phase 4 (boilerplate FastAPI + Depends() DI), Phase 5 (standard HITL review-table pattern).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Versions cross-verified against pypi.org/npm registry directly |
| Features | MEDIUM | Grounded in comparable-tool analysis; no case study for this exact domain combination |
| Architecture | HIGH | Grounded directly in the existing, already-mapped codebase |
| Pitfalls | MEDIUM | Web-corroborated general patterns plus static analysis of this codebase's own CONCERNS.md; no exact-combination case study exists |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- No canonical external source validates the exact column-signature hashing recipe — it follows from the project's own principles rather than external authority; validate empirically during Phase 2.
- Life-sciences data hazards (unit scale, date locale, replicate columns) are synthesized from adjacent bioactivity-curation literature — confirm each is exercised by a synthetic demo file (Phase 6).
- Demo-recording reliability practices are a hackathon-specific synthesis — treat as a starting checklist, refine based on observed API variance during rehearsal.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `.planning/codebase/ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `CONCERNS.md` (2026-07-09)
- pypi.org direct registry fetches: fastapi, pydantic, uvicorn, python-multipart
- registry.npmjs.org direct fetches: vite, react, zustand, create-vite, tailwindcss, typescript

### Secondary (MEDIUM confidence)
- FastAPI Clean Architecture layering guides; HITL design pattern sources (Zapier, Redis, Databricks, ScrapingAnt, Matillion); document-AI confidence/review UX (Microsoft Learn, LandingAI, Extend, Nanonets); OpenRefine reconciliation docs; LLM guardrail pattern articles; bioactivity data curation error literature (PMC/PLOS ONE, CDD)

### Tertiary (LOW confidence)
- Schema-fingerprinting general background (Zeenea); live-demo LLM reliability practices (propelcode.ai, Devpost)

---
*Research completed: 2026-07-09*
*Ready for roadmap: yes*

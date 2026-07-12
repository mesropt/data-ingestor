# Phase 4: API & Review UI — Discussion Log

**Date:** 2026-07-10
**Mode:** discuss (human-facing questions in Russian per builder's language)

> Human-reference audit trail only. Downstream agents consume CONTEXT.md, not this file.

## Areas selected for discussion

The builder selected all four surfaced gray areas: review-screen look, yellow-field resolution, field-set template storage, inline structural-hint UX. The following were pre-locked by PROJECT.md/CLAUDE.md and not re-asked: React+Vite frontend, FastAPI backend wrapping the existing library, local single-user (no auth), server-side SQLite learning store, server independently re-checks the no-yellow gate.

## Decisions

### 1. Review-screen look (→ D-01)
- Options: (A) clean clinical/lab, light theme [chosen, recommended]; (B) dark data-tool theme; (C) minimal, colour only on yellow.
- **Chosen:** A — light clinical aesthetic, restrained blue-green accent, amber highlight + visible reason on uncertain fields. Credible for medical-adjacent data; strongest "cool to watch" for judging.

### 2. Yellow-field resolution (→ D-02)
- Options: (A) alternative chips + accept + manual dropdown fallback [chosen, recommended]; (B) dropdown only; (C) chips only.
- **Chosen:** A — chips keep Claude's ranked alternatives (VAL-02) visible, accept takes the top proposal, manual dropdown guarantees the human can always reach any column. Covers every case.

### 3. Field-set template storage (→ D-03)
- Options: (A) server SQLite like profiles [chosen, recommended]; (B) browser localStorage.
- **Chosen:** A — same local store + repository seam as the learning profiles; consistent, portable, API-reachable, Postgres-swappable.

### 4. Inline structural-hint UX (→ D-04)
- Options: (A) inline form in the upload flow [chosen, recommended]; (B) modal; (C) separate wizard step.
- **Chosen:** A — one flow, good for the demo; under `--headers-only` the preview shows no cell values (Phase 3 CR-01 fix honored).

## Deferred / redirected
- Multi-user/auth, Postgres, formal medical certification + confidentiality legal angle + fully-local model → deferred (cert to be raised at project close).
- Parser-hardening todos matched on keywords but are out of Phase 4 scope → left deferred.

## Claude's discretion (noted in CONTEXT.md)
- FastAPI route/schema shapes, React serving model (Vite dev proxy vs FastAPI static), state/data-fetching approach, design-token implementation (subject to a UI-SPEC).

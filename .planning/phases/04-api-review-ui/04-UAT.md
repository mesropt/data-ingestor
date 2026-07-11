---
status: testing
phase: 04-api-review-ui
source: [04-VERIFICATION.md, 04-06-SUMMARY.md]
started: 2026-07-11
updated: 2026-07-11
---

## Current Test

number: 1
name: End-to-end browser money-shot (define → upload → resolve → confirm → re-upload → zero amber + banner)
expected: |
  The full learning-loop cycle works visibly in the browser, and the second same-signature
  upload shows zero amber fields with the "0 Claude calls" banner.
awaiting: user response

## How to run the stack (one command each)

```bash
# 1. build the frontend bundle
cd frontend && npm run build && cd ..
# 2. run the server (serves the built React app at http://127.0.0.1:8000 and the API under /api)
ANTHROPIC_API_KEY=<your-key-inline> .venv/bin/python -m uvicorn assayingest.api.app:app --port 8000
# then open http://127.0.0.1:8000
```
(The API key is only needed for the FIRST upload's Claude mapping; the money-shot second
upload auto-applies locally with zero Claude calls.)

## Tests

### 1. Define + save a field set (UI-01)
expected: In "Define Fields", create/save a field set (e.g. the assay-potency shape). It persists via /api/field-sets.
result: [pending]

### 2. Upload → side-by-side review with amber fields (UI-02/03/04)
expected: Upload data/synthetic/novascreen_batch01.csv with that field set. Review loads with source columns left, target fields right; several amber rows each show Claude's reason inline (always visible, never hover-only) + validator_note where present + ranked confidence chips + Accept + manual dropdown.
result: [pending]

### 3. Resolve every amber field; gate stays locked until clear (UI-04/05)
expected: Resolve each amber field via chip-click / Accept / manual dropdown; each turns green. "Confirm & Save Mapping" stays DISABLED (with tooltip) until the last field clears, then enables.
result: [pending]

### 4. Confirm + export (API-02 server-side gate; EXPORT)
expected: Click "Confirm & Save Mapping" → success toast; footer switches to ExportBar (CSV / Excel / JSON / Manifest), all four download real files.
result: [pending]

### 5. Money-shot: second same-signature upload = zero amber, no Claude call (UI-06/API-03)
expected: Re-upload data/synthetic/novascreen_batch02.csv (same headers) with the SAME field set. Review loads directly with the accent "Auto-mapped from a saved profile — 0 Claude calls." banner, ZERO amber rows, Confirm already enabled.
result: [pending]

### 6. Privacy: headers-only hides cell values (P2)
expected: Toggle "Headers only" on a fresh upload of a structurally-ambiguous file; the StructuralHintPanel preview shows column names + row count only, NO cell values.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

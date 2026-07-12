---
status: passed
phase: 02-user-defined-fields-dynamic-mapper
source: [02-VERIFICATION.md]
started: 2026-07-10
updated: 2026-07-10
---

## Current Test

number: 1
name: Confirm the live-evidence transcript is accurate
expected: |
  `02-LIVE-EVIDENCE.md` records that running the reagent-inventory preset against
  `verity_reagents_stock.xlsx` maps all six fields at confidence 1.00, leaves
  `flagged: []`, and exits 0. The verifier notes this transcript is reconstructable
  from committed files alone, so it cannot itself prove a billed API call occurred.
  A human with credentials confirms it by running the command once.
awaiting: none — closed

## Tests

### 1. Confirm the live-evidence transcript is accurate
expected: |
  ANTHROPIC_API_KEY=... uv run assayingest --fields presets/reagent-inventory.yaml \
    --hint header-row=2 --hint decimal=. data/synthetic/verity_reagents_stock.xlsx

  Six green fields, `✓ READY: all fields clear`, exit code 0.

  Equivalently: ANTHROPIC_API_KEY=... uv run pytest tests/test_cross_domain.py -q
  → 4 passed (the 4th is the live mapping call).
result: passed — live run 4/4 green (2026-07-10), orchestrator-run with real key

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

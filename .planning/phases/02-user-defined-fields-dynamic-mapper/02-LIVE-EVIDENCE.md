---
phase: 02-user-defined-fields-dynamic-mapper
kind: live-evidence
recorded: 2026-07-10
recorded_by: orchestrator (real ANTHROPIC_API_KEY, real billed calls)
---

# Phase 2 — live evidence

Every automated test in this repo runs offline. Four are credential-gated and skip
without `ANTHROPIC_API_KEY`, so their *outcome* is not recorded by a green suite.
This file records what happened when they were actually run, so the claims below rest
on observed behaviour rather than on a narrative in a SUMMARY.

Reproduce with:

```bash
ANTHROPIC_API_KEY=... uv run pytest tests/test_cross_domain.py tests/test_max_tokens_live.py -q
ANTHROPIC_API_KEY=... uv run assayingest --fields presets/reagent-inventory.yaml \
  --hint header-row=2 --hint decimal=. data/synthetic/verity_reagents_stock.xlsx
```

Result: `5 passed in 32.93s`; CLI exit code `0`.

## 1. ROADMAP SC3/SC5 — a brand-new field set from a neighbouring domain

`presets/reagent-inventory.yaml` describes a stockroom. The fixture's headers share no
vocabulary with its field names, and it carries a `Reordered?` column the field set
never asked for. No code under `src/` knows any of these words.

```
  ✓ catalogue_number <- 'SKU'  (conf 1.00)
  ✓ name          <- 'Item'  (conf 1.00)
  ✓ quantity      <- 'On hand'  (conf 1.00)
  ✓ unit          <- 'Units'  (conf 1.00)
  ✓ expiry_date   <- 'Use By'  (conf 1.00)
  ✓ shelf         <- 'Location'  (conf 1.00)
```

Canonical output — `quantity` is a real number, `expiry_date` converted to ISO because
the preset declared `date_format`, and nothing is flagged:

```json
  "records": [
    {
      "catalogue_number": "AB-11023",
      "name": "Anti-FLAG M2 antibody",
      "quantity": 2.5,
      "unit": "mL",
      "expiry_date": "2026-03-01",
      "shelf": "Freezer B / rack 4"
    },
```

```
  "flagged": []
✓ READY: all fields clear — safe to confirm and export.
```

Exit code `0` — the export gate is open only because every field is genuinely clear.

## 2. RESEARCH Open Question 1 — the 50-field token budget

`tests/test_max_tokens_live.py` issues one billed call with a synthetic 50-field set
(the D-04 cap) and asserts `stop_reason != "max_tokens"`. It passes:
`_MAX_TOKENS = 16000` is validated by measurement, not estimated. The test asserts
non-truncation, not headroom — if the cap ever rises above 50 fields, re-run it rather
than reasoning about it statically.

## 3. What these runs did NOT establish

On `pinnacle_labs_export.csv`, the `value` field still returns `needs_confirmation=true`
at confidence 0.95, with reasoning that explicitly credits the parser's decimal-comma
evidence. The D-22 mechanism works; the yellow flag is Claude's own judgment, and the
code deliberately does not override it. Making a repeat file go green is the Phase 3
learning loop's job — see the withdrawn must_have clause in `02-01-PLAN.md`.

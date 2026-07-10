# Phase 3: Validator + Learning Loop — Discussion Log

**Date:** 2026-07-10
**Mode:** default (interactive), simplified language per builder request

> Human reference only. Downstream agents read `03-CONTEXT.md`.

## Gray areas presented

All four selected: profile store location, signature/format-drift, validator on an auto-applied profile, export/manifest.

The builder twice asked for plainer language ("объясни суперпросто"); each area was re-explained with everyday analogies before decisions were taken.

## Two binding principles the builder introduced mid-discussion

1. **Accuracy over convenience — "we often deal with human lives."** Reframed every decision toward fail-closed behaviour. Confirmed the strict-signature and always-validate choices rather than changing them.
2. **Data confidentiality — values may be unpublished research know-how that must not reach a competitor or Anthropic.** Prompted an honest account that the mapper currently sends headers + 6 real rows to the API, and three mitigations: the learning loop as a privacy control (known formats → zero Claude calls), a headers-only privacy mode (D-10), and local SQLite for memory. Legal/contractual and fully-local-model options deferred to the end.

## Decisions (see 03-CONTEXT.md for full text)

- **D-01** Store: `.assayingest/profiles.db` in the working dir, `--profiles-db` override; persists for the demo.
- **D-02** Signature: strict normalisation (case/whitespace/order + NFC), never typos/punctuation/membership; drift → new profile.
- **D-03** Validator runs on every value even under an auto-applied 1.0 profile; objection forces yellow; all alternatives validated.
- **D-04** Unconstrained field never silently trusted; objection shown beside Claude's reasoning.
- **D-05** Auto-apply only on exact signature match; any mismatch falls back to Claude, never a stale profile.
- **D-06** Save blocked unless fully clear; key (field set, signature, mapping).
- **D-07** Structural hint saved with the profile (LEARN-06).
- **D-08** Auto-applied profile shown explicitly; manifest records provenance.
- **D-09** Export CSV/xlsx/JSON from the canonical table, blocked until clear, with a provenance manifest; `-o DIR`; tool never writes on its own.
- **D-10** `--headers-only` privacy mode: send headers, no values. Taken into Phase 3 (builder: "так и делаем").

## Deferred — must be raised at the end

Formal medical certification (CLIA/IEC 62304/FDA SaMD); data-confidentiality legal/contractual angle (Anthropic terms, ZDR, data rights); fully-local model option. The builder explicitly asked that the certification question be raised at the end.

## Not committed by choice

Per the builder's standing instruction across this project, `.planning/` docs are written to the working tree; commits happen but the builder has been told each time.

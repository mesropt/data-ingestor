# Phase 2: User-Defined Fields + Dynamic Mapper — Discussion Log

**Date:** 2026-07-10
**Mode:** default (interactive)

> Human reference only. Downstream agents read `02-CONTEXT.md`.

## Gray areas presented

All four selected:

1. How the user declares fields (FIELD-01 says "in the UI"; the UI is Phase 4)
2. What a field may declare (FIELD-02)
3. What "normalised" means in the canonical table (EXPORT-01)
4. Presets: which domains, and how they read as data rather than code

Alongside the selection the builder asked: *"я бы хотел визуально видеть что есть на текущий момент. это возможно?"*

## Interlude — a state snapshot

Published from real tool output on real fixtures (not a mockup):
https://claude.ai/code/artifact/b5f31a03-aced-4114-a3cf-8b38b4897da0

Showed the five-stage chain, `pinnacle_labs_export.csv` end-to-end (2 yellow), `zephyr_bio_ZB-2025.xlsx` asking then resolving with a hint (7/7 green), `apex_labs_wide_matrix.xlsx` refusing honestly, the four places the domain is currently hardcoded, and the two defects the live run exposed.

## Area 1 — how fields are declared

**Q:** Which format? → **"Оба: YAML для людей, JSON для машин"** (D-02).
**Q:** How many fields may a set hold? → **"50"** — taken as a hard, named limit with a clear error (D-04).

Consequences surfaced and recorded: `PyYAML` becomes a dependency, and `yaml.safe_load` is mandatory (D-03) — `yaml.load` constructs arbitrary Python objects, which is a remote-code path in a tool built to ingest strangers' files.

## Area 2 — what a field may declare

**Builder:** *"не знаю, решим сам. главное — чтобы было максимально полезно в реальной работе учёным."*

Decided against the criterion "what catches a scientist's mistakes", not "what is cheap". Six constraints (D-05..D-11): `name`/`description`, `type`, `allowed_values` (case-insensitive), `unit`, `required`, `min`/`max`, `date_format`.

Two were **added beyond the requirement**, deliberately:

- `min`/`max` — the generalised form of `reference.py`'s `UNIT_VALUE_RANGES`, which exists to catch the 1000× nM-vs-µM error. Dropping it while removing hardcoded domain would be a regression dressed as progress.
- `date_format` — the live run showed `assay_date` going yellow on `01/01/2025` because DD/MM and MM/DD are indistinguishable. A declared format ends that permanently.

## Area 3 — what "normalised" means

The unit question was re-asked twice in plainer language (*"не понял — объясни проще"*), framed as: the file says µM, you asked for nM; does the tool multiply by a thousand, or stop and ask?

**Answer: stop and ask** (D-12). Converting requires the tool to know that `n` is 10⁻⁹ — domain knowledge the project forbids. And silent ×1000 on a stranger's numbers is precisely what "trust the numbers" exists to prevent.

Dates decided by the same rule (D-13): converted to ISO only when the human declared `date_format`; otherwise passed through as written and flagged. Decimal commas ARE converted here (D-14) — Phase 1 deferred exactly that.

**The rule that unifies them:** *the tool may act on knowledge the human supplied, never on knowledge it inferred about the world.* A declared `date_format` is permission; a unit prefix table would be a belief.

## Area 4 — presets

**Q:** Which non-life-sciences preset proves universality? → **"Склад реактивов"** (reagent inventory) (D-20, D-21).

Chosen over bank transactions: a neighbouring world with entirely different fields makes the point legibly at a Life Sciences hackathon, whereas finance reads as foreign to the track. Presets are YAML files loaded by path — no registry, no import, no per-preset code branch. That is what makes them provably data.

## Decided without asking (Claude's call, recorded)

- **Dynamic schema** built with `pydantic.create_model` and `Literal[tuple(names)]` for `target_field` (D-16) — Claude structurally cannot invent a field. A free `str` validated afterwards would demote a schema guarantee to a runtime check.
- **Two live-run defects folded into this phase** (D-22, D-23): the mapper never receives `RawTable.column_locales`, so Claude re-asks about a comma the parser already resolved; and a blocked mapping exits 0, indistinguishable from success.

## Scope handling

Unit conversion, date-format inference, per-value synonym maps, and field-set versioning were all raised and pushed to `<deferred>` — the first two on principle, not merely for time.

## Not committed

Per the builder's standing instruction, `02-CONTEXT.md` and this log are written to the working tree but left uncommitted.

# Synthetic demo data

Fully synthetic CRO assay exports — no confidential or real data. Each "lab" formats
its file differently on purpose, so the mapper has real work to do. Target fields the
mapper must produce: `compound_id`, `assay_type`, `value`, `unit`, `target`,
`n_replicates`, `assay_date`.

| File | Lab | The mess it demonstrates |
|------|-----|--------------------------|
| `novascreen_batch01.csv` | NovaScreen | **Missing unit column** (blank header). Unit must be *inferred* from the value range (0.8–880 → nM) and flagged yellow. Terse headers: `cmpd`, `potency`, `target_gene`. |
| `helixbio_export.csv` | HelixBio | **Unit embedded in the header** `Conc (uM)` → must be extracted to `unit = µM`. Dates are `DD/MM/YYYY` (ambiguous vs MM/DD). `# Reps` → `n_replicates`. |
| `crestchem_results.csv` | Crestchem | **Mixed assay types + units in one file**: `Inhibition %` (→ `%inhibition`, unit `%`), `IC50`/`Kd` in `nM`. Assay labels need normalization. Leading space in the `ID` header to strip. |
| `novascreen_batch02.csv` | NovaScreen | **Learning-loop payload.** Identical column signature to `batch01`. First NovaScreen file = several yellow fields; this second file should auto-map at confidence 1.0 from the saved lab profile — zero yellows. |

## Demo narrative (the money shot)

1. Upload `novascreen_batch01.csv` → mapper returns a draft; the **unit** field is yellow
   ("no unit column; inferred nM from value range") + waits for human confirm.
2. Curator confirms `unit = nM`. Mapping is saved as the **NovaScreen lab profile**.
3. Upload `novascreen_batch02.csv` (same lab, same columns) → **zero yellow fields**,
   auto-mapped at confidence 1.0. That contrast is the differentiator.

## Value-range heuristic (for unit inference / validation)

Typical potency magnitudes, useful for the no-LLM validator:

- `nM`: ~0.1 – 1000
- `µM`: ~0.001 – 100 (often < 10 for potent compounds)
- `%` (inhibition): 0 – 100

These overlap by design — which is exactly why a bare guess is unsafe and the field must
be flagged for human confirmation rather than silently filled.
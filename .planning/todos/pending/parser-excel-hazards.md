---
kind: enhancement
area: parsing
surfaced_by: data/synthetic/lab_corpus/wild
created: 2026-07-10
---

# Excel-specific hazards from the wild corpus

Supported `.xlsx` files that parse without crashing but need real handling in
the parser-hardening phase:

- `wild/10_genelab_date_disaster.xlsx` — Excel auto-converted gene names and
  ratios/titres into dates and IDs into scientific notation. Silent upstream
  corruption; at minimum detect and flag columns whose stored type disagrees
  with a plausible declared type.
- `wild/11_horizon_error_values.xlsx` — cells hold Excel error strings
  (`#REF!`, `#DIV/0!`, `#N/A`). Should surface as flags, not slip through as
  data.
- `wild/12_kaiser_crosstab.xlsx`, `wild/13_sonora_multiheader.xlsx` — two-row /
  merged group headers needing concatenation; candidates for the
  StructureQuestion path.
- `wild/14_carbon_hidden.xlsx` — hidden rows/cols carry the superseded vs true
  value; decide whether hidden cells are dropped or flagged.
- `wild/15_probe_ref_in_comments.xlsx` — the reference range lives only in cell
  comments, which pandas/openpyxl-via-pandas never sees.

None are in scope for the current phase; filed so they are not silently lost.

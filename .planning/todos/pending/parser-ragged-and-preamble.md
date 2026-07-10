---
kind: enhancement
area: parsing
surfaced_by: data/synthetic/lab_corpus
created: 2026-07-10
---

# Handle ragged rows, preamble/footer, and multi-table CSVs

Currently refused with a named "rows do not form a consistent table" error:
- `edge/cinder_tumor.csv` — preamble junk + footer lines + header not on row 1.
- `edge/redwood_coag.csv` — ragged rows (missing/extra fields), empty results.
- `edge/pallas_allergy.csv` — two tables with different schemas in one file
  (this one currently parses as one 4-col table — verify that is acceptable or
  should become a StructureQuestion).

These overlap the existing table-shape / StructureQuestion machinery: the right
outcome for most is a returned StructureQuestion proposing the real data region,
not a hard refusal. Parser-hardening phase.

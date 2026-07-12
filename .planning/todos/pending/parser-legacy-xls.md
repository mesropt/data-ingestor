---
kind: enhancement
area: parsing
surfaced_by: data/synthetic/lab_corpus
created: 2026-07-10
---

# Read legacy binary .xls (OLE2/BIFF), or keep refusing by decision

`edge/foxglove_cmp.xls` and `edge/umbra_cbc.xls` are the old binary format
openpyxl cannot open. They are currently refused with a named error telling the
user to re-save as .xlsx.

Decision needed (dependency-level, like the PyYAML checkpoint): add `xlrd` (or
`pyexcel-xls`) to read `.xls`, or keep the honest refusal. If read: route `.xls`
through a separate reader, keep `.xlsx` on openpyxl. `foxglove` also splits data
across sheets; `umbra_cbc.xls` + `umbra_cbc_1.xls` are a near-duplicate pair for
a dedup case.

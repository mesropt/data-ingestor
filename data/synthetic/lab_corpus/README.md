# Lab report corpus — parser stress fixtures

53 synthetic lab-report files spanning many vendors, panels (CBC, CMP, lipid,
thyroid, coag, PCR, immuno, tumor, allergy, urine) and layouts (long, wide,
matrix/transposed, two-patient batch, multi-table). Ground truth for the
quirks each file carries is in `manifest.json` and `MAP.md`; the `edge/`
subfolder holds deliberate parser-killers (`manifest_edge.json` / `MAP_edge.md`).

All data is synthetic. Nothing here derives from any real patient, vendor, or
confidential source.

## How the tests use it

`tests/test_real_corpus.py` runs `parse()` over every file and pins Phase 1's
D-05 invariant: the parser returns a `RawTable`, returns a `StructureQuestion`
when structure is genuinely unfamiliar, or raises a **named** `ValueError` a
curator can act on — and never leaks a raw pandas/openpyxl/csv traceback.

Running this corpus is what surfaced eight files that previously crashed with a
library traceback (legacy binary `.xls`, non-UTF-8 CSVs, ragged rows, a
zero-byte file); those are now named errors.

## Known-unhardened, tracked for the parser-hardening phase

These files parse without crashing but are not yet handled *well* — they are
refused with a named error where a future phase should instead read them:

- `edge/bluecrest_cmp.csv` (cp1251), `edge/silvarea_immuno.csv` (latin-1) —
  encoding auto-detection.
- `edge/foxglove_cmp.xls`, `edge/umbra_cbc.xls` — legacy `.xls` reading (needs
  an `xlrd`-class dependency decision).
- `edge/cinder_tumor.csv`, `edge/redwood_coag.csv` — ragged rows / preamble +
  footer trimming.

See `.planning/todos/pending/` for the tracked items.

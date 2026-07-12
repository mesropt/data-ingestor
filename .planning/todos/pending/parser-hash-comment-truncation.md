---
kind: bug
area: parsing
surfaced_by: data/synthetic/helixbio_export.csv
created: 2026-07-12
---

# `parse()`'s CSV comment stripping truncates a line at any mid-line `#`, silently dropping a column

`parsing/structure/delimiter.py::_read_or_name_the_failure` reads CSVs via
`pd.read_csv(path, sep=delimiter, engine="python", comment="#", dtype=str)`.
pandas' `comment=` kwarg does not only ignore whole lines that *begin* with
the character — for the `python` engine it truncates the rest of ANY line
from the first `#` found anywhere in it, even mid-line, even inside a header
row that is not a comment at all.

`data/synthetic/helixbio_export.csv` has a `# Reps` header column. Its header
row `Compound Name,Endpoint,Conc (uM),Gene Symbol,# Reps,Experiment Date`
gets silently truncated to `Compound Name,Endpoint,Conc (uM),Gene Symbol,`
(5 columns, last one empty) — every data row still has 6 columns, so pandas
treats the first column as an unnamed index and drops the compound ID from
every row. Reproduced directly:

```python
from assayingest.parsing.table import parse
table = parse("data/synthetic/helixbio_export.csv")
table.headers  # ['Compound Name', 'Endpoint', 'Conc (uM)', 'Gene Symbol', '']
table.rows[0]  # ['EC50', '0.045', 'EGFR', '3', '03/11/2025']  -- HLX-100 is GONE
```

Any vendor export with a literal `#` anywhere in a header cell (`# Reps`,
`#samples`, `Item #`) silently loses its first column through this path. The
older/legacy `parsing/table.py::parse_file` entry point (still used by the
CLI) does NOT go through this code path and parses the same file correctly
(`tests/test_parsing.py`) — only the newer structural-detection `parse()`
entry point (used by `service.resolve_or_map`, and therefore every
`/api/upload` call) is affected.

Approach: stop trusting pandas' `comment=` kwarg for anything beyond
leading-line comments. Either (a) pre-scan lines and strip only ones that
START with `#` before handing the buffer to pandas (no `comment=` kwarg at
all), or (b) quote/escape data before sniffing. Needs a real fix + a
regression test asserting a `#` inside a non-comment header/data cell
survives verbatim, plus confirmation that `pinnacle_labs_export.csv`'s
genuine leading-line comments (`# Pinnacle Labs...`, `# generated: ...`)
still strip correctly. Belongs in the parser-hardening phase, alongside the
existing delimiter/locale/encoding detection work.

Discovered during Phase 10 Plan 05 (10-05) while writing an HTTP-level
integration test for the `date_question` response arm; worked around there
with an inline CSV fixture rather than the real file (see that phase's
`deferred-items.md`).

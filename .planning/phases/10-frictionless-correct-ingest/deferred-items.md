# Deferred items — Phase 10

Out-of-scope discoveries logged during execution, not fixed (per the
executor's scope boundary: only fix issues directly caused by the current
task's changes).

## `parse()`'s CSV comment-stripping truncates any line containing a literal `#`, not just lines starting with one

**Found during:** 10-05 Task 2, while writing an HTTP-level integration test
that uploads `data/synthetic/helixbio_export.csv` (which has a `# Reps`
header column) through the real `parse()` pipeline.

**Issue:** `parsing/structure/delimiter.py::_read_or_name_the_failure` calls
`pd.read_csv(path, sep=delimiter, engine="python", comment="#", dtype=str)`.
pandas' `comment` parameter does not only ignore lines that *begin* with the
comment character — for the `python` engine it truncates the REST OF ANY
LINE from the first `#` found anywhere in it, even mid-line. Reproduced
directly:

```python
from assayingest.parsing.table import parse
table = parse("data/synthetic/helixbio_export.csv")
table.headers  # ['Compound Name', 'Endpoint', 'Conc (uM)', 'Gene Symbol', '']
table.rows[0]  # ['EC50', '0.045', 'EGFR', '3', '03/11/2025']  -- HLX-100 is GONE
```

The header row `Compound Name,Endpoint,Conc (uM),Gene Symbol,# Reps,Experiment
Date` gets truncated at the `#` to `Compound Name,Endpoint,Conc (uM),Gene
Symbol,` (5 columns, the last one empty). Every data row still has 6 columns
(no `#` in any row), so pandas — seeing more data columns than header columns
— silently treats the FIRST column as an unnamed index and drops it from the
returned frame. The net effect: the compound ID column vanishes from every
row, and the real "Experiment Date" column's values survive but under an
empty-string header.

This is a genuine, real-world-triggerable data-corruption bug: any vendor
export with a literal `#` anywhere in a header cell (a plausible convention —
`# Reps`, `#samples`, `Item #`) silently loses its first column through this
path. `parsing/table.py::parse_file` (the older/legacy entry point, still
used by the CLI) does NOT go through `read_csv_grid`/`comment="#"` at all and
parses this same file correctly (`tests/test_parsing.py` proves it) — only
the newer structural-detection `parse()` entry point (used by
`service.resolve_or_map`, and therefore every `/api/upload` call) is affected.

**Why not fixed here:** `parsing/structure/delimiter.py` is not in 10-05's
`files_modified` list (`upload.py`, `date_format.py`, `state.py`, `wire.py`,
`app.py`, plus the two new test files). The fix likely needs a real design
decision (e.g. only strip a leading-line comment via a regex/line-scan
instead of trusting pandas' `comment=` kwarg, or quoting/escaping data before
the sniff) that deserves its own focused plan + tests against the parser
corpus, not a one-line patch bolted onto an HTTP-wire plan.

**Workaround used in 10-05's own tests:** `tests/api/test_date_format_route.py`
uses an inline CSV fixture carrying the same genuinely-ambiguous
`Experiment Date` values as the real file, with a 2-column header
(`Compound Name,Experiment Date`, no `# Reps` column) instead of reading
`helixbio_export.csv` through the real upload pipeline. `pinnacle_labs_export.csv`
has no `#` in any header and is used directly.

**Suggested next step:** file as a `parser-hardening` todo (mirrors
`parser-excel-hazards.md`'s existing convention) and fix before this file, or
any real vendor file with a `#` in a header, is ever uploaded through the
live `/api/upload` demo path.

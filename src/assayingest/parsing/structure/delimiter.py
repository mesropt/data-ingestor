"""CSV delimiter and comment-line sniffing — the CSV half of structural
detection (PARSE-02).

`csv.Sniffer()` is poisoned by comment lines: a comment reading
`# generated: ...; delimiter=';'` fools it into picking `=` as the
delimiter, empirically reproduced against this project's own
`pinnacle_labs_export.csv` fixture (01-RESEARCH.md Pattern 2 / Pitfall 1).
Never sniff raw, unfiltered file content — let pandas' python engine strip
comments internally before it sniffs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

#: Vendor exports in this corpus use '#' to prefix generation-metadata lines
#: above the header row (see pinnacle_labs_export.csv).
_COMMENT_PREFIX = "#"


def read_csv_grid(
    path: str | Path, *, delimiter: str | None = None
) -> tuple[list[str], list[list[str]]]:
    """Read a CSV's headers and rows as strings, sniffing delimiter + comments.

    A `delimiter` given by the human (PARSE-06) is used verbatim and skips
    sniffing altogether — the point of a hint is that the tool stops guessing.

    Raises `FileNotFoundError` for a missing path and `ValueError` for a
    non-CSV extension, matching `parsing/table.py`'s existing contract.
    """
    # Local import: `parsing/table.py` also imports this module (to wire the
    # structural CSV branch into `parse()`), so a module-level import here
    # would create a circular import at load time.
    from ..table import _clean_header

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError(
            f"Cannot ingest {path.name}: expected a .csv file, got '{path.suffix}'"
        )

    frame = pd.read_csv(
        path, sep=delimiter, engine="python", comment=_COMMENT_PREFIX, dtype=str
    )
    headers = [_clean_header(h) for h in frame.columns]
    rows = [
        ["" if pd.isna(cell) else str(cell) for cell in record]
        for record in frame.itertuples(index=False, name=None)
    ]
    return headers, rows

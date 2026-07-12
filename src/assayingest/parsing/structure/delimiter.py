"""CSV delimiter and comment-line sniffing — the CSV half of structural
detection (PARSE-02).

`csv.Sniffer()` is poisoned by comment lines: a comment reading
`# generated: ...; delimiter=';'` fools it into picking `=` as the
delimiter, empirically reproduced against this project's own
`pinnacle_labs_export.csv` fixture (01-RESEARCH.md Pattern 2 / Pitfall 1).
Never sniff raw, unfiltered file content — comment lines are stripped by
our own explicit whole-line pre-filter (`_strip_comment_lines`), which runs
BEFORE any sniffing and so still defuses the `delimiter=';'` comment trap.

Comment stripping is deliberately NOT delegated to pandas' `comment=`
kwarg: the `python` engine's `comment=` truncates any line at the FIRST
occurrence of the prefix character anywhere in it, not just at the start
of the line. That destroys a genuine header/data cell containing a literal
`#` (e.g. a `# Reps` column) — silent data loss, not a comment. Our
pre-filter only drops a line whose first non-whitespace character is the
comment prefix, and is quote-aware so a `#` inside an open multi-line
quoted cell is never mistaken for a comment.
"""

from __future__ import annotations

import csv
import io
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

    frame = _read_or_name_the_failure(path, delimiter)
    headers = [_clean_header(h) for h in frame.columns]
    rows = [
        ["" if pd.isna(cell) else str(cell) for cell in record]
        for record in frame.itertuples(index=False, name=None)
    ]
    return headers, rows


def _read_or_name_the_failure(path: Path, delimiter: str | None) -> pd.DataFrame:
    """Read the grid, turning the csv/pandas libraries' own exceptions into a
    named `ValueError` (D-05) — an empty file, a non-UTF-8 encoding, or rows
    that disagree on column count must name a consequence, not leak a
    'Could not determine delimiter' / codec traceback.
    """
    if path.stat().st_size == 0:
        raise ValueError(
            f"Cannot ingest {path.name}: the file is empty — there is no table "
            "to read."
        )
    try:
        # The decode MUST stay inside this try: it is what raises
        # UnicodeDecodeError for a non-UTF-8 file, caught below.
        text = path.read_text(encoding="utf-8")
        kept_text, dropped_lines = _strip_comment_lines(text)
        if not kept_text.strip():
            # Comment-only file: honest to call this "empty" — there is no
            # table left once every line has been stripped as a comment.
            # (With `sep=None`, pandas' python engine raises a generic
            # "Could not determine delimiter" csv.Error here instead of
            # EmptyDataError, so this is checked explicitly rather than
            # relying on which exception pandas happens to raise.)
            raise pd.errors.EmptyDataError("No columns to parse from file")
        # No `comment=` kwarg here — see the module docstring for why.
        frame = pd.read_csv(
            io.StringIO(kept_text), sep=delimiter, engine="python", dtype=str
        )
        _refuse_if_dropped_line_matches_table_shape(
            dropped_lines, frame, delimiter, kept_text, path
        )
        return frame
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Cannot ingest {path.name}: the file is not UTF-8 text — it may "
            "use a regional encoding (e.g. Windows-1251, Latin-1); re-save it "
            "as UTF-8."
        ) from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(
            f"Cannot ingest {path.name}: the file is empty — there is no table "
            "to read."
        ) from exc
    except (pd.errors.ParserError, csv.Error) as exc:
        raise ValueError(
            f"Cannot ingest {path.name}: the rows do not form a single "
            "consistent table (columns per row disagree); check for extra "
            "delimiters or split it into one table per file."
        ) from exc


def _strip_comment_lines(text: str) -> tuple[str, list[str]]:
    """Drop only WHOLE comment lines — a line whose first non-whitespace
    character is `#`. A `#` anywhere else in a line is data (e.g. a `# Reps`
    header cell or a `Lot #42` value) and must survive verbatim; pandas'
    `comment=` kwarg cannot make that distinction, which is the bug this
    pre-filter exists to fix.

    Quote-aware: while a multi-line quoted cell is open, a line starting
    with `#` is a continuation of that cell's text, not a comment, and is
    kept. Quote-open state toggles once per line for each ODD count of `"`
    on that line — a doubled `""` escape inside a quoted field is an EVEN
    count and self-cancels, leaving the state unchanged.
    """
    kept_lines: list[str] = []
    dropped_lines: list[str] = []
    in_quoted_field = False
    for line in text.splitlines(keepends=True):
        is_comment = line.lstrip().startswith(_COMMENT_PREFIX) and not in_quoted_field
        (dropped_lines if is_comment else kept_lines).append(line)
        if line.count('"') % 2 == 1:
            in_quoted_field = not in_quoted_field
    return "".join(kept_lines), dropped_lines


def _refuse_if_dropped_line_matches_table_shape(
    dropped_lines: list[str],
    frame: pd.DataFrame,
    delimiter: str | None,
    kept_text: str,
    path: Path,
) -> None:
    """D-01: a `#`-prefixed line that is structurally indistinguishable from
    a header/data row (splits into exactly the table's own column count)
    must never be silently dropped as "just a comment" — that would let the
    first real data row silently become the header, the same class of
    silent corruption this whole fix exists to close. Fail closed instead:
    raise a named `ValueError` and let a human decide.
    """
    num_columns = len(frame.columns)
    if num_columns <= 1 or not dropped_lines:
        return
    resolved_delimiter = delimiter or _sniff_delimiter_for_guard(kept_text)
    for line in dropped_lines:
        fields = next(csv.reader([line], delimiter=resolved_delimiter), [])
        if len(fields) == num_columns:
            raise ValueError(
                f"Cannot ingest {path.name}: a line starting with "
                f"'{_COMMENT_PREFIX}' splits into the same {num_columns} "
                "columns as the table, so a comment cannot be told apart "
                f"from a header row here — remove the leading "
                f"'{_COMMENT_PREFIX}' if it is a header, or delete the line "
                "if it is a comment."
            )


def _sniff_delimiter_for_guard(kept_text: str) -> str:
    """Best-effort delimiter guess used ONLY to split a dropped comment line
    for the D-01 shape check — the table itself has already been read by
    the time this runs. Falls back to `,` when the already-filtered text is
    too sparse for `csv.Sniffer` to decide.
    """
    try:
        return csv.Sniffer().sniff(kept_text).delimiter
    except csv.Error:
        return ","

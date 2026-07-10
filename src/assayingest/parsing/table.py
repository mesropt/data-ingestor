"""Turn a messy CRO Excel/CSV file into a clean in-memory table.

The parser's only job is to get from bytes on disk to headers + rows. It does
not interpret meaning — deciding what a column *is* belongs to the mapper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .hint import NumericLocale, StructuralHint, StructureQuestion


@dataclass(frozen=True)
class RawTable:
    """A parsed source sheet: cleaned headers plus every row as strings.

    Values are kept as strings so the mapper sees them exactly as written
    (e.g. `03/11/2025`, `0.045`) without pandas coercing types and hiding the
    ambiguity the curator needs to resolve. `sheet_name` is set only for Excel
    workbooks with more than one sheet — a single CSV or one-sheet workbook
    leaves it None.
    """

    headers: list[str]
    rows: list[list[str]]
    source_name: str
    sheet_name: str | None = None
    #: One `NumericLocale` value (as a string) per column, in header order.
    #: Empty for tables that haven't gone through structural detection yet
    #: (the legacy `parse_file()` path) — a defaulted field so every existing
    #: `RawTable(...)` construction stays valid.
    column_locales: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def label(self) -> str:
        """Human/prompt-facing name, disambiguating the sheet when there is one."""
        if self.sheet_name:
            return f"{self.source_name} :: {self.sheet_name}"
        return self.source_name

    def sample(self, limit: int = 5) -> list[list[str]]:
        """First `limit` rows — enough for the mapper to read value shapes."""
        return self.rows[:limit]


_EXCEL_SUFFIXES = {".xlsx", ".xls"}


def sheet_names(path: str | Path) -> list[str]:
    """List an Excel workbook's sheet names; empty list for a CSV.

    Raises `FileNotFoundError` if the path is missing so a bad path is reported
    the same way for every file type, and `ValueError` for an unsupported one.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")
    suffix = path.suffix.lower()
    if suffix in _EXCEL_SUFFIXES:
        with pd.ExcelFile(path) as workbook:
            return [str(name) for name in workbook.sheet_names]
    if suffix == ".csv":
        return []
    raise ValueError(
        f"Cannot ingest {path.name}: expected a .csv or .xlsx file, "
        f"got '{path.suffix}'"
    )


def parse_file(path: str | Path, sheet: str | None = None) -> RawTable:
    """Parse one CSV, or one sheet of an Excel workbook, into a `RawTable`.

    For a multi-sheet workbook the caller must say which `sheet` to read — a
    workbook is never collapsed to sheet 0 silently. Raises `FileNotFoundError`
    for a missing path and `ValueError` for an unsupported extension or an
    unknown sheet name.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")

    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str, skipinitialspace=False)
        return _to_raw_table(frame, source_name=path.name)

    if path.suffix.lower() in _EXCEL_SUFFIXES:
        return _parse_excel_sheet(path, sheet)

    raise ValueError(
        f"Cannot ingest {path.name}: expected a .csv or .xlsx file, "
        f"got '{path.suffix}'"
    )


def _parse_excel_sheet(path: Path, sheet: str | None) -> RawTable:
    names = sheet_names(path)
    target = sheet if sheet is not None else names[0]
    if target not in names:
        available = ", ".join(names)
        raise ValueError(
            f"Cannot ingest {path.name}: sheet '{sheet}' not found "
            f"(available: {available})"
        )
    frame = pd.read_excel(path, sheet_name=target, dtype=str)
    # Only tag the sheet when the workbook actually has more than one.
    tag = target if len(names) > 1 else None
    return _to_raw_table(frame, source_name=path.name, sheet_name=tag)


def _to_raw_table(
    frame: pd.DataFrame, source_name: str, sheet_name: str | None = None
) -> RawTable:
    headers = [_clean_header(h) for h in frame.columns]
    rows = [
        ["" if pd.isna(cell) else str(cell) for cell in record]
        for record in frame.itertuples(index=False, name=None)
    ]
    return RawTable(
        headers=headers,
        rows=rows,
        source_name=source_name,
        sheet_name=sheet_name,
    )


def _clean_header(header: object) -> str:
    """Strip surrounding whitespace; keep blank headers as empty strings.

    A blank header is signal, not noise — NovaScreen ships its unit column with
    no name, and the mapper must be told the column exists but is unlabelled.
    """
    text = "" if header is None else str(header)
    if text.startswith("Unnamed:"):  # pandas' placeholder for a blank header
        return ""
    return text.strip()


def parse(
    path: str | Path, *, sheet: str | None = None, hint: StructuralHint | None = None
) -> RawTable | StructureQuestion:
    """Resolve a file's structure into a clean table, or ask when unsure.

    Structural uncertainty is a RETURNED `StructureQuestion`, never an
    exception (D-05) — only a genuinely broken file (missing path,
    unsupported extension, unknown sheet) still raises
    `FileNotFoundError`/`ValueError`, exactly as `parse_file()` does today.
    `hint.header_row_index`, when given, overrides Excel header detection and
    builds the table from that row directly (PARSE-06's "proceed using the
    human's hint" path). Sheet ranking and shape classification land in later
    plans of this phase; a multi-sheet workbook still requires an explicit
    `sheet` (or takes the first) here.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _parse_csv_structurally(path)
    if path.suffix.lower() in _EXCEL_SUFFIXES:
        return _parse_excel_structurally(path, sheet, hint)
    return parse_file(path, sheet)


def _parse_csv_structurally(path: Path) -> RawTable | StructureQuestion:
    """The CSV branch of `parse()`: sniff, annotate, and gate on ambiguity."""
    # Local import: avoids a module-load-time circular import with
    # `structure/delimiter.py`, which itself imports `_clean_header` from
    # this module.
    from .structure.delimiter import read_csv_grid
    from .structure.locale import annotate_columns

    headers, rows = read_csv_grid(path)
    locales = annotate_columns(headers, rows)
    ambiguous_columns = [
        headers[i] for i, loc in enumerate(locales) if loc == NumericLocale.AMBIGUOUS
    ]
    if ambiguous_columns:
        return _ambiguous_locale_question(path, rows, ambiguous_columns)
    return RawTable(
        headers=headers,
        rows=rows,
        source_name=path.name,
        column_locales=[loc.value for loc in locales],
    )


def _ambiguous_locale_question(
    path: Path, rows: list[list[str]], ambiguous_columns: list[str]
) -> StructureQuestion:
    """Build the D-14 ask: a 1000x-corrupting guess must never be silent."""
    names = ", ".join(ambiguous_columns)
    return StructureQuestion(
        unsure_about=f"decimal locale of column(s): {names}",
        reason=(
            f"{path.name}: every value in {names} shows exactly 3 digits "
            "after the comma — that pattern matches both thousands grouping "
            "(1,234 = one thousand two hundred thirty-four) and a "
            "3-decimal comma display, so guessing risks corrupting the "
            "value by 1000x."
        ),
        confidence=0.5,
        proposal=StructuralHint(decimal_separator=","),
        alternatives=[StructuralHint(decimal_separator=".")],
        evidence_rows=rows[:8],
    )


def _parse_excel_structurally(
    path: Path, sheet: str | None, hint: StructuralHint | None
) -> RawTable | StructureQuestion:
    """The Excel branch of `parse()`: detect the header row structurally,
    slice the grid, and gate on confidence (D-03/D-05).

    Local imports: `structure/grid.py` and `structure/header.py` don't
    depend on this module, but every other `parse()` branch imports its
    `structure/*` helper locally too (see `_parse_csv_structurally`) — kept
    consistent rather than mixing import styles across branches.
    """
    from .structure.grid import read_grid
    from .structure.header import detect_header

    names = sheet_names(path)
    target = sheet if sheet is not None else names[0]
    if target not in names:
        available = ", ".join(names)
        raise ValueError(
            f"Cannot ingest {path.name}: sheet '{sheet}' not found "
            f"(available: {available})"
        )
    tag = target if len(names) > 1 else None
    rows = read_grid(path, target)

    if hint is not None and hint.header_row_index is not None:
        return _raw_table_from_header_row(path, rows, hint.header_row_index, tag)

    detection = detect_header(rows)
    if not detection.confident:
        return _header_uncertain_question(path, rows, detection.index)
    return _raw_table_from_header_row(path, rows, detection.index, tag)


def _raw_table_from_header_row(
    path: Path, rows: list[tuple], header_index: int, sheet_tag: str | None
) -> RawTable:
    """Slice the native-typed grid at the resolved header row, then convert
    to the strings-only `RawTable` shape (D-12) — detection runs on native
    types (Pattern 6), the output never does.
    """
    header_row = rows[header_index]
    data_rows = rows[header_index + 1 :]
    headers = [_clean_header(h) for h in header_row]
    string_rows = [_row_to_strings(row) for row in data_rows]
    return RawTable(
        headers=headers, rows=string_rows, source_name=path.name, sheet_name=sheet_tag
    )


def _header_uncertain_question(
    path: Path, rows: list[tuple], best_guess_index: int | None
) -> StructureQuestion:
    """Build the D-03/D-05 ask: no row scored clearly ahead of the others,
    so the tool asks instead of picking the marginally-higher score."""
    return StructureQuestion(
        unsure_about=f"{path.name}: which row is the real header",
        reason=(
            f"{path.name}: no candidate header row scored clearly ahead of "
            "the others — picking the higher score risks a shifted header "
            "that looks clean but maps every field wrong."
        ),
        confidence=0.5,
        proposal=StructuralHint(header_row_index=best_guess_index),
        evidence_rows=[_row_to_strings(row) for row in rows[:8]],
    )


def _row_to_strings(row: tuple) -> list[str]:
    """Convert one native-typed grid row to the strings-only `RawTable` shape."""
    return ["" if cell is None else str(cell) for cell in row]
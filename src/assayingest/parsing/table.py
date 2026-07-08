"""Turn a messy CRO Excel/CSV file into a clean in-memory table.

The parser's only job is to get from bytes on disk to headers + rows. It does
not interpret meaning — deciding what a column *is* belongs to the mapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


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
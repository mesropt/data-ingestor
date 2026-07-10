"""Raw-grid Excel reader — native cell types, NORMAL mode (01-RESEARCH.md
Pattern 6/7, Pitfall 2/3).

Detection heuristics elsewhere in this package (header-row scoring, and the
drawing/shape detection later plans build) need to see a numeric cell as a
`float`/`int`, not a string — `pd.read_excel(..., dtype=str)` erases that
signal before any heuristic can use it (Pitfall 3). `openpyxl.load_workbook`
in NORMAL mode (never `read_only=True`) is the only reader that keeps native
types *and* `ws._charts`/`ws._images`/`ws._rels` available (Pitfall 2) — this
module reads the grid once, for every structural consumer in this package.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

_EXCEL_SUFFIXES = {".xlsx", ".xls"}


def read_grid(path: str | Path, sheet: str | None = None) -> list[tuple]:
    """Read one worksheet's raw grid with native openpyxl cell types intact.

    `sheet` defaults to the workbook's first worksheet. Raises
    `FileNotFoundError` for a missing path and `ValueError` for a non-Excel
    extension or an unknown sheet name, matching `parsing/table.py`'s
    existing contract.
    """
    worksheets = list_worksheets(path)
    target = _select_worksheet(worksheets, sheet)
    return list(target.iter_rows(values_only=True))


def list_worksheets(path: str | Path) -> list:
    """List a workbook's real worksheets — structurally excludes Chartsheet.

    Iterates `wb.worksheets`, never `wb.sheetnames` + `wb[name]` (D-17):
    `Workbook.worksheets` only ever contains cell-bearing sheet types, so a
    dedicated chart sheet can never reach a caller as something that looks
    touchable but crashes the moment `.iter_rows()` is called on it.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")
    if path.suffix.lower() not in _EXCEL_SUFFIXES:
        raise ValueError(
            f"Cannot ingest {path.name}: expected a .csv or .xlsx file, "
            f"got '{path.suffix}'"
        )
    workbook = openpyxl.load_workbook(path)  # NORMAL mode -- see module docstring
    return list(workbook.worksheets)


def _select_worksheet(worksheets: list, sheet: str | None):
    if sheet is None:
        return worksheets[0]
    for worksheet in worksheets:
        if worksheet.title == sheet:
            return worksheet
    available = ", ".join(worksheet.title for worksheet in worksheets)
    raise ValueError(f"sheet '{sheet}' not found (available: {available})")

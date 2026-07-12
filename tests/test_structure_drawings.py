"""Tests for `parsing.structure.grid.is_drawing_only_sheet` — D-18.

Uses `ws._rels`, not `ws._images` (empty whenever Pillow is absent — Pitfall
4) and not `ws.max_row == 0` (a drawing-only sheet reports `max_row=1`, not
0 — Pitfall 5). Requires normal (non-`read_only`) mode, already the default
in `grid.list_worksheets`/`grid.read_grid`.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from assayingest.parsing.structure.grid import is_drawing_only_sheet

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _worksheet(path: Path, sheet: str):
    workbook = openpyxl.load_workbook(path)  # NORMAL mode
    return workbook[sheet]


def test_is_drawing_only_sheet_true_for_image_only_fixture():
    ws = _worksheet(_FIXTURES / "quantex_scanned_report.xlsx", "Scanned Report")

    assert is_drawing_only_sheet(ws) is True


def test_is_drawing_only_sheet_false_for_a_normal_data_sheet():
    ws = _worksheet(_FIXTURES / "meridian_cro_codes.xlsx", "DATA")

    assert is_drawing_only_sheet(ws) is False


def test_is_drawing_only_sheet_false_for_a_sheet_with_an_embedded_chart():
    """A chart is not an image-only sheet — the sheet has real cell content
    (D-16's "chart never disqualifies its data sheet", applied here too)."""
    ws = _worksheet(_FIXTURES / "vantage_pk_with_chart.xlsx", "Results")

    assert is_drawing_only_sheet(ws) is False

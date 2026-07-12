"""`parse()`'s Excel branch detects the true header row structurally: banner
rows above the header must not leak into the table, an explicit hint
overrides detection, and a genuinely uncertain header returns a
`StructureQuestion` instead of guessing (01-CONTEXT.md D-03, D-05, D-12;
PARSE-01, PARSE-06)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from assayingest.parsing.hint import StructuralHint, StructureQuestion
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"

_ZEPHYR_HEADERS = [
    "Compound ID",
    "Assay",
    "Result",
    "Units",
    "Protein Target",
    "Replicates",
    "Run Date",
]


def _near_tie_workbook(tmp_path: Path) -> Path:
    """Two equally header-like rows -- the deterministic layer must ask, not
    guess (D-03/D-05). Mirrors tests/test_structure_header.py's fixture."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in [
        ("ID", "Kind", "Amount"),
        (1, "x", 10.5),
        (2, "y", 20.5),
        (3, "z", 30.5),
        (4, "w", 40.5),
        (5, "v", 50.5),
        ("Code", "Type", "Value"),
        (10, "p", 100.5),
        (11, "q", 200.5),
        (12, "r", 300.5),
        (13, "s", 400.5),
        (14, "t", 500.5),
    ]:
        ws.append(row)
    path = tmp_path / "near_tie.xlsx"
    wb.save(path)
    return path


def test_parse_zephyr_detects_header_beneath_banner_rows():
    outcome = parse(DATA / "zephyr_bio_ZB-2025.xlsx", sheet="Week 1")
    assert isinstance(outcome, RawTable)
    assert outcome.headers == _ZEPHYR_HEADERS
    assert outcome.rows[0][0] == "ZB-100"  # first real record, not banner text


def test_parse_zephyr_all_cells_are_strings():
    # Detection reads native types; the output RawTable stays strings-only
    # regardless (D-12) -- conversion happens only after the header resolves.
    outcome = parse(DATA / "zephyr_bio_ZB-2025.xlsx", sheet="Week 1")
    for row in outcome.rows:
        for cell in row:
            assert isinstance(cell, str)
    assert outcome.rows[0][2] == "32.051"  # the float 32.051, as a string


def test_parse_zephyr_hint_overrides_detection_with_equivalent_result():
    detected = parse(DATA / "zephyr_bio_ZB-2025.xlsx", sheet="Week 1")
    hinted = parse(
        DATA / "zephyr_bio_ZB-2025.xlsx",
        sheet="Week 1",
        hint=StructuralHint(header_row_index=4),
    )
    assert isinstance(hinted, RawTable)
    assert hinted.headers == detected.headers
    assert hinted.rows == detected.rows


def test_parse_uncertain_header_returns_structure_question_not_raise(tmp_path):
    outcome = parse(_near_tie_workbook(tmp_path))
    assert isinstance(outcome, StructureQuestion)


def test_parse_uncertain_header_proposal_prefills_best_guess(tmp_path):
    outcome = parse(_near_tie_workbook(tmp_path))
    assert outcome.proposal is not None
    assert outcome.proposal.header_row_index is not None


def test_parse_uncertain_header_evidence_rows_show_first_rows(tmp_path):
    outcome = parse(_near_tie_workbook(tmp_path))
    assert 1 <= len(outcome.evidence_rows) <= 8


def test_parse_missing_excel_file_still_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        parse(DATA / "does_not_exist.xlsx")

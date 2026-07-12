"""Header-row detection by width-consistency + type-mismatch scoring
(01-RESEARCH.md Pattern 1). "Not confident" is a first-class outcome
(01-CONTEXT.md D-03) -- a genuine near-tie must never be silently broken by
picking the marginally-higher score."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from assayingest.parsing.structure.header import (
    _CONFIDENCE_MARGIN,
    detect_header,
    header_row_scores,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"

#: Two equally header-like rows (idx 0, idx 6), each followed by its own
#: internally-consistent data block -- a constructed, genuine tie (top score
#: margin == 0.0) the deterministic layer must not silently break (D-03).
_NEAR_TIE_ROWS: list[tuple] = [
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
]


def _zephyr_week1_rows() -> list[tuple]:
    wb = openpyxl.load_workbook(DATA / "zephyr_bio_ZB-2025.xlsx")
    return list(wb["Week 1"].iter_rows(values_only=True))


def test_detect_header_finds_zephyr_row_beneath_banner_rows_confidently():
    detection = detect_header(_zephyr_week1_rows())
    assert detection.index == 4
    assert detection.confident is True


def test_blank_spacer_row_is_never_a_header_candidate():
    rows = _zephyr_week1_rows()
    scored_indices = [i for i, _ in header_row_scores(rows)]
    assert 3 not in scored_indices  # row 3 is the fully-blank spacer row


def test_blank_spacer_row_never_wins_detection():
    detection = detect_header(_zephyr_week1_rows())
    assert detection.index != 3


def test_near_tie_rows_report_not_confident():
    detection = detect_header(_NEAR_TIE_ROWS)
    assert detection.confident is False


def test_near_tie_scores_are_within_the_confidence_margin():
    scores = sorted(
        (score for _, score in header_row_scores(_NEAR_TIE_ROWS)), reverse=True
    )
    assert scores[0] - scores[1] < _CONFIDENCE_MARGIN


def test_confidence_margin_is_a_named_module_constant_not_a_magic_number():
    assert isinstance(_CONFIDENCE_MARGIN, float)
    assert 0.0 < _CONFIDENCE_MARGIN < 1.0


def test_header_module_imports_no_anthropic_or_file_io():
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "structure"
        / "header.py"
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("anthropic" in line for line in import_lines)
    assert not any(
        line in ("import pathlib", "from pathlib import Path") for line in import_lines
    )

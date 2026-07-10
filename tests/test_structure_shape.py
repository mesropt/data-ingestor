"""Table-shape classification -- row/column type-homogeneity inversion for
`transposed`, and a numeric-column-cluster fingerprint for `wide_matrix`
(01-RESEARCH.md Pattern 5; 01-CONTEXT.md D-10/D-11). Only `row_per_record`
may ever become a `RawTable` -- every other shape is a corpus-grounded,
structurally-detected reason to ask instead of guess."""

from __future__ import annotations

from pathlib import Path

from assayingest.parsing.hint import TableShape
from assayingest.parsing.structure.grid import read_grid
from assayingest.parsing.structure.header import detect_header
from assayingest.parsing.structure.shape import (
    _TRANSPOSED_MARGIN,
    _column_type_homogeneity,
    _row_type_homogeneity,
    classify_shape,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _data_region(name: str, sheet: str | None = None) -> list[tuple]:
    """Mirror `table.py`'s eventual gate: slice off the best-guess header
    row (always populated, even when detection isn't confident -- D-02),
    exactly as `_parse_excel_structurally` must for `bionexus_transposed.xlsx`,
    whose header detection is genuinely not confident (D-03)."""
    rows = read_grid(DATA / name, sheet=sheet)
    detection = detect_header(rows)
    index = detection.index if detection.index is not None else -1
    return rows[index + 1 :]


def test_classify_shape_apex_is_wide_matrix():
    assert classify_shape(_data_region("apex_labs_wide_matrix.xlsx")) == (
        TableShape.WIDE_MATRIX
    )


def test_classify_shape_bionexus_is_transposed():
    assert classify_shape(_data_region("bionexus_transposed.xlsx")) == (
        TableShape.TRANSPOSED
    )


def test_classify_shape_zephyr_week1_is_row_per_record_control():
    assert classify_shape(_data_region("zephyr_bio_ZB-2025.xlsx", sheet="Week 1")) == (
        TableShape.ROW_PER_RECORD
    )


def test_classify_shape_transposed_fires_on_the_row_col_homogeneity_inversion():
    """The verified signal (01-RESEARCH.md Pattern 5): bionexus's
    row-homogeneity exceeds its column-homogeneity by more than the named
    margin; the two control fixtures never invert."""
    bionexus = _data_region("bionexus_transposed.xlsx")
    zephyr = _data_region("zephyr_bio_ZB-2025.xlsx", sheet="Week 1")
    apex = _data_region("apex_labs_wide_matrix.xlsx")

    bionexus_diff = _row_type_homogeneity(bionexus) - _column_type_homogeneity(bionexus)
    zephyr_diff = _row_type_homogeneity(zephyr) - _column_type_homogeneity(zephyr)
    apex_diff = _row_type_homogeneity(apex) - _column_type_homogeneity(apex)

    assert bionexus_diff >= _TRANSPOSED_MARGIN
    assert zephyr_diff < _TRANSPOSED_MARGIN
    assert apex_diff < _TRANSPOSED_MARGIN


def test_classify_shape_multiple_tables_fixture_never_misclassifies_as_row_per_record():
    """`triton_screening_two_tables.xlsx` (plan 03) is a real corpus fixture
    for the blank-separator-block case -- two independent tables on one
    sheet, split by fully-blank rows. It must not read as one clean
    row_per_record table (D-10/D-11)."""
    shape = classify_shape(_data_region("triton_screening_two_tables.xlsx"))
    assert shape in (TableShape.MULTIPLE_TABLES, TableShape.UNKNOWN)
    assert shape != TableShape.ROW_PER_RECORD


def test_classify_shape_blank_separator_block_classifies_multiple_tables():
    """A synthetic grid with a genuine blank-row block between two populated
    regions -- the defensive predicate 01-RESEARCH.md flagged as having no
    corpus fixture at the time RESEARCH.md was written (Assumptions A4);
    triton now grounds it, but this construction pins the exact predicate."""
    rows = [
        ("A-1", "x", 1.5),
        ("A-2", "y", 2.5),
        ("A-3", "z", 3.5),
        (None, None, None),
        (None, None, None),
        ("B-1", "reviewer-1", "pass"),
        ("B-2", "reviewer-2", "flag"),
    ]
    assert classify_shape(rows) == TableShape.MULTIPLE_TABLES


def test_classify_shape_empty_grid_is_unknown():
    assert classify_shape([]) == TableShape.UNKNOWN


def test_classify_shape_module_imports_no_anthropic_or_pandas():
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "structure"
        / "shape.py"
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("anthropic" in line for line in import_lines)
    assert not any("pandas" in line for line in import_lines)
    assert not any("openpyxl" in line for line in import_lines)

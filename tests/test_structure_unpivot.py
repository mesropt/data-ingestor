"""parsing/structure/unpivot.py — the pure key-value/transposed transform
(SHAPE-02). Written test-first (TDD RED).

Unit tests run on hand-built native-typed grids (no file I/O); the two golden
tests run against the real driving workbook via `grid.read_grid` and pin
12-RESEARCH's measured outputs (Summary → 10 headers / 1 row; Patient Info →
17 headers / 1 row) — the transform is proven against the file that forced
the phase.
"""

from __future__ import annotations

from pathlib import Path

from assayingest.parsing.structure.grid import read_grid
from assayingest.parsing.structure.layout import KeyValueBlock, LayoutKind, SheetLayout
from assayingest.parsing.structure.unpivot import unpivot_key_value

_DRIVING_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "synthetic"
    / "lab_corpus"
    / "cascade_allergy_CS-2026-698392.xlsx"
)


def _kv_layout(blocks, *, one_record_per_value_column: bool = False) -> SheetLayout:
    return SheetLayout(
        kind=LayoutKind.KEY_VALUE,
        confidence=1.0,
        reasoning="hand-built test layout",
        key_value_blocks=tuple(
            KeyValueBlock(
                label_column=label_column,
                value_columns=tuple(value_columns),
                first_row=first_row,
                last_row=last_row,
            )
            for label_column, value_columns, first_row, last_row in blocks
        ),
        one_record_per_value_column=one_record_per_value_column,
    )


# --- Single block, one value column --------------------------------------------


def test_single_block_labels_become_headers_and_values_the_single_row():
    rows = [
        ("Name", "TAYLOR, James"),
        ("Age", 65),
        ("Sex", "M"),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 2)]))
    assert headers == ["Name", "Age", "Sex"]
    assert string_rows == [["TAYLOR, James", "65", "M"]]


# --- Two blocks, one record ------------------------------------------------------


def test_two_blocks_contribute_columns_to_one_record_in_block_order():
    rows = [
        ("Name", "TAYLOR, James", None, "Accession #", "CS-2026-698392"),
        ("Age", 65, None, "Priority", "Routine"),
    ]
    headers, string_rows = unpivot_key_value(
        rows, _kv_layout([(0, (1,), 0, 1), (3, (4,), 0, 1)])
    )
    assert headers == ["Name", "Age", "Accession #", "Priority"]
    assert string_rows == [["TAYLOR, James", "65", "CS-2026-698392", "Routine"]]


# --- GOLDEN: the real driving sheets (12-RESEARCH measured outputs) --------------


def test_golden_cascade_summary_yields_ten_headers_and_one_row():
    rows = read_grid(_DRIVING_FILE, "Summary")
    headers, string_rows = unpivot_key_value(
        rows, _kv_layout([(0, (1,), 7, 12), (4, (5,), 7, 12)])
    )
    assert headers == [
        "Patient Name",
        "MRN",
        "DOB",
        "Age / Sex",
        "Ordering Provider",
        "Accession #",
        "Collected",
        "Received",
        "Reported",
        "Specimen",
    ]
    assert len(string_rows) == 1
    assert string_rows[0][0] == "TAYLOR, James"


def test_golden_cascade_patient_info_yields_seventeen_headers_and_one_row():
    rows = read_grid(_DRIVING_FILE, "Patient Info")
    headers, string_rows = unpivot_key_value(
        rows, _kv_layout([(0, (1,), 1, 10), (3, (4,), 1, 10)])
    )
    assert len(headers) == 17
    assert len(string_rows) == 1
    assert len(string_rows[0]) == 17
    # Zero duplicate labels on the driving sheet -- measured in 12-RESEARCH.
    assert len(set(headers)) == 17


# --- Transposed melt (D-12-13: falls out of the same transform for free) ---------


def test_transposed_one_block_melts_one_row_per_value_column():
    rows = [
        ("Compound", "A-1", "A-2", "A-3"),
        ("IC50", 12.5, 13.1, 9.8),
    ]
    headers, string_rows = unpivot_key_value(
        rows, _kv_layout([(0, (1, 2, 3), 0, 1)], one_record_per_value_column=True)
    )
    assert headers == ["Compound", "IC50"]
    assert string_rows == [
        ["A-1", "12.5"],
        ["A-2", "13.1"],
        ["A-3", "9.8"],
    ]


# --- Duplicate labels: deterministic disambiguation (RESEARCH Pitfall 6) ---------


def test_duplicate_labels_are_deterministically_suffixed_never_duplicated():
    # canonical._column_index resolves headers by FIRST occurrence -- a
    # duplicate header's second column would be silently unreachable.
    rows = [
        ("Collected", "May 02, 2026"),
        ("Collected", "May 03, 2026"),
        ("Collected", "May 04, 2026"),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 2)]))
    assert headers == ["Collected", "Collected (2)", "Collected (3)"]
    assert string_rows == [["May 02, 2026", "May 03, 2026", "May 04, 2026"]]


def test_duplicate_labels_across_blocks_are_disambiguated_too():
    rows = [
        ("Collected", "May 02, 2026", None, "Collected", "May 03, 2026"),
    ]
    headers, _ = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 0), (3, (4,), 0, 0)]))
    assert headers == ["Collected", "Collected (2)"]


# --- Stringification: the _row_to_strings contract -------------------------------


def test_native_float_stringifies_with_no_thousands_separator():
    # Matching table.py's `_row_to_strings` contract keeps the downstream
    # locale gate honest on the un-pivoted table.
    rows = [("Ratio", 0.19)]
    _, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 0)]))
    assert string_rows == [["0.19"]]


def test_none_value_under_a_real_label_becomes_the_empty_string():
    rows = [
        ("Name", "TAYLOR, James"),
        ("Fasting Status", None),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 1)]))
    assert headers == ["Name", "Fasting Status"]
    assert string_rows == [["TAYLOR, James", ""]]


# --- Blank labels stay blank (the _clean_header rationale) ------------------------


def test_blank_label_with_a_value_keeps_an_empty_header():
    # An unlabelled row is signal, not noise -- the column exists but is
    # unlabelled, and the mapper must be told so.
    rows = [
        ("Name", "TAYLOR, James"),
        ("   ", "unlabelled value"),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 1)]))
    assert headers == ["Name", ""]
    assert string_rows == [["TAYLOR, James", "unlabelled value"]]


def test_fully_blank_label_and_value_rows_are_skipped():
    # This is what makes the driving sheets' golden counts (10 and 17, not
    # 12 and 20): trailing blank rows inside a block are padding, not fields.
    rows = [
        ("Name", "TAYLOR, James"),
        (None, None),
        ("Age", 65),
        ("", "   "),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 3)]))
    assert headers == ["Name", "Age"]
    assert string_rows == [["TAYLOR, James", "65"]]


# --- Bounds: nothing outside the declared blocks is ever read ---------------------


def test_cells_outside_the_declared_rows_and_columns_are_never_read():
    rows = [
        ("LEAK-above", "LEAK-above-value"),
        ("Name", "TAYLOR, James", "LEAK-right"),
        ("Age", 65, "LEAK-right"),
        ("LEAK-below", "LEAK-below-value"),
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 1, 2)]))
    emitted = set(headers) | {cell for row in string_rows for cell in row}
    assert headers == ["Name", "Age"]
    assert string_rows == [["TAYLOR, James", "65"]]
    assert not any("LEAK" in cell for cell in emitted)


def test_a_short_row_inside_a_block_reads_as_blank_not_index_error():
    rows = [
        ("Name", "TAYLOR, James"),
        ("Fasting Status",),  # ragged row: no cell at the value column
    ]
    headers, string_rows = unpivot_key_value(rows, _kv_layout([(0, (1,), 0, 1)]))
    assert headers == ["Name", "Fasting Status"]
    assert string_rows == [["TAYLOR, James", ""]]

"""`parse()`'s Excel branch gates `RawTable` construction on
`TableShape.ROW_PER_RECORD` (01-CONTEXT.md D-10/D-11, PARSE-05) -- a
wide-matrix or transposed layout must never reach the mapper looking like a
clean table with every field silently wrong. There is no
"parse-anyway-with-a-warning" path: any other shape returns a
`StructureQuestion` naming the detected shape, and a normal table (the
zephyr control) still parses exactly as plans 02/03 established."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from openpyxl import Workbook

from assayingest.parsing.hint import StructuralHint, StructureQuestion, TableShape
from assayingest.parsing.structure.layout import LayoutKind, SheetLayout
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_parse_apex_wide_matrix_returns_structure_question_not_raw_table():
    outcome = parse(DATA / "apex_labs_wide_matrix.xlsx")

    assert isinstance(outcome, StructureQuestion)
    assert outcome.proposal is not None
    assert outcome.proposal.table_shape == TableShape.WIDE_MATRIX


def test_parse_bionexus_transposed_returns_structure_question_not_raw_table():
    outcome = parse(DATA / "bionexus_transposed.xlsx")

    assert isinstance(outcome, StructureQuestion)
    assert outcome.proposal is not None
    assert outcome.proposal.table_shape == TableShape.TRANSPOSED


def test_parse_shape_question_reason_names_the_consequence_not_the_symptom():
    outcome = parse(DATA / "apex_labs_wide_matrix.xlsx")

    assert isinstance(outcome, StructureQuestion)
    assert "wide_matrix" in outcome.reason
    assert "v1" in outcome.reason or "unsupported" in outcome.reason


def test_parse_zephyr_week1_still_returns_a_raw_table_control():
    """The shape gate must not regress plan 02's confidently-detected,
    normal row_per_record table."""
    outcome = parse(DATA / "zephyr_bio_ZB-2025.xlsx", sheet="Week 1")

    assert isinstance(outcome, RawTable)
    assert outcome.rows[0][0] == "ZB-100"


def test_parse_meridian_still_returns_a_raw_table_no_shape_regression():
    """A second control -- plan 03's confidently-selected sheet must also
    still classify row_per_record and build a table."""
    outcome = parse(DATA / "meridian_cro_codes.xlsx")

    assert isinstance(outcome, RawTable)
    assert outcome.sheet_name == "DATA"


def test_no_raw_table_construction_path_attaches_a_shape_field():
    """D-11: there is no parse-anyway-with-a-warning path. `RawTable` itself
    carries no shape/warning field to attach one to -- structurally, not
    just behaviourally, enforced."""
    field_names = {f.name for f in dataclasses.fields(RawTable)}
    assert "table_shape" not in field_names
    assert "shape_warning" not in field_names


def test_parse_source_never_returns_a_raw_table_for_a_non_row_per_record_shape():
    """Directly exercises D-10/D-11 across both unsupported-shape fixtures:
    no code path in table.py's parse() may construct a RawTable when the
    classified shape isn't row_per_record."""
    for name in ("apex_labs_wide_matrix.xlsx", "bionexus_transposed.xlsx"):
        outcome = parse(DATA / name)
        assert not isinstance(outcome, RawTable), (
            f"{name} must never produce a RawTable (D-10/D-11)"
        )


# --- Phase 12 Wave A: the layout-verdict dispatch (D-12-13/D-12-15, SHAPE-02) ------
#
# When a `StructuralHint` carries a `SheetLayout` verdict, `parse()` dispatches
# on `layout.kind` BEFORE the heuristic classifier: `row_per_record` reads the
# ordinary way with the verdict's row indices; everything the verdict cannot
# make readable asks, answerably. When `hint.layout is None`, nothing above
# this comment moves -- the classifier still runs (the Wave A invariant).


def _save_workbook(tmp_path, grid, name: str = "book.xlsx") -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    for row in grid:
        worksheet.append(row)
    path = tmp_path / name
    workbook.save(path)
    return path


def _row_verdict(
    header_row_index=None,
    first_data_row=None,
    last_data_row=None,
    confidence: float = 0.95,
) -> SheetLayout:
    return SheetLayout(
        kind=LayoutKind.ROW_PER_RECORD,
        confidence=confidence,
        reasoning="hand-built test verdict",
        header_row_index=header_row_index,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
    )


def test_a_row_per_record_verdict_takes_the_header_from_the_verdict_not_redetection(
    tmp_path,
):
    """Row 0 is a perfect-looking header the heuristic would pick; the verdict
    says row 1. If parse() re-detected, headers would be row 0's."""
    path = _save_workbook(
        tmp_path,
        [
            ("Compound", "Result", "Unit"),
            ("Assay", "Reading", "Scale"),
            ("A-1", "12.5", "nM"),
        ],
    )
    outcome = parse(path, hint=StructuralHint(layout=_row_verdict(header_row_index=1)))

    assert isinstance(outcome, RawTable)
    assert outcome.headers == ["Assay", "Reading", "Scale"]
    assert outcome.rows == [["A-1", "12.5", "nM"]]


def test_a_row_per_record_verdict_row_range_excludes_trailing_prose(tmp_path):
    """The Quality Control case: a real 3-row table, a blank row, then prose.
    With first/last_data_row set, the prose never poisons the RawTable."""
    path = _save_workbook(
        tmp_path,
        [
            ("Control", "Level", "Result"),
            ("QC-1", "Low", "0.5"),
            ("QC-2", "Mid", "1.4"),
            ("QC-3", "High", "2.9"),
            (None, None, None),
            ("All runs passed Westgard rules 1-3s and 2-2s.", None, None),
            ("Reviewed by J. Chen, 2026-05-04", None, None),
        ],
    )
    outcome = parse(
        path,
        hint=StructuralHint(
            layout=_row_verdict(header_row_index=0, first_data_row=1, last_data_row=3)
        ),
    )

    assert isinstance(outcome, RawTable)
    assert outcome.headers == ["Control", "Level", "Result"]
    assert len(outcome.rows) == 3
    emitted = {cell for row in outcome.rows for cell in row}
    assert not any("Westgard" in cell or "Reviewed" in cell for cell in emitted)


def test_a_low_confidence_row_per_record_verdict_passed_as_a_hint_still_parses(
    tmp_path,
):
    """The hint path IS the confirmation: deciding when to ask about a
    low-confidence verdict lives in service (plan 12-05), not in parse().

    The grid deliberately carries a blank separator + trailing prose so the
    heuristic classifier refuses it today (multiple_tables) -- only the
    verdict path can produce this RawTable, so the test cannot pass vacuously.
    """
    path = _save_workbook(
        tmp_path,
        [
            ("Compound", "Result"),
            ("A-1", "12.5"),
            (None, None),
            ("Reviewed by J. Chen", None),
        ],
    )
    unconfident = _row_verdict(
        header_row_index=0, first_data_row=1, last_data_row=1, confidence=0.2
    )
    assert unconfident.needs_confirmation

    outcome = parse(path, hint=StructuralHint(layout=unconfident))
    assert isinstance(outcome, RawTable)
    assert outcome.headers == ["Compound", "Result"]
    assert outcome.rows == [["A-1", "12.5"]]


def test_a_hint_without_a_layout_still_runs_the_shape_classifier():
    """The Wave A invariant, stated as its own test: a verdict-less hint takes
    exactly yesterday's path -- classify_shape still gates, and the old
    unanswerable question still comes back."""
    outcome = parse(DATA / "apex_labs_wide_matrix.xlsx", hint=StructuralHint())

    assert isinstance(outcome, StructureQuestion)
    assert outcome.proposal is not None
    assert outcome.proposal.table_shape == TableShape.WIDE_MATRIX
    assert outcome.answerable_by_hint is False

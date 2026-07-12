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

from assayingest.parsing.hint import StructureQuestion, TableShape
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

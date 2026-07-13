"""The structural-question contract must round-trip through JSON exactly and
never import pandas or the Anthropic SDK (01-CONTEXT.md D-04/D-06)."""

from __future__ import annotations

import json
from pathlib import Path

from assayingest.parsing.hint import (
    NumericLocale,
    StructuralHint,
    StructureQuestion,
    TableShape,
)
from assayingest.parsing.structure.layout import KeyValueBlock, LayoutKind, SheetLayout


def _layout_hint() -> StructuralHint:
    return StructuralHint(
        layout=SheetLayout(
            kind=LayoutKind.KEY_VALUE,
            confidence=0.92,
            reasoning="labels down the side, values beside them",
            key_value_blocks=(
                KeyValueBlock(label_column=0, value_columns=(1,), first_row=1, last_row=10),
            ),
        )
    )


def test_structural_hint_json_round_trips_when_fully_populated():
    hint = StructuralHint(
        sheet_name="Week 1",
        header_row_index=4,
        delimiter=";",
        decimal_separator=",",
        data_region="A5:G20",
        table_shape=TableShape.ROW_PER_RECORD,
    )
    round_tripped = json.loads(json.dumps(hint.to_dict()))
    assert round_tripped == hint.to_dict()


def test_structural_hint_json_round_trips_when_all_none():
    hint = StructuralHint()
    round_tripped = json.loads(json.dumps(hint.to_dict()))
    assert round_tripped == hint.to_dict()


def test_structural_hint_with_layout_to_dict_is_fully_json_safe():
    # `_jsonable` must coerce the tuple of KeyValueBlock to plain lists so the
    # dict IS canonical JSON types -- json.dumps alone would accept a tuple but
    # hand back a list, and the round trip would no longer compare equal.
    hint = _layout_hint()
    as_dict = hint.to_dict()
    round_tripped = json.loads(json.dumps(as_dict))
    assert round_tripped == as_dict
    assert as_dict["layout"]["kind"] == "key_value"
    assert as_dict["layout"]["key_value_blocks"] == [
        {"label_column": 0, "value_columns": [1], "first_row": 1, "last_row": 10}
    ]


def test_structural_hint_with_layout_round_trips_through_from_dict():
    hint = _layout_hint()
    rebuilt = StructuralHint.from_dict(json.loads(json.dumps(hint.to_dict())))
    assert rebuilt == hint
    assert isinstance(rebuilt.layout, SheetLayout)
    assert rebuilt.layout.kind is LayoutKind.KEY_VALUE
    assert rebuilt.layout.key_value_blocks == (
        KeyValueBlock(label_column=0, value_columns=(1,), first_row=1, last_row=10),
    )


def test_from_dict_tolerates_a_stored_profile_with_no_layout_key():
    # Old rows deserialise unchanged -- no migration (12-RESEARCH Runtime
    # State Inventory).
    rebuilt = StructuralHint.from_dict(
        {"header_row_index": 2, "table_shape": "row_per_record"}
    )
    assert rebuilt.layout is None
    assert rebuilt.header_row_index == 2
    assert rebuilt.table_shape is TableShape.ROW_PER_RECORD


def test_table_shape_members_serialise_to_string_values():
    assert TableShape.ROW_PER_RECORD.value == "row_per_record"
    assert TableShape.WIDE_MATRIX.value == "wide_matrix"
    assert TableShape.TRANSPOSED.value == "transposed"
    assert TableShape.MULTIPLE_TABLES.value == "multiple_tables"
    assert TableShape.UNKNOWN.value == "unknown"


def test_numeric_locale_members_serialise_to_string_values():
    assert NumericLocale.DECIMAL_COMMA.value == "decimal_comma"
    assert NumericLocale.DECIMAL_POINT.value == "decimal_point"
    assert NumericLocale.AMBIGUOUS.value == "ambiguous"
    assert NumericLocale.NON_NUMERIC.value == "non_numeric"


def test_structure_question_valid_with_no_proposal_and_no_alternatives():
    question = StructureQuestion(
        unsure_about="header_row",
        reason="Two rows score equally header-like; picking wrong silently "
        "shifts every column one row.",
        confidence=0.4,
    )
    assert question.proposal is None
    assert question.alternatives == []
    assert question.evidence_rows == []


def test_structure_question_carries_reason_confidence_proposal_alternatives_evidence():
    proposal = StructuralHint(header_row_index=4)
    alt = StructuralHint(header_row_index=3)
    question = StructureQuestion(
        unsure_about="header_row",
        reason="Row 3 and row 4 both look header-like.",
        confidence=0.55,
        proposal=proposal,
        alternatives=[alt],
        evidence_rows=[["ZB-100", "Ki", "32.051"]],
    )
    assert question.reason == "Row 3 and row 4 both look header-like."
    assert question.confidence == 0.55
    assert question.proposal == proposal
    assert question.alternatives == [alt]
    assert question.evidence_rows == [["ZB-100", "Ki", "32.051"]]


def test_structure_question_to_dict_is_json_serialisable_with_proposal():
    question = StructureQuestion(
        unsure_about="decimal_locale",
        reason="Every comma group is exactly 3 digits; could be thousands "
        "grouping or a decimal separator.",
        confidence=0.5,
        proposal=StructuralHint(decimal_separator=","),
        alternatives=[StructuralHint(decimal_separator=".")],
        evidence_rows=[["1,234"], ["5,678"]],
    )
    as_dict = question.to_dict()
    json.dumps(as_dict)  # must not raise
    assert isinstance(as_dict["proposal"], dict)
    assert isinstance(as_dict["alternatives"], list)
    assert all(isinstance(a, dict) for a in as_dict["alternatives"])


def test_structure_question_to_dict_proposal_is_none_when_absent():
    question = StructureQuestion(
        unsure_about="header_row", reason="no proposal available", confidence=0.0
    )
    as_dict = question.to_dict()
    assert as_dict["proposal"] is None
    assert as_dict["alternatives"] == []


def test_hint_module_imports_only_stdlib():
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "hint.py"
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    allowed_prefixes = (
        "from __future__",
        "import dataclasses",
        "from dataclasses",
        "import enum",
        "from enum",
        # `structure/layout.py` is itself pure stdlib (its own purity guard in
        # tests/test_structure_layout.py pins that), so importing it keeps
        # hint.py testable without pandas or an API key.
        "from .structure.layout",
    )
    for line in import_lines:
        assert line.startswith(allowed_prefixes), f"unexpected import: {line}"
    assert not any("pandas" in line for line in import_lines)
    assert not any("anthropic" in line for line in import_lines)

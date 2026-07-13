"""Domain gating: nothing is ready while any field still needs confirmation."""

import dataclasses

import pytest

from assayingest.domain.models import (
    DateFormatConflict,
    DateFormatQuestion,
    FieldMapping,
    MappingProposal,
)


def _mapping(target_field: str, *, clear: bool) -> FieldMapping:
    return FieldMapping(
        target_field=target_field,
        source_column="col" if clear else None,
        confidence=1.0 if clear else 0.5,
        reasoning="",
        needs_confirmation=not clear,
    )


def test_clear_field_has_no_confirmation():
    assert _mapping("value", clear=True).is_clear


def test_proposal_ready_only_when_all_clear():
    proposal = MappingProposal(
        source_columns=["a", "b"],
        field_mappings=[
            _mapping("value", clear=True),
            _mapping("unit", clear=True),
        ],
    )
    assert proposal.is_ready
    assert proposal.unclear_fields == []


def test_proposal_blocked_by_a_single_yellow_field():
    unit = _mapping("unit", clear=False)
    proposal = MappingProposal(
        source_columns=["a", "b"],
        field_mappings=[_mapping("value", clear=True), unit],
    )
    assert not proposal.is_ready
    assert proposal.unclear_fields == [unit]


# --- Phase 10: DateFormatConflict/DateFormatQuestion (D-10-07) --------------


def _conflict(**overrides) -> DateFormatConflict:
    defaults = dict(
        target_field="assay_date",
        source_column="Experiment Date",
        day_first_format="%d/%m/%Y",
        month_first_format="%m/%d/%Y",
        example_values=("03/11/2025", "04/11/2025"),
        ambiguous_row_count=4,
    )
    defaults.update(overrides)
    return DateFormatConflict(**defaults)


def test_date_format_conflict_round_trips_through_to_dict():
    conflict = _conflict()
    assert conflict.to_dict() == {
        "target_field": "assay_date",
        "source_column": "Experiment Date",
        "day_first_format": "%d/%m/%Y",
        "month_first_format": "%m/%d/%Y",
        "example_values": ("03/11/2025", "04/11/2025"),
        "ambiguous_row_count": 4,
    }


def test_date_format_question_has_conflicts_only_when_non_empty():
    assert DateFormatQuestion(conflicts=()).has_conflicts is False
    assert DateFormatQuestion(conflicts=(_conflict(),)).has_conflicts is True


def test_date_format_question_to_dict_is_a_list_of_column_conflicts():
    conflict = _conflict()
    question = DateFormatQuestion(conflicts=(conflict,))
    assert question.to_dict() == {"columns": [conflict.to_dict()]}


def test_date_format_conflict_is_frozen():
    conflict = _conflict()
    with pytest.raises(dataclasses.FrozenInstanceError):
        conflict.target_field = "other_field"


def test_date_format_question_is_frozen():
    question = DateFormatQuestion(conflicts=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        question.conflicts = (_conflict(),)

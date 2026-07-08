"""Domain gating: nothing is ready while any field still needs confirmation."""

from assayingest.domain.models import (
    FieldMapping,
    MappingProposal,
    TargetField,
)


def _mapping(field: TargetField, *, clear: bool) -> FieldMapping:
    return FieldMapping(
        target_field=field,
        source_column="col" if clear else None,
        confidence=1.0 if clear else 0.5,
        reasoning="",
        needs_confirmation=not clear,
    )


def test_clear_field_has_no_confirmation():
    assert _mapping(TargetField.VALUE, clear=True).is_clear


def test_proposal_ready_only_when_all_clear():
    proposal = MappingProposal(
        source_columns=["a", "b"],
        field_mappings=[
            _mapping(TargetField.VALUE, clear=True),
            _mapping(TargetField.UNIT, clear=True),
        ],
    )
    assert proposal.is_ready
    assert proposal.unclear_fields == []


def test_proposal_blocked_by_a_single_yellow_field():
    unit = _mapping(TargetField.UNIT, clear=False)
    proposal = MappingProposal(
        source_columns=["a", "b"],
        field_mappings=[_mapping(TargetField.VALUE, clear=True), unit],
    )
    assert not proposal.is_ready
    assert proposal.unclear_fields == [unit]
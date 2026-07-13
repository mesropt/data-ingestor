"""VAL-01/02/03: the no-LLM validator — declared constraints checked on every
mapped value and every ranked alternative, additive-only, no LLM call.

Built directly as fixtures, the same "no file I/O, no live Claude call" idiom
`test_canonical.py`/`test_mapper_boundary.py` use. This is Phase 3's safety
net: a violation forces `needs_confirmation=True` regardless of Claude's
reported confidence or an auto-applied profile's 1.0, and the validator may
never clear a flag someone else already raised.
"""

import pytest

from assayingest.domain.models import ColumnCandidate, FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable
from assayingest.validation.validator import validate


def _table(headers: list[str], rows: list[list[str]], locales: list[str] | None = None) -> RawTable:
    return RawTable(
        headers=headers,
        rows=rows,
        source_name="fixture.csv",
        column_locales=locales or [],
    )


def _mapping(
    target_field: str,
    source_column: str | None,
    *,
    confidence: float = 1.0,
    needs_confirmation: bool = False,
    inferred_value: str | None = None,
    alternatives: list[ColumnCandidate] | None = None,
) -> FieldMapping:
    return FieldMapping(
        target_field=target_field,
        source_column=source_column,
        confidence=confidence,
        reasoning="test fixture",
        needs_confirmation=needs_confirmation,
        inferred_value=inferred_value,
        alternatives=alternatives or [],
    )


def _proposal(mappings: list[FieldMapping]) -> MappingProposal:
    return MappingProposal(source_columns=[], field_mappings=mappings)


# --- allowed_values (VAL-01, case-insensitive per D-07) ---------------------


def test_allowed_values_flags_a_value_not_in_the_declared_set():
    table = _table(headers=["Flag"], rows=[["X"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L", "A")),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    assert field_mapping.validator_note is not None


def test_allowed_values_matches_case_insensitively():
    table = _table(headers=["Flag"], rows=[["h"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is False


# --- allowed_values blank-cell policy (IN-02, fail-closed-by-default) -------


def test_blank_cell_on_a_required_allowed_values_field_is_flagged():
    """A blank cell (here, whitespace-only) in a REQUIRED allowed_values
    field is a missing result a human must see -- required is the default,
    so this is the fail-closed baseline."""
    table = _table(headers=["Flag"], rows=[["  "]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L"), required=True),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    assert field_mapping.validator_note is not None


def test_blank_cell_on_an_explicitly_optional_allowed_values_field_is_not_flagged():
    """A legitimately-absent value on an explicitly optional field must not
    raise a false yellow -- alert fatigue is itself a safety risk."""
    table = _table(headers=["Flag"], rows=[[""]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L"), required=False),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is False


def test_non_blank_out_of_set_value_on_an_optional_field_is_still_flagged():
    """required=False only exempts BLANK cells -- a present-but-wrong value
    is always an objection, regardless of required."""
    table = _table(headers=["Flag"], rows=[["X"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L"), required=False),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


def test_non_blank_in_set_value_is_clean_control():
    table = _table(headers=["Flag"], rows=[["H"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L"), required=False),))
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is False


# --- min/max (VAL-01) --------------------------------------------------------


def test_min_flags_a_value_below_the_declared_minimum():
    table = _table(headers=["Result"], rows=[["-3"]], locales=["decimal_point"])
    field_set = FieldSet(fields=(Field(name="result", type="number", min=0.0),))
    proposal = _proposal([_mapping("result", "Result")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


def test_max_flags_a_value_above_the_declared_maximum():
    table = _table(headers=["Result"], rows=[["5000"]], locales=["decimal_point"])
    field_set = FieldSet(fields=(Field(name="result", type="number", max=1000.0),))
    proposal = _proposal([_mapping("result", "Result")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


def test_value_inside_bounds_is_not_flagged():
    table = _table(headers=["Result"], rows=[["42"]], locales=["decimal_point"])
    field_set = FieldSet(fields=(Field(name="result", type="number", min=0.0, max=1000.0),))
    proposal = _proposal([_mapping("result", "Result")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is False


def test_nan_in_a_bounded_field_is_flagged_not_silently_passed():
    """WR-02: `float("nan")` parses successfully and every comparison
    against it is False, so a literal 'nan' cell used to pass a min/max
    check unflagged -- a fail-open in the "runs on every value" safety net.
    """
    table = _table(headers=["Result"], rows=[["nan"]], locales=["decimal_point"])
    field_set = FieldSet(fields=(Field(name="result", type="number", min=0.0, max=1000.0),))
    proposal = _proposal([_mapping("result", "Result")])

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    assert "not a finite number" in field_mapping.validator_note.lower()


# --- canonical reuse (Pattern 1) ---------------------------------------------


def test_a_decimal_comma_conversion_failure_flagged_by_canonical_forces_confirmation():
    table = _table(headers=["Value"], rows=[["not-a-number"]], locales=["non_numeric"])
    field_set = FieldSet(fields=(Field(name="value", type="number"),))
    proposal = _proposal([_mapping("value", "Value")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


def test_a_date_format_mismatch_flagged_by_canonical_forces_confirmation():
    table = _table(headers=["Date"], rows=[["32/01/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),))
    proposal = _proposal([_mapping("assay_date", "Date")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


def test_a_date_field_without_a_declared_format_gets_an_actionable_note():
    """UAT trap: a date-typed field with no date_format is ALWAYS flagged
    (D-13). The objection is a field-definition issue, not a column issue, so
    the note must say so — otherwise the curator cycles every source column in
    the dropdown and none of them ever clears the field."""
    table = _table(headers=["Date"], rows=[["2025-01-15"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date", date_format=None),))
    proposal = _proposal([_mapping("assay_date", "Date")])

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    note = field_mapping.validator_note or ""
    assert "date_format" in note
    assert "definition" in note  # points at the field definition, not the column


def test_a_text_unit_mismatch_flagged_by_canonical_forces_confirmation():
    table = _table(headers=["Unit"], rows=[["µM"]])
    field_set = FieldSet(fields=(Field(name="unit", type="text", unit="nM"),))
    proposal = _proposal([_mapping("unit", "Unit")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


# --- override (VAL-02): objection beats Claude's own confidence -------------


def test_validator_overrides_a_confidence_1_0_clear_field():
    table = _table(headers=["Flag"], rows=[["X"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))
    proposal = _proposal(
        [_mapping("flag", "Flag", confidence=1.0, needs_confirmation=False)]
    )

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.confidence == 1.0  # Claude's own confidence untouched
    assert field_mapping.needs_confirmation is True  # but the gate is forced


# --- additive-only (Pattern 2/P1) --------------------------------------------


def test_validator_never_clears_an_existing_confirmation_on_a_no_constraint_field():
    table = _table(headers=["Notes"], rows=[["anything"]])
    field_set = FieldSet(fields=(Field(name="notes"),))  # no type/allowed_values/unit/min/max
    proposal = _proposal(
        [_mapping("notes", "Notes", confidence=0.4, needs_confirmation=True)]
    )

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True  # never cleared
    assert field_mapping.validator_note is not None


# --- alternatives (VAL-02) ---------------------------------------------------


def test_every_alternative_is_validated_not_only_the_chosen_column():
    table = _table(
        headers=["Good", "Bad"],
        rows=[["H", "X"]],
    )
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))
    proposal = _proposal(
        [
            _mapping(
                "flag",
                "Good",
                confidence=1.0,
                needs_confirmation=False,
                alternatives=[ColumnCandidate(source_column="Bad", confidence=0.6)],
            )
        ]
    )

    result = validate(table, proposal, field_set)

    # The chosen column ("Good") is clean, but a ranked alternative ("Bad")
    # violates the same field's constraint -- the field must still be flagged.
    assert result.field_mappings[0].needs_confirmation is True


def test_review_stage_explicitly_still_flags_a_violating_alternative():
    """`stage="review"` is the spelled-out default: a ranked alternative is
    still a live candidate on the upload path, so its violation stays an
    honest objection about the proposal's quality (VAL-02)."""
    table = _table(headers=["Good", "Bad"], rows=[["H", "X"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))
    proposal = _proposal(
        [
            _mapping(
                "flag", "Good",
                alternatives=[ColumnCandidate(source_column="Bad", confidence=0.6)],
            )
        ]
    )

    result = validate(table, proposal, field_set, stage="review")

    assert result.field_mappings[0].needs_confirmation is True


# --- stage="confirm": judge only what reaches the export ---------------------


def test_confirm_stage_does_not_condemn_a_field_for_a_rejected_alternative():
    """The dead end: no unit column exists, the human accepted the inferred
    'nM', and Claude's low-ranked alternative ('potency') violates
    allowed_values. Once the human has chosen, that alternative is a rejected
    suggestion no export reads -- the confirm gate must not object to it."""
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(
        fields=(Field(name="unit", type="text", allowed_values=("µM", "nM", "%"), required=False),)
    )
    proposal = _proposal(
        [
            _mapping(
                "unit", None,
                inferred_value="nM",
                alternatives=[ColumnCandidate(source_column="potency", confidence=0.1)],
            )
        ]
    )

    result = validate(table, proposal, field_set, stage="confirm")

    assert result.field_mappings[0].needs_confirmation is False


def test_confirm_stage_still_flags_a_violation_in_the_chosen_column():
    """Scoping to the chosen column must not weaken the gate: a violation in
    the column the human actually picked is exactly what the gate exists
    for."""
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(
        fields=(Field(name="unit", type="text", allowed_values=("µM", "nM", "%")),)
    )
    proposal = _proposal([_mapping("unit", "potency")])

    result = validate(table, proposal, field_set, stage="confirm")

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    assert field_mapping.validator_note is not None


def test_validate_rejects_an_unrecognised_stage():
    table = _table(headers=["Flag"], rows=[["H"]])
    field_set = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H", "L")),))
    proposal = _proposal([_mapping("flag", "Flag")])

    with pytest.raises(ValueError):
        validate(table, proposal, field_set, stage="export")


# --- an inferred_value is judged against the field's own constraints --------


def test_an_inferred_value_outside_allowed_values_is_flagged():
    """An inferred value reaches the manifest and any saved profile exactly
    as Claude wrote it -- an ASCII 'uM' against an allowed set of µM/nM/%
    must never sail through unchecked."""
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(
        fields=(Field(name="unit", type="text", allowed_values=("µM", "nM", "%"), required=False),)
    )
    proposal = _proposal([_mapping("unit", None, inferred_value="uM")])

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is True
    assert "uM" in field_mapping.validator_note


def test_an_inferred_value_outside_allowed_values_is_flagged_at_confirm_too():
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(
        fields=(Field(name="unit", type="text", allowed_values=("µM", "nM", "%"), required=False),)
    )
    proposal = _proposal([_mapping("unit", None, inferred_value="uM")])

    result = validate(table, proposal, field_set, stage="confirm")

    assert result.field_mappings[0].needs_confirmation is True


def test_an_inferred_value_inside_allowed_values_is_clean():
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(
        fields=(Field(name="unit", type="text", allowed_values=("µM", "nM", "%"), required=False),)
    )
    proposal = _proposal([_mapping("unit", None, inferred_value="nM")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is False


def test_an_inferred_value_outside_declared_bounds_is_flagged():
    """The inferred value goes through the same VAL-01 checks as a cell:
    min/max apply too, not only allowed_values."""
    table = _table(headers=["potency"], rows=[["507.735"]])
    field_set = FieldSet(fields=(Field(name="n_replicates", type="number", min=1.0, max=12.0),))
    proposal = _proposal([_mapping("n_replicates", None, inferred_value="100")])

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True


# --- VAL-03: no declared constraints is never silently trusted --------------


def test_no_constraints_field_gets_an_explicit_absence_note_and_keeps_claudes_gate():
    table = _table(headers=["Notes"], rows=[["anything"]])
    field_set = FieldSet(fields=(Field(name="notes"),))
    proposal = _proposal(
        [_mapping("notes", "Notes", confidence=1.0, needs_confirmation=False)]
    )

    result = validate(table, proposal, field_set)

    field_mapping = result.field_mappings[0]
    assert field_mapping.needs_confirmation is False  # left to Claude's own gate
    assert field_mapping.validator_note is not None
    assert "no declared constraints" in field_mapping.validator_note.lower()

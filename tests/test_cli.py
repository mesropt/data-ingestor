"""CLI rendering: the JSON draft and the human review summary.

Written test-first — these pin the output the demo relies on, with no API call.
"""

import json

from assayingest.cli import proposal_to_dict, render_report
from assayingest.domain.models import (
    ColumnCandidate,
    FieldMapping,
    MappingProposal,
    TargetField,
)


def _proposal(*, ready: bool) -> MappingProposal:
    unit = FieldMapping(
        target_field=TargetField.UNIT,
        source_column=None if not ready else "Units",
        confidence=1.0 if ready else 0.6,
        reasoning="inferred nM from value range" if not ready else "exact match",
        needs_confirmation=not ready,
        inferred_value=None if ready else "nM",
        alternatives=[] if ready else [ColumnCandidate("Conc", 0.3)],
    )
    compound = FieldMapping(
        target_field=TargetField.COMPOUND_ID,
        source_column="cmpd",
        confidence=1.0,
        reasoning="exact match",
        needs_confirmation=False,
    )
    return MappingProposal(source_columns=["cmpd", "Units"],
                           field_mappings=[compound, unit])


def test_proposal_to_dict_is_json_serialisable_and_complete():
    data = proposal_to_dict(_proposal(ready=False))
    text = json.dumps(data)  # must not raise
    assert data["ready"] is False
    assert data["source_columns"] == ["cmpd", "Units"]
    unit = next(f for f in data["field_mappings"]
                if f["target_field"] == "unit")
    assert unit["inferred_value"] == "nM"
    assert unit["needs_confirmation"] is True
    assert unit["alternatives"][0]["source_column"] == "Conc"
    assert "unit" in text


def test_render_report_flags_unclear_fields():
    report = render_report(_proposal(ready=False))
    assert "compound_id" in report
    assert "unit" in report
    assert "inferred nM from value range" in report
    # A blocked proposal must say so, and name the count of unclear fields.
    assert "BLOCKED" in report
    assert "1" in report


def test_render_report_signals_ready_when_all_clear():
    report = render_report(_proposal(ready=True))
    assert "READY" in report
    assert "BLOCKED" not in report


def test_render_report_labels_a_blank_alternative_column():
    unit = FieldMapping(
        target_field=TargetField.UNIT,
        source_column=None,
        confidence=0.5,
        reasoning="inferred nM",
        needs_confirmation=True,
        inferred_value="nM",
        alternatives=[ColumnCandidate("", 0.2)],  # the unlabelled column
    )
    report = render_report(
        MappingProposal(source_columns=[""], field_mappings=[unit])
    )
    assert "(blank header) (0.20)" in report
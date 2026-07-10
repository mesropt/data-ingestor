"""The runtime structured-output schema — `build_wire_models` (D-16/D-17).

No API key, no network: this is pure Pydantic model construction, verified
against the field-name list a user's field set supplies (RESEARCH.md
Pattern 1/2/3).
"""

import pytest
from pydantic import ValidationError

from assayingest.mapping.schema import WireCandidate, build_wire_models


def test_dynamic_schema_enum_matches_field_names_exactly():
    field_names = ["compound id", "µM value", "1st replicate"]
    model = build_wire_models(field_names)

    schema = model.model_json_schema()
    defs = schema["$defs"]
    wire_field_mapping = defs["WireFieldMapping"]
    assert wire_field_mapping["properties"]["target_field"]["enum"] == field_names


def test_dynamic_model_validates_a_well_formed_payload():
    model = build_wire_models(["compound_id", "value"])
    instance = model(
        field_mappings=[
            {
                "target_field": "value",
                "source_column": "Value",
                "confidence": 0.95,
                "reasoning": "exact header match",
                "needs_confirmation": False,
                "inferred_value": None,
                "alternatives": [],
            }
        ]
    )
    mapping = instance.field_mappings[0]
    assert mapping.target_field == "value"
    assert mapping.source_column == "Value"
    assert mapping.confidence == 0.95
    assert mapping.reasoning == "exact header match"
    assert mapping.needs_confirmation is False
    assert mapping.inferred_value is None
    assert mapping.alternatives == []


def test_dynamic_model_rejects_a_target_field_outside_the_set():
    model = build_wire_models(["compound_id", "value"])
    with pytest.raises(ValidationError):
        model(
            field_mappings=[
                {
                    "target_field": "not_a_declared_field",
                    "source_column": "Value",
                    "confidence": 0.5,
                    "reasoning": "made up",
                    "needs_confirmation": True,
                }
            ]
        )


def test_wire_candidate_remains_importable_and_static():
    candidate = WireCandidate(source_column="Conc", confidence=0.3)
    assert candidate.source_column == "Conc"
    assert candidate.confidence == 0.3

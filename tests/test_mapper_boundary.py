"""The mapper's pure boundary logic — wire→domain and prompt rendering.

These run without an API key; the live call is exercised separately.
"""

from assayingest.mapping.mapper import (
    _render_system_prompt,
    _render_table,
    _to_domain,
)
from assayingest.mapping.schema import build_wire_models
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable


def test_wire_maps_to_domain_field_with_alternatives():
    wire_model = build_wire_models(["assay_type", "type"])
    wire = wire_model(
        field_mappings=[
            {
                "target_field": "assay_type",
                "source_column": "assay",
                "confidence": 0.7,
                "reasoning": "ambiguous label",
                "needs_confirmation": True,
                "alternatives": [{"source_column": "type", "confidence": 0.3}],
            }
        ]
    )
    proposal = _to_domain(wire, headers=["assay", "type"])

    field = proposal.field_mappings[0]
    assert field.target_field == "assay_type"
    assert field.needs_confirmation
    assert not proposal.is_ready
    assert field.alternatives[0].source_column == "type"


def test_inferred_value_survives_the_boundary():
    wire_model = build_wire_models(["unit"])
    wire = wire_model(
        field_mappings=[
            {
                "target_field": "unit",
                "source_column": None,
                "confidence": 0.6,
                "reasoning": "no unit column; inferred nM from range",
                "needs_confirmation": True,
                "inferred_value": "nM",
            }
        ]
    )
    field = _to_domain(wire, headers=["potency"]).field_mappings[0]
    assert field.source_column is None
    assert field.inferred_value == "nM"


# --- MAP-02 / SC4: alternatives order and inferred-value confirmation -------


def test_two_ranked_alternatives_arrive_in_order():
    wire_model = build_wire_models(["value"])
    wire = wire_model(
        field_mappings=[
            {
                "target_field": "value",
                "source_column": None,
                "confidence": 0.4,
                "reasoning": "two columns could match",
                "needs_confirmation": True,
                "alternatives": [
                    {"source_column": "Conc", "confidence": 0.4},
                    {"source_column": "Value2", "confidence": 0.3},
                ],
            }
        ]
    )
    field = _to_domain(wire, headers=["Conc", "Value2"]).field_mappings[0]
    assert [c.source_column for c in field.alternatives] == ["Conc", "Value2"]


def test_inferred_value_without_source_column_always_needs_confirmation():
    wire_model = build_wire_models(["unit"])
    wire = wire_model(
        field_mappings=[
            {
                "target_field": "unit",
                "source_column": None,
                "confidence": 0.8,
                "reasoning": "inferred from value range",
                "needs_confirmation": True,
                "inferred_value": "nM",
            }
        ]
    )
    field = _to_domain(wire, headers=[]).field_mappings[0]
    assert field.source_column is None
    assert field.inferred_value is not None
    assert field.needs_confirmation is True


def test_render_table_labels_blank_headers():
    table = RawTable(
        headers=["cmpd", "", "potency"],
        rows=[["NVS-1", "", "12.5"]],
        source_name="x.csv",
    )
    rendered = _render_table(table)
    assert "(blank header)" in rendered
    assert "(empty)" in rendered
    assert "NVS-1" in rendered


# --- D-22 regression guard ----------------------------------------------


def test_render_table_names_a_decimal_comma_column_as_evidence():
    table = RawTable(
        headers=["Compound", "Value"],
        rows=[["PIN-010", "11,076"]],
        source_name="pinnacle_labs_export.csv",
        column_locales=["non_numeric", "decimal_comma"],
    )
    rendered = _render_table(table)
    assert "Value" in rendered
    assert "decimal_comma" in rendered


def test_render_table_never_names_an_ambiguous_column_as_resolved():
    table = RawTable(
        headers=["Compound", "Value"],
        rows=[["A-1", "1,234"]],
        source_name="ambiguous.csv",
        column_locales=["non_numeric", "ambiguous"],
    )
    rendered = _render_table(table)
    # An ambiguous column gets no evidence line -- Claude must still flag it.
    assert "ambiguous" not in rendered.lower()


def test_render_table_evidence_never_claims_trustworthiness():
    table = RawTable(
        headers=["Value"],
        rows=[["11,076"]],
        source_name="pinnacle_labs_export.csv",
        column_locales=["decimal_comma"],
    )
    rendered = _render_table(table).lower()
    assert "trust" not in rendered
    assert "validated" not in rendered
    assert "verified" not in rendered


def test_render_table_with_no_locales_emits_no_locale_lines_and_does_not_raise():
    table = RawTable(
        headers=["Compound", "Value"],
        rows=[["A-1", "1.5"]],
        source_name="legacy.csv",
    )
    rendered = _render_table(table)  # must not raise
    assert "decimal_comma" not in rendered


# --- D-18/SC3: no domain vocabulary compiled into the prompt ----------------


def test_system_prompt_reflects_only_the_declared_assay_fields():
    field_set = FieldSet(
        fields=(
            Field(name="assay_type", allowed_values=("IC50", "EC50", "Ki", "Kd", "%inhibition")),
            Field(name="compound_id"),
        )
    )
    prompt = _render_system_prompt(field_set)
    assert "assay_type" in prompt
    assert "compound_id" in prompt
    assert "IC50" in prompt


def test_system_prompt_from_a_non_assay_field_set_carries_no_biology():
    field_set = FieldSet(
        fields=(
            Field(name="catalogue_number"),
            Field(name="quantity", type="number"),
            Field(name="shelf"),
        )
    )
    prompt = _render_system_prompt(field_set)
    assert "catalogue_number" in prompt
    assert "quantity" in prompt
    assert "shelf" in prompt
    for banned in ("IC50", "EC50", "Ki", "Kd", "%inhibition", "nM", "µM"):
        assert banned not in prompt

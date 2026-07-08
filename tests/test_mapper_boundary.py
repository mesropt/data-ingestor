"""The mapper's pure boundary logic — wire→domain and prompt rendering.

These run without an API key; the live call is exercised separately.
"""

from assayingest.domain.models import TargetField
from assayingest.mapping.mapper import _render_table, _to_domain
from assayingest.mapping.schema import (
    WireCandidate,
    WireFieldMapping,
    WireMappingProposal,
)
from assayingest.parsing.table import RawTable


def test_wire_maps_to_domain_field_with_alternatives():
    wire = WireMappingProposal(
        field_mappings=[
            WireFieldMapping(
                target_field="assay_type",
                source_column="assay",
                confidence=0.7,
                reasoning="ambiguous label",
                needs_confirmation=True,
                alternatives=[WireCandidate(source_column="type", confidence=0.3)],
            )
        ]
    )
    proposal = _to_domain(wire, headers=["assay", "type"])

    field = proposal.field_mappings[0]
    assert field.target_field is TargetField.ASSAY_TYPE
    assert field.needs_confirmation
    assert not proposal.is_ready
    assert field.alternatives[0].source_column == "type"


def test_inferred_value_survives_the_boundary():
    wire = WireMappingProposal(
        field_mappings=[
            WireFieldMapping(
                target_field="unit",
                source_column=None,
                confidence=0.6,
                reasoning="no unit column; inferred nM from range",
                needs_confirmation=True,
                inferred_value="nM",
            )
        ]
    )
    field = _to_domain(wire, headers=["potency"]).field_mappings[0]
    assert field.source_column is None
    assert field.inferred_value == "nM"


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
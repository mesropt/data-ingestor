"""Proof that no domain is compiled into the mapper (ROADMAP SC3 / SC5).

`reagent-inventory.yaml` describes a stockroom, not an assay. The fixture it
runs against uses column names that share no vocabulary with the field names
(`SKU`, `Use By`, `Location`) and carries an extra column the field set never
asked for. Nothing in `src/` knows any of those words.

The offline tests here prove the mechanism. The live test proves the outcome,
and is the only test in this file that costs money — it skips without
credentials, like every other live test in the suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from assayingest.fields.loader import load
from assayingest.mapping.mapper import _render_system_prompt, propose_mapping
from assayingest.mapping.schema import build_wire_models
from assayingest.parsing.hint import StructuralHint
from assayingest.parsing.table import RawTable, parse

_FIXTURE = Path("data/synthetic/verity_reagents_stock.xlsx")
_PRESET = Path("presets/reagent-inventory.yaml")

#: Every term that would betray a hardcoded life-sciences domain.
_BIOLOGY = ("IC50", "EC50", "Ki", "Kd", "%inhibition", "nM", "µM")

#: The hint the parser itself proposes for this file: a merged title row and a
#: blank row sit above the real header, so it declines to guess (D-05).
_HINT = StructuralHint(header_row_index=2, decimal_separator=".")


def _field_set():
    return load(_PRESET)


def test_the_stockroom_fixture_parses_with_the_hint_the_parser_proposes():
    table = parse(_FIXTURE, hint=_HINT)

    assert isinstance(table, RawTable), "expected a table, got a structural question"
    assert table.headers == [
        "SKU",
        "Item",
        "On hand",
        "Units",
        "Use By",
        "Location",
        "Reordered?",
    ]


def test_no_source_column_name_matches_any_field_name():
    """If a header happened to equal a field name, a correct mapping would
    prove nothing about the mapper."""
    table = parse(_FIXTURE, hint=_HINT)
    field_names = {name.lower() for name in _field_set().field_names}

    overlap = field_names & {header.lower() for header in table.headers}

    assert overlap == set(), f"fixture leaks field names into its headers: {overlap}"


def test_the_prompt_and_schema_built_from_this_preset_contain_no_biology():
    field_set = _field_set()

    prompt = _render_system_prompt(field_set)
    schema_fields = build_wire_models(field_set.field_names)

    assert [term for term in _BIOLOGY if term in prompt] == []
    assert "catalogue_number" in prompt
    assert schema_fields is not None


@pytest.mark.skipif(
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live cross-domain mapping proof costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
)
def test_claude_maps_the_stockroom_file_onto_the_stockroom_field_set():
    """The differentiator claim: a brand-new field set from a neighbouring
    world, a messy file, and no code change anywhere."""
    field_set = _field_set()
    table = parse(_FIXTURE, hint=_HINT)

    proposal = propose_mapping(table, field_set)

    resolved = {m.target_field: m.source_column for m in proposal.field_mappings}
    assert resolved == {
        "catalogue_number": "SKU",
        "name": "Item",
        "quantity": "On hand",
        "unit": "Units",
        "expiry_date": "Use By",
        "shelf": "Location",
    }
    assert proposal.is_ready, f"unexpectedly blocked on {proposal.unclear_fields}"

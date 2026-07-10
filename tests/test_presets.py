"""The shipped starter preset library (FIELD-05, D-20/D-21).

Three field-set presets ship as plain editable YAML data, loaded through the
exact same `fields.loader.load(path)` any user-supplied field set uses — no
registry, no import, no per-preset code branch (D-20). These tests load each
preset by path and, for `reagent-inventory`, drive the mapper's runtime
schema builder and system-prompt renderer to prove no biology is compiled
into the mapper (SC5): a field set from a neighbouring, non-life-sciences
world produces a schema and prompt that name none of the assay vocabulary.

Pure/offline: no API key, no network call (`_render_system_prompt` and
`build_wire_models` are both pure functions of a `FieldSet`).
"""

from assayingest.fields.loader import load
from assayingest.mapping.mapper import _render_system_prompt
from assayingest.mapping.schema import build_wire_models

_FORBIDDEN_ASSAY_TERMS = ("IC50", "EC50", "Ki", "Kd", "%inhibition", "nM", "µM")


def test_pk_parameters_preset_loads_with_the_declared_pk_fields():
    field_set = load("presets/pk-parameters.yaml")
    for expected in ("compound_id", "cmax", "tmax", "auc", "half_life"):
        assert expected in field_set.field_names


def test_reagent_inventory_preset_loads_with_the_declared_inventory_fields():
    field_set = load("presets/reagent-inventory.yaml")
    for expected in ("catalogue_number", "quantity", "shelf", "expiry_date"):
        assert expected in field_set.field_names


def test_assay_potency_preset_still_loads_unchanged():
    field_set = load("presets/assay-potency.yaml")
    assert "assay_type" in field_set.field_names


def test_reagent_inventory_schema_enum_matches_its_own_field_names():
    field_set = load("presets/reagent-inventory.yaml")
    wire_model = build_wire_models(field_set.field_names)
    target_field_schema = wire_model.model_json_schema()["$defs"]["WireFieldMapping"][
        "properties"
    ]["target_field"]
    assert set(target_field_schema["enum"]) == set(field_set.field_names)


def test_reagent_inventory_prompt_carries_no_biology():
    field_set = load("presets/reagent-inventory.yaml")
    prompt = _render_system_prompt(field_set)

    assert "catalogue_number" in prompt
    assert "quantity" in prompt
    for term in _FORBIDDEN_ASSAY_TERMS:
        assert term not in prompt


def test_all_three_presets_load_through_the_identical_load_call():
    """No per-preset branch: the same `load(path)` call handles all three
    (D-20) — the assertion IS that no preset-specific code exists to call."""
    for path in (
        "presets/assay-potency.yaml",
        "presets/pk-parameters.yaml",
        "presets/reagent-inventory.yaml",
    ):
        field_set = load(path)
        assert field_set.field_names

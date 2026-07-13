"""The user-declared field-set model and its safe YAML/JSON loader (D-01..D-11).

These run without an API key and without pandas — a field set is a pure data
structure, and its loader is a pure function of a file path (RESEARCH.md,
02-PATTERNS.md "pure dataclass + loader, no API key" idiom).
"""

import inspect
import json
from pathlib import Path

import pytest

from assayingest.fields import loader as loader_module
from assayingest.fields.loader import MAX_FIELDS, from_dict, load
from assayingest.fields.models import FIELD_TYPES, Field, FieldSet


def test_field_constructs_with_defaults():
    f = Field(name="value", type="number", min=0.0, max=1000.0)
    assert f.name == "value"
    assert f.type == "number"
    assert f.min == 0.0
    assert f.max == 1000.0
    assert f.description is None
    assert f.allowed_values is None
    assert f.unit is None
    assert f.required is True
    assert f.date_format is None


def test_field_set_field_names_preserve_declaration_order():
    fs = FieldSet((Field("a"), Field("b")))
    assert fs.field_names == ["a", "b"]


def test_signature_is_order_independent():
    a = FieldSet((Field("a"), Field("b")))
    b = FieldSet((Field("b"), Field("a")))
    assert a.signature == b.signature


def test_signature_changes_when_a_field_is_renamed():
    a = FieldSet((Field("a"), Field("b")))
    renamed = FieldSet((Field("a"), Field("c")))
    assert a.signature != renamed.signature


def test_signature_identifies_a_bound_by_its_value_not_its_python_type():
    """A bound's identity is the NUMBER, never the Python type carrying it.

    JavaScript has a single number type, so a browser that reads
    `{"min": 0.0}` off `GET /api/schemas` re-serializes it as `{"min": 0}` --
    `JSON.stringify(0.0) === "0"`. The loader hands that back as a Python int
    while the retained field set (loaded from a preset, stored as a DB Double)
    holds a float. Hashing them separately -- `json.dumps(0.0)` is `"0.0"`,
    `json.dumps(0)` is `"0"` -- made every confirm sent from the UI fail
    `confirm.py`'s CR-01 signature check against an unchanged Schema. The
    browser cannot preserve that distinction and must not have to.
    """
    from_preset = FieldSet((Field("value", type="number", min=0.0, max=1000.0),))
    from_browser = FieldSet((Field("value", type="number", min=0, max=1000),))
    assert from_preset.signature == from_browser.signature


def test_signature_still_changes_when_a_bound_genuinely_changes():
    """The guard on the fix above: only the int-vs-float REPRESENTATION of one
    number stops mattering. A different number is still a different field set,
    so the gate is not weakened."""
    original = FieldSet((Field("value", type="number", min=0.0, max=1000.0),))
    widened = FieldSet((Field("value", type="number", min=0.0, max=2000.0),))
    dropped = FieldSet((Field("value", type="number", min=None, max=1000.0),))
    assert original.signature != widened.signature
    assert original.signature != dropped.signature


def test_shipped_preset_signatures_are_stable():
    """Learned profiles are keyed on `(field set signature, column signature)`,
    so a change to how the signature is computed must not silently orphan every
    profile a curator already taught the tool. These are the four shipped
    presets' signatures as of the int/float normalisation above -- if this test
    fails, a signature change has invalidated the learning store, and that has
    to be a deliberate, migrated decision rather than a side effect.
    """
    signatures = {
        path.stem: load(path).signature
        for path in sorted(Path("presets").glob("*.yaml"))
    }
    assert signatures == {
        "assay-potency": "f249fd8aad09f16832ac96ed49c4ce0df71756b629d6cfcf743f74669804a126",
        "clinical-labs": "e36cb03ead7c3f65a07528f188b8b93c8bf2c0d35377d9b04df5d0ef0930b46d",
        "pk-parameters": "613904f0aeafe3fd3dc7270adb8a55e5758b2abe2ef5723218371142a8fef64c",
        "reagent-inventory": "f05df476b822e1b88c1a0c2b38f412fd5835da9ace5737edcd96df6f2f1378b4",
    }


# --- load(): YAML and JSON dispatch into one internal model -----------------


_YAML_FIXTURE = """\
name: reagent-inventory
fields:
  - name: catalogue_number
    description: The vendor's catalogue SKU.
    required: true
  - name: quantity
    type: number
    min: 0.0
"""

_JSON_FIXTURE = json.dumps(
    {
        "name": "reagent-inventory",
        "fields": [
            {
                "name": "catalogue_number",
                "description": "The vendor's catalogue SKU.",
                "required": True,
            },
            {"name": "quantity", "type": "number", "min": 0.0},
        ],
    }
)


def test_load_yaml_and_equivalent_json_produce_the_same_field_set(tmp_path):
    yaml_path = tmp_path / "reagents.yaml"
    yaml_path.write_text(_YAML_FIXTURE, encoding="utf-8")
    json_path = tmp_path / "reagents.json"
    json_path.write_text(_JSON_FIXTURE, encoding="utf-8")

    from_yaml = load(yaml_path)
    from_json = load(json_path)

    assert from_yaml == from_json
    assert from_yaml.field_names == ["catalogue_number", "quantity"]
    assert from_yaml.name == "reagent-inventory"


def test_load_missing_path_raises_file_not_found_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "nope.yaml")


def test_load_unsupported_extension_names_it(tmp_path):
    bad = tmp_path / "fields.txt"
    bad.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.txt"):
        load(bad)


def test_load_rejects_more_than_fifty_fields(tmp_path):
    assert MAX_FIELDS == 50
    fields = [{"name": f"field_{i}"} for i in range(MAX_FIELDS + 1)]
    path = tmp_path / "too_many.json"
    path.write_text(json.dumps({"fields": fields}), encoding="utf-8")
    with pytest.raises(ValueError, match=r"51") as exc_info:
        load(path)
    assert "50" in str(exc_info.value)


def test_load_rejects_an_unknown_field_type(tmp_path):
    path = tmp_path / "bad_type.json"
    path.write_text(
        json.dumps({"fields": [{"name": "hue", "type": "colour"}]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="colour") as exc_info:
        load(path)
    message = str(exc_info.value)
    for allowed in FIELD_TYPES:
        assert allowed in message


# --- Security: safe_load only (D-03, T-02-01) --------------------------------


def test_loader_source_uses_safe_load_only():
    source = inspect.getsource(loader_module)
    assert "yaml.safe_load" in source
    assert "yaml.load(" not in source


# --- from_dict(): the in-memory seam load() delegates to (04-01) ------------
#
# A future HTTP `POST /api/field-sets` body arrives as a parsed JSON dict,
# never a file on disk -- from_dict() is the shared builder so the browser
# path enforces the exact same _validated_name/length/type guards load()
# already does, rather than a second, possibly-weaker HTTP-layer check.


def test_from_dict_matches_load_of_the_equivalent_json_file(tmp_path):
    raw = json.loads(_JSON_FIXTURE)
    json_path = tmp_path / "reagents.json"
    json_path.write_text(_JSON_FIXTURE, encoding="utf-8")

    assert from_dict(raw) == load(json_path)


def test_from_dict_rejects_a_bad_field_name_same_as_load():
    with pytest.raises(ValueError, match="no letter or digit"):
        from_dict({"fields": [{"name": "***"}]})


def test_from_dict_rejects_more_than_fifty_fields():
    fields = [{"name": f"field_{i}"} for i in range(MAX_FIELDS + 1)]
    with pytest.raises(ValueError, match="50"):
        from_dict({"fields": fields})


def test_load_delegates_to_from_dict_for_the_parsed_document(tmp_path):
    """load() must not carry its own second copy of the field-building
    logic -- it dispatches by suffix, then hands the parsed document to the
    same from_dict() a JSON request body would go through."""
    source = inspect.getsource(loader_module)
    assert "return from_dict(_parse(path, suffix))" in source

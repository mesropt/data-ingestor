"""The user-declared field-set model and its safe YAML/JSON loader (D-01..D-11).

These run without an API key and without pandas — a field set is a pure data
structure, and its loader is a pure function of a file path (RESEARCH.md,
02-PATTERNS.md "pure dataclass + loader, no API key" idiom).
"""

import inspect
import json

import pytest

from assayingest.fields import loader as loader_module
from assayingest.fields.loader import MAX_FIELDS, load
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

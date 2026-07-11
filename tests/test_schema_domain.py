"""domain.models Schema / Alias / CanonicalField -- the pure-domain backbone
of Phase 07's canonical-schema + vendor-alias crosswalk (D-07-01). The JSON
`to_master_map()` / `from_master_map()` round-trip IS the downloadable master
map file contract (SCHEMA-02/03). Written test-first (TDD RED).

Canonical fields REUSE `fields.models.Field` unchanged (composition, not
subclassing); imported field names are re-validated through the SAME
`fields.loader` guard the CLI `--fields` flag enforces (T-07-03).
"""

from __future__ import annotations

import pytest

from assayingest.domain.models import Alias, CanonicalField, Schema
from assayingest.fields.models import Field


def _alias(
    vendor: str = "AcmeLabs",
    source_column: str = "Cmpd ID",
    provenance_kind: str = "manual",
    provenance_actor: str = "curator@example.com",
    created_at: str = "2026-07-11T00:00:00+00:00",
    **extra,
) -> Alias:
    return Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind=provenance_kind,
        provenance_actor=provenance_actor,
        created_at=created_at,
        **extra,
    )


def _schema() -> Schema:
    return Schema(
        id="sch-1",
        name="assay-potency",
        fields=(
            CanonicalField(
                field=Field(name="compound_id", type="text"),
                aliases=(
                    _alias(vendor="AcmeLabs", source_column="Cmpd ID"),
                    _alias(vendor="BetaCRO", source_column="compound"),
                ),
            ),
            CanonicalField(
                field=Field(name="value", type="number", unit="nM", min=0.0),
                aliases=(),
            ),
        ),
        created_by="owner@example.com",
        created_at="2026-07-11T00:00:00+00:00",
    )


# --- Alias -----------------------------------------------------------------


def test_alias_to_dict_emits_exactly_the_five_required_keys():
    data = _alias().to_dict()
    assert set(data.keys()) == {
        "vendor",
        "source_column",
        "provenance_kind",
        "provenance_actor",
        "created_at",
    }


def test_alias_optional_fields_appear_only_when_set():
    with_extras = _alias(confidence=0.9, note="inferred from range").to_dict()
    assert with_extras["confidence"] == 0.9
    assert with_extras["note"] == "inferred from range"


def test_alias_round_trips_through_its_own_dict():
    original = _alias(confidence=0.75, note="hi")
    assert Alias(**original.to_dict()) == original


@pytest.mark.parametrize("kind", ["manual", "from_map_file"])
def test_alias_accepts_both_provenance_kinds(kind):
    assert _alias(provenance_kind=kind).provenance_kind == kind


# --- CanonicalField --------------------------------------------------------


def test_canonical_field_composes_field_plus_aliases_and_leaves_field_untouched():
    field = Field(name="compound_id", type="text")
    cf = CanonicalField(field=field, aliases=(_alias(),))
    # Composition, not subclassing: the bare Field is reusable and intact.
    assert cf.field is field
    assert not isinstance(field, CanonicalField)


def test_canonical_field_to_dict_merges_field_dict_with_an_aliases_list():
    field = Field(name="value", type="number", unit="nM")
    cf = CanonicalField(field=field, aliases=(_alias(vendor="AcmeLabs"),))
    data = cf.to_dict()
    # Every key of Field.to_dict() is present, plus an "aliases" list.
    for key, value in field.to_dict().items():
        assert data[key] == value
    assert [a["vendor"] for a in data["aliases"]] == ["AcmeLabs"]


# --- Schema master-map envelope --------------------------------------------


def test_to_master_map_is_a_versioned_envelope():
    envelope = _schema().to_master_map()
    assert envelope["schema_version"] == 1
    assert envelope["name"] == "assay-potency"
    assert envelope["id"] == "sch-1"
    assert envelope["created_by"] == "owner@example.com"
    assert envelope["created_at"] == "2026-07-11T00:00:00+00:00"
    # fields is a list; each entry carries an embedded aliases list.
    names = [f["name"] for f in envelope["fields"]]
    assert names == ["compound_id", "value"]
    compound = next(f for f in envelope["fields"] if f["name"] == "compound_id")
    assert {a["vendor"] for a in compound["aliases"]} == {"AcmeLabs", "BetaCRO"}


def test_from_master_map_round_trips_name_fields_and_aliases():
    original = _schema()
    rebuilt = Schema.from_master_map(original.to_master_map())

    assert rebuilt.name == original.name
    assert rebuilt.id == original.id
    assert rebuilt.created_by == original.created_by
    assert rebuilt.created_at == original.created_at

    # Same canonical field names, order preserved.
    assert [c.field.name for c in rebuilt.fields] == [
        c.field.name for c in original.fields
    ]

    # Same aliases per field, order-insensitive.
    def alias_key(a: Alias) -> tuple:
        return (a.vendor, a.source_column, a.provenance_kind, a.provenance_actor)

    for orig_cf, new_cf in zip(original.fields, rebuilt.fields):
        assert {alias_key(a) for a in new_cf.aliases} == {
            alias_key(a) for a in orig_cf.aliases
        }


def test_from_master_map_preserves_field_constraints_via_the_loader():
    rebuilt = Schema.from_master_map(_schema().to_master_map())
    value_field = next(c.field for c in rebuilt.fields if c.field.name == "value")
    assert value_field.type == "number"
    assert value_field.unit == "nM"
    assert value_field.min == 0.0


def test_from_master_map_rejects_an_unsafe_field_name_via_the_shared_guard():
    # A field name carrying a newline/control character must raise ValueError
    # through fields.loader (_validated_name) -- never reach a prompt (T-07-03).
    envelope = _schema().to_master_map()
    envelope["fields"][0]["name"] = "compound\nid"
    with pytest.raises(ValueError):
        Schema.from_master_map(envelope)

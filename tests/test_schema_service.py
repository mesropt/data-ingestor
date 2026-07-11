"""service.promote / export_master_map / import_master_map (D-07-03/04,
SCHEMA-01/02/03/04), TDD RED-first (07-02 Task 1).

Store-level tests against a tmp-path `SqliteSchemaStore` -- no HTTP, no
network. These pin the augment-never-discard contract (SCHEMA-03) and the
SCHEMA-04 isolation the route layer (Task 2) then exposes over HTTP.
"""

from __future__ import annotations

import pytest

from assayingest import service
from assayingest.domain.models import Alias
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.sqlite_schema_store import SqliteSchemaStore


def _store(tmp_path) -> SqliteSchemaStore:
    return SqliteSchemaStore(tmp_path / "profiles.db")


def _assay_field_set() -> FieldSet:
    return FieldSet(
        name="assay-potency",
        fields=(Field(name="compound_id", type="text"), Field(name="value", type="number")),
    )


def _reagent_field_set() -> FieldSet:
    return FieldSet(
        name="reagent-inventory",
        fields=(Field(name="reagent_id", type="text"), Field(name="lot", type="text")),
    )


# --- SCHEMA-01: promote creates a governed Schema -----------------------------


def test_promote_creates_schema_whose_fields_are_the_field_sets_with_created_by(tmp_path):
    store = _store(tmp_path)

    schema = service.promote(
        _assay_field_set(), created_by="curator@example.com", store=store
    )

    assert schema.name == "assay-potency"
    assert schema.created_by == "curator@example.com"
    assert [cf.field.name for cf in schema.fields] == ["compound_id", "value"]
    # Each canonical field starts with an empty alias list (SCHEMA-01).
    assert all(cf.aliases == () for cf in schema.fields)


def test_promote_uses_explicit_name_when_given(tmp_path):
    store = _store(tmp_path)

    schema = service.promote(
        _assay_field_set(), created_by=None, store=store, name="custom-name"
    )

    assert schema.name == "custom-name"


def test_promote_without_any_name_raises(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        service.promote(
            FieldSet(fields=(Field(name="x"),)), created_by=None, store=store
        )


# --- SCHEMA-04: two schemas coexist, isolated ---------------------------------


def test_promote_two_field_sets_yields_isolated_schemas(tmp_path):
    store = _store(tmp_path)

    a = service.promote(_assay_field_set(), created_by="c@e.com", store=store)
    b = service.promote(_reagent_field_set(), created_by="c@e.com", store=store)

    a_names = {cf.field.name for cf in a.fields}
    b_names = {cf.field.name for cf in b.fields}
    assert a.id != b.id
    assert a_names.isdisjoint(b_names)
    assert {s.name for s in store.list_schemas()} == {
        "assay-potency",
        "reagent-inventory",
    }


# --- SCHEMA-02: export the versioned envelope ---------------------------------


def test_export_master_map_returns_versioned_envelope(tmp_path):
    store = _store(tmp_path)
    schema = service.promote(_assay_field_set(), created_by="c@e.com", store=store)

    envelope = service.export_master_map(schema)

    assert envelope["schema_version"] == 1
    assert envelope["name"] == "assay-potency"
    assert [f["name"] for f in envelope["fields"]] == ["compound_id", "value"]


# --- SCHEMA-03: import augments (adds missing fields + aliases) ----------------


def test_import_master_map_adds_missing_fields_and_stamps_from_map_file(tmp_path):
    store = _store(tmp_path)
    source = service.promote(_assay_field_set(), created_by="c@e.com", store=store)
    store.add_alias(
        source.id,
        "value",
        Alias(
            vendor="NovaScreen",
            source_column="potency",
            provenance_kind="manual",
            provenance_actor="curator@example.com",
            created_at="2026-07-11T00:00:00Z",
        ),
    )
    envelope = service.export_master_map(store.get_schema(source.id))

    target = service.promote(
        FieldSet(name="target-b", fields=(Field(name="compound_id", type="text"),)),
        created_by="c@e.com",
        store=store,
    )
    updated = service.import_master_map(
        store, "target-b", envelope, source_name="novascreen-map.json"
    )

    names = {cf.field.name for cf in updated.fields}
    assert names == {"compound_id", "value"}
    value_field = next(cf for cf in updated.fields if cf.field.name == "value")
    assert len(value_field.aliases) == 1
    imported = value_field.aliases[0]
    assert imported.source_column == "potency"
    assert imported.provenance_kind == "from_map_file"
    assert imported.provenance_actor == "novascreen-map.json"


def test_import_into_unknown_schema_raises(tmp_path):
    store = _store(tmp_path)
    envelope = service.export_master_map(
        service.promote(_assay_field_set(), created_by="c@e.com", store=store)
    )

    with pytest.raises(service.SchemaNotFoundError):
        service.import_master_map(store, "does-not-exist", envelope, source_name="x")


# --- Round-trip proof: augment-never-discard, existing provenance preserved ----


def test_export_import_round_trip_preserves_existing_manual_alias(tmp_path):
    """Export schema A, import its envelope into schema B that already holds a
    manual alias on the SAME (field, vendor, source_column). B must end with
    A's fields+aliases added AND B's original manual alias intact with its
    original provenance (augment-never-discard, ALIAS-03)."""
    store = _store(tmp_path)

    # Schema A: compound_id + value, with a from_map_file alias on `value`.
    a = service.promote(_assay_field_set(), created_by="c@e.com", store=store)
    store.add_alias(
        a.id,
        "value",
        Alias(
            vendor="NovaScreen",
            source_column="potency",
            provenance_kind="from_map_file",
            provenance_actor="source-map",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    envelope = service.export_master_map(store.get_schema(a.id))

    # Schema B: value + target, with its OWN manual alias on the SAME key.
    b = service.promote(
        FieldSet(
            name="schema-b",
            fields=(Field(name="value", type="number"), Field(name="target", type="text")),
        ),
        created_by="c@e.com",
        store=store,
    )
    store.add_alias(
        b.id,
        "value",
        Alias(
            vendor="NovaScreen",
            source_column="potency",
            provenance_kind="manual",
            provenance_actor="curator@example.com",
            created_at="2026-05-05T00:00:00Z",
        ),
    )

    updated = service.import_master_map(store, "schema-b", envelope, source_name="a-map.json")

    # B keeps its own field `target`, and gains `compound_id` from A (augment).
    names = {cf.field.name for cf in updated.fields}
    assert {"value", "target", "compound_id"} <= names

    # The pre-existing manual alias is intact with its ORIGINAL provenance --
    # the import (from_map_file) never overwrote it (ALIAS-03, INSERT OR IGNORE).
    value_field = next(cf for cf in updated.fields if cf.field.name == "value")
    nova = [
        al
        for al in value_field.aliases
        if al.vendor == "NovaScreen" and al.source_column == "potency"
    ]
    assert len(nova) == 1
    assert nova[0].provenance_kind == "manual"
    assert nova[0].provenance_actor == "curator@example.com"
    assert nova[0].created_at == "2026-05-05T00:00:00Z"

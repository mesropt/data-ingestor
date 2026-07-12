"""learning.schema_store / learning.sqlite_schema_store -- the governed
canonical-schema repository seam and its local SQLite implementation
(D-07-02, SCHEMA-04, ALIAS-01/02/03). Written test-first (TDD RED).

Mirrors `test_profile_store.py`: a tmp_path DB per test, the same
`_DEFAULT_DB_PATH` shared file in production, parameterised queries proven
against a hostile input. The two load-bearing invariants:
  * SCHEMA-04 isolation -- two schemas never share fields or aliases,
    enforced structurally by the `schema_id` foreign key, not name filtering.
  * ALIAS-03 immutable provenance -- a re-observed alias keeps its first-seen
    actor and timestamp; augment never discards.
"""

from __future__ import annotations

import sqlite3

from assayingest.domain.models import Alias
from assayingest.fields.models import Field
from assayingest.learning.sqlite_schema_store import SqliteSchemaStore
from assayingest.learning.sqlite_store import _DEFAULT_DB_PATH


def _alias(
    vendor: str = "AcmeLabs",
    source_column: str = "Cmpd ID",
    provenance_kind: str = "manual",
    provenance_actor: str = "curator@example.com",
    created_at: str = "2026-07-11T00:00:00+00:00",
) -> Alias:
    return Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind=provenance_kind,
        provenance_actor=provenance_actor,
        created_at=created_at,
    )


def test_store_uses_the_same_shared_db_file_as_the_profile_store():
    # SCHEMA persists in the SAME local DB the profile/field-set stores use --
    # one governed local file, never a second database (D-07-02).
    assert _DEFAULT_DB_PATH == ".assayingest/profiles.db"


def test_create_schema_persists_and_is_retrievable_by_name_and_by_id(tmp_path):
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    created = store.create_schema(
        "assay-potency",
        (Field(name="compound_id", type="text"), Field(name="value", type="number")),
        created_by="owner@example.com",
    )

    assert created.id
    assert store.get_schema("assay-potency").id == created.id
    assert store.get_schema(created.id).name == "assay-potency"
    assert {c.field.name for c in created.fields} == {"compound_id", "value"}


def test_list_schemas_returns_every_schema(tmp_path):
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    store.create_schema("assay-potency", (Field(name="value"),), created_by="a@x.io")
    store.create_schema("reagent-inventory", (Field(name="lot"),), created_by="a@x.io")

    assert {s.name for s in store.list_schemas()} == {
        "assay-potency",
        "reagent-inventory",
    }


def test_get_schema_returns_none_on_a_miss(tmp_path):
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    assert store.get_schema("no-such-schema") is None


def test_schemas_are_isolated_no_shared_fields_or_aliases(tmp_path):
    # SCHEMA-04: assay-potency and reagent-inventory coexist and never share a
    # canonical field or an alias -- enforced by the schema_id foreign key.
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    a = store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    b = store.create_schema(
        "reagent-inventory", (Field(name="lot", type="text"),), created_by="a@x.io"
    )

    store.add_or_update_fields(a.id, (Field(name="potency", type="number"),))
    store.add_alias(a.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    got_b = store.get_schema(b.id)
    assert {c.field.name for c in got_b.fields} == {"lot"}  # none of A's fields
    assert store.list_aliases_for(b.id) == []  # none of A's aliases

    got_a = store.get_schema(a.id)
    assert {c.field.name for c in got_a.fields} == {"value", "potency"}
    assert [al.vendor for al in store.list_aliases_for(a.id)] == ["AcmeLabs"]


def test_add_or_update_fields_is_augment_only(tmp_path):
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    schema = store.create_schema(
        "assay-potency", (Field(name="value", type="number", unit="nM"),), created_by="a@x.io"
    )

    # Re-adding an existing field name: no duplicate, and the original
    # definition is NOT overwritten by a benign constraint difference.
    store.add_or_update_fields(schema.id, (Field(name="value", type="number", unit="uM"),))
    # A genuinely new field is appended.
    store.add_or_update_fields(schema.id, (Field(name="target", type="text"),))

    got = store.get_schema(schema.id)
    names = [c.field.name for c in got.fields]
    assert names.count("value") == 1  # no duplicate
    assert set(names) == {"value", "target"}  # new field appended, none deleted
    value_field = next(c.field for c in got.fields if c.field.name == "value")
    assert value_field.unit == "nM"  # first definition kept, not overwritten


def test_add_alias_is_idempotent_and_provenance_is_immutable(tmp_path):
    # ALIAS-03: re-observing the same (vendor, source_column) keeps a single
    # row and never overwrites the first-seen actor / timestamp.
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    schema = store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="AcmeLabs",
            source_column="IC50",
            provenance_actor="first@example.com",
            created_at="2026-07-11T00:00:00+00:00",
        ),
    )
    # A second observation of the SAME (vendor, source_column) with a DIFFERENT
    # actor and time must not create a row nor overwrite the original.
    store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="AcmeLabs",
            source_column="IC50",
            provenance_actor="second@example.com",
            created_at="2026-12-31T23:59:59+00:00",
        ),
    )

    aliases = store.list_aliases_for(schema.id)
    assert len(aliases) == 1
    assert aliases[0].provenance_actor == "first@example.com"
    assert aliases[0].created_at == "2026-07-11T00:00:00+00:00"


def test_list_aliases_for_preserves_vendor_and_full_provenance(tmp_path):
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    schema = store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="BetaCRO",
            source_column="potency_nm",
            provenance_kind="from_map_file",
            provenance_actor="betacro_map.json",
            created_at="2026-07-11T09:00:00+00:00",
        ),
    )

    (alias,) = store.list_aliases_for(schema.id)
    assert alias.vendor == "BetaCRO"
    assert alias.provenance_kind == "from_map_file"
    assert alias.provenance_actor == "betacro_map.json"
    assert alias.created_at == "2026-07-11T09:00:00+00:00"


def test_aliases_surface_on_the_matching_canonical_field(tmp_path):
    # ALIAS-01: a canonical field carries its list of vendor aliases when the
    # whole schema is read back.
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    schema = store.create_schema(
        "assay-potency", (Field(name="value"), Field(name="target")), created_by="a@x.io"
    )
    store.add_alias(schema.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    got = store.get_schema(schema.id)
    value_cf = next(c for c in got.fields if c.field.name == "value")
    target_cf = next(c for c in got.fields if c.field.name == "target")
    assert [a.vendor for a in value_cf.aliases] == ["AcmeLabs"]
    assert target_cf.aliases == ()


def test_store_never_string_formats_untrusted_input_into_sql(tmp_path):
    # A schema name / vendor / column carrying a SQL metacharacter must
    # round-trip safely -- proof of parameterised queries (T-07-01, ASVS V5).
    db_path = tmp_path / "profiles.db"
    store = SqliteSchemaStore(db_path)
    hostile = "'; DROP TABLE schema; --"
    schema = store.create_schema(hostile, (Field(name="value"),), created_by="a@x.io")
    store.add_alias(schema.id, "value", _alias(vendor=hostile, source_column=hostile))

    assert store.get_schema(hostile) is not None
    assert store.list_aliases_for(schema.id)[0].vendor == hostile
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema").fetchone()[0] == 1


def test_store_creates_the_db_file_and_parent_dir_on_construction(tmp_path):
    db_path = tmp_path / "nested" / "profiles.db"
    SqliteSchemaStore(db_path)
    assert db_path.exists()

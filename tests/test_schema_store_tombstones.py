"""learning.schema_store / learning.postgres_schema_store -- tombstone semantics
for removing a canonical field or a vendor alias (D-10-15), the store's first
genuine UPDATE (`update_field`), and the partial-unique-index re-add contract
the whole design depends on (T-10-09). Written test-first (TDD RED).

Mirrors test_schema_store.py's harness and assertion idiom: the same
`schema_store`/`db_session` fixtures, no second harness. See
10-02-PLAN.md and 10-CONTEXT.md D-10-15 for the full rationale -- soft
delete keeps the audit trail, and the accepted cost (every read must filter
tombstones) is paid down structurally inside the store's four queries.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from assayingest.domain.models import Alias
from assayingest.fields.models import Field
from assayingest.persistence.models import AliasRow, CanonicalFieldRow


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


# --- tombstone, never DELETE -------------------------------------------------


def test_remove_field_hides_it_from_every_read_but_keeps_the_physical_row(
    schema_store, db_session
):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )

    returned = schema_store.remove_field(
        schema.id,
        "value",
        removed_by="curator@example.com",
        removed_at="2026-07-12T00:00:00+00:00",
    )

    assert returned.fields == ()
    assert schema_store.get_schema(schema.id).fields == ()
    assert schema_store.list_schemas()[0].fields == ()

    row = db_session.execute(
        select(CanonicalFieldRow).where(CanonicalFieldRow.schema_id == schema.id)
    ).scalar_one()
    assert row.name == "value"  # the row survives -- this is the whole point
    assert row.removed_by == "curator@example.com"
    assert row.removed_at == "2026-07-12T00:00:00+00:00"


def test_remove_field_cascades_a_tombstone_to_every_alias_in_one_transaction(
    schema_store, db_session
):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    schema_store.add_alias(schema.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))
    schema_store.add_alias(
        schema.id, "value", _alias(vendor="BetaCRO", source_column="potency_nm")
    )

    schema_store.remove_field(
        schema.id,
        "value",
        removed_by="curator@example.com",
        removed_at="2026-07-12T00:00:00+00:00",
    )

    # Gone from the read path -- the crosswalk can no longer match a vendor
    # name onto a field that no longer exists.
    assert schema_store.list_aliases_for(schema.id) == []

    rows = (
        db_session.execute(
            select(AliasRow)
            .join(CanonicalFieldRow, AliasRow.canonical_field_id == CanonicalFieldRow.id)
            .where(CanonicalFieldRow.schema_id == schema.id)
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2  # both alias rows survive physically
    assert all(r.removed_by == "curator@example.com" for r in rows)
    assert all(r.removed_at == "2026-07-12T00:00:00+00:00" for r in rows)


def test_remove_alias_hides_it_from_every_read_but_keeps_the_physical_row(
    schema_store, db_session
):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    schema_store.add_alias(schema.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    schema_store.remove_alias(
        schema.id,
        "value",
        "AcmeLabs",
        "IC50",
        removed_by="curator@example.com",
        removed_at="2026-07-12T00:00:00+00:00",
    )

    assert schema_store.list_aliases_for(schema.id) == []
    got = schema_store.get_schema(schema.id)
    value_cf = next(c for c in got.fields if c.field.name == "value")
    assert value_cf.aliases == ()

    row = db_session.execute(select(AliasRow)).scalar_one()
    assert row.vendor == "AcmeLabs"
    assert row.removed_by == "curator@example.com"
    assert row.removed_at == "2026-07-12T00:00:00+00:00"


# --- ValueError on every miss, never a silent no-op or IntegrityError -------


def test_remove_field_on_an_unknown_name_raises_value_error(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    with pytest.raises(ValueError):
        schema_store.remove_field(
            schema.id,
            "no-such-field",
            removed_by="a@x.io",
            removed_at="2026-07-12T00:00:00+00:00",
        )


def test_remove_field_on_an_already_tombstoned_field_raises_value_error(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    schema_store.remove_field(
        schema.id, "value", removed_by="a@x.io", removed_at="2026-07-12T00:00:00+00:00"
    )
    with pytest.raises(ValueError):
        schema_store.remove_field(
            schema.id, "value", removed_by="a@x.io", removed_at="2026-07-12T01:00:00+00:00"
        )


def test_remove_alias_on_an_unknown_pair_raises_value_error(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    with pytest.raises(ValueError):
        schema_store.remove_alias(
            schema.id,
            "value",
            "AcmeLabs",
            "no-such-column",
            removed_by="a@x.io",
            removed_at="2026-07-12T00:00:00+00:00",
        )


# --- the re-add / partial-index trap ----------------------------------------


def test_a_tombstoned_alias_can_be_re_added_and_becomes_live_with_new_provenance(
    schema_store, db_session
):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    schema_store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="AcmeLabs",
            source_column="Cmpd",
            provenance_actor="first@example.com",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    schema_store.remove_alias(
        schema.id,
        "value",
        "AcmeLabs",
        "Cmpd",
        removed_by="curator@example.com",
        removed_at="2026-07-12T00:00:00+00:00",
    )
    assert schema_store.list_aliases_for(schema.id) == []

    # Re-adding the SAME (vendor, source_column) must NOT be swallowed by
    # ON CONFLICT DO NOTHING against a tombstoned row (T-10-09) -- it must
    # come back live, with the NEW caller's provenance.
    schema_store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="AcmeLabs",
            source_column="Cmpd",
            provenance_actor="second@example.com",
            created_at="2026-07-13T00:00:00+00:00",
        ),
    )

    aliases = schema_store.list_aliases_for(schema.id)
    assert len(aliases) == 1
    assert aliases[0].provenance_actor == "second@example.com"
    assert aliases[0].created_at == "2026-07-13T00:00:00+00:00"

    # TWO physical rows: one tombstoned, one live -- never a swallowed re-add.
    assert db_session.execute(text("SELECT COUNT(*) FROM alias")).scalar() == 2


def test_a_tombstoned_field_can_be_re_added_via_add_or_update_fields_and_becomes_live(
    schema_store, db_session
):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    schema_store.remove_field(
        schema.id, "value", removed_by="a@x.io", removed_at="2026-07-12T00:00:00+00:00"
    )
    assert schema_store.get_schema(schema.id).fields == ()

    schema_store.add_or_update_fields(schema.id, (Field(name="value", type="text"),))

    got = schema_store.get_schema(schema.id)
    assert [c.field.name for c in got.fields] == ["value"]
    count = db_session.execute(
        text("SELECT COUNT(*) FROM canonical_field WHERE schema_id = :sid"),
        {"sid": schema.id},
    ).scalar()
    assert count == 2  # one tombstoned, one live


# --- update_field: the store's first real UPDATE ----------------------------


def test_update_field_overwrites_stored_constraints(schema_store):
    schema = schema_store.create_schema(
        "assay-potency",
        (Field(name="value", type="number", unit="nM", min=0.0, max=10.0),),
        created_by="a@x.io",
    )

    updated = schema_store.update_field(
        schema.id,
        "value",
        Field(name="value", type="number", unit="nM", min=0.0, max=1000.0),
    )

    stored = schema_store.get_schema(schema.id).fields[0].field
    assert stored.max == 1000.0
    assert updated.fields[0].field.max == 1000.0


def test_update_field_rename_preserves_aliases(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    schema_store.add_alias(schema.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    schema_store.update_field(schema.id, "value", Field(name="potency", type="number"))

    got = schema_store.get_schema(schema.id)
    assert [c.field.name for c in got.fields] == ["potency"]
    potency_cf = got.fields[0]
    assert [a.vendor for a in potency_cf.aliases] == ["AcmeLabs"]


def test_update_field_on_a_tombstoned_field_raises_value_error(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    schema_store.remove_field(
        schema.id, "value", removed_by="a@x.io", removed_at="2026-07-12T00:00:00+00:00"
    )

    with pytest.raises(ValueError):
        schema_store.update_field(schema.id, "value", Field(name="value", type="text"))


def test_update_field_on_a_name_in_a_different_schema_raises_value_error(schema_store):
    schema_store.create_schema("assay-potency", (Field(name="value"),), created_by="a@x.io")
    b = schema_store.create_schema("reagent-inventory", (Field(name="lot"),), created_by="a@x.io")

    with pytest.raises(ValueError):
        schema_store.update_field(b.id, "value", Field(name="value", type="text"))


# --- SCHEMA-04 isolation for all three new methods --------------------------


def test_update_field_never_touches_a_same_named_field_in_a_different_schema(schema_store):
    a = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number", unit="nM"),), created_by="a@x.io"
    )
    b = schema_store.create_schema(
        "reagent-inventory",
        (Field(name="value", type="number", unit="mg"),),
        created_by="a@x.io",
    )

    schema_store.update_field(a.id, "value", Field(name="value", type="number", unit="uM"))

    b_value = schema_store.get_schema(b.id).fields[0].field
    assert b_value.unit == "mg"  # Schema B's own "value" field is untouched


def test_remove_field_never_touches_a_same_named_field_in_a_different_schema(schema_store):
    a = schema_store.create_schema("assay-potency", (Field(name="value"),), created_by="a@x.io")
    b = schema_store.create_schema("reagent-inventory", (Field(name="value"),), created_by="a@x.io")

    schema_store.remove_field(
        a.id, "value", removed_by="a@x.io", removed_at="2026-07-12T00:00:00+00:00"
    )

    assert schema_store.get_schema(a.id).fields == ()
    assert [c.field.name for c in schema_store.get_schema(b.id).fields] == ["value"]


def test_remove_alias_never_touches_a_same_pair_alias_in_a_different_schema(schema_store):
    a = schema_store.create_schema("assay-potency", (Field(name="value"),), created_by="a@x.io")
    b = schema_store.create_schema("reagent-inventory", (Field(name="value"),), created_by="a@x.io")
    schema_store.add_alias(a.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))
    schema_store.add_alias(b.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    schema_store.remove_alias(
        a.id,
        "value",
        "AcmeLabs",
        "IC50",
        removed_by="a@x.io",
        removed_at="2026-07-12T00:00:00+00:00",
    )

    assert schema_store.list_aliases_for(a.id) == []
    assert len(schema_store.list_aliases_for(b.id)) == 1


# --- SQL safety --------------------------------------------------------------


def test_new_methods_never_string_format_untrusted_input_into_sql(schema_store, db_session):
    # Extends test_schema_store.py's existing idiom to the three NEW methods:
    # a hostile field name / vendor / source-column must round-trip verbatim
    # as data, never execute as SQL (T-10-05, ASVS V5).
    hostile = "'; DROP TABLE alias; --"
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    schema_store.add_alias(schema.id, "value", _alias(vendor=hostile, source_column=hostile))

    schema_store.update_field(schema.id, "value", Field(name=hostile, type="text"))
    got = schema_store.get_schema(schema.id)
    assert got.fields[0].field.name == hostile

    schema_store.remove_alias(
        schema.id,
        hostile,
        hostile,
        hostile,
        removed_by=hostile,
        removed_at="2026-07-12T00:00:00+00:00",
    )
    schema_store.remove_field(
        schema.id, hostile, removed_by=hostile, removed_at="2026-07-12T00:00:00+00:00"
    )

    # Both tables still exist and hold exactly their one (now-tombstoned) row.
    assert db_session.execute(text("SELECT COUNT(*) FROM alias")).scalar() == 1
    assert db_session.execute(text("SELECT COUNT(*) FROM canonical_field")).scalar() == 1

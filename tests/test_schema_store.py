"""learning.schema_store / learning.postgres_schema_store -- the governed
canonical-schema repository seam and its PostgreSQL implementation
(D-07-02, SCHEMA-04, ALIAS-01/02/03). Written test-first (TDD RED).

Mirrors `test_profile_store.py`: the harness's rolled-back outer transaction per
test, parameterised queries proven against a hostile input. The two load-bearing
invariants:
  * SCHEMA-04 isolation -- two schemas never share fields or aliases, enforced
    structurally by the `schema_id` foreign key, not name filtering.
  * ALIAS-03 immutable provenance -- a re-observed alias keeps its first-seen
    actor and timestamp; augment never discards.
"""

from __future__ import annotations

from sqlalchemy import text

from assayingest.domain.models import Alias
from assayingest.fields.models import Field


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


def test_create_schema_persists_and_is_retrievable_by_name_and_by_id(schema_store):
    created = schema_store.create_schema(
        "assay-potency",
        (Field(name="compound_id", type="text"), Field(name="value", type="number")),
        created_by="owner@example.com",
    )

    assert created.id
    assert schema_store.get_schema("assay-potency").id == created.id
    assert schema_store.get_schema(created.id).name == "assay-potency"
    assert {c.field.name for c in created.fields} == {"compound_id", "value"}


def test_list_schemas_returns_every_schema(schema_store):
    schema_store.create_schema("assay-potency", (Field(name="value"),), created_by="a@x.io")
    schema_store.create_schema("reagent-inventory", (Field(name="lot"),), created_by="a@x.io")

    assert {s.name for s in schema_store.list_schemas()} == {
        "assay-potency",
        "reagent-inventory",
    }


def test_get_schema_returns_none_on_a_miss(schema_store):
    assert schema_store.get_schema("no-such-schema") is None


def test_schemas_are_isolated_no_shared_fields_or_aliases(schema_store):
    # SCHEMA-04: assay-potency and reagent-inventory coexist and never share a
    # canonical field or an alias -- enforced by the schema_id foreign key, which
    # Postgres enforces unconditionally (no PRAGMA needed).
    a = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    b = schema_store.create_schema(
        "reagent-inventory", (Field(name="lot", type="text"),), created_by="a@x.io"
    )

    schema_store.add_or_update_fields(a.id, (Field(name="potency", type="number"),))
    schema_store.add_alias(a.id, "value", _alias(vendor="AcmeLabs", source_column="IC50"))

    got_b = schema_store.get_schema(b.id)
    assert {c.field.name for c in got_b.fields} == {"lot"}  # none of A's fields
    assert schema_store.list_aliases_for(b.id) == []  # none of A's aliases

    got_a = schema_store.get_schema(a.id)
    assert {c.field.name for c in got_a.fields} == {"value", "potency"}
    assert [al.vendor for al in schema_store.list_aliases_for(a.id)] == ["AcmeLabs"]


def test_add_or_update_fields_is_augment_only(schema_store):
    schema = schema_store.create_schema(
        "assay-potency",
        (Field(name="value", type="number", unit="nM"),),
        created_by="a@x.io",
    )

    # Re-adding an existing field name: no duplicate, and the original
    # definition is NOT overwritten by a benign constraint difference.
    schema_store.add_or_update_fields(
        schema.id, (Field(name="value", type="number", unit="uM"),)
    )
    # A genuinely new field is appended.
    schema_store.add_or_update_fields(schema.id, (Field(name="target", type="text"),))

    got = schema_store.get_schema(schema.id)
    names = [c.field.name for c in got.fields]
    assert names.count("value") == 1  # no duplicate
    assert set(names) == {"value", "target"}  # new field appended, none deleted
    value_field = next(c.field for c in got.fields if c.field.name == "value")
    assert value_field.unit == "nM"  # first definition kept, not overwritten


def test_add_alias_is_idempotent_and_provenance_is_immutable(schema_store):
    # ALIAS-03: re-observing the same (vendor, source_column) keeps a single
    # row and never overwrites the first-seen actor / timestamp.
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value", type="number"),), created_by="a@x.io"
    )
    schema_store.add_alias(
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
    schema_store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="AcmeLabs",
            source_column="IC50",
            provenance_actor="second@example.com",
            created_at="2026-12-31T23:59:59+00:00",
        ),
    )

    aliases = schema_store.list_aliases_for(schema.id)
    assert len(aliases) == 1
    assert aliases[0].provenance_actor == "first@example.com"
    assert aliases[0].created_at == "2026-07-11T00:00:00+00:00"


def test_list_aliases_for_preserves_vendor_and_full_provenance(schema_store):
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    schema_store.add_alias(
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

    (alias,) = schema_store.list_aliases_for(schema.id)
    assert alias.vendor == "BetaCRO"
    assert alias.provenance_kind == "from_map_file"
    assert alias.provenance_actor == "betacro_map.json"
    assert alias.created_at == "2026-07-11T09:00:00+00:00"


def test_aliases_surface_on_the_matching_canonical_field(schema_store):
    # ALIAS-01: a canonical field carries its list of vendor aliases when the
    # whole schema is read back.
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"), Field(name="target")), created_by="a@x.io"
    )
    schema_store.add_alias(
        schema.id, "value", _alias(vendor="AcmeLabs", source_column="IC50")
    )

    got = schema_store.get_schema(schema.id)
    value_cf = next(c for c in got.fields if c.field.name == "value")
    target_cf = next(c for c in got.fields if c.field.name == "target")
    assert [a.vendor for a in value_cf.aliases] == ["AcmeLabs"]
    assert target_cf.aliases == ()


def test_store_never_string_formats_untrusted_input_into_sql(schema_store, db_session):
    # A schema name / vendor / column carrying a SQL metacharacter must round-trip
    # safely -- proof of parameterised queries (T-07-01, ASVS V5). If the store ever
    # f-stringed the value in, the DROP TABLE would execute and the COUNT below would
    # raise UndefinedTable instead of returning 1.
    hostile = "'; DROP TABLE canonical_schema; --"
    schema = schema_store.create_schema(hostile, (Field(name="value"),), created_by="a@x.io")
    schema_store.add_alias(schema.id, "value", _alias(vendor=hostile, source_column=hostile))

    assert schema_store.get_schema(hostile) is not None
    assert schema_store.list_aliases_for(schema.id)[0].vendor == hostile
    assert db_session.execute(text("SELECT COUNT(*) FROM canonical_schema")).scalar() == 1


# --- The three trap canaries (quick 260712-ghn) -----------------------------
#
# Nothing else in the suite would catch a regression on these three, and each one
# is a silent corruption rather than a crash.


def _disagree_physical_order_with_insertion_order(db_session) -> None:
    """Make the heap's physical order genuinely disagree with insertion order, AND
    make the planner's output actually depend on it.

    BOTH STEPS ARE LOAD-BEARING. Removing either one silently defangs the two
    ordering canaries below into tests that pass against a store with no `ORDER BY`
    at all. This was verified by mutation, not assumed:

      * The UPDATE (done by the caller) makes Postgres MVCC write a NEW tuple version
        at the END of the heap, so physical order no longer matches insertion order.

      * Forcing a SEQ SCAN is what makes that visible. Without it the planner picks an
        `Index Scan using ix_canonical_field_schema_id`, and because the updated column
        is not indexed the update is a HOT update: the index entry keeps pointing at the
        ORIGINAL line pointer, which merely redirects to the relocated tuple. The row
        therefore comes back in its original index position and insertion order survives
        BY ACCIDENT. A canary that relied on that accident would pass with `ORDER BY seq`
        deleted -- exactly the worthless test this construction exists to avoid.

    A seq scan is not a contrivance: it is the plan Postgres legitimately chooses once
    these tables are no longer trivially small. The store must not depend on the plan.
    """
    db_session.execute(text("SET LOCAL enable_indexscan = off"))
    db_session.execute(text("SET LOCAL enable_bitmapscan = off"))
    db_session.execute(text("SET LOCAL enable_indexonlyscan = off"))


def test_canonical_fields_come_back_in_declaration_order_even_after_an_update(
    schema_store, db_session
):
    """TRAP 1 -- `ORDER BY seq` replaces SQLite's `ORDER BY rowid`, which does not
    exist in Postgres. Without it, `Schema.fields` is silently non-deterministic.

    Verified by mutation: deleting `ORDER BY seq` from the store makes this FAIL
    (the read returns alpha, mike, bravo, zulu -- the updated field last).
    """
    schema = schema_store.create_schema(
        "ordered",
        (
            Field(name="zulu"),
            Field(name="alpha"),
            Field(name="mike"),
            Field(name="bravo"),
        ),
        created_by="a@x.io",
    )
    declared = ["zulu", "alpha", "mike", "bravo"]
    assert [c.field.name for c in schema_store.get_schema(schema.id).fields] == declared

    # Rewrite the FIRST-declared row -> MVCC relocates its tuple to the heap's end.
    db_session.execute(
        text(
            "UPDATE canonical_field SET description = 'touched' "
            "WHERE schema_id = :sid AND name = 'zulu'"
        ),
        {"sid": schema.id},
    )
    db_session.commit()
    _disagree_physical_order_with_insertion_order(db_session)

    got = schema_store.get_schema(schema.id)
    assert [c.field.name for c in got.fields] == declared


def test_aliases_come_back_in_insertion_order_even_after_an_update(schema_store, db_session):
    """TRAP 1, alias side. Same construction, same reason -- see the test above and
    `_disagree_physical_order_with_insertion_order`'s docstring. The UPDATE and the
    forced seq scan are together what make this a real canary rather than a tautology.
    """
    schema = schema_store.create_schema("ordered", (Field(name="value"),), created_by="a@x.io")
    for vendor in ("VendorA", "VendorB", "VendorC"):
        schema_store.add_alias(
            schema.id, "value", _alias(vendor=vendor, source_column=f"col_{vendor}")
        )
    inserted = ["VendorA", "VendorB", "VendorC"]
    assert [a.vendor for a in schema_store.list_aliases_for(schema.id)] == inserted

    # Rewrite the FIRST-inserted alias -> MVCC moves its tuple to the heap's end.
    db_session.execute(
        text("UPDATE alias SET provenance_kind = 'touched' WHERE vendor = 'VendorA'")
    )
    db_session.commit()
    _disagree_physical_order_with_insertion_order(db_session)

    assert [a.vendor for a in schema_store.list_aliases_for(schema.id)] == inserted


def test_a_re_observed_alias_keeps_its_first_seen_provenance_row(schema_store, db_session):
    """TRAP 5 / ALIAS-03 -- `on_conflict_do_nothing`, NEVER `do_update`.

    This is the test that fails loudly if someone ever "tidies" the schema store's
    first-write-wins into an upsert to match the other three stores. The asymmetry is
    deliberate: it is what makes immutable provenance a STRUCTURAL invariant rather
    than a conventional one.
    """
    schema = schema_store.create_schema("gov", (Field(name="value"),), created_by="a@x.io")
    schema_store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="Acme",
            source_column="IC50",
            provenance_kind="manual",
            provenance_actor="first@example.com",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    stored_id = db_session.execute(text("SELECT id FROM alias")).scalar()

    schema_store.add_alias(
        schema.id,
        "value",
        _alias(
            vendor="Acme",
            source_column="IC50",
            provenance_kind="from_map_file",
            provenance_actor="second@example.com",
            created_at="2026-12-31T23:59:59+00:00",
        ),
    )

    # Not merely "the same values" -- the very same ROW, never replaced.
    assert db_session.execute(text("SELECT COUNT(*) FROM alias")).scalar() == 1
    assert db_session.execute(text("SELECT id FROM alias")).scalar() == stored_id
    (alias,) = schema_store.list_aliases_for(schema.id)
    assert alias.provenance_kind == "manual"
    assert alias.provenance_actor == "first@example.com"
    assert alias.created_at == "2026-01-01T00:00:00+00:00"


def test_re_adding_an_existing_field_never_overwrites_its_stored_constraints(
    schema_store, db_session
):
    """TRAP 5 / P3 augment-only -- `_insert_missing_fields` is `DO NOTHING` too.

    Fails if `_insert_missing_fields` ever starts overwriting: the stored definition
    of an existing (schema_id, name) must survive a re-declaration with different
    constraints, and the ROW must be the same row (not replaced).
    """
    schema = schema_store.create_schema(
        "gov",
        (Field(name="value", type="number", unit="nM", min=0.0, max=10.0, required=True),),
        created_by="a@x.io",
    )
    stored_id = db_session.execute(text("SELECT id FROM canonical_field")).scalar()

    schema_store.add_or_update_fields(
        schema.id,
        (Field(name="value", type="text", unit="uM", min=999.0, max=1000.0, required=False),),
    )

    assert db_session.execute(text("SELECT COUNT(*) FROM canonical_field")).scalar() == 1
    assert db_session.execute(text("SELECT id FROM canonical_field")).scalar() == stored_id
    stored = schema_store.get_schema(schema.id).fields[0].field
    assert stored.type == "number"
    assert stored.unit == "nM"
    assert stored.min == 0.0
    assert stored.max == 10.0
    # `required` is a real bool from a Postgres BOOLEAN -- no int()/bool() cast.
    assert stored.required is True

"""Seeding the 4 shipped presets into the field-set template store at startup
(FIELD-05, quick task 260712-e0e), TDD RED-first.

Store-level tests exercise `seed_presets` directly against a `PostgresFieldSetStore`
on the test connection. HTTP-level tests prove the app's lifespan actually runs
seeding on startup, using the `with TestClient(app) as client:` context-manager form
(a bare `TestClient(app)` does not run lifespan), so these are the only tests that
exercise it.

THE HTTP-LEVEL TESTS DELIBERATELY INSTALL NO FIELD-SET STORE OVERRIDE, and that is
the whole point of them (quick 260712-ghn, Blocker 1).

Their previous form overrode `get_field_set_store` with a zero-arg `lambda: store`.
That override was hiding a real defect: `_lifespan` used to resolve the store by
calling the `Depends`-typed factory as a PLAIN FUNCTION. In production -- where there
is no override -- `session` would bind to the `Depends` OBJECT, `session.execute(...)`
would raise `AttributeError`, lifespan's `except Exception` would swallow it as a
warning, and the app would boot with a BLANK field-set picker. Green suite, broken
product. Overriding the factory made all four tests blind to exactly the thing they
existed to prove.

So they now run the REAL, un-overridden lifespan path. They can still see its writes
because `tests/conftest.py` binds the composition-root session factory to the SAME
CONNECTION `db_session` holds. If one of these ever fails, the fix is that seam --
NOT re-adding a store override, which would re-blind the gate to the defect it exists
to catch.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from assayingest.api.app import app
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.seed import seed_presets, seed_schemas

_PRESET_NAMES = {"assay-potency", "clinical-labs", "pk-parameters", "reagent-inventory"}


# --- seed_presets (store-level) ----------------------------------------------


def test_seed_presets_on_an_empty_store_seeds_all_4(field_set_store):
    seeded = seed_presets(field_set_store)

    listed = field_set_store.list()
    assert set(seeded) == _PRESET_NAMES
    assert {name for _, name in listed} == _PRESET_NAMES
    for template_id, _ in listed:
        field_set = field_set_store.get(template_id)
        assert field_set is not None
        assert len(field_set.field_names) > 0


def test_seed_presets_is_idempotent_and_id_stable(field_set_store):
    seed_presets(field_set_store)
    first_ids = {name: tid for tid, name in field_set_store.list()}

    second_seeded = seed_presets(field_set_store)
    second_ids = {name: tid for tid, name in field_set_store.list()}

    assert second_seeded == []
    assert len(field_set_store.list()) == 4
    assert second_ids == first_ids


def test_seed_presets_leaves_a_pre_existing_user_row_untouched(field_set_store):
    empty_named_id = field_set_store.save("", FieldSet(fields=(Field(name="x"),)))
    my_fields_id = field_set_store.save("my-fields", FieldSet(fields=(Field(name="y"),)))

    seed_presets(field_set_store)

    listed = field_set_store.list()
    assert len(listed) == 6
    ids_by_name = {name: tid for tid, name in listed}
    assert ids_by_name[""] == empty_named_id
    assert ids_by_name["my-fields"] == my_fields_id


def test_seed_presets_does_not_overwrite_a_user_row_sharing_a_preset_name(field_set_store):
    custom_field_set = FieldSet(fields=(Field(name="custom_field"),))
    user_id = field_set_store.save("assay-potency", custom_field_set)

    seed_presets(field_set_store)

    listed = field_set_store.list()
    assert len(listed) == 4  # not 5 -- the user row was not duplicated
    ids_by_name = {name: tid for tid, name in listed}
    assert ids_by_name["assay-potency"] == user_id
    found = field_set_store.get(user_id)
    assert found.field_names == ["custom_field"]


# --- app lifespan (HTTP-level) ------------------------------------------------


def test_get_field_sets_returns_the_4_presets_after_a_fresh_startup():
    # NO dependency override -- see the module docstring. This is the regression gate
    # for Blocker 1: it fails with `AttributeError` (swallowed -> zero rows -> empty
    # list) the moment anyone reintroduces `Depends` resolution into `_lifespan`.
    with TestClient(app) as client:
        response = client.get("/api/field-sets")

    assert response.status_code == 200
    names = {row["name"] for row in response.json()}
    assert _PRESET_NAMES <= names


def test_the_un_overridden_lifespan_really_wrote_rows_to_the_database(db_session):
    # The strongest form of the Blocker-1 gate: not "the endpoint answered", but "the
    # real lifespan, with no override anywhere, actually committed rows that the test's
    # own Session can see". Only true if lifespan went through the composition-root
    # seam AND conftest bound that seam to this test's connection.
    assert db_session.execute(text("SELECT COUNT(*) FROM field_set_templates")).scalar() == 0

    with TestClient(app):
        pass

    seeded = db_session.execute(
        text("SELECT name FROM field_set_templates ORDER BY name")
    ).scalars().all()
    assert set(seeded) == _PRESET_NAMES


def test_a_second_startup_against_the_same_store_does_not_duplicate_or_remint_ids():
    # Seeding is idempotent AND id-stable across restarts: the frontend persists the
    # last-used template id, so re-minting ids on every boot would silently break it.
    with TestClient(app) as client:
        first_response = client.get("/api/field-sets")
    first_ids = {row["name"]: row["id"] for row in first_response.json()}

    with TestClient(app) as client:
        second_response = client.get("/api/field-sets")
    second_ids = {row["name"]: row["id"] for row in second_response.json()}

    assert second_ids == first_ids
    assert len(second_response.json()) == 4


# --- seed_schemas (Phase 10, D-10-14: presets re-targeted from field sets to
# governed Schemas -- store-level) --------------------------------------------


def test_seed_schemas_on_an_empty_store_seeds_all_4_with_zero_aliases(schema_store):
    seeded = seed_schemas(schema_store)

    schemas = schema_store.list_schemas()
    assert set(seeded) == _PRESET_NAMES
    assert {schema.name for schema in schemas} == _PRESET_NAMES
    for schema in schemas:
        assert len(schema.fields) > 0
        assert schema.created_by is None
        for canonical_field in schema.fields:
            assert canonical_field.aliases == ()


def test_seed_schemas_is_idempotent_and_id_stable(schema_store):
    seed_schemas(schema_store)
    first_ids = {schema.name: schema.id for schema in schema_store.list_schemas()}

    second_seeded = seed_schemas(schema_store)
    second_ids = {schema.name: schema.id for schema in schema_store.list_schemas()}

    assert second_seeded == []
    assert len(schema_store.list_schemas()) == 4
    assert second_ids == first_ids


def test_seed_schemas_leaves_a_curator_created_schema_under_a_preset_name_untouched(
    schema_store,
):
    curator_field = Field(name="custom_field")
    curator_schema = schema_store.create_schema(
        "assay-potency", (curator_field,), "curator@example.com"
    )

    seed_schemas(schema_store)

    schemas = schema_store.list_schemas()
    assert len(schemas) == 4  # not 5 -- the curator's row was not duplicated
    assay_potency = next(s for s in schemas if s.name == "assay-potency")
    assert assay_potency.id == curator_schema.id
    assert assay_potency.created_by == "curator@example.com"
    assert [cf.field.name for cf in assay_potency.fields] == ["custom_field"]


def test_seed_schemas_does_not_resurrect_a_tombstoned_field_on_restart(schema_store):
    # A naive "seed the fields too" implementation would call
    # add_or_update_fields on an ALREADY-SEEDED Schema, re-adding a field the
    # curator deliberately removed. Seeding is insert-if-schema-ABSENT only.
    seed_schemas(schema_store)
    assay_potency = next(
        s for s in schema_store.list_schemas() if s.name == "assay-potency"
    )
    schema_store.remove_field(
        assay_potency.id, "compound_id", removed_by="curator@example.com",
        removed_at="2026-07-12T00:00:00Z",
    )

    seed_schemas(schema_store)  # a "restart"

    reloaded = schema_store.get_schema("assay-potency")
    assert "compound_id" not in {cf.field.name for cf in reloaded.fields}


# --- app lifespan (HTTP-level, INGEST-06) -------------------------------------


def test_get_schemas_returns_the_4_preset_schemas_after_a_fresh_startup():
    # A signed-in user has something to select immediately (INGEST-06) --
    # no dependency override, mirroring the field-set-store regression gate.
    with TestClient(app) as client:
        response = client.get("/api/schemas")

    assert response.status_code == 200
    names = {row["name"] for row in response.json()}
    assert _PRESET_NAMES <= names


def test_a_bad_preset_yaml_still_does_not_brick_startup(monkeypatch, caplog):
    from assayingest.learning import seed as seed_module

    def _explode():
        raise ValueError("preset yaml is malformed")

    monkeypatch.setattr(seed_module, "load_presets", _explode)

    with TestClient(app) as client:  # must NOT raise
        response = client.get("/api/schemas")

    assert response.status_code == 200
    assert "Starter field sets are unavailable" in caplog.text
